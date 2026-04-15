#!/usr/bin/env bash
# Установщик ChatGPT Telegram Bot на Linux-VDS через systemd.
# Запускать от root (или через sudo):
#   sudo bash install.sh
#
# Идемпотентен: повторный запуск обновляет код и перезапускает сервис.

set -euo pipefail

# --- параметры ----------------------------------------------------------

BOT_USER="${BOT_USER:-deployer}"
BOT_HOME="/home/${BOT_USER}"
APP_DIR="${BOT_HOME}/chatgpt-telegram-bot"
REPO_URL="${REPO_URL:-}"            # можно задать: REPO_URL=git@github.com:you/repo.git bash install.sh
BRANCH="${BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SERVICE_NAME="chatgpt-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# --- утилиты ------------------------------------------------------------

log()  { printf "\033[1;32m[+]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[!]\033[0m %s\n" "$*"; }
die()  { printf "\033[1;31m[x]\033[0m %s\n" "$*" >&2; exit 1; }

require_root() {
    [[ $EUID -eq 0 ]] || die "Запустите через sudo: sudo bash $0"
}

# --- шаги ---------------------------------------------------------------

install_packages() {
    log "Устанавливаю системные пакеты..."
    apt-get update -qq
    apt-get install -y -qq \
        git ffmpeg curl ca-certificates \
        python3 python3-venv python3-pip
}

check_python() {
    local ver
    ver=$("${PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log "Python: ${ver}"
    local major minor
    major=$(echo "${ver}" | cut -d. -f1)
    minor=$(echo "${ver}" | cut -d. -f2)
    if (( major < 3 || (major == 3 && minor < 10) )); then
        warn "Обнаружен Python ${ver}. yt-dlp требует 3.10+."
        warn "Поставьте свежий Python (например, через deadsnakes) и перезапустите скрипт с PYTHON_BIN=python3.12."
        die "Слишком старый Python."
    fi
}

create_user() {
    if id -u "${BOT_USER}" >/dev/null 2>&1; then
        log "Пользователь ${BOT_USER} уже существует."
    else
        log "Создаю пользователя ${BOT_USER}..."
        useradd -m -s /bin/bash "${BOT_USER}"
    fi
}

clone_or_update_repo() {
    if [[ -d "${APP_DIR}/.git" ]]; then
        log "Обновляю репозиторий в ${APP_DIR}..."
        sudo -u "${BOT_USER}" git -C "${APP_DIR}" fetch --quiet
        sudo -u "${BOT_USER}" git -C "${APP_DIR}" checkout --quiet "${BRANCH}"
        sudo -u "${BOT_USER}" git -C "${APP_DIR}" pull --quiet --ff-only
    else
        [[ -n "${REPO_URL}" ]] || die "Не задан REPO_URL. Пример: REPO_URL=https://github.com/you/repo.git sudo bash $0"
        log "Клонирую ${REPO_URL} -> ${APP_DIR}..."
        sudo -u "${BOT_USER}" git clone --branch "${BRANCH}" --quiet "${REPO_URL}" "${APP_DIR}"
    fi
}

setup_venv() {
    log "Готовлю виртуальное окружение..."
    sudo -u "${BOT_USER}" bash -c "
        cd '${APP_DIR}'
        if [[ ! -d venv ]]; then
            ${PYTHON_BIN} -m venv venv
        fi
        source venv/bin/activate
        pip install --quiet --upgrade pip
        pip install --quiet -r requirements.txt
    "
}

prepare_env_file() {
    if [[ ! -f "${APP_DIR}/.env" ]]; then
        log "Создаю .env из .env.example (нужно будет отредактировать)."
        sudo -u "${BOT_USER}" cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    else
        log ".env уже существует — не трогаю."
    fi
    chmod 600 "${APP_DIR}/.env"
    chown "${BOT_USER}:${BOT_USER}" "${APP_DIR}/.env"
}

prepare_data_dirs() {
    log "Создаю memory/ и usage_logs/..."
    sudo -u "${BOT_USER}" mkdir -p "${APP_DIR}/memory" "${APP_DIR}/usage_logs"
}

install_service() {
    log "Устанавливаю systemd-юнит ${SERVICE_FILE}..."
    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=ChatGPT Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${BOT_USER}
Group=${BOT_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/python bot/main.py
Restart=on-failure
RestartSec=5

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=${APP_DIR}

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable --quiet "${SERVICE_NAME}"
}

restart_service() {
    log "Перезапускаю сервис..."
    systemctl restart "${SERVICE_NAME}" || true
    sleep 2
    systemctl --no-pager --lines=0 status "${SERVICE_NAME}" || true
}

print_next_steps() {
    cat <<EOF

────────────────────────────────────────────────────────
Установка завершена.

Следующие шаги:
  1. Отредактируйте .env:
       sudo -u ${BOT_USER} nano ${APP_DIR}/.env
     (минимум: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, ADMIN_USER_IDS)

  2. Перезапустите сервис:
       sudo systemctl restart ${SERVICE_NAME}

  3. Посмотрите логи:
       sudo journalctl -u ${SERVICE_NAME} -f

Полезные команды:
  sudo systemctl status ${SERVICE_NAME}
  sudo systemctl stop ${SERVICE_NAME}
  sudo systemctl disable ${SERVICE_NAME}

Обновление кода:
  sudo REPO_URL='<тот же URL>' bash $0
────────────────────────────────────────────────────────
EOF
}

# --- main ---------------------------------------------------------------

main() {
    require_root
    install_packages
    check_python
    create_user
    clone_or_update_repo
    setup_venv
    prepare_env_file
    prepare_data_dirs
    install_service
    restart_service
    print_next_steps
}

main "$@"
