# Деплой бота на VDS

Краткая пошаговая инструкция: поднять бот на чистом Linux-VDS через Docker + git.

## 1. Требования к серверу

- Ubuntu 22.04 / 24.04 или Debian 12 (подойдёт любой Linux с Docker)
- 1 CPU, 1 ГБ RAM, 10 ГБ диска — минимум
- Открытый исходящий интернет (к `api.telegram.org`, `api.openai.com`, `api.groq.com`)
- SSH-доступ к серверу

## 2. Установка Docker

```bash
# Debian / Ubuntu
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# перелогиньтесь, чтобы права applied
```

Проверка:

```bash
docker --version
docker compose version
```

## 3. Клонирование репозитория

```bash
cd ~
git clone <URL вашего форка репозитория> chatgpt-telegram-bot
cd chatgpt-telegram-bot
```

Если код приватный — используйте deploy-key или HTTPS-токен.

## 4. Настройка `.env`

Скопируйте шаблон и заполните реальными значениями:

```bash
cp .env.example .env
nano .env
```

Минимальный набор переменных:

```ini
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
ADMIN_USER_IDS=123456789        # ваш id, получить у @userinfobot
ALLOWED_TELEGRAM_USER_IDS=*     # или список id через запятую

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Транскрипция (опционально — если пусто, используется OpenAI Whisper)
TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=gsk_...

# Anthropic для /brief (опционально)
LLM_PROVIDER=openai             # или anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# Показывать токены/цену
SHOW_USAGE=false                # true — показать всем; админы видят всегда
```

Остальные поля из `.env.example` — при необходимости.

## 5. Подготовка persistence (шаблоны /brief и usage)

Чтобы шаблоны и счётчики токенов переживали пересборку:

```bash
mkdir -p memory usage_logs
```

Обновите `docker-compose.yml`, добавив явный bind-mount для `memory`:

```yaml
services:
  chatgpt-telegram-bot:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - .:/app
      - ./memory:/app/memory
    restart: unless-stopped
```

Bind-mount `.:/app` уже покрывает всё, но отдельный маппинг `memory` страхует от конфликтов прав при разных окружениях.

## 6. Сборка и запуск

```bash
docker compose build
docker compose up -d
```

Проверить логи:

```bash
docker compose logs -f
```

Должно появиться:

```
root - INFO - Transcription provider: Groq (...)
telegram.ext.Application - INFO - Application started
```

## 7. Проверка

В Telegram:

- `/start` — приветствие
- `/brief` — опросник сценариста
- `/clips` — нарезка длинного видео
- `/reset` — сброс контекста

## 8. Обновление кода

```bash
cd ~/chatgpt-telegram-bot
git pull
docker compose build
docker compose up -d
```

`--no-cache` нужен только если что-то сломалось в кэше слоёв:

```bash
docker compose build --no-cache
```

## 9. Типичные проблемы

**`409 Conflict: terminated by other getUpdates`**
Один токен опрашивается сразу двумя ботами. Остановите лишний:

```bash
docker compose down
# убедитесь, что локальный бот на машине разработчика тоже выключен
```

**`FileNotFoundError: '/app/memory'`**
Создайте папку на хосте и пересоберите:

```bash
mkdir -p memory
docker compose up -d --build
```

**`yt-dlp: No matching distribution found`**
Проверьте, что версия в `requirements.txt` действительно существует в PyPI:

```bash
pip index versions yt-dlp | head
```

**`Deprecated Feature: Support for Python version 3.9`**
Это warning, не ошибка. Если серия yt-dlp начала ломаться на 3.9 — поднимите Python в `Dockerfile` до `python:3.12-alpine` (код совместим).

## 10. Остановка / удаление

```bash
# остановить
docker compose stop

# остановить и удалить контейнер
docker compose down

# + удалить образ
docker compose down --rmi all
```

## 11. Бэкапы

Критичное:

- `.env` — токены/ключи
- `memory/` — шаблоны брифов
- `usage_logs/` — если включён трекинг

Простая схема:

```bash
tar czf ~/chatgpt-bot-backup-$(date +%F).tgz .env memory usage_logs
```

Храните дампы вне сервера.
