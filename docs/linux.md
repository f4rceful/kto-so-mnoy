[← К оглавлению](../README.md) · [Windows](windows.md) · [macOS](macos.md) · **Linux**

# Linux

Все команды выполняются в терминале (bash).

## 1. Что понадобится

- Docker с Docker Compose v2: так проект запускается проще всего
- Git, чтобы скачать проект
- Бот на [платформе партнёров MAX](https://business.max.ru/self): его токен и имя ([как получить](configuration.md#бот-на-платформе-max))
- Публичный HTTPS-адрес сервиса, чтобы открыть мини-приложение в MAX ([подробнее](configuration.md#публичный-адрес-и-webhook))
- Для запуска без Docker дополнительно: Python 3.12+, Node.js 22+ и PostgreSQL 15+ (PostgreSQL можно взять из Compose)

## 2. Установка инструментов

Установите [Docker Engine](https://docs.docker.com/engine/install/) с плагином Compose и Git. Например, в Ubuntu и Debian:

```bash
sudo apt update
sudo apt install docker.io docker-compose-v2 git
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

После `usermod` выйдите из системы и войдите снова, чтобы запускать `docker` без `sudo`. Для других дистрибутивов
используйте инструкцию Docker по ссылке выше.

Для запуска без Docker установите ещё Python и Node.js. В Ubuntu и Debian:

```bash
sudo apt install python3 python3-venv python3-pip
```

Node.js 22 берите с [nodejs.org](https://nodejs.org/) или через [nvm](https://github.com/nvm-sh/nvm).

## 3. Проверка установки

Эти команды должны вывести версии:

```bash
docker --version
docker compose version
git --version
```

## 4. Скачивание и настройка

```bash
git clone https://github.com/f4rceful/kto-so-mnoy.git
cd kto-so-mnoy
cp .env.example .env
nano .env
```

Заполните `.env`. Минимум: `BOT_TOKEN`, `BOT_USERNAME` и `POSTGRES_PASSWORD` (пароль для базы в контейнере, придумайте любой).
Остальное необязательно. Полный список переменных и как получить случайные ключи: [Настройка](configuration.md).

## 5. Запуск через Docker Compose

```bash
docker compose up --build -d
```

Поднимаются два контейнера: `db` (PostgreSQL 17) и `app` (сервис). Таблицы в базе создаются при первом старте, а список
городов загружается сам. Первая сборка занимает несколько минут. Дальше:

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

Данные базы лежат в томе `pg-data` и переживают перезапуск. Удалить их вместе с контейнерами: `docker compose down -v`.
После изменения `.env` примените настройки командой `docker compose up -d`.

## 6. Проверка работы

Откройте `http://localhost:8000/api/health` в браузере или выполните:

```bash
curl http://localhost:8000/api/health
```

Ответ `"status": "ok"` значит, что база доступна и бот получает события. Сразу после запуска бот может показывать `"stale"`:
первый запрос к MAX длится до 30 секунд. Панель модератора: `http://localhost:8000/admin` (если задан `ADMIN_KEY`).

## 7. Образ вручную и готовый образ

Сборка и запуск без Compose:

Linux:

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

Готовый образ из GitHub Container Registry можно скачать вместо сборки и подставить в команду `docker run` вместо `kto-so-mnoy`
(команда `docker build` тогда не нужна):

```bash
docker pull ghcr.io/f4rceful/kto-so-mnoy:latest
```

Нужная версия указывается вместо `latest`, например `1.3`: список на странице [релизов](https://github.com/f4rceful/kto-so-mnoy/releases).
Если образ передан файлом `kto-so-mnoy.tar.gz`, загрузите его и используйте образ `kto-so-mnoy:latest`:

```bash
docker load -i kto-so-mnoy.tar.gz
```

## 8. Запуск без Docker

Нужны Python 3.12+, Node.js 22+ и PostgreSQL 15+. Базу можно взять из Compose, остальное запускается на вашем компьютере:

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

Вместо `docker compose up -d db` можно использовать свой PostgreSQL: тогда укажите его в `DATABASE_URL`. При базе из Compose
в `.env` нужно `DATABASE_URL=postgresql+psycopg://kto:<POSTGRES_PASSWORD>@localhost:5432/kto_so_mnoy`.

Режим разработки с горячей перезагрузкой запускается в двух окнах терминала, в каждом сначала активируйте `.venv`:

```bash
cd backend
uvicorn app.main:app --reload
```

```bash
cd frontend
npm run dev
```

## 9. Тесты

Тесты не требуют токена, интернета и PostgreSQL:

```bash
source .venv/bin/activate
pytest tests
```

## 10. Мониторинг

Необязательные графики, журнал и оповещения включаются профилями Compose. В `.env` нужны `METRICS_TOKEN` и `GRAFANA_PASSWORD`:

```bash
docker compose --profile monitoring up --build -d
```

Затем откройте Grafana на `http://localhost:3000` (логин `admin`). Все возможности, адреса и оповещения: [Мониторинг](monitoring.md).

На Linux-сервере cAdvisor показывает каждый контейнер отдельно: панели "Контейнеры" в Grafana работают полностью.

## Сервер с публичным адресом

Сервис публикует порт `8000`. На сервере поставьте перед ним обратный прокси с HTTPS (например, [Caddy](https://caddyserver.com/)),
укажите получившийся адрес в `PUBLIC_URL` ([подробнее](configuration.md#публичный-адрес-и-webhook)), а порты мониторинга
не открывайте наружу: они слушают только `localhost`

Дальше: [Мониторинг](monitoring.md) · [Справочник](reference.md)
