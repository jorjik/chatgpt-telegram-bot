"""Video-brief questionnaire: collects a structured brief from the user
(text idea OR reference video) before asking the LLM to produce a script/storyboard."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
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

# Conversation states
(
    SOURCE,
    WAIT_VIDEO,
    TOPIC,
    CONFIRM_TOPIC,
    PLATFORM,
    DURATION,
    FORMAT,
    STYLE,
    AUDIENCE,
) = range(9)

# Callback-data sentinels
SKIP = "__skip__"
CANCEL = "__cancel__"
SOURCE_TEXT = "__src_text__"
SOURCE_VIDEO = "__src_video__"
CONFIRM_YES = "__confirm_yes__"
CONFIRM_EDIT = "__confirm_edit__"

PLATFORMS: list[tuple[str, str]] = [
    ("youtube_shorts", "YouTube Shorts"),
    ("tiktok", "TikTok"),
    ("reels", "Instagram Reels"),
    ("youtube_long", "YouTube (длинное)"),
]

DURATIONS_BY_PLATFORM: dict[str, list[tuple[str, str]]] = {
    "youtube_shorts": [("15s", "15 сек"), ("30s", "30 сек"), ("60s", "60 сек")],
    "tiktok": [("15s", "15 сек"), ("30s", "30 сек"), ("60s", "60 сек"), ("180s", "до 3 мин")],
    "reels": [("15s", "15 сек"), ("30s", "30 сек"), ("60s", "60 сек"), ("90s", "90 сек")],
    "youtube_long": [("3m", "~3 мин"), ("5m", "~5 мин"), ("10m", "~10 мин"), ("20m_plus", "20+ мин")],
}

FORMATS: list[tuple[str, str]] = [
    ("educational", "🎓 Обучающий"),
    ("entertainment", "🎭 Развлекательный"),
    ("talking", "🗣 Разговорный / Talking"),
    ("news_review", "📰 Новостной / обзор"),
]

STYLES_BY_PLATFORM: dict[str, list[tuple[str, str]]] = {
    "youtube_shorts": [
        ("hook_punch", "Hook + панчлайн"),
        ("talking_head", "Talking head"),
        ("voice_over", "Voice over + b-roll"),
        ("meme", "Мем / тренд"),
    ],
    "tiktok": [
        ("trend", "Под тренд / звук"),
        ("pov", "POV"),
        ("tutorial_short", "Мини-туториал"),
        ("storytime", "Storytime"),
    ],
    "reels": [
        ("aesthetic", "Эстетика / lifestyle"),
        ("before_after", "Before / After"),
        ("talking_head", "Talking head"),
        ("product", "Продукт в кадре"),
    ],
    "youtube_long": [
        ("tutorial", "Туториал / разбор"),
        ("interview", "Интервью"),
        ("documentary", "Документальный"),
        ("vlog", "Влог"),
    ],
}


@dataclass
class Brief:
    topic: str = ""
    platform_key: str = ""
    platform_label: str = ""
    duration_key: str = ""
    duration_label: str = ""
    format_key: str = ""
    format_label: str = ""
    style_label: Optional[str] = None
    audience: Optional[str] = None
    source: str = "text"                    # "text" | "video"
    video_transcript: Optional[str] = None


@dataclass
class BriefProviders:
    """Container with the async callables /brief depends on.

    Injected via application.bot_data['brief_providers'] so video_brief stays
    decoupled from OpenAIHelper / AnthropicHelper."""
    # (ctx, attachment) -> transcript text
    transcribe: Optional[Callable[[ContextTypes.DEFAULT_TYPE, object], Awaitable[str]]]
    # (transcript) -> 2-3 sentence topic summary
    summarize_topic: Callable[[str], Awaitable[str]]
    # (system_prompt, user_prompt) -> final script text
    script: Callable[[str, str], Awaitable[str]]


# --- keyboards -----------------------------------------------------------


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def _source_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [("📝 Текстовая идея", SOURCE_TEXT)],
        [("🎞 Загрузить видео-референс", SOURCE_VIDEO)],
        [("❌ Отмена", CANCEL)],
    ])


def _platform_keyboard() -> InlineKeyboardMarkup:
    rows = [[(label, key)] for key, label in PLATFORMS]
    rows.append([("❌ Отмена", CANCEL)])
    return _kb(rows)


def _duration_keyboard(platform_key: str) -> InlineKeyboardMarkup:
    rows = [[(label, key)] for key, label in DURATIONS_BY_PLATFORM.get(platform_key, [])]
    rows.append([("❌ Отмена", CANCEL)])
    return _kb(rows)


def _format_keyboard() -> InlineKeyboardMarkup:
    rows = [[(label, key)] for key, label in FORMATS]
    rows.append([("❌ Отмена", CANCEL)])
    return _kb(rows)


def _style_keyboard(platform_key: str) -> InlineKeyboardMarkup:
    rows = [[(label, key)] for key, label in STYLES_BY_PLATFORM.get(platform_key, [])]
    rows.append([("⏭ Пропустить", SKIP)])
    rows.append([("❌ Отмена", CANCEL)])
    return _kb(rows)


def _skip_keyboard() -> InlineKeyboardMarkup:
    return _kb([[("⏭ Пропустить", SKIP)], [("❌ Отмена", CANCEL)]])


def _confirm_topic_keyboard() -> InlineKeyboardMarkup:
    return _kb([
        [("✅ Да", CONFIRM_YES)],
        [("✍️ Отредактировать", CONFIRM_EDIT)],
        [("❌ Отмена", CANCEL)],
    ])


# --- state helpers -------------------------------------------------------


def _get_brief(context: ContextTypes.DEFAULT_TYPE) -> Brief:
    brief = context.user_data.get("video_brief")
    if brief is None:
        brief = Brief()
        context.user_data["video_brief"] = brief
    return brief


def _get_providers(context: ContextTypes.DEFAULT_TYPE) -> Optional[BriefProviders]:
    return context.bot_data.get("brief_providers")


# --- entry / source branch ----------------------------------------------


async def start_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["video_brief"] = Brief()
    await update.message.reply_text(
        "🎬 Создаём бриф для видео. С чего начнём?\n\n"
        "В любой момент отправь /cancel, чтобы отменить.",
        reply_markup=_source_keyboard(),
    )
    return SOURCE


async def on_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CANCEL:
        return await _cancel_via_callback(update, context)

    if data == SOURCE_TEXT:
        await query.edit_message_text(
            "1/6 — О чём видео? Опиши тему или идею одним-двумя предложениями."
        )
        return TOPIC

    if data == SOURCE_VIDEO:
        providers = _get_providers(context)
        if providers is None or providers.transcribe is None:
            await query.edit_message_text(
                "⚠️ Транскрипция не настроена. Запусти /brief снова и выбери «📝 Текстовая идея»."
            )
            return ConversationHandler.END
        await query.edit_message_text(
            "🎞 Пришли видео-файл (mp4, video-note или документ-видео).\n"
            "Лимит: ~25 МБ. /cancel — отменить."
        )
        return WAIT_VIDEO

    return SOURCE


# --- video branch -------------------------------------------------------


def _extract_attachment(msg):
    if msg.video:
        return msg.video
    if msg.video_note:
        return msg.video_note
    if msg.document and (msg.document.mime_type or "").startswith("video/"):
        return msg.document
    return None


async def on_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    attachment = _extract_attachment(msg)
    if attachment is None:
        await msg.reply_text("Нужен именно видео-файл. Пришли ещё раз или /cancel.")
        return WAIT_VIDEO

    providers = _get_providers(context)
    if providers is None or providers.transcribe is None:
        await msg.reply_text("⚠️ Транскрипция не настроена. /cancel и начни заново.")
        return WAIT_VIDEO

    status = await msg.reply_text("⏳ Загружаю и транскрибирую видео...")

    try:
        transcript = await providers.transcribe(context, attachment)
    except Exception as e:  # noqa: BLE001
        logging.exception("video transcription failed")
        await status.edit_text(
            f"⚠️ Не получилось обработать видео: {e}\n\nПришли другой файл или /cancel."
        )
        return WAIT_VIDEO

    if not transcript or not transcript.strip():
        await status.edit_text(
            "⚠️ В видео не нашёл распознаваемой речи. Пришли другой файл или /cancel."
        )
        return WAIT_VIDEO

    brief = _get_brief(context)
    brief.source = "video"
    brief.video_transcript = transcript

    try:
        summary = await providers.summarize_topic(transcript)
    except Exception as e:  # noqa: BLE001
        logging.exception("topic summarization failed")
        await status.edit_text(f"⚠️ Не получилось сделать резюме: {e}")
        return WAIT_VIDEO

    brief.topic = summary.strip()

    await status.edit_text(
        f"📋 Предварительная тема из видео:\n\n{brief.topic}\n\nИспользовать как тему?",
        reply_markup=_confirm_topic_keyboard(),
    )
    return CONFIRM_TOPIC


async def on_confirm_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CANCEL:
        return await _cancel_via_callback(update, context)

    if data == CONFIRM_YES:
        await query.edit_message_text(
            f"Тема: {_get_brief(context).topic}\n\n2/6 — Для какой платформы?",
            reply_markup=_platform_keyboard(),
        )
        return PLATFORM

    if data == CONFIRM_EDIT:
        await query.edit_message_text(
            "Напиши уточнённую тему — одним-двумя предложениями."
        )
        return TOPIC

    return CONFIRM_TOPIC


# --- text topic ---------------------------------------------------------


async def on_topic_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Нужен непустой текст темы. Попробуй ещё раз или /cancel.")
        return TOPIC
    _get_brief(context).topic = text
    await update.message.reply_text(
        "2/6 — Для какой платформы?",
        reply_markup=_platform_keyboard(),
    )
    return PLATFORM


# --- platform / duration / format / style / audience -------------------


async def on_platform_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == CANCEL:
        return await _cancel_via_callback(update, context)

    platform_key = query.data
    label = dict(PLATFORMS).get(platform_key, platform_key)
    brief = _get_brief(context)
    brief.platform_key = platform_key
    brief.platform_label = label

    await query.edit_message_text(
        f"Платформа: {label}\n\n3/6 — Длительность?",
        reply_markup=_duration_keyboard(platform_key),
    )
    return DURATION


async def on_duration_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == CANCEL:
        return await _cancel_via_callback(update, context)

    brief = _get_brief(context)
    durations = dict(DURATIONS_BY_PLATFORM.get(brief.platform_key, []))
    brief.duration_key = query.data
    brief.duration_label = durations.get(query.data, query.data)

    await query.edit_message_text(
        f"Длительность: {brief.duration_label}\n\n4/6 — Формат подачи?",
        reply_markup=_format_keyboard(),
    )
    return FORMAT


async def on_format_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == CANCEL:
        return await _cancel_via_callback(update, context)

    brief = _get_brief(context)
    formats = dict(FORMATS)
    brief.format_key = query.data
    brief.format_label = formats.get(query.data, query.data)

    await query.edit_message_text(
        f"Формат: {brief.format_label}\n\n5/6 — Стиль подачи? (можно пропустить)",
        reply_markup=_style_keyboard(brief.platform_key),
    )
    return STYLE


async def on_style_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == CANCEL:
        return await _cancel_via_callback(update, context)

    brief = _get_brief(context)
    if data == SKIP:
        brief.style_label = None
        head = "Стиль: пропущено."
    else:
        styles = dict(STYLES_BY_PLATFORM.get(brief.platform_key, []))
        brief.style_label = styles.get(data, data)
        head = f"Стиль: {brief.style_label}"

    await query.edit_message_text(
        f"{head}\n\n6/6 — Целевая аудитория? (напиши или пропусти)",
        reply_markup=_skip_keyboard(),
    )
    return AUDIENCE


async def on_audience_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    _get_brief(context).audience = text or None
    return await _finalize(update, context)


async def on_audience_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == CANCEL:
        return await _cancel_via_callback(update, context)
    _get_brief(context).audience = None
    await query.edit_message_text("Целевая аудитория: пропущено.")
    return await _finalize(update, context, from_callback=True)


# --- render / finalize --------------------------------------------------


def _render_brief(brief: Brief) -> str:
    lines = [
        "📋 Бриф собран:",
        f"• Источник: {'видео-референс' if brief.source == 'video' else 'текст'}",
        f"• Тема: {brief.topic}",
        f"• Платформа: {brief.platform_label}",
        f"• Длительность: {brief.duration_label}",
        f"• Формат: {brief.format_label}",
    ]
    if brief.style_label:
        lines.append(f"• Стиль: {brief.style_label}")
    if brief.audience:
        lines.append(f"• Целевая аудитория: {brief.audience}")
    return "\n".join(lines)


def build_script_prompt(brief: Brief) -> tuple[str, str]:
    system_prompt = (
        "Ты — опытный сценарист коротких и длинных видео. "
        "По брифу собери подробный сценарий: hook/intro, раскадровку по сценам с таймкодами, "
        "текст закадрового голоса или реплики, описание визуала и монтажных склеек, "
        "заключительный CTA. Пиши на русском."
    )
    parts = [
        f"Тема: {brief.topic}",
        f"Платформа: {brief.platform_label}",
        f"Длительность: {brief.duration_label}",
        f"Формат подачи: {brief.format_label}",
    ]
    if brief.style_label:
        parts.append(f"Стиль подачи: {brief.style_label}")
    if brief.audience:
        parts.append(f"Целевая аудитория: {brief.audience}")

    user_prompt = "Бриф:\n" + "\n".join(parts)
    if brief.video_transcript:
        snippet = brief.video_transcript.strip()[:2000]
        user_prompt += f"\n\nРеференс-транскрипт (сжато):\n{snippet}"
    user_prompt += "\n\nСоздай сценарий видео."
    return system_prompt, user_prompt


async def _finalize(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    from_callback: bool = False,
) -> int:
    brief = _get_brief(context)
    summary = _render_brief(brief)
    reply_target = update.callback_query.message if from_callback else update.message

    await reply_target.reply_text(summary + "\n\n⏳ Генерирую сценарий...")

    providers = _get_providers(context)
    if providers is None:
        await reply_target.reply_text(
            "⚠️ LLM-провайдер не настроен. Бриф сохранён, сценарий не сгенерирован."
        )
        context.user_data.pop("video_brief", None)
        return ConversationHandler.END

    system_prompt, user_prompt = build_script_prompt(brief)
    try:
        script = await providers.script(system_prompt, user_prompt)
    except Exception as e:  # noqa: BLE001
        logging.exception("Failed to generate video script")
        await reply_target.reply_text(f"⚠️ Ошибка генерации: {e}")
        context.user_data.pop("video_brief", None)
        return ConversationHandler.END

    for chunk in _chunks(script, 3900):
        await reply_target.reply_text(chunk)

    context.user_data.pop("video_brief", None)
    return ConversationHandler.END


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


# --- cancel -------------------------------------------------------------


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("video_brief", None)
    await update.message.reply_text("Окей, отменил. Запусти /brief снова, когда будешь готов.")
    return ConversationHandler.END


async def _cancel_via_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("video_brief", None)
    await update.callback_query.edit_message_text(
        "Окей, отменил. Запусти /brief снова, когда будешь готов."
    )
    return ConversationHandler.END


# --- public handler builder --------------------------------------------


def build_video_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("brief", start_brief)],
        states={
            SOURCE: [CallbackQueryHandler(on_source)],
            WAIT_VIDEO: [
                MessageHandler(
                    filters.VIDEO
                    | filters.VIDEO_NOTE
                    | filters.Document.VIDEO,
                    on_video_upload,
                ),
                MessageHandler(filters.ALL & ~filters.COMMAND, on_video_upload),
            ],
            TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_topic_text)],
            CONFIRM_TOPIC: [CallbackQueryHandler(on_confirm_topic)],
            PLATFORM: [CallbackQueryHandler(on_platform_chosen)],
            DURATION: [CallbackQueryHandler(on_duration_chosen)],
            FORMAT: [CallbackQueryHandler(on_format_chosen)],
            STYLE: [CallbackQueryHandler(on_style_reply)],
            AUDIENCE: [
                CallbackQueryHandler(on_audience_skip, pattern=f"^({SKIP}|{CANCEL})$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, on_audience_text),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="video_brief",
        persistent=False,
    )
