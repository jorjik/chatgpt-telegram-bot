# HowTo: Запуск бота локально

## Один раз — установить зависимости

```bash
cd c:/dev/tg/chatgpt-telegram-bot
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```

`ffmpeg` должен быть в PATH (проверка: `ffmpeg -version`). На Windows — [gyan.dev static build](https://www.gyan.dev/ffmpeg/builds/) + добавить в PATH. `yt-dlp` приедет из `requirements.txt`.

## Настроить `.env`

Минимум:

```
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
```

Опционально — для `/brief` и `/clips` на Claude вместо OpenAI:

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-5
```

Опционально — вынести транскрипцию в Groq Whisper:

```
TRANSCRIPTION_PROVIDER=groq
GROQ_API_KEY=...
TRANSCRIPTION_MODEL=whisper-large-v3-turbo
```

## Запуск

```bash
python bot/main.py
```

Бот стартует в long-polling, подхватит `.env`, зарегистрирует команды (в меню появятся `/brief` и `/clips`).

## Смоук-тест `/clips`

1. В Telegram в чате с ботом → `/clips`
2. Нажми «🔗 Прислать ссылку» → кинь короткий YouTube (5–10 мин лекция/подкаст)
3. Платформа → TikTok → 3 клипа
4. Жди прогресс-статусы: скачивание → аудио → транскрипция → highlights → рендер. Клипы прилетят по одному с подписями (title + hook + таймкоды).

## Смоук-тест `/brief`

1. `/brief` → «📝 Текстовая идея» или «🎞 Загрузить видео-референс»
2. Пройти опросник: платформа → длительность → формат → стиль → аудитория
3. Получить сценарий от LLM

## Типичные ошибки

| Симптом | Причина / фикс |
|---|---|
| `yt-dlp: not found` | Перезапусти терминал после `pip install` или проверь, что `.venv` активирован |
| Whisper "file too large" | Видео длиннее ~30 мин, MVP не тянет (чанкинг — в roadmap) |
| `⚠️ Файл XX МБ — Telegram Bot API ограничен 20 МБ` | Шли ссылкой вместо файла |
| `ffmpeg failed` в логах | Проверь, что `ffmpeg -version` работает из того же shell, где запущен бот |
| Клип пустой / без звука | Источник без аудиодорожки или проблема в `-ss` перед `-i` — смотри stderr в stdout-логах |

## Полезное

- Логи идут в stdout. При ошибках ffmpeg/yt-dlp видно tail stderr с точной причиной.
- Временные файлы живут в `%TEMP%/clips_*`, чистятся автоматически в конце задачи или при `/cancel`.
- `/cancel` работает в любой момент флоу `/brief` и `/clips`.
- Перезапуск бота: Ctrl+C в терминале → `python bot/main.py` снова.
