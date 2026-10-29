import re

CITY_NOISE = {"г", "город", "пгт", "пос", "посёлок", "поселок", "с", "село", "д", "деревня", "ст", "станица"}
SCHOOL_NOISE = {
    "мбоу", "моу", "мкоу", "мавоу", "мбобу", "гбоу", "гоу", "гкоу", "боу", "оош", "сош", "соош",
    "школа", "средняя", "основная", "общеобразовательная", "общеобразовательное", "образовательное",
    "муниципальное", "государственное", "бюджетное", "автономное", "казённое", "казенное",
    "учреждение", "им", "имени",
}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zа-я0-9]+", text.lower().replace("ё", "е"))
    return [w.lstrip("0") or "0" if w.isdigit() else w for w in words]


def _norm(text: str, noise: set[str]) -> str:
    tokens = _tokens(text)
    return " ".join([t for t in tokens if t not in noise] or tokens)


def norm_city(name: str) -> str:
    return _norm(name, CITY_NOISE)


def norm_school(name: str) -> str:
    return _norm(name, SCHOOL_NOISE)


def clean_name(text: str) -> str:
    return " ".join(text.split())


def looks_like_name(text: str) -> bool:
    return re.search(r"[A-Za-zА-Яа-яЁё]{2}", text) is not None
