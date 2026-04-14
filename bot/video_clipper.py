"""/clips ConversationHandler: long video → N vertical short clips with captions.

Flow:
  1. Источник — URL или видео-файл ≤ ~20 МБ.
  2. Платформа (TikTok / Reels / Shorts) → целевая длина.
  3. Количество клипов (3 / 5 / 10).
  4. Пайплайн (clip_engine) → отправка файлов.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from clip_engine import (
    ClipJobInput,
    ClipResult,
    LLMFn,
    TranscribeFn,
    download_from_url,
    ensure_tools_available,
    is_url,
    make_workdir,
    run_clip_job,
)


logger = logging.getLogger(__name__)


# Conversation states.
SOURCE, WAIT_SOURCE, PLATFORM, COUNT, SUBTITLES = range(5)

CANCEL = "__cancel__"
SOURCE_URL = "__src_url__"
SOURCE_FILE = "__src_file__"
SUBS_YES = "__subs_yes__"
SUBS_NO = "__subs_no__"

PLATFORMS: list[tuple[str, str, int]] = [
    ("tiktok", "TikTok (30s)", 30),
    ("reels", "Instagram Reels (30s)", 30),
    ("shorts", "YouTube Shorts (45s)", 45),
]

COUNTS: list[int] = [3, 5, 10]

FILE_SIZE_LIMIT = 20 * 1024 * 1024  # Telegram Bot API hard cap.


@dataclass
class ClipperProviders:
    """Async callables injected from main.py to decouple from OpenAI/Anthropic."""

    transcribe: TranscribeFn
    llm: LLMFn
    # (ctx, attachment) -> local Path of downloaded video file.
    download_attachment: Callable[[ContextTypes.DEFAULT_TYPE, object, Path], Awaitable[Path]]


@dataclass
class ClipperState:
    workdir: Optional[Path] = None
    source_video: Optional[Path] = None
    platform_key: str = ""
    target_duration: int = 30
    count: int = 3
    burn_subtitles: bool = True
    temp_paths: list[Path] = field(default_factory=list)


# --- keyboards ----------------------------------------------------------


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def _source_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [("🔗 Прислать ссылку", SOURCE_URL)],
            [("📤 Загрузить файл (≤20 МБ)", SOURCE_FILE)],
            [("❌ Отмена", CANCEL)],
        ]
    )


def _platform_keyboard() -> InlineKeyboardMarkup:
    rows = [[(label, key)] for key, label, _ in PLATFORMS]
    rows.append([("❌ Отмена", CANCEL)])
    return _kb(rows)


def _count_keyboard() -> InlineKeyboardMarkup:
    rows = [[(f"{n} клипов", str(n))] for n in COUNTS]
    rows.append([("❌ Отмена", CANCEL)])
    return _kb(rows)


def _subtitles_keyboard() -> InlineKeyboardMarkup:
    return _kb(
        [
            [("✅ Со субтитрами", SUBS_YES)],
            [("🚫 Без субтитров", SUBS_NO)],
            [("❌ Отмена", CANCEL)],
        ]
    )


# --- state helpers ------------------------------------------------------


def _get_state(context: ContextTypes.DEFAULT_TYPE) -> ClipperState:
    state = context.user_data.get("clipper_state")
    if state is None:
        state = ClipperState()
        context.user_data["clipper_state"] = state
    return state


def _get_providers(context: ContextTypes.DEFAULT_TYPE) -> Optional[ClipperProviders]:
    return context.bot_data.get("clipper_providers")


def _cleanup(state: ClipperState) -> None:
    if state.workdir and state.workdir.exists():
        shutil.rmtree(state.workdir, ignore_errors=True)
    state.workdir = None
    state.source_video = None


# --- entry --------------------------------------------------------------


async def start_clips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    missing = ensure_tools_available()
    if missing:
        await update.message.reply_text(
            f"⚠️ На сервере не установлены: {', '.join(missing)}. "
            "Админ должен поставить ffmpeg и yt-dlp."
        )
        return ConversationHandler.END

    providers = _get_providers(context)
    if providers is None:
        await update.message.reply_text(
            "⚠️ /clips не настроен (нет transcribe/llm провайдеров). См. логи запуска."
        )
        return ConversationHandler.END

    context.user_data["clipper_state"] = ClipperState()
    await update.message.reply_text(
        "✂️ Нарезаю длинное видео на вертикальные шорты 9:16 с субтитрами.\n\n"
        "Как пришлёшь исходник?\n"
        "В любой момент /cancel.",
        reply_markup=_source_keyboard(),
    )
    return SOURCE


async def on_source_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CANCEL:
        return await _cancel_via_callback(update, context)

    if data == SOURCE_URL:
        await query.edit_message_text(
            "🔗 Пришли ссылку на видео (YouTube / Vimeo / прямой mp4).\n"
            "Поддерживается всё, что качает yt-dlp."
        )
        return WAIT_SOURCE

    if data == SOURCE_FILE:
        await query.edit_message_text(
            "📤 Загрузи видео-файл (≤20 МБ из-за лимита Telegram Bot API).\n"
            "Для длинных видео используй ссылку вместо файла."
        )
        return WAIT_SOURCE

    return SOURCE


# --- source ingestion ---------------------------------------------------


async def on_source_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not is_url(text):
        await update.message.reply_text(
            "Это не похоже на URL. Пришли ссылку http(s)://... или /cancel."
        )
        return WAIT_SOURCE

    state = _get_state(context)
    state.workdir = make_workdir()
    status = await update.message.reply_text("⏳ Скачиваю видео через yt-dlp...")

    try:
        state.source_video = await download_from_url(text, state.workdir)
    except Exception as e:  # noqa: BLE001
        logger.exception("yt-dlp download failed")
        await status.edit_text(f"⚠️ Не получилось скачать: {e}")
        _cleanup(state)
        return ConversationHandler.END

    await status.edit_text("✅ Видео скачано. Для какой платформы режем?")
    await update.message.reply_text("Выбери платформу:", reply_markup=_platform_keyboard())
    return PLATFORM


def _extract_video_attachment(msg):
    if msg.video:
        return msg.video
    if msg.video_note:
        return msg.video_note
    if msg.document and (msg.document.mime_type or "").startswith("video/"):
        return msg.document
    return None


async def on_source_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    attachment = _extract_video_attachment(msg)
    if attachment is None:
        await msg.reply_text("Нужен видео-файл. Пришли ещё раз или /cancel.")
        return WAIT_SOURCE

    size = getattr(attachment, "file_size", None)
    if size and size > FILE_SIZE_LIMIT:
        await msg.reply_text(
            f"⚠️ Файл {size // (1024 * 1024)} МБ — Telegram Bot API ограничен 20 МБ. "
            "Пришли ссылку вместо файла через /cancel → /clips."
        )
        return WAIT_SOURCE

    providers = _get_providers(context)
    if providers is None:
        await msg.reply_text("⚠️ Провайдеры не настроены.")
        return ConversationHandler.END

    state = _get_state(context)
    state.workdir = make_workdir()
    status = await msg.reply_text("⏳ Загружаю файл...")

    try:
        target = state.workdir / f"source_{attachment.file_unique_id}.mp4"
        state.source_video = await providers.download_attachment(context, attachment, target)
    except Exception as e:  # noqa: BLE001
        logger.exception("attachment download failed")
        await status.edit_text(f"⚠️ Ошибка загрузки: {e}")
        _cleanup(state)
        return ConversationHandler.END

    await status.edit_text("✅ Файл получен. Выбери платформу:")
    await msg.reply_text("Платформа:", reply_markup=_platform_keyboard())
    return PLATFORM


# --- platform / count ---------------------------------------------------


async def on_platform_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == CANCEL:
        return await _cancel_via_callback(update, context)

    key = query.data
    match = next((p for p in PLATFORMS if p[0] == key), None)
    if match is None:
        return PLATFORM

    state = _get_state(context)
    state.platform_key = key
    state.target_duration = match[2]

    await query.edit_message_text(
        f"Платформа: {match[1]}\n\nСколько клипов сделать?",
        reply_markup=_count_keyboard(),
    )
    return COUNT


async def on_count_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == CANCEL:
        return await _cancel_via_callback(update, context)

    try:
        count = int(query.data)
    except ValueError:
        return COUNT

    state = _get_state(context)
    state.count = count

    await query.edit_message_text(
        f"Клипов: {count}. Вжигать субтитры в видео?",
        reply_markup=_subtitles_keyboard(),
    )
    return SUBTITLES


async def on_subtitles_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == CANCEL:
        return await _cancel_via_callback(update, context)

    state = _get_state(context)
    state.burn_subtitles = query.data == SUBS_YES
    subs_label = "с субтитрами" if state.burn_subtitles else "без субтитров"

    await query.edit_message_text(
        f"⏳ Готовлю {state.count} клипов по ~{state.target_duration}с ({subs_label}). "
        "Это займёт несколько минут."
    )
    return await _run_pipeline(update, context)


# --- pipeline -----------------------------------------------------------


async def _run_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = _get_state(context)
    providers = _get_providers(context)
    chat = update.effective_chat

    if providers is None or state.source_video is None or state.workdir is None:
        await chat.send_message("⚠️ Состояние потеряно. Запусти /clips заново.")
        _cleanup(state)
        context.user_data.pop("clipper_state", None)
        return ConversationHandler.END

    status_msg = await chat.send_message("⏳ Стартую пайплайн...")

    async def progress(msg: str) -> None:
        try:
            await status_msg.edit_text(msg)
        except Exception:  # noqa: BLE001
            logger.debug("progress edit failed", exc_info=True)

    job = ClipJobInput(
        source_video=state.source_video,
        count=state.count,
        target_duration_sec=state.target_duration,
        burn_subtitles=state.burn_subtitles,
    )

    try:
        results = await run_clip_job(
            job,
            transcribe=providers.transcribe,
            llm=providers.llm,
            workdir=state.workdir,
            progress=progress,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("clip pipeline failed")
        await chat.send_message(f"⚠️ Ошибка пайплайна: {e}")
        _cleanup(state)
        context.user_data.pop("clipper_state", None)
        return ConversationHandler.END

    await status_msg.edit_text(f"✅ Готово: {len(results)} клипов. Отправляю...")
    for idx, result in enumerate(results, start=1):
        caption = _format_caption(idx, result)
        try:
            with open(result.path, "rb") as fh:
                await chat.send_video(video=fh, caption=caption, supports_streaming=True)
        except Exception:  # noqa: BLE001
            logger.exception("failed to send clip %s", result.path)
            await chat.send_message(f"⚠️ Не смог отправить клип {idx}.")

    _cleanup(state)
    context.user_data.pop("clipper_state", None)
    return ConversationHandler.END


def _format_caption(idx: int, result: ClipResult) -> str:
    h = result.highlight
    parts = [f"🎬 Клип {idx}: {h.title}"]
    if h.hook:
        parts.append(h.hook)
    parts.append(f"⏱ {h.start:.0f}s–{h.end:.0f}s")
    text = "\n\n".join(parts)
    return text[:1024]


# --- cancel -------------------------------------------------------------


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get("clipper_state")
    if state is not None:
        _cleanup(state)
    context.user_data.pop("clipper_state", None)
    await update.message.reply_text("Отменил. Запусти /clips снова, когда будешь готов.")
    return ConversationHandler.END


async def _cancel_via_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get("clipper_state")
    if state is not None:
        _cleanup(state)
    context.user_data.pop("clipper_state", None)
    await update.callback_query.edit_message_text("Отменил. /clips чтобы начать заново.")
    return ConversationHandler.END


# --- public builder -----------------------------------------------------


def build_clipper_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("clips", start_clips)],
        states={
            SOURCE: [CallbackQueryHandler(on_source_choice)],
            WAIT_SOURCE: [
                MessageHandler(
                    filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO,
                    on_source_file,
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_source_url),
            ],
            PLATFORM: [CallbackQueryHandler(on_platform_chosen)],
            COUNT: [CallbackQueryHandler(on_count_chosen)],
            SUBTITLES: [CallbackQueryHandler(on_subtitles_chosen)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="video_clipper",
        persistent=False,
    )
