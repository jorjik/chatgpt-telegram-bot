# Деплой на VDS без Docker (systemd)

Запуск бота на чистом Linux-VDS через Python + systemd. Подходит, когда вы не хотите тянуть Docker.

## Автоматическая установка одной командой

Если лень читать ручной гайд — есть `scripts/install.sh`:

```bash
ssh root@SERVER
# первый запуск — задайте REPO_URL
REPO_URL=https://github.com/you/chatgpt-telegram-bot.git \
    bash <(curl -fsSL https://raw.githubusercontent.com/you/chatgpt-telegram-bot/main/scripts/install.sh)

# или локально, после git clone:
sudo REPO_URL=https://github.com/you/chatgpt-telegram-bot.git bash scripts/install.sh
```

Скрипт идемпотентен: повторный запуск обновит код и перезапустит сервис.
Доступные переменные: `REPO_URL`, `BRANCH` (default `main`), `BOT_USER` (default `deployer`), `PYTHON_BIN` (default `python3`).

После окончания — отредактируйте `.env` и перезапустите:
```bash
sudo -u deployer nano /home/deployer/chatgpt-telegram-bot/.env
sudo systemctl restart chatgpt-bot
sudo journalctl -u chatgpt-bot -f
```

Ниже — подробный ручной гайд, если что-то пошло не так.


## 1. Требования

- Ubuntu 22.04 / 24.04 или Debian 12
- 1 CPU, 512 МБ RAM, 5 ГБ диска — минимум
- Python **3.12** (или 3.10+; 3.9 уже deprecated для yt-dlp)
- SSH-доступ с sudo

## 2. Системные пакеты

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git ffmpeg
```

Проверка:

```bash
python3 --version      # 3.10+
ffmpeg -version | head -1
```

Если в репозитории Debian старый Python — поставьте свежий через deadsnakes (Ubuntu) или pyenv.

## 3. Отдельный пользователь (не root)

```bash
sudo useradd -m -s /bin/bash deployer
sudo su - deployer
```

Дальше всё делаем от имени `deployer`.

## 4. Клонирование и виртуальное окружение

```bash
cd ~
git clone <URL-вашего-репозитория> chatgpt-telegram-bot
cd chatgpt-telegram-bot

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Настройка `.env`

```bash
cp .env.example .env
nano .env
```

Минимум:

```ini
TELEGRAM_BOT_TOKEN=123456:ABCDEF...
ADMIN_USER_IDS=123456789
ALLOWED_TELEGRAM_USER_IDS=*

OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=gsk_...

LLM_PROVIDER=openai
SHOW_USAGE=false
```

Закройте права:

```bash
chmod 600 .env
```

## 6. Создать папки для данных

```bash
mkdir -p memory usage_logs
```

## 7. Быстрая проверка

```bash
source venv/bin/activate
python bot/main.py
```

Должны увидеть:

```
root - INFO - Transcription provider: Groq (...)
telegram.ext.Application - INFO - Application started
```

Нажмите `Ctrl+C`, чтобы остановить — переводим на systemd.

## 8. systemd-юнит

Создайте файл (от root):

```bash
sudo nano /etc/systemd/system/chatgpt-bot.service
```

Содержимое:

```ini
[Unit]
Description=ChatGPT Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=deployer
Group=deployer
WorkingDirectory=/home/deployer/chatgpt-telegram-bot
EnvironmentFile=/home/deployer/chatgpt-telegram-bot/.env
ExecStart=/home/deployer/chatgpt-telegram-bot/venv/bin/python bot/main.py
Restart=on-failure
RestartSec=5

# Безопасность
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=/home/deployer/chatgpt-telegram-bot

# Логи
StandardOutput=journal
StandardError=journal
SyslogIdentifier=chatgpt-bot

[Install]
WantedBy=multi-user.target
```

**Важно:** `ProtectHome=read-only` + `ReadWritePaths=...` разрешают писать только в папку бота (там `memory/`, `usage_logs/`).

## 9. Запуск сервиса

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now chatgpt-bot
sudo systemctl status chatgpt-bot
```

Статус должен быть `active (running)`.

## 10. Просмотр логов

```bash
# живой поток
sudo journalctl -u chatgpt-bot -f

# последние 200 строк
sudo journalctl -u chatgpt-bot -n 200 --no-pager

# логи за сегодня
sudo journalctl -u chatgpt-bot --since today
```

## 11. Обновление кода

```bash
sudo su - deployer
cd ~/chatgpt-telegram-bot
git pull
source venv/bin/activate
pip install -r requirements.txt    # только если requirements менялись
exit

sudo systemctl restart chatgpt-bot
sudo journalctl -u chatgpt-bot -f
```

## 12. Управление сервисом

```bash
sudo systemctl start chatgpt-bot       # запуск
sudo systemctl stop chatgpt-bot        # остановка
sudo systemctl restart chatgpt-bot     # перезапуск
sudo systemctl status chatgpt-bot      # статус
sudo systemctl disable chatgpt-bot     # убрать из автозагрузки
```

## 13. Ротация логов

`journalctl` сам ограничивает размер. Настройка:

```bash
sudo nano /etc/systemd/journald.conf
```

```ini
[Journal]
SystemMaxUse=500M
SystemMaxFileSize=50M
MaxRetentionSec=1month
```

```bash
sudo systemctl restart systemd-journald
```

## 14. Типичные проблемы

**`409 Conflict: terminated by other getUpdates`**
Другой инстанс опрашивает тот же токен. Остановите всё лишнее:

```bash
sudo systemctl stop chatgpt-bot
ps aux | grep 'bot/main.py'   # убедитесь, что нет других процессов
sudo systemctl start chatgpt-bot
```

**`ModuleNotFoundError` после обновления**

```bash
sudo su - deployer
cd ~/chatgpt-telegram-bot
source venv/bin/activate
pip install -r requirements.txt
exit
sudo systemctl restart chatgpt-bot
```

**`Deprecated Feature: Support for Python version 3.9`**
Обновите Python до 3.10+ (лучше 3.12). На Ubuntu через deadsnakes:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.12 python3.12-venv
# пересоздать venv:
rm -rf venv
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Падает при отправке сценария: `Can't parse entities`**
Telegram-парсер ругнулся на HTML. Фоллбэк на plain-text уже встроен в код, но если повторяется — проверьте логи `journalctl -u chatgpt-bot`.

## 15. Бэкапы

На самом сервере:

```bash
cd /home/deployer/chatgpt-telegram-bot
tar czf ~/backup-$(date +%F).tgz .env memory usage_logs
```

Скачать к себе:

```bash
scp deployer@SERVER:~/backup-*.tgz ~/backups/
```

Автоматизация через cron (от `deployer`):

```bash
crontab -e
```

```cron
0 3 * * * cd /home/deployer/chatgpt-telegram-bot && tar czf /home/deployer/backup-$(date +\%F).tgz .env memory usage_logs && find /home/deployer -name 'backup-*.tgz' -mtime +14 -delete
```

## 16. Firewall

Боту нужны только исходящие соединения. Если включили UFW:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
```

Никакие порты открывать не нужно — бот использует long-polling к Telegram.
