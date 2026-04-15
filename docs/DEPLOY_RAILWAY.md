# Деплой на Railway

[Railway](https://railway.app) — PaaS, который сам собирает Docker-образ из репозитория и держит контейнер онлайн. Подходит, чтобы поднять бота без своего VDS.

## 1. Что потребуется

- Аккаунт на railway.app (вход через GitHub)
- Репозиторий с ботом на GitHub (публичный или приватный)
- Токены: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, опц. `GROQ_API_KEY`, `ANTHROPIC_API_KEY`

Бот работает через long-polling — публичный URL и открытые порты не нужны.

## 2. Создание проекта

1. Зайдите на https://railway.app → **New Project** → **Deploy from GitHub repo**.
2. Выберите репозиторий `chatgpt-telegram-bot`. Railway сам найдёт `Dockerfile` и начнёт сборку.
3. Первый билд упадёт — нет переменных окружения. Это нормально, настроим дальше.

## 3. Переменные окружения

В сервисе → **Variables** → **Raw Editor** вставьте (значения — ваши):

```ini
TELEGRAM_BOT_TOKEN=123456:ABCDEF
ADMIN_USER_IDS=123456789
ALLOWED_TELEGRAM_USER_IDS=*

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=gsk_...

LLM_PROVIDER=openai
SHOW_USAGE=false

# опционально:
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-sonnet-4-5
# BRIEF_MEMORY_DIR=/data/memory
```

Сохраните — Railway автоматически перезапустит контейнер.

## 4. Persistence (важно!)

Контейнерная ФС эфемерная — шаблоны `/brief` и usage-логи сгорят при редеплое. Подключите volume:

1. В сервисе → **Settings** → **Volumes** → **New Volume**.
2. **Mount path:** `/data`
3. **Size:** 1 GB хватит.
4. Добавьте переменную `BRIEF_MEMORY_DIR=/data/memory` (чтобы код писал туда).
5. Для `usage_logs` можно так же вынести, если уместно.

После redeploy файлы в `/data/*` переживут перезапуски.

## 5. Проверка деплоя

- Вкладка **Deployments** → смотрите логи текущего билда.
- Должно появиться:
  ```
  root - INFO - Transcription provider: Groq (...)
  telegram.ext.Application - INFO - Application started
  ```
- В Telegram напишите боту `/start` — должен ответить.

## 6. Обновление

Railway автоматически редеплоит на каждый push в отслеживаемую ветку (по умолчанию `main`). Поменять ветку: **Settings** → **Source** → **Branch**.

Откатиться: **Deployments** → у нужного билда → **Redeploy**.

## 7. Healthcheck и рестарты

Railway по умолчанию держит контейнер живым. Дополнительных healthcheck'ов для long-polling не нужно — если `bot/main.py` упадёт, Railway перезапустит его сам.

Можно увеличить надёжность, добавив в **Settings** → **Deploy** → **Restart Policy**: `always`.

## 8. Лимиты бесплатного тарифа

На free-плане Railway даёт ограниченный pool часов/RAM. Если бот тихий — хватит. Активный бот с транскрипцией видео лучше держать на Hobby-плане ($5/мес).

## 9. Конфликт `409 Conflict`

Если одновременно жив ещё один бот с тем же токеном (на VDS, локально, в Docker) — Railway словит `409 Conflict: terminated by other getUpdates`. Остановите лишние инстансы: один токен = один активный поллер.

## 10. Стоимость AI-вызовов

Railway не отвечает за биллинг OpenAI/Anthropic/Groq — они считаются у них отдельно. Включите `SHOW_USAGE=true` либо добавьте свой `ADMIN_USER_IDS`, чтобы видеть расход токенов/денег в сообщениях бота.

## 11. Альтернативы

- **Fly.io** — похожий PaaS, тоже умеет читать `Dockerfile`.
- **Render** — аналогично; для background workers тариф Starter $7/мес.
- **VDS через systemd** — см. [DEPLOY_SYSTEMD.md](DEPLOY_SYSTEMD.md), если нужен полный контроль и фикс-цена.
