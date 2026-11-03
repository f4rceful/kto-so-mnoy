import hashlib
import hmac
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode

from .config import settings
from .db import Invitation
from .max_client import max_client

EVENT_LENGTH = timedelta(hours=1)
DESCRIPTION_MAX = 500
FILENAME = "kto-so-mnoy.ics"
FORMATS = {"offline": "Очно", "online": "Онлайн"}
LINE_LIMIT = 75
GOOGLE_URL = "https://calendar.google.com/calendar/render"


def sign(inv_id: int) -> str:
    key = (settings.webhook_secret or settings.bot_token or "dev").encode()
    return hmac.new(key, f"calendar:{inv_id}".encode(), hashlib.sha256).hexdigest()[:32]


def verify(inv_id: int, token: str) -> bool:
    return hmac.compare_digest(sign(inv_id).encode(), token.encode())


def calendar_path(inv: Invitation) -> str | None:
    if not inv.when_date:
        return None
    return f"/api/invitations/{inv.id}/calendar.ics?t={sign(inv.id)}"


def google_path(inv: Invitation) -> str | None:
    if not inv.when_date:
        return None
    return f"/api/invitations/{inv.id}/google-calendar?t={sign(inv.id)}"


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    lines, current, size = [], "", 0
    for ch in line:
        width = len(ch.encode())
        if size + width > LINE_LIMIT:
            lines.append(current)
            current, size = " ", 1
        current += ch
        size += width
    lines.append(current)
    return "\r\n".join(lines)


def _stamp(moment: datetime, utc: bool) -> str:
    return moment.strftime("%Y%m%dT%H%M%S") + ("Z" if utc else "")


def _span(inv: Invitation, offset_minutes: int | None) -> tuple[str, str, bool]:
    if not inv.when_time:
        end = inv.when_date + timedelta(days=1)
        return f"{inv.when_date:%Y%m%d}", f"{end:%Y%m%d}", True
    hour, minute = map(int, inv.when_time.split(":"))
    start = datetime.combine(inv.when_date, time(hour, minute))
    end = start + EVENT_LENGTH
    if offset_minutes is None:
        return _stamp(start, False), _stamp(end, False), False
    shift = timedelta(minutes=offset_minutes)
    return _stamp(start - shift, True), _stamp(end - shift, True), False


def _times(inv: Invitation, offset_minutes: int | None) -> list[str]:
    start, end, all_day = _span(inv, offset_minutes)
    if all_day:
        return [f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}"]
    return [f"DTSTART:{start}", f"DTEND:{end}"]


def _description(inv: Invitation, link: str | None) -> str:
    parts = [inv.when, inv.description[:DESCRIPTION_MAX].strip(), f"Формат: {FORMATS.get(inv.fmt, inv.fmt)}"]
    if link:
        parts.append(f"Приглашение в «Кто со мной?»: {link}")
    return "\n".join(p for p in parts if p)


def _app_link(inv: Invitation) -> str | None:
    return max_client.app_link(f"inv_{inv.id}") if settings.bot_username else None


def google_link(inv: Invitation, offset_minutes: int | None) -> str:
    start, end, _ = _span(inv, offset_minutes)
    params = {
        "action": "TEMPLATE",
        "text": inv.title,
        "dates": f"{start}/{end}",
        "details": _description(inv, _app_link(inv)),
    }
    if inv.fmt == "online":
        params["location"] = "Онлайн"
    return f"{GOOGLE_URL}?{urlencode(params)}"


def build(inv: Invitation, offset_minutes: int | None, at: datetime | None = None) -> str:
    link = _app_link(inv)
    stamp = (at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//kto-so-mnoy//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:inv-{inv.id}@kto-so-mnoy",
        f"DTSTAMP:{_stamp(stamp, True)}",
        *_times(inv, offset_minutes),
        f"SUMMARY:{_escape(inv.title)}",
        f"DESCRIPTION:{_escape(_description(inv, link))}",
    ]
    if inv.fmt == "online":
        lines.append("LOCATION:Онлайн")
    if link:
        lines.append(f"URL:{link}")
    if inv.when_time:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape(inv.title)}",
            "TRIGGER:-PT1H",
            "END:VALARM",
        ]
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
