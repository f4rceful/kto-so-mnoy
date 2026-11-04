from prometheus_client import CollectorRegistry, Counter, Gauge, GCCollector, Histogram, PlatformCollector, ProcessCollector

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)

registry = CollectorRegistry()
ProcessCollector(registry=registry)
PlatformCollector(registry=registry)
GCCollector(registry=registry)

REQUESTS = Counter("kto_http_requests", "HTTP-запросы по маршрутам и кодам ответа", ["method", "route", "status"], registry=registry)
LATENCY = Histogram("kto_http_request_duration_seconds", "Время обработки HTTP-запроса", ["method", "route"], buckets=LATENCY_BUCKETS, registry=registry)
IN_PROGRESS = Gauge("kto_http_requests_in_progress", "Запросы, которые обрабатываются сейчас", registry=registry)
UNHANDLED_ERRORS = Counter("kto_unhandled_errors", "Необработанные ошибки сервера", ["route"], registry=registry)

MAX_API_DURATION = Histogram("kto_max_api_duration_seconds", "Время ответа API MAX", ["call"], buckets=LATENCY_BUCKETS, registry=registry)
MAX_API_RESPONSES = Counter("kto_max_api_responses", "Ответы API MAX по кодам", ["call", "status"], registry=registry)
MAX_API_FAILURES = Counter("kto_max_api_failures", "Сбои сети при обращении к API MAX", ["call"], registry=registry)
BOT_EVENTS = Counter("kto_bot_events", "События, полученные ботом", ["type"], registry=registry)
