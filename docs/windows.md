[← К оглавлению](../README.md) · **Windows** · [macOS](macos.md) · [Linux](linux.md)

# Windows 10/11

Все команды выполняются в PowerShell.

## 1. Что понадобится

- Docker с Docker Compose v2: так проект запускается проще всего
- Git, чтобы скачать проект
- Бот на [платформе партнёров MAX](https://business.max.ru/self): его токен и имя ([как получить](configuration.md#бот-на-платформе-max))
- Публичный HTTPS-адрес сервиса, чтобы открыть мини-приложение в MAX ([подробнее](configuration.md#публичный-адрес-и-webhook))
- Для запуска без Docker дополнительно: Python 3.12+, Node.js 22+ и PostgreSQL 15+ (PostgreSQL можно взять из Compose)

## 2. Установка инструментов

1. Установите [Docker Desktop для Windows](https://www.docker.com/products/docker-desktop/). При установке оставьте
   включённым WSL 2; если установщик попросит, перезагрузите компьютер. Перед запуском проекта Docker Desktop должен быть открыт.
2. Установите Git, а для запуска без Docker ещё Python и Node.js. Проще всего через PowerShell:

   ```powershell
   winget install Git.Git
   winget install Python.Python.3.12
   winget install OpenJS.NodeJS.LTS
   ```

   Или с сайтов [git-scm.com](https://git-scm.com/download/win), [python.org](https://www.python.org/downloads/),
   [nodejs.org](https://nodejs.org/). При установке Python отметьте "Add python.exe to PATH".
3. После установки закройте и заново откройте PowerShell, чтобы новые команды стали доступны.

## 3. Проверка установки

Эти команды должны вывести версии:

```powershell
docker --version
docker compose version
git --version
```

## 4. Скачивание и настройка

```powershell
git clone https://github.com/f4rceful/kto-so-mnoy.git
cd kto-so-mnoy
copy .env.example .env
notepad .env
```

Заполните `.env`. Минимум: `BOT_TOKEN`, `BOT_USERNAME` и `POSTGRES_PASSWORD` (пароль для базы в контейнере, придумайте любой).
Остальное необязательно. Полный список переменных и как получить случайные ключи: [Настройка](configuration.md).

## 5. Запуск через Docker Compose

```powershell
docker compose up --build -d
```

Поднимаются два контейнера: `db` (PostgreSQL 17) и `app` (сервис). Таблицы в базе создаются при первом старте, а список
городов загружается сам. Первая сборка занимает несколько минут. Дальше:

```powershell
docker compose ps
docker compose logs -f app
docker compose down
```

Данные базы лежат в томе `pg-data` и переживают перезапуск. Удалить их вместе с контейнерами: `docker compose down -v`.
После изменения `.env` примените настройки командой `docker compose up -d`.

## 6. Проверка работы

Откройте `http://localhost:8000/api/health` в браузере или выполните:

```powershell
curl.exe http://localhost:8000/api/health
```

Ответ `"status": "ok"` значит, что база доступна и бот получает события. Сразу после запуска бот может показывать `"stale"`:
первый запрос к MAX длится до 30 секунд. Панель модератора: `http://localhost:8000/admin` (если задан `ADMIN_KEY`).

## 7. Образ вручную и готовый образ

Сборка и запуск без Compose:

Windows (PowerShell):

```powershell
docker build -t kto-so-mnoy .

docker network create kto

docker run -d --name kto-db --network kto `
  -e POSTGRES_DB=kto_so_mnoy -e POSTGRES_USER=kto -e POSTGRES_PASSWORD=secret `
  -v kto-pg:/var/lib/postgresql/data `
  postgres:17-alpine

docker run -d --name kto-app --network kto --restart unless-stopped `
  -p 8000:8000 --env-file .env `
  -e DATABASE_URL=postgresql+psycopg://kto:secret@kto-db:5432/kto_so_mnoy `
  kto-so-mnoy
```

Готовый образ из GitHub Container Registry можно скачать вместо сборки и подставить в команду `docker run` вместо `kto-so-mnoy`
(команда `docker build` тогда не нужна):

```powershell
docker pull ghcr.io/f4rceful/kto-so-mnoy:latest
```

Нужная версия указывается вместо `latest`, например `1.3`: список на странице [релизов](https://github.com/f4rceful/kto-so-mnoy/releases).
Если образ передан файлом `kto-so-mnoy.tar.gz`, загрузите его и используйте образ `kto-so-mnoy:latest`:

```powershell
docker load -i kto-so-mnoy.tar.gz
```

## 8. Запуск без Docker

Нужны Python 3.12+, Node.js 22+ и PostgreSQL 15+. Базу можно взять из Compose, остальное запускается на вашем компьютере:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

cd frontend
npm ci
npm run build
cd ..

docker compose up -d db

cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Если PowerShell пишет, что выполнение сценариев отключено, разрешите его один раз и повторите активацию:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Вместо `docker compose up -d db` можно использовать свой PostgreSQL: тогда укажите его в `DATABASE_URL`. При базе из Compose
в `.env` нужно `DATABASE_URL=postgresql+psycopg://kto:<POSTGRES_PASSWORD>@localhost:5432/kto_so_mnoy`.

Режим разработки с горячей перезагрузкой запускается в двух окнах PowerShell, в каждом сначала активируйте `.venv`:

```powershell
cd backend
uvicorn app.main:app --reload
```

```powershell
cd frontend
npm run dev
```

## 9. Тесты

Тесты не требуют токена, интернета и PostgreSQL:

```powershell
.venv\Scripts\Activate.ps1
pytest tests
```

## 10. Мониторинг

Необязательные графики, журнал и оповещения включаются профилями Compose. В `.env` нужны `METRICS_TOKEN` и `GRAFANA_PASSWORD`:

```powershell
docker compose --profile monitoring up --build -d
```

Затем откройте Grafana на `http://localhost:3000` (логин `admin`). Все возможности, адреса и оповещения: [Мониторинг](monitoring.md).

Скрипт резервной копии `monitoring/backup.sh` написан для оболочки `sh`: запускайте его из Git Bash (ставится вместе с Git) или WSL:
`bash monitoring/backup.sh backups`

Дальше: [Мониторинг](monitoring.md) · [Справочник](reference.md)
