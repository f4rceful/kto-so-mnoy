[← К оглавлению](../README.md)

# Справочник

## Структура проекта

```text
backend/        сервис на FastAPI: API, бот, уведомления, метрики
  app/          код сервиса
  scripts/      вспомогательные скрипты (загрузка городов, замеры нагрузки)
frontend/       мини-приложение и панель модератора на React + Vite
monitoring/     Prometheus, Grafana, Alertmanager, Loki: настройки и готовые панели
tests/          автоматические тесты
docs/           подробные инструкции
Dockerfile      сборка одного образа: фронтенд и бэкенд вместе
docker-compose.yml   база данных, сервис и необязательный мониторинг
```

## Адреса сервиса

| Адрес | Что это |
| --- | --- |
| `/` | мини-приложение |
| `/admin` | панель модератора (нужен `ADMIN_KEY`) |
| `/api/health` | состояние сервиса |
| `/docs` | описание API |
| `/metrics` | метрики Prometheus (нужен `METRICS_TOKEN`) |

Ответ `/api/health` с `"status": "ok"` значит, что база доступна и бот получает события. Сразу после запуска бот может
показывать `"stale"`: первый запрос к MAX длится до 30 секунд.

## Справочник городов

Список из 1116 городов России встроен в проект (`backend/app/cities.csv`) и загружается в базу автоматически при первом
запуске, ничего делать не нужно. Города, которых нет в списке, пользователи вписывают сами

Данные: [hflabs/city](https://github.com/hflabs/city), лицензия [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

## Зависимости

- Python: [`backend/requirements.txt`](../backend/requirements.txt) - все библиотеки с точными версиями
- Фронтенд: [`frontend/package.json`](../frontend/package.json) и `frontend/package-lock.json`
- Образ: [`Dockerfile`](../Dockerfile), окружение: [`docker-compose.yml`](../docker-compose.yml)
