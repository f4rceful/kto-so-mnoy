import hmac
import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .config import settings
from .max_client import max_client

log = logging.getLogger(__name__)

ALERTS_PER_MESSAGE = 8
SEVERITY = {"critical": "критично", "warning": "важно", "info": "к сведению"}

router = APIRouter()


class AlertIn(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class WebhookIn(BaseModel):
    alerts: list[AlertIn] = Field(default_factory=list, max_length=100)


def recipients() -> list[int]:
    ids = []
    for part in settings.alert_user_ids.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def describe(alert: AlertIn) -> str:
    name = alert.labels.get("alertname", "Оповещение")
    title = alert.annotations.get("summary") or name
    detail = alert.annotations.get("description", "")
    severity = SEVERITY.get(alert.labels.get("severity", ""), "")
    head = f"Решено: {title}" if alert.status == "resolved" else f"Проблема: {title}"
    lines = [head, detail] if detail else [head]
    if severity and alert.status != "resolved":
        lines.append(f"Важность: {severity}")
    return "\n".join(lines)


def messages(alerts: list[AlertIn]) -> list[str]:
    texts = [describe(a) for a in alerts]
    return ["\n\n".join(texts[i : i + ALERTS_PER_MESSAGE]) for i in range(0, len(texts), ALERTS_PER_MESSAGE)]


@router.post("/api/alerts/webhook", include_in_schema=False)
async def alert_webhook(body: WebhookIn, authorization: str = Header(default="")):
    ids = recipients()
    if not settings.metrics_token or not ids:
        raise HTTPException(404, "Not Found")
    if not hmac.compare_digest(authorization.encode(), f"Bearer {settings.metrics_token}".encode()):
        raise HTTPException(401, "Неверный токен")
    delivered = 0
    for text in messages(body.alerts):
        for user_id in ids:
            result = await max_client.send(user_id, text)
            delivered += 1 if result.ok else 0
            if not result.ok:
                log.warning("Оповещение не доставлено пользователю %s", user_id)
    return {"alerts": len(body.alerts), "delivered": delivered}
