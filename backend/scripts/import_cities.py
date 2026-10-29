import sys

import httpx

from app.citylist import import_rows, parse_csv
from app.db import Base, SessionLocal, engine

USAGE = "Запуск из backend/: python -m scripts.import_cities <файл или URL>"


def read_rows(source: str) -> list[dict]:
    if source.startswith(("http://", "https://")):
        return parse_csv(httpx.get(source, follow_redirects=True, timeout=30).raise_for_status().text)
    with open(source, encoding="utf-8") as f:
        return parse_csv(f.read())


def import_cities(rows: list[dict]) -> tuple[int, int]:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        return import_rows(db, rows)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(USAGE)
    added, skipped = import_cities(read_rows(sys.argv[1]))
    print(f"Добавлено городов: {added}, пропущено строк: {skipped}")
