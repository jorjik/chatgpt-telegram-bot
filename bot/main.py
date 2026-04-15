from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from pydub import AudioSegment

from plugin_manager import PluginManager
from openai_helper import OpenAIHelper, default_max_tokens, are_functions_available
from telegram_bot import ChatGPTTelegramBot
from video_brief import BriefProviders
from video_clipper import ClipperProviders
from clip_engine import Segment
from pathlib import Path


SUMMARIZE_SYSTEM_PROMPT = (
    "Ты помогаешь сценаристу. По транскрипту видео кратко сформулируй тему/идею "
    "ролика в 2–3 предложениях по-русски. Без преамбул и списков — связный текст."
)


def _build_text_provider(openai_helper: OpenAIHelper):
    """(system, user, user_id) -> str with optional usage footer. Provider picked via LLM_PROVIDER."""
    provider = os.environ.get('LLM_PROVIDER', 'openai').lower()

    if provider == 'anthropic':
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            logging.warning(
                'LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is missing; '
                'falling back to OpenAI for /brief text generation.'
            )
        else:
            from anthropic_helper import AnthropicConfig, AnthropicHelper
            helper = AnthropicHelper(AnthropicConfig(
                api_key=api_key,
                model=os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5'),
                max_tokens=int(os.environ.get('ANTHROPIC_MAX_TOKENS', '4096')),
            ))

            async def anthropic_provider(system: str, user: str, user_id: int | None = None) -> str:
                text, p_tok, c_tok = await helper.generate(system, user)
                footer = openai_helper._build_usage_footer(
                    user_id=user_id,
                    total_tokens=p_tok + c_tok,
                    prompt_tokens=p_tok,
                    completion_tokens=c_tok,
                )
                return text + footer

            return anthropic_provider

    async def openai_provider(system: str, user: str, user_id: int | None = None) -> str:
        response = await openai_helper.client.chat.completions.create(
            model=openai_helper.config['model'],
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ],
            max_tokens=openai_helper.config.get('max_tokens', 4096),
            temperature=openai_helper.config.get('temperature', 1.0),
        )
        text = response.choices[0].message.content.strip()
        usage = getattr(response, 'usage', None)
        p_tok = getattr(usage, 'prompt_tokens', 0) or 0
        c_tok = getattr(usage, 'completion_tokens', 0) or 0
        total = getattr(usage, 'total_tokens', p_tok + c_tok) or (p_tok + c_tok)
        footer = openai_helper._build_usage_footer(
            user_id=user_id,
            total_tokens=total,
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
        )
        return text + footer

    return openai_provider


def _build_brief_providers(openai_helper: OpenAIHelper) -> BriefProviders:
    """Assemble BriefProviders: Whisper transcription + LLM summarize + LLM script."""
    text_provider = _build_text_provider(openai_helper)

    async def transcribe(ctx, attachment) -> str:
        raw_path = f"{attachment.file_unique_id}.bin"
        mp3_path = f"{attachment.file_unique_id}.mp3"
        try:
            media_file = await ctx.bot.get_file(attachment.file_id)
            await media_file.download_to_drive(raw_path)
            audio = AudioSegment.from_file(raw_path)
            audio.export(mp3_path, format="mp3")
            return await openai_helper.transcribe(mp3_path)
        finally:
            for p in (raw_path, mp3_path):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    logging.warning("Failed to clean up %s", p)

    async def summarize_topic(transcript: str) -> str:
        snippet = transcript.strip()[:6000]
        return await text_provider(
            SUMMARIZE_SYSTEM_PROMPT,
            f"Транскрипт видео:\n{snippet}",
        )

    return BriefProviders(
        transcribe=transcribe,
        summarize_topic=summarize_topic,
        script=text_provider,
    )


def _build_clipper_providers(openai_helper: OpenAIHelper) -> ClipperProviders:
    """Transcription with word-level timestamps + LLM for highlight picking."""
    text_provider = _build_text_provider(openai_helper)

    async def transcribe_segments(audio_path: Path) -> list[Segment]:
        result = await openai_helper.transcribe_raw(str(audio_path), response_format="verbose_json")
        raw_segments = getattr(result, "segments", None) or []
        segments: list[Segment] = []
        for seg in raw_segments:
            start = getattr(seg, "start", None) if not isinstance(seg, dict) else seg.get("start")
            end = getattr(seg, "end", None) if not isinstance(seg, dict) else seg.get("end")
            text = getattr(seg, "text", None) if not isinstance(seg, dict) else seg.get("text")
            if start is None or end is None or not text:
                continue
            segments.append(Segment(start=float(start), end=float(end), text=str(text)))
        return segments

    async def download_attachment(ctx, attachment, target: Path) -> Path:
        media_file = await ctx.bot.get_file(attachment.file_id)
        await media_file.download_to_drive(str(target))
        return target

    return ClipperProviders(
        transcribe=transcribe_segments,
        llm=text_provider,
        download_attachment=download_attachment,
    )


def main():
    # Read .env file
    load_dotenv()

    # Setup logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Check if the required environment variables are set
    required_values = ['TELEGRAM_BOT_TOKEN', 'OPENAI_API_KEY']
    missing_values = [value for value in required_values if os.environ.get(value) is None]
    if len(missing_values) > 0:
        logging.error(f'The following environment values are missing in your .env: {", ".join(missing_values)}')
        exit(1)

    # Setup configurations
    model = os.environ.get('OPENAI_MODEL', 'gpt-4o')
    functions_available = are_functions_available(model=model)
    max_tokens_default = default_max_tokens(model=model)
    openai_config = {
        'api_key': os.environ['OPENAI_API_KEY'],
        'transcription_provider': os.environ.get('TRANSCRIPTION_PROVIDER', 'openai'),
        'transcription_model': os.environ.get('TRANSCRIPTION_MODEL', 'whisper-1'),
        'groq_api_key': os.environ.get('GROQ_API_KEY'),
        'groq_base_url': os.environ.get('GROQ_BASE_URL', 'https://api.groq.com/openai/v1'),
        'show_usage': os.environ.get('SHOW_USAGE', 'false').lower() == 'true',
        'stream': os.environ.get('STREAM', 'true').lower() == 'true',
        'proxy': os.environ.get('PROXY', None) or os.environ.get('OPENAI_PROXY', None),
        'max_history_size': int(os.environ.get('MAX_HISTORY_SIZE', 15)),
        'max_conversation_age_minutes': int(os.environ.get('MAX_CONVERSATION_AGE_MINUTES', 180)),
        'assistant_prompt': os.environ.get('ASSISTANT_PROMPT', 'You are a helpful assistant.'),
        'max_tokens': int(os.environ.get('MAX_TOKENS', max_tokens_default)),
        'n_choices': int(os.environ.get('N_CHOICES', 1)),
        'temperature': float(os.environ.get('TEMPERATURE', 1.0)),
        'image_model': os.environ.get('IMAGE_MODEL', 'dall-e-2'),
        'image_quality': os.environ.get('IMAGE_QUALITY', 'standard'),
        'image_style': os.environ.get('IMAGE_STYLE', 'vivid'),
        'image_size': os.environ.get('IMAGE_SIZE', '512x512'),
        'model': model,
        'enable_functions': os.environ.get('ENABLE_FUNCTIONS', str(functions_available)).lower() == 'true',
        'functions_max_consecutive_calls': int(os.environ.get('FUNCTIONS_MAX_CONSECUTIVE_CALLS', 10)),
        'presence_penalty': float(os.environ.get('PRESENCE_PENALTY', 0.0)),
        'frequency_penalty': float(os.environ.get('FREQUENCY_PENALTY', 0.0)),
        'bot_language': os.environ.get('BOT_LANGUAGE', 'ru'),
        'show_plugins_used': os.environ.get('SHOW_PLUGINS_USED', 'false').lower() == 'true',
        'whisper_prompt': os.environ.get('WHISPER_PROMPT', ''),
        'vision_model': os.environ.get('VISION_MODEL', 'gpt-4o'),
        'enable_vision_follow_up_questions': os.environ.get('ENABLE_VISION_FOLLOW_UP_QUESTIONS', 'true').lower() == 'true',
        'vision_prompt': os.environ.get('VISION_PROMPT', 'What is in this image'),
        'vision_detail': os.environ.get('VISION_DETAIL', 'auto'),
        'vision_max_tokens': int(os.environ.get('VISION_MAX_TOKENS', '300')),
        'tts_model': os.environ.get('TTS_MODEL', 'tts-1'),
        'tts_voice': os.environ.get('TTS_VOICE', 'alloy'),
        'admin_user_ids': os.environ.get('ADMIN_USER_IDS', '-'),
        'token_price': float(os.environ.get('TOKEN_PRICE', 0.002)),
    }

    if openai_config['enable_functions'] and not functions_available:
        logging.error(f'ENABLE_FUNCTIONS is set to true, but the model {model} does not support it. '
                        'Please set ENABLE_FUNCTIONS to false or use a model that supports it.')
        exit(1)
    if os.environ.get('MONTHLY_USER_BUDGETS') is not None:
        logging.warning('The environment variable MONTHLY_USER_BUDGETS is deprecated. '
                        'Please use USER_BUDGETS with BUDGET_PERIOD instead.')
    if os.environ.get('MONTHLY_GUEST_BUDGET') is not None:
        logging.warning('The environment variable MONTHLY_GUEST_BUDGET is deprecated. '
                        'Please use GUEST_BUDGET with BUDGET_PERIOD instead.')

    telegram_config = {
        'token': os.environ['TELEGRAM_BOT_TOKEN'],
        'admin_user_ids': os.environ.get('ADMIN_USER_IDS', '-'),
        'allowed_user_ids': os.environ.get('ALLOWED_TELEGRAM_USER_IDS', '*'),
        'enable_quoting': os.environ.get('ENABLE_QUOTING', 'true').lower() == 'true',
        'enable_image_generation': os.environ.get('ENABLE_IMAGE_GENERATION', 'true').lower() == 'true',
        'enable_transcription': os.environ.get('ENABLE_TRANSCRIPTION', 'true').lower() == 'true',
        'enable_vision': os.environ.get('ENABLE_VISION', 'true').lower() == 'true',
        'enable_tts_generation': os.environ.get('ENABLE_TTS_GENERATION', 'true').lower() == 'true',
        'budget_period': os.environ.get('BUDGET_PERIOD', 'monthly').lower(),
        'user_budgets': os.environ.get('USER_BUDGETS', os.environ.get('MONTHLY_USER_BUDGETS', '*')),
        'guest_budget': float(os.environ.get('GUEST_BUDGET', os.environ.get('MONTHLY_GUEST_BUDGET', '100.0'))),
        'stream': os.environ.get('STREAM', 'true').lower() == 'true',
        'proxy': os.environ.get('PROXY', None) or os.environ.get('TELEGRAM_PROXY', None),
        'voice_reply_transcript': os.environ.get('VOICE_REPLY_WITH_TRANSCRIPT_ONLY', 'false').lower() == 'true',
        'voice_reply_prompts': os.environ.get('VOICE_REPLY_PROMPTS', '').split(';'),
        'ignore_group_transcriptions': os.environ.get('IGNORE_GROUP_TRANSCRIPTIONS', 'true').lower() == 'true',
        'ignore_group_vision': os.environ.get('IGNORE_GROUP_VISION', 'true').lower() == 'true',
        'group_trigger_keyword': os.environ.get('GROUP_TRIGGER_KEYWORD', ''),
        'token_price': float(os.environ.get('TOKEN_PRICE', 0.002)),
        'image_prices': [float(i) for i in os.environ.get('IMAGE_PRICES', "0.016,0.018,0.02").split(",")],
        'vision_token_price': float(os.environ.get('VISION_TOKEN_PRICE', '0.01')),
        'image_receive_mode': os.environ.get('IMAGE_FORMAT', "photo"),
        'tts_model': os.environ.get('TTS_MODEL', 'tts-1'),
        'tts_prices': [float(i) for i in os.environ.get('TTS_PRICES', "0.015,0.030").split(",")],
        'transcription_price': float(os.environ.get('TRANSCRIPTION_PRICE', 0.006)),
        'bot_language': os.environ.get('BOT_LANGUAGE', 'ru'),
    }

    plugin_config = {
        'plugins': os.environ.get('PLUGINS', '').split(',')
    }

    # Setup and run ChatGPT and Telegram bot
    plugin_manager = PluginManager(config=plugin_config)
    openai_helper = OpenAIHelper(config=openai_config, plugin_manager=plugin_manager)
    brief_providers = _build_brief_providers(openai_helper)
    clipper_providers = _build_clipper_providers(openai_helper)
    telegram_bot = ChatGPTTelegramBot(
        config=telegram_config,
        openai=openai_helper,
        brief_providers=brief_providers,
        clipper_providers=clipper_providers,
    )
    telegram_bot.run()


if __name__ == '__main__':
    main()
