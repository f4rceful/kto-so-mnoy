# Кто со мной?

Бот и мини-приложение в MAX для поиска компании по интересам среди школьников.
Хакатон "Идея фикс"

Один Docker-образ собирает фронтенд (React + Vite) и бэкенд (FastAPI) и отдаёт на порту 8000 и API, и мини-приложение.
Данные хранятся в PostgreSQL

## Что понадобится

- Docker 24+ с Docker Compose v2 - для запуска в контейнерах
- Для запуска без Docker: Python 3.12+, Node.js 22+, PostgreSQL 15+
- Бот на [платформе партнёров MAX](https://business.max.ru/self): его токен и имя
- Публичный HTTPS-адрес сервиса, чтобы открыть мини-приложение в MAX

## Настройка

```bash
git clone f4rceful/kto-so-mnoy
cd kto-so-mnoy
cp .env.example .env
```

Заполните `.env`:

| Переменная | Обязательна | Значение |
| --- | --- | --- |
| `BOT_TOKEN` | да | токен бота с платформы партнёров MAX |
| `BOT_USERNAME` | да | имя бота без `@` |
| `ADMIN_KEY` | нет | ключ панели модератора `/admin`; пусто - панель выключена |
| `POSTGRES_PASSWORD` | для Docker | пароль базы в контейнере `db` |
| `DATABASE_URL` | без Docker | строка подключения, например `postgresql+psycopg://kto:пароль@localhost:5432/kto_so_mnoy` |
| `PUBLIC_URL` | нет | публичный HTTPS-адрес, например `https://kto.example.ru`; задан - бот получает события через webhook, пусто — через long polling |
| `WEBHOOK_SECRET` | нет | секрет webhook (5–256 символов: латиница, цифры, `-`, `_`); пусто - выводится из токена |
| `DEV_MODE` | нет | `true` - вход без MAX по адресу `http://localhost:8000/?dev=1`, только для разработки |
| `BOT_QUICK_ACTIONS` | нет | `true` - кнопки "Принять / Отклонить" прямо в чате с ботом |

## Запуск через Docker Compose

```bash
docker compose up --build -d
```

Поднимаются два контейнера: `db` (PostgreSQL 17) и `app` (сервис). Приложение доступно на `http://localhost:8000`,
таблицы в базе создаются при первом старте

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

Данные базы лежат в томе `pg-data` и переживают перезапуск. Удалить их вместе с контейнерами: `docker compose down -v`

## Сборка и запуск образа вручную

```bash
docker build -t kto-so-mnoy .

docker network create kto

docker run -d --name kto-db --network kto \
  -e POSTGRES_DB=kto_so_mnoy -e POSTGRES_USER=kto -e POSTGRES_PASSWORD=secret \
  -v kto-pg:/var/lib/postgresql/data \
  postgres:17-alpine

docker run -d --name kto-app --network kto --restart unless-stopped \
  -p 8000:8000 --env-file .env \
  -e DATABASE_URL=postgresql+psycopg://kto:secret@kto-db:5432/kto_so_mnoy \
  kto-so-mnoy
```

## Запуск из командной строки без Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd frontend
npm ci
npm run build
cd ..

docker compose up -d db

cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Вместо `docker compose up -d db` можно использовать свой PostgreSQL: тогда укажите его в `DATABASE_URL`.
При базе из `docker compose` в `.env` нужно `DATABASE_URL=postgresql+psycopg://kto:<POSTGRES_PASSWORD>@localhost:5432/kto_so_mnoy`

Режим разработки с горячей перезагрузкой - в двух терминалах:

```bash
cd backend && uvicorn app.main:app --reload
cd frontend && npm run dev
```


## Справочник городов

Необязательный шаг: без него пользователи вписывают город сами. Повторный запуск безопасен.

```bash
docker compose run --rm app python -m scripts.import_cities https://raw.githubusercontent.com/hflabs/city/master/city.csv
```

Без Docker - из папки `backend`: `python -m scripts.import_cities <URL или путь к файлу>`.
Данные: [hflabs/city](https://github.com/hflabs/city)

## Проверка

```bash
curl http://localhost:8000/api/health
```

Ответ `"status": "ok"` значит, что база доступна и бот получает события

Тесты не требуют токена, интернета и PostgreSQL:

```bash
source .venv/bin/activate
pytest tests
```

## Зависимости

- Python: [`backend/requirements.txt`](backend/requirements.txt) - все библиотеки с точными версиями
- Фронтенд: [`frontend/package.json`](frontend/package.json) и `frontend/package-lock.json`
- Образ: [`Dockerfile`](Dockerfile), окружение: [`docker-compose.yml`](docker-compose.yml)
