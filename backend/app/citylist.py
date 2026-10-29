import csv
import io
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import City
from .names import clean_name, norm_city
from .regions import region_from_dataset

BUILTIN_CSV = Path(__file__).resolve().parent / "cities.csv"


def parse_csv(text: str) -> list[dict]:
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


def import_rows(db: Session, rows: list[dict]) -> tuple[int, int]:
    added = skipped = 0
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


def seed_builtin(db: Session) -> int:
    if db.scalar(select(City.id).where(City.custom.is_(False)).limit(1)) is not None:
        return 0
    added, _ = import_rows(db, parse_csv(BUILTIN_CSV.read_text(encoding="utf-8")))
    return added
