<img src="https://i.ibb.co/T6jvMy3/Frame-233.png" width="220" align="left" alt="Кто со мной?">

<h3>Кто со мной?</h3>

Бот и мини-приложение в MAX для поиска компании по интересам среди школьников.<br>
Хакатон "Идея фикс".
Один Docker-образ собирает фронтенд (React + Vite) и бэкенд (FastAPI) и отдаёт на порту 8000 и API, и мини-приложение.
Данные хранятся в PostgreSQL

<br clear="left">

## Что понадобится

- Docker 24+ с Docker Compose v2 - для запуска в контейнерах
- Git - чтобы скачать проект
- Для запуска без Docker: Python 3.12+, Node.js 22+, PostgreSQL 15+
- Бот на [платформе партнёров MAX](https://business.max.ru/self): его токен и имя
- Публичный HTTPS-адрес сервиса, чтобы открыть мини-приложение в MAX

## Установка инструментов

### Windows 10/11

1. Установите [Docker Desktop для Windows](https://www.docker.com/products/docker-desktop/). При установке оставьте
   включённым WSL 2; если установщик попросит, перезагрузите компьютер. Перед запуском проекта Docker Desktop должен быть открыт
2. Установите Git, а для запуска без Docker ещё Python и Node.js. Проще всего через PowerShell:

   ```powershell
   winget install Git.Git
   winget install Python.Python.3.12
   winget install OpenJS.NodeJS.LTS
   ```

   Или с сайтов [git-scm.com](https://git-scm.com/download/win), [python.org](https://www.python.org/downloads/),
   [nodejs.org](https://nodejs.org/). При установке Python отметьте "Add python.exe to PATH"
3. После установки закройте и заново откройте PowerShell, чтобы новые команды стали доступны


### macOS

1. Установите [Docker Desktop для Mac](https://www.docker.com/products/docker-desktop/) (Apple Silicon или Intel) и запустите его
2. Git уже есть в системе: при первом вызове `git` macOS предложит установить Command Line Tools
3. Для запуска без Docker: [Python](https://www.python.org/downloads/) и [Node.js](https://nodejs.org/) с официальных сайтов
   или через Homebrew: `brew install python@3.12 node@22`


### Linux

Установите [Docker Engine](https://docs.docker.com/engine/install/) и плагин Compose, например в Ubuntu:

```bash
sudo apt install docker.io docker-compose-v2 git
sudo usermod -aG docker $USER
```

После `usermod` выйдите из системы и войдите снова, чтобы запускать `docker` без `sudo`

### Проверка установки

Во всех системах эти команды должны вывести версии:

```bash
docker --version
docker compose version
git --version
```

## Настройка

Windows (PowerShell):

```powershell
git clone https://github.com/f4rceful/kto-so-mnoy.git
cd kto-so-mnoy
copy .env.example .env
notepad .env
```

macOS / Linux:

```bash
git clone https://github.com/f4rceful/kto-so-mnoy.git
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
| `METRICS_TOKEN` | для мониторинга | токен доступа к `/metrics` (длинная случайная строка); пусто - метрики выключены |
| `GRAFANA_PASSWORD` | для мониторинга | пароль администратора Grafana (логин `admin`); не задан - `admin` |
| `GRAFANA_PORT`, `PROMETHEUS_PORT`, `ALERTMANAGER_PORT` | нет | порты на вашем компьютере, по умолчанию `3000`, `9090` и `9093` |
| `ALERT_USER_IDS` | нет | номера пользователей MAX, которым бот пишет об авариях; пусто - оповещения выключены |
| `GRAFANA_URL` | нет | адрес Grafana для кнопки «Графики» в панели модератора |
| `APP_VERSION` | нет | версия, которую сервис показывает в метриках; по умолчанию `dev` |

## Запуск через Docker Compose

Одинаково во всех системах:

```bash
docker compose up --build -d
```

Поднимаются два контейнера: `db` (PostgreSQL 17) и `app` (сервис). Приложение доступно на `http://localhost:8000`,
таблицы в базе создаются при первом старте. Первая сборка занимает несколько минут

```bash
docker compose ps
docker compose logs -f app
docker compose down
```

Данные базы лежат в томе `pg-data` и переживают перезапуск. Удалить их вместе с контейнерами: `docker compose down -v`

## Мониторинг (Prometheus и Grafana)

Всё необязательно и включается профилями: обычный `docker compose up` поднимает только `db` и `app`.
В `.env` задайте `METRICS_TOKEN` (например, `openssl rand -hex 24`) и `GRAFANA_PASSWORD`, затем:

```bash
docker compose --profile monitoring up --build -d
```

| Профиль | Что добавляет |
| --- | --- |
| `monitoring` | Prometheus, Grafana с готовыми панелями, проверка публичного адреса снаружи (blackbox), экспортёр PostgreSQL, cAdvisor |
| `logs` | Журнал сервисов в Grafana: Loki и Grafana Alloy |
| `alerts` | Alertmanager: оповещения о проблемах сообщением от бота в MAX (по умолчанию выключены) |

Профили можно сочетать: `docker compose --profile monitoring --profile logs up -d`.

| Что | Адрес |
| --- | --- |
| Grafana, панель «Кто со мной? — сервис и продукт» | `http://localhost:3000` (логин `admin`) |
| Журнал сервисов (профиль `logs`) | в Grafana: панель «Кто со мной? — журнал» |
| Prometheus | `http://localhost:9090` |
| Alertmanager (профиль `alerts`) | `http://localhost:9093` |
| Метрики сервиса | `http://localhost:8000/metrics` с заголовком `Authorization: Bearer <METRICS_TOKEN>` |

Если порт занят другой программой, поменяйте `GRAFANA_PORT`, `PROMETHEUS_PORT` или `ALERTMANAGER_PORT` в `.env`.
Все порты открыты только на `localhost`. Если задать `GRAFANA_URL` (например, `http://localhost:3000`), в панели модератора
появится кнопка «Графики».

Что показывает панель:

- состояние сервиса: база данных, бот, запросы в секунду, доля ошибок 5xx, время ответа (p95), очередь сообщений;
- версия и доступность: версия сервиса, время без перезапуска, проверка публичного адреса снаружи, срок сертификата,
  доступность за 30 дней и остаток бюджета ошибок (цель 99%). Перезапуски отмечены на графиках;
- охват и воронка: активные пользователи за день, неделю и месяц, воронка от открытия сервиса до принятого отклика,
  состоявшиеся занятия, доля набранных приглашений, время до первого отклика;
- продукт, запросы, самые частые и самые медленные маршруты, необработанные ошибки;
- бот и MAX API: доставка сообщений, время и коды ответов MAX, события бота, возраст самого старого сообщения в очереди;
- база данных (размер, подключения, кэш, транзакции) и процессор и память контейнеров.

Проверка публичного адреса берёт `PUBLIC_URL` из `.env`: пусто — проверки нет. Метрики по отдельным контейнерам видны
на Linux-сервере; Docker Desktop (Mac, Windows) отдаёт cAdvisor только общую картину по виртуальной машине.

### Оповещения

Правила описаны в `monitoring/alerts.yml`: недоступны сервис, база или публичный адрес, много ошибок 5xx, медленные ответы,
бот не получает события, очередь сообщений растёт, сообщения не доставляются, жалобы ждут решения больше двух часов,
сертификат скоро закончится. Prometheus проверяет правила всегда, но **сообщения не отправляются, пока вы не включите оповещения**:

1. В `.env` задайте `ALERT_USER_IDS` — номера пользователей MAX через запятую. Каждый из них должен был нажать «Старт» у бота.
2. Запустите Alertmanager: `docker compose --profile monitoring --profile alerts up -d`.

Alertmanager вызывает адрес `/api/alerts/webhook` сервиса (с тем же `METRICS_TOKEN`), а сервис пересылает оповещения
сообщением от бота. Пока `ALERT_USER_IDS` пуст, этот адрес отвечает `404`.

### Безопасность и хранение

Без `METRICS_TOKEN` адрес `/metrics` отвечает `404`, с неверным токеном - `401`, поэтому метрики не видны посторонним, даже
если сервис открыт в интернет. Prometheus хранит данные 30 дней, Loki - 14 дней. Данные лежат в томах `prometheus-data`,
`grafana-data`, `loki-data`, `alertmanager-data`. Контейнеры мониторинга ограничены по памяти. Панели описаны файлами
в каталоге `monitoring/` и подхватываются Grafana автоматически.

Резервная копия базы и всех данных мониторинга:

```bash
./monitoring/backup.sh backups
```

Скрипт кладёт в каталог `backups` дамп базы и архивы томов. Версия сервиса берётся из `APP_VERSION`; в образе из релиза
она равна номеру релиза, при локальной сборке — `dev`

## Сборка и запуск образа вручную

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

macOS / Linux:

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

Если образ собирается на Mac с Apple Silicon для обычного сервера, добавьте к `docker build` флаг `--platform linux/amd64`

### Запуск готового образа

Собранный образ опубликован в GitHub Container Registry. Вместо `docker build` скачайте его (команда одинакова
во всех системах), затем выполните команды `docker network create` и `docker run` выше, указав образ
`ghcr.io/f4rceful/kto-so-mnoy:latest`:

```bash
docker pull ghcr.io/f4rceful/kto-so-mnoy:latest
```

Нужная версия указывается вместо `latest`, например `1.2`. Список версий есть на странице [релизов](https://github.com/f4rceful/kto-so-mnoy/releases).

Если образ передан файлом `kto-so-mnoy.tar.gz`, загрузите его и укажите в `docker run` образ `kto-so-mnoy:latest`:

```bash
docker load -i kto-so-mnoy.tar.gz
```

## Запуск из командной строки без Docker

Windows (PowerShell):

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

macOS / Linux:

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

Если PowerShell пишет, что выполнение сценариев отключено, разрешите его один раз и повторите активацию:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Вместо `docker compose up -d db` можно использовать свой PostgreSQL: тогда укажите его в `DATABASE_URL`.
При базе из `docker compose` в `.env` нужно `DATABASE_URL=postgresql+psycopg://kto:<POSTGRES_PASSWORD>@localhost:5432/kto_so_mnoy`

Режим разработки с горячей перезагрузкой - в двух терминалах, в каждом сначала активируйте `.venv`:

```bash
cd backend
uvicorn app.main:app --reload
```

```bash
cd frontend
npm run dev
```

## Справочник городов

Список из 1116 городов России встроен в проект (`backend/app/cities.csv`) и загружается в базу автоматически при первом
запуске, ничего делать не нужно. Города, которых нет в списке, пользователи вписывают сами

Данные: [hflabs/city](https://github.com/hflabs/city), лицензия [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

## Проверка

Windows (PowerShell):

```powershell
curl.exe http://localhost:8000/api/health
```

macOS / Linux:

```bash
curl http://localhost:8000/api/health
```

Можно просто открыть `http://localhost:8000/api/health` в браузере

Ответ `"status": "ok"` значит, что база доступна и бот получает события. Сразу после запуска бот может показывать
`"stale"`: первый запрос к MAX длится до 30 секунд

Тесты не требуют токена, интернета и PostgreSQL:

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
pytest tests
```

macOS / Linux:

```bash
source .venv/bin/activate
pytest tests
```

## Зависимости

- Python: [`backend/requirements.txt`](backend/requirements.txt) - все библиотеки с точными версиями
- Фронтенд: [`frontend/package.json`](frontend/package.json) и `frontend/package-lock.json`
- Образ: [`Dockerfile`](Dockerfile), окружение: [`docker-compose.yml`](docker-compose.yml)
