import argparse
import os
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import httpx
import psycopg
from sqlalchemy.engine import make_url

BENCH_DB = "kto_bench"
USER_BASE = 1_000_000
CHUNK = 5000
TITLES = ["Шахматы после уроков", "3 на 3 в баскетбол", "Настольные игры в субботу", "Снимаем ролик", "Играем на гитарах", "Готовимся к ОГЭ вместе", "Бег в парке", "Собираем команду на олимпиаду"]


def bench_url() -> str:
    return make_url(os.environ["DATABASE_URL"]).set(database=BENCH_DB).render_as_string(hide_password=False)


def plain_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def recreate_database() -> None:
    admin = make_url(os.environ["DATABASE_URL"]).render_as_string(hide_password=False)
    with psycopg.connect(plain_url(admin), autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {BENCH_DB}")
        conn.execute(f"CREATE DATABASE {BENCH_DB}")


def chunks(rows: list, size: int = CHUNK):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def seed(users: int, invitations: int, responses: int, schools: int) -> None:
    recreate_database()
    os.environ["DATABASE_URL"] = bench_url()
    from sqlalchemy import insert, select, text

    from app import db, terms
    from app.interests import INTERESTS

    db.init_db()
    rng = random.Random(7)
    now = datetime.now(timezone.utc)
    interest_ids = list(INTERESTS)
    with db.SessionLocal() as s:
        city = s.scalar(select(db.City).where(db.City.name == "Казань"))
        city_id, region = city.id, city.region
        s.execute(insert(db.School), [{"city_id": city_id, "name": f"Школа {i}", "name_norm": f"{i}", "custom": False} for i in range(1, schools + 1)])
        school_ids = list(s.scalars(select(db.School.id)))
        weights = [1 / (i + 1) ** 0.9 for i in range(len(school_ids))]

        user_rows, user_school = [], {}
        for i in range(users):
            uid = USER_BASE + i
            school = rng.choices(school_ids, weights)[0]
            user_school[uid] = school
            user_rows.append({
                "id": uid, "name": f"Пользователь {i}", "username": f"user{i}", "interests": ",".join(rng.sample(interest_ids, 3)),
                "notify": rng.random() < 0.8, "onboarded": True, "region": region, "city_id": city_id, "school_id": school,
                "grade": rng.randint(5, 11), "display_name": f"Имя{i}", "terms_version": terms.TERMS_VERSION, "consented_at": now,
                "banned": False, "notify_activity": True, "bot_state": "ok", "bot_fails": 0, "legacy_city": "", "legacy_school": "",
            })
        for part in chunks(user_rows):
            s.execute(insert(db.User), part)

        user_ids = list(user_school)
        invitation_rows = []
        for i in range(invitations):
            author = rng.choice(user_ids)
            offset = rng.randint(-30, 30)
            invitation_rows.append({
                "author_id": author, "interest": rng.choice(interest_ids), "title": f"{rng.choice(TITLES)} {i}", "when": "",
                "when_date": (date.today() + timedelta(days=offset)) if rng.random() < 0.6 else None, "when_time": "15:00" if rng.random() < 0.5 else "",
                "description": "Приходите, будет интересно. " * 3, "fmt": rng.choice(["offline", "online"]), "max_participants": rng.randint(2, 10),
                "status": "open" if rng.random() < 0.85 else "closed", "created_at": now - timedelta(minutes=rng.randint(0, 120 * 24 * 60)),
                "hidden": rng.random() < 0.01, "hidden_reason": "", "city_id": city_id, "school_id": user_school[author],
            })
        for part in chunks(invitation_rows):
            s.execute(insert(db.Invitation), part)
        invitation_ids = list(s.scalars(select(db.Invitation.id)))

        seen, response_rows = set(), []
        hot = invitation_ids[: max(1, len(invitation_ids) // 50)]
        while len(response_rows) < responses:
            inv = rng.choice(hot) if rng.random() < 0.3 else rng.choice(invitation_ids)
            user = rng.choice(user_ids)
            if (inv, user) in seen:
                continue
            seen.add((inv, user))
            response_rows.append({"invitation_id": inv, "user_id": user, "status": rng.choices(["pending", "accepted", "declined"], [4, 4, 2])[0], "created_at": now - timedelta(minutes=rng.randint(0, 100 * 24 * 60))})
        for part in chunks(response_rows):
            s.execute(insert(db.Response), part)
        s.commit()
        s.execute(text("ANALYZE"))
        s.commit()
        counts = {t: s.scalar(text(f"select count(*) from {t}")) for t in ("users", "schools", "invitations", "responses")}
    print("seeded", counts)


def pick_users() -> dict:
    with psycopg.connect(plain_url(bench_url())) as conn:
        school = conn.execute("select school_id from users group by school_id order by count(*) desc limit 1").fetchone()[0]
        member = conn.execute("select id from users where school_id = %s limit 1", (school,)).fetchone()[0]
        author = conn.execute("select author_id from invitations group by author_id order by count(*) desc limit 1").fetchone()[0]
        busy = conn.execute("select user_id from responses group by user_id order by count(*) desc limit 1").fetchone()[0]
        inv = conn.execute("select invitation_id from responses group by invitation_id order by count(*) desc limit 1").fetchone()[0]
    return {"member": member, "author": author, "busy": busy, "invitation": inv}


def timed(client: httpx.Client, path: str, headers: dict, repeat: int) -> tuple[list[float], int, int]:
    for _ in range(2):
        client.get(path, headers=headers)
    samples, size, status = [], 0, 0
    for _ in range(repeat):
        started = time.perf_counter()
        r = client.get(path, headers=headers)
        samples.append((time.perf_counter() - started) * 1000)
        size, status = len(r.content), r.status_code
    return samples, size, status


def percentile(samples: list[float], p: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


def run(base: str, repeat: int, concurrency: int) -> None:
    who = pick_users()
    as_user = lambda uid: {"X-Dev-User": str(uid)}
    cases = [
        ("feed: моя школа", "/api/invitations?scope=school&limit=20", as_user(who["member"])),
        ("feed: весь город", "/api/invitations?scope=city&limit=20", as_user(who["member"])),
        ("feed: поиск 'шахматы'", "/api/invitations?scope=city&limit=20&q=%D1%88%D0%B0%D1%85%D0%BC%D0%B0%D1%82%D1%8B", as_user(who["member"])),
        ("feed: есть места", "/api/invitations?scope=city&limit=20&has_spots=true", as_user(who["member"])),
        ("feed: скоро", "/api/invitations?scope=city&limit=20&sort=soon", as_user(who["member"])),
        ("feed: свободные места", "/api/invitations?scope=city&limit=20&sort=spots", as_user(who["member"])),
        ("приглашение (много откликов)", f"/api/invitations/{who['invitation']}", as_user(who["member"])),
        ("мои приглашения", "/api/invitations/mine", as_user(who["author"])),
        ("где я участвую", "/api/invitations/joined", as_user(who["busy"])),
        ("профиль", "/api/me", as_user(who["member"])),
    ]
    print(f"{'сценарий':32} {'p50':>8} {'p95':>8} {'max':>8} {'байт':>9}  код")
    with httpx.Client(base_url=base, timeout=120) as client:
        for title, path, headers in cases:
            samples, size, status = timed(client, path, headers, repeat)
            print(f"{title:32} {statistics.median(samples):7.1f}ms {percentile(samples, 0.95):7.1f}ms {max(samples):7.1f}ms {size:9}  {status}")
        path, headers = cases[0][1], cases[0][2]

        def one(_):
            started = time.perf_counter()
            httpx.get(base + path, headers=headers, timeout=120)
            return (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        total = concurrency * 6
        with ThreadPoolExecutor(concurrency) as pool:
            latencies = list(pool.map(one, range(total)))
        elapsed = time.perf_counter() - started
    print(f"\nпараллельно: {concurrency} клиентов, {total} запросов 'feed: моя школа': {total / elapsed:.1f} запросов/с, p95 {percentile(latencies, 0.95):.0f}ms")


EXPLAIN = {
    "отклики приглашения": "select * from responses where invitation_id = {inv}",
    "отклики пользователя": "select * from responses where user_id = {busy}",
    "приглашения автора": "select * from invitations where author_id = {author}",
    "лента школы": "select * from invitations where school_id = {school} and status = 'open' and not hidden order by created_at desc limit 20",
    "получатели уведомлений": "select id, interests from users where city_id = {city} and notify and school_id = {school}",
}


def explain() -> None:
    who = pick_users()
    with psycopg.connect(plain_url(bench_url())) as conn:
        school = conn.execute("select school_id from users where id = %s", (who["member"],)).fetchone()[0]
        city = conn.execute("select city_id from users where id = %s", (who["member"],)).fetchone()[0]
        values = {"inv": who["invitation"], "busy": who["busy"], "author": who["author"], "school": school, "city": city}
        print(f"{'запрос':26} {'время':>9}  способ чтения")
        for title, sql in EXPLAIN.items():
            plan = conn.execute("explain (analyze, format json) " + sql.format(**values)).fetchone()[0][0]
            nodes, stack = [], [plan["Plan"]]
            while stack:
                node = stack.pop()
                nodes.append(node["Node Type"])
                stack.extend(node.get("Plans", []))
            print(f"{title:26} {plan['Execution Time']:7.2f}ms  {', '.join(dict.fromkeys(nodes))}")


def reference_order(rows: list, sort: str, has_spots: bool, needle: str) -> list[int]:
    today = date.today()
    items = [r for r in rows]
    items.sort(key=lambda r: (r["created_at"], r["id"]), reverse=(sort != "old"))
    if sort == "old":
        items.sort(key=lambda r: (r["created_at"], r["id"]))
    if needle:
        items = [r for r in items if needle in r["title"].lower()]
    if has_spots:
        items = [r for r in items if r["taken"] < r["max_participants"]]
    if sort == "soon":
        since = today - timedelta(days=1)

        def key(r):
            if r["when_date"] is None:
                return (1, 0, "")
            if r["when_date"] < since:
                return (2, -r["when_date"].toordinal(), "")
            return (0, r["when_date"].toordinal(), r["when_time"])

        items.sort(key=key)
    elif sort == "spots":
        items.sort(key=lambda r: r["max_participants"] - r["taken"], reverse=True)
    return [r["id"] for r in items]


def verify(base: str) -> None:
    who = pick_users()
    with psycopg.connect(plain_url(bench_url())) as conn:
        city = conn.execute("select city_id from users where id = %s", (who["member"],)).fetchone()[0]
        cursor = conn.execute(
            "select i.id, i.created_at, i.when_date, i.when_time, i.max_participants, i.title, "
            "(select count(*) from responses r where r.invitation_id = i.id and r.status = 'accepted') "
            "from invitations i where i.city_id = %s and i.status = 'open' and not i.hidden",
            (city,),
        )
        rows = [dict(zip(("id", "created_at", "when_date", "when_time", "max_participants", "title", "taken"), r)) for r in cursor]
    failures = 0
    print(f"сверка с эталоном на {len(rows)} приглашениях")
    with httpx.Client(base_url=base, timeout=120) as client:
        for sort in ("new", "old", "soon", "spots"):
            for has_spots in (False, True):
                for needle in ("", "шахматы"):
                    expected = reference_order(rows, sort, has_spots, needle)
                    got, offset = [], 0
                    while offset < min(len(expected), 300):
                        r = client.get("/api/invitations", params={"scope": "city", "sort": sort, "has_spots": str(has_spots).lower(), "q": needle, "limit": 100, "offset": offset}, headers={"X-Dev-User": str(who["member"])})
                        got += [i["id"] for i in r.json()]
                        total = int(r.headers["X-Total-Count"])
                        offset += 100
                    ok = got == expected[: len(got)] and len(got) == min(len(expected), 300) and total == len(expected)
                    failures += not ok
                    print(f"  sort={sort:5} has_spots={str(has_spots):5} q={needle or '-':9} {'совпало' if ok else 'РАЗЛИЧИЕ'} (всего {len(expected)})")
    print("итог:", "всё совпало" if not failures else f"расхождений: {failures}")
    if failures:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Нагрузочный набор данных и замеры задержек")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("seed")
    p.add_argument("--users", type=int, default=20000)
    p.add_argument("--invitations", type=int, default=50000)
    p.add_argument("--responses", type=int, default=200000)
    p.add_argument("--schools", type=int, default=300)
    p = sub.add_parser("run")
    p.add_argument("--base", default="http://127.0.0.1:8002")
    p.add_argument("--repeat", type=int, default=15)
    p.add_argument("--concurrency", type=int, default=8)
    sub.add_parser("explain")
    p = sub.add_parser("verify")
    p.add_argument("--base", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.users, args.invitations, args.responses, args.schools)
    elif args.command == "verify":
        verify(args.base)
    elif args.command == "run":
        os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
        run(args.base, args.repeat, args.concurrency)
    else:
        explain()


if __name__ == "__main__":
    if os.environ.get("DATABASE_URL") is None:
        sys.exit("задайте DATABASE_URL")
    main()
