import csv
import io
import re
import sys

import httpx
from sqlalchemy import select

from app.db import City, SessionLocal, init_db
from app.names import clean_name, norm_city
from app.regions import region_from_dataset

USAGE = "Запуск из backend/: python -m scripts.import_cities <файл или URL>"


def read_rows(source: str) -> list[dict]:
    if source.startswith(("http://", "https://")):
        text = httpx.get(source, follow_redirects=True, timeout=30).raise_for_status().text
    else:
        with open(source, encoding="utf-8") as f:
            text = f.read()
    return list(csv.DictReader(io.StringIO(text)))


def utc_offset(row: dict) -> int | None:
    m = re.fullmatch(r"UTC([+-])(\d{1,2})(?::(\d{2}))?", (row.get("timezone") or "").strip())
    if not m:
        return None
    minutes = int(m.group(2)) * 60 + int(m.group(3) or 0)
    return -minutes if m.group(1) == "-" else minutes


def city_name(row: dict) -> str:
    if row.get("city") or row.get("settlement"):
        return row.get("city") or row["settlement"]
    if row.get("area_type") == "г" and row.get("area"):
        return row["area"]
    return row["region"] if row.get("region_type") == "г" else ""


def _population(row: dict) -> int | None:
    raw = row.get("population") or ""
    return int(raw) if raw.isdigit() else None


def import_cities(rows: list[dict]) -> tuple[int, int]:
    init_db()
    added = skipped = 0
    with SessionLocal() as db:
        known = {(c.region, c.name_norm): c for c in db.scalars(select(City))}
        for row in rows:
            region = region_from_dataset(row.get("region_type", ""), row.get("region", ""))
            name = clean_name(city_name(row))
            if not region or not name:
                skipped += 1
                continue
            key = (region, norm_city(name))
            city = known.get(key)
            if city is None:
                city = known[key] = City(region=region, name=name, name_norm=key[1])
                db.add(city)
                added += 1
            city.custom, city.population = False, _population(row) or city.population
            offset = utc_offset(row)
            if offset is not None:
                city.utc_offset = offset
        db.commit()
    return added, skipped


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(USAGE)
    added, skipped = import_cities(read_rows(sys.argv[1]))
    print(f"Добавлено городов: {added}, пропущено строк: {skipped}")
