# ChatGPT Telegram Bot

![python-version](https://img.shields.io/badge/python-3.9-blue.svg)
[![openai-version](https://img.shields.io/badge/openai-1.58.1-orange.svg)](https://openai.com/)
[![license](https://img.shields.io/badge/License-GPL%202.0-brightgreen.svg)](LICENSE)
[![Publish Docker image](https://github.com/n3d1117/chatgpt-telegram-bot/actions/workflows/publish.yaml/badge.svg)](https://github.com/n3d1117/chatgpt-telegram-bot/actions/workflows/publish.yaml)

A [Telegram bot](https://core.telegram.org/bots/api) that integrates with OpenAI's _official_ [ChatGPT](https://openai.com/blog/chatgpt/) APIs and Whisper-based transcription (OpenAI or Groq) to provide answers. Ready to use with minimal configuration required.

## Screenshots

### Demo

![demo](https://user-images.githubusercontent.com/11541888/225114786-0d639854-b3e1-4214-b49a-e51ce8c40387.png)

### Plugins

![plugins](https://github.com/n3d1117/chatgpt-telegram-bot/assets/11541888/83d5e0cd-e09a-463d-a292-722f919e929f)

## Features

- [x] Support markdown in answers
- [x] Reset conversation with the `/reset` command
- [x] Typing indicator while generating a response
- [x] Access can be restricted by specifying a list of allowed users
- [x] Docker and Proxy support
- [x] Transcribe audio and video messages using Whisper (OpenAI or Groq, may require [ffmpeg](https://ffmpeg.org))
- [x] Automatic conversation summary to avoid excessive token usage
- [x] Track token usage per user - by [@AlexHTW](https://github.com/AlexHTW)
- [x] User budgets and guest budgets - by [@AlexHTW](https://github.com/AlexHTW)
- [x] Stream support
- [x] GPT-4 support
  - If you have access to the GPT-4 API, simply change the `OPENAI_MODEL` parameter to `gpt-4`
- [x] Localized bot language
  - Available languages :brazil: :cn: :finland: :de: :indonesia: :iran: :it: :malaysia: :netherlands: :poland: :ru: :saudi_arabia: :es: :taiwan: :tr: :ukraine: :gb: :uzbekistan: :vietnam: :israel:
- [x] Improved inline queries support for group and private chats - by [@bugfloyd](https://github.com/bugfloyd)
  - To use this feature, enable inline queries for your bot in BotFather via the `/setinline` [command](https://core.telegram.org/bots/inline)
- [x] Support _new models_ [announced on June 13, 2023](https://openai.com/blog/function-calling-and-other-api-updates)
- [x] Support _functions_ (plugins) to extend the bot's functionality with 3rd party services
  - Weather, Spotify, Web search, text-to-speech and more. See [here](#available-plugins) for a list of available plugins
- [x] Support unofficial OpenAI-compatible APIs - by [@kristaller486](https://github.com/kristaller486)
- [x] (NEW!) Vision support [announced on November 6, 2023](https://platform.openai.com/docs/guides/vision) - by [@gilcu3](https://github.com/gilcu3)
- [x] (NEW!) GPT-4o model support [announced on May 12, 2024](https://openai.com/index/hello-gpt-4o/) - by [@err09r](https://github.com/err09r)
- [x] (NEW!) o1 and o1-mini model preliminary support
- [x] (NEW!) Guided video-brief questionnaire via the `/brief` command — collects topic, platform, duration (platform-dependent presets), delivery format, style, audience, and can ingest a reference video (Whisper transcript → auto topic summary) as input. Supports per-user templates: save the current brief as a template and reuse/override it on the next run.
- [x] (NEW!) Optional Anthropic (Claude) provider for `/brief` script generation via the `LLM_PROVIDER=anthropic` env var
- [x] (NEW!) Auto-clipping of long videos into vertical 9:16 shorts via `/clips` — Opus.pro-style highlight selection with Whisper + LLM, center-crop reframe, and **optional** burned-in subtitles (toggle in the flow)
- [x] (NEW!) Dedicated `/transcribe` command — walks the user through sending a voice/audio/video/video-note and returns a Whisper transcript

## Additional features - help needed

If you'd like to help, check out the [issues](https://github.com/n3d1117/chatgpt-telegram-bot/issues) section and contribute!  
If you want to help with translations, check out the [Translations Manual](https://github.com/n3d1117/chatgpt-telegram-bot/discussions/219)

PRs are always welcome!

## Prerequisites

- Python 3.9+
- A [Telegram bot](https://core.telegram.org/bots#6-botfather) and its token (see [tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token))
- An [OpenAI](https://openai.com) account (see [configuration](#configuration) section)

## Getting started

### Configuration

Customize the configuration by copying `.env.example` and renaming it to `.env`, then editing the required parameters as desired:

| Parameter                   | Description                                                                                                                                                                                                                   |
|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `OPENAI_API_KEY`            | Your OpenAI API key, you can get it from [here](https://platform.openai.com/account/api-keys)                                                                                                                                 |
| `TELEGRAM_BOT_TOKEN`        | Your Telegram bot's token, obtained using [BotFather](http://t.me/botfather) (see [tutorial](https://core.telegram.org/bots/tutorial#obtain-your-bot-token))                                                                  |
| `ADMIN_USER_IDS`            | Telegram user IDs of admins. These users have access to special admin commands, information and no budget restrictions. Admin IDs don't have to be added to `ALLOWED_TELEGRAM_USER_IDS`. **Note**: by default, no admin (`-`) |
| `ALLOWED_TELEGRAM_USER_IDS` | A comma-separated list of Telegram user IDs that are allowed to interact with the bot (use [getidsbot](https://t.me/getidsbot) to find your user ID). **Note**: by default, _everyone_ is allowed (`*`)                       |

### Optional configuration

The following parameters are optional and can be set in the `.env` file:

#### Budgets

| Parameter             | Description                                                                                                                                                                                                                                                                                                                                                                               | Default value      |
|-----------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------|
| `BUDGET_PERIOD`       | Determines the time frame all budgets are applied to. Available periods: `daily` _(resets budget every day)_, `monthly` _(resets budgets on the first of each month)_, `all-time` _(never resets budget)_. See the [Budget Manual](https://github.com/n3d1117/chatgpt-telegram-bot/discussions/184) for more information                                                                  | `monthly`          |
| `USER_BUDGETS`        | A comma-separated list of $-amounts per user from list `ALLOWED_TELEGRAM_USER_IDS` to set custom usage limit of OpenAI API costs for each. For `*`- user lists the first `USER_BUDGETS` value is given to every user. **Note**: by default, _no limits_ for any user (`*`). See the [Budget Manual](https://github.com/n3d1117/chatgpt-telegram-bot/discussions/184) for more information | `*`                |
| `GUEST_BUDGET`        | $-amount as usage limit for all guest users. Guest users are users in group chats that are not in the `ALLOWED_TELEGRAM_USER_IDS` list. Value is ignored if no usage limits are set in user budgets (`USER_BUDGETS`=`*`). See the [Budget Manual](https://github.com/n3d1117/chatgpt-telegram-bot/discussions/184) for more information                                                   | `100.0`            |
| `TOKEN_PRICE`         | $-price per 1000 tokens used to compute cost information in usage statistics. Source: <https://openai.com/pricing>                                                                                                                                                                                                                                                                          | `0.002`            |
| `TRANSCRIPTION_PRICE` | USD-price for one minute of audio transcription. Source: <https://openai.com/pricing>                                                                                                                                                                                                                                                                                                       | `0.006`            |
| `VISION_TOKEN_PRICE`  | USD-price per 1K tokens of image interpretation. Source: <https://openai.com/pricing>                                                                                                                                                                                                                                                                                                       | `0.01`             |

Check out the [Budget Manual](https://github.com/n3d1117/chatgpt-telegram-bot/discussions/184) for possible budget configurations.

#### Additional optional configuration options

| Parameter                           | Description                                                                                                                                                                                                                                                                             | Default value                      |
|-------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------|
| `ENABLE_QUOTING`                    | Whether to enable message quoting in private chats                                                                                                                                                                                                                                      | `true`                             |
| `ENABLE_TRANSCRIPTION`              | Whether to enable transcriptions of audio and video messages                                                                                                                                                                                                                            | `true`                             |
| `ENABLE_VISION`                     | Whether to enable vision capabilities in supported models                                                                                                                                                                                                                               | `true`                             |
| `PROXY`                             | Proxy to be used for OpenAI and Telegram bot (e.g. `http://localhost:8080`)                                                                                                                                                                                                             | -                                  |
| `OPENAI_PROXY`                      | Proxy to be used only for OpenAI (e.g. `http://localhost:8080`)                                                                                                                                                                                                                         | -                                  |
| `TELEGRAM_PROXY`                    | Proxy to be used only for Telegram bot (e.g. `http://localhost:8080`)                                                                                                                                                                                                                   | -                                  |
| `OPENAI_MODEL`                      | The OpenAI model to use for generating responses. You can find all available models [here](https://platform.openai.com/docs/models/)                                                                                                                                                    | `gpt-4o`                           |
| `OPENAI_BASE_URL`                   | Endpoint URL for unofficial OpenAI-compatible APIs (e.g., LocalAI or text-generation-webui)                                                                                                                                                                                             | Default OpenAI API URL             |
| `ASSISTANT_PROMPT`                  | A system message that sets the tone and controls the behavior of the assistant                                                                                                                                                                                                          | `You are a helpful assistant.`     |
| `SHOW_USAGE`                        | Показывать ли количество токенов под каждым ответом **всем** пользователям. Админы (`ADMIN_USER_IDS`) видят футер с токенами и ценой запроса независимо от этого флага.                                                                                                                 | `false`                            |
| `STREAM`                            | Whether to stream responses. **Note**: incompatible, if enabled, with `N_CHOICES` higher than 1                                                                                                                                                                                         | `true`                             |
| `MAX_TOKENS`                        | Upper bound on how many tokens the ChatGPT API will return                                                                                                                                                                                                                              | `1200` for GPT-3, `2400` for GPT-4 |
| `VISION_MAX_TOKENS`                 | Upper bound on how many tokens vision models will return                                                                                                                                                                                                                                | `300` for gpt-4o                   |
| `VISION_MODEL`                      | The Vision to Speech model to use. Allowed values: `gpt-4o`                                                                                                                                                                                                                             | `gpt-4o`                           |
| `ENABLE_VISION_FOLLOW_UP_QUESTIONS` | If true, once you send an image to the bot, it uses the configured VISION_MODEL until the conversation ends. Otherwise, it uses the OPENAI_MODEL to follow the conversation. Allowed values: `true` or `false`                                                                          | `true`                             |
| `MAX_HISTORY_SIZE`                  | Max number of messages to keep in memory, after which the conversation will be summarised to avoid excessive token usage                                                                                                                                                                | `15`                               |
| `MAX_CONVERSATION_AGE_MINUTES`      | Maximum number of minutes a conversation should live since the last message, after which the conversation will be reset                                                                                                                                                                 | `180`                              |
| `VOICE_REPLY_WITH_TRANSCRIPT_ONLY`  | Whether to answer to voice messages with the transcript only or with a ChatGPT response of the transcript                                                                                                                                                                               | `false`                            |
| `VOICE_REPLY_PROMPTS`               | A semicolon separated list of phrases (i.e. `Hi bot;Hello chat`). If the transcript starts with any of them, it will be treated as a prompt even if `VOICE_REPLY_WITH_TRANSCRIPT_ONLY` is set to `true`                                                                                 | -                                  |
| `VISION_PROMPT`                     | A phrase (i.e. `What is in this image`). The vision models use it as prompt to interpret a given image. If there is caption in the image sent to the bot, that supersedes this parameter                                                                                                | `What is in this image`            |
| `N_CHOICES`                         | Number of answers to generate for each input message. **Note**: setting this to a number higher than 1 will not work properly if `STREAM` is enabled                                                                                                                                    | `1`                                |
| `TEMPERATURE`                       | Number between 0 and 2. Higher values will make the output more random                                                                                                                                                                                                                  | `1.0`                              |
| `PRESENCE_PENALTY`                  | Number between -2.0 and 2.0. Positive values penalize new tokens based on whether they appear in the text so far                                                                                                                                                                        | `0.0`                              |
| `FREQUENCY_PENALTY`                 | Number between -2.0 and 2.0. Positive values penalize new tokens based on their existing frequency in the text so far                                                                                                                                                                   | `0.0`                              |
| `VISION_DETAIL`                     | The detail parameter for vision models, explained [Vision Guide](https://platform.openai.com/docs/guides/vision). Allowed values: `low` or `high`                                                                                                                                       | `auto`                             |
| `GROUP_TRIGGER_KEYWORD`             | If set, the bot in group chats will only respond to messages that start with this keyword                                                                                                                                                                                               | -                                  |
| `IGNORE_GROUP_TRANSCRIPTIONS`       | If set to true, the bot will not process transcriptions in group chats                                                                                                                                                                                                                  | `true`                             |
| `IGNORE_GROUP_VISION`               | If set to true, the bot will not process vision queries in group chats                                                                                                                                                                                                                  | `true`                             |
| `BOT_LANGUAGE`                      | Language of general bot messages. Currently available: `en`, `de`, `ru`, `tr`, `it`, `fi`, `es`, `id`, `nl`, `zh-cn`, `zh-tw`, `vi`, `fa`, `pt-br`, `uk`, `ms`, `uz`, `ar`.  [Contribute with additional translations](https://github.com/n3d1117/chatgpt-telegram-bot/discussions/219) | `en`                               |
| `TRANSCRIPTION_PROVIDER`            | Provider used for speech-to-text. Supported values: `openai` or `groq`. If `groq` is set but `GROQ_API_KEY` is missing, the bot falls back to OpenAI transcription.                                                                                                              | `openai`                           |
| `TRANSCRIPTION_MODEL`               | Transcription model name passed to the configured provider (e.g. `whisper-1` for OpenAI, `whisper-large-v3-turbo` for Groq).                                                                                                                                      | `whisper-1`                        |
| `GROQ_API_KEY`                      | Groq API key. Required only when `TRANSCRIPTION_PROVIDER=groq`.                                                                                                                                                                                                   | `-`                                |
| `GROQ_BASE_URL`                     | Groq OpenAI-compatible base URL for transcription requests.                                                                                                                                                                                                        | `https://api.groq.com/openai/v1`   |
| `WHISPER_PROMPT`                    | To improve transcription accuracy for specific names or terms, you can set up a custom prompt message. [Speech to text - Prompting](https://platform.openai.com/docs/guides/speech-to-text/prompting)                                                                          | `-`                                |

Check out the [official API reference](https://platform.openai.com/docs/api-reference/chat) for more details.

#### Functions

| Parameter                         | Description                                                                                                                                      | Default value                       |
|-----------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------|
| `ENABLE_FUNCTIONS`                | Whether to use functions (aka plugins). You can read more about functions [here](https://openai.com/blog/function-calling-and-other-api-updates) | `true` (if available for the model) |
| `FUNCTIONS_MAX_CONSECUTIVE_CALLS` | Maximum number of back-to-back function calls to be made by the model in a single response, before displaying a user-facing message              | `10`                                |
| `PLUGINS`                         | List of plugins to enable (see below for a full list), e.g: `PLUGINS=wolfram,weather`                                                            | -                                   |
| `SHOW_PLUGINS_USED`               | Whether to show which plugins were used for a response                                                                                           | `false`                             |

#### Available plugins

| Name                      | Description                                                                                                                                         | Required environment variable(s)                                     | Dependency          |
|---------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|---------------------|
| `weather`                 | Daily weather and 7-day forecast for any location (powered by [Open-Meteo](https://open-meteo.com))                                                 | -                                                                    |                     |
| `wolfram`                 | WolframAlpha queries (powered by [WolframAlpha](https://www.wolframalpha.com))                                                                      | `WOLFRAM_APP_ID`                                                     | `wolframalpha`      |
| `ddg_web_search`          | Web search (powered by [DuckDuckGo](https://duckduckgo.com))                                                                                        | -                                                                    | `duckduckgo_search` |
| `ddg_image_search`        | Search image or GIF (powered by [DuckDuckGo](https://duckduckgo.com))                                                                               | -                                                                    | `duckduckgo_search` |
| `crypto`                  | Live cryptocurrencies rate (powered by [CoinCap](https://coincap.io)) - by [@stumpyfr](https://github.com/stumpyfr)                                 | -                                                                    |                     |
| `spotify`                 | Spotify top tracks/artists, currently playing song and content search (powered by [Spotify](https://spotify.com)). Requires one-time authorization. | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI` | `spotipy`           |
| `worldtimeapi`            | Get latest world time (powered by [WorldTimeAPI](https://worldtimeapi.org/)) - by [@noriellecruz](https://github.com/noriellecruz)                  | `WORLDTIME_DEFAULT_TIMEZONE`                                         |                     |
| `dice`                    | Send a dice in the chat!                                                                                                                            | -                                                                    |                     |
| `youtube_audio_extractor` | Extract audio from YouTube videos                                                                                                                   | -                                                                    | `pytube`            |
| `deepl_translate`         | Translate text to any language (powered by [DeepL](https://deepl.com)) - by [@LedyBacer](https://github.com/LedyBacer)                              | `DEEPL_API_KEY`                                                      |                     |
| `gtts_text_to_speech`     | Text to speech (powered by Google Translate APIs)                                                                                                   | -                                                                    | `gtts`              |
| `whois`                   | Query the whois domain database - by [@jnaskali](https://github.com/jnaskali)                                                                       | -                                                                    | `whois`             |
| `webshot`                 | Screenshot a website from a given url or domain name - by [@noriellecruz](https://github.com/noriellecruz)                                          | -                                                                    |                     |
| `auto_tts`                | Text to speech using OpenAI APIs - by [@Jipok](https://github.com/Jipok)                                                                            | -                                                                    |                     |

#### Environment variables

| Variable                          | Description                                                                                                                                                                                     | Default value                       |
|-----------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------|
| `WOLFRAM_APP_ID`                  | Wolfram Alpha APP ID (required only for the `wolfram` plugin, you can get one [here](https://products.wolframalpha.com/simple-api/documentation))                                               | -                                   |
| `SPOTIFY_CLIENT_ID`               | Spotify app Client ID (required only for the `spotify` plugin, you can find it on the [dashboard](https://developer.spotify.com/dashboard/))                                                    | -                                   |
| `SPOTIFY_CLIENT_SECRET`           | Spotify app Client Secret (required only for the `spotify` plugin, you can find it on the [dashboard](https://developer.spotify.com/dashboard/))                                                | -                                   |
| `SPOTIFY_REDIRECT_URI`            | Spotify app Redirect URI (required only for the `spotify` plugin, you can find it on the [dashboard](https://developer.spotify.com/dashboard/))                                                 | -                                   |
| `WORLDTIME_DEFAULT_TIMEZONE`      | Default timezone to use, i.e. `Europe/Rome` (required only for the `worldtimeapi` plugin, you can get TZ Identifiers from [here](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)) | -                                   |
| `DUCKDUCKGO_SAFESEARCH`           | DuckDuckGo safe search (`on`, `off` or `moderate`) (optional, applies to `ddg_web_search` and `ddg_image_search`)                                                                               | `moderate`                          |
| `DEEPL_API_KEY`                   | DeepL API key (required for the `deepl` plugin, you can get one [here](https://www.deepl.com/pro-api?cta=header-pro-api))                                                                       | -                                   |

### Admin privileges (`ADMIN_USER_IDS`)

Пользователи, чьи Telegram ID перечислены через запятую в переменной `ADMIN_USER_IDS`, получают в этом боте расширенные права:

- **Полный доступ к боту без добавления в whitelist.** Админам не нужно быть в `ALLOWED_TELEGRAM_USER_IDS` — они считаются разрешёнными автоматически и могут пользоваться всеми командами (`/chat`, `/brief`, `/clips`, `/transcribe`, `/reset`, а также свободным общением с моделью).
- **Обход бюджетных ограничений.** На админов не распространяются лимиты `USER_BUDGETS`, `GUEST_BUDGET` и период `BUDGET_PERIOD` — они могут расходовать OpenAI/Anthropic API без учёта квот.
- **Получение запросов на доступ от гостей.** Когда незнакомый пользователь обращается к боту в групповом чате и попадает в гостевой бюджет, уведомление уходит первому админу из списка `ADMIN_USER_IDS`.
- **Счётчик токенов и стоимости под каждым ответом.** После каждого ответа бота админ видит футер вида `💰 134 tokens (88 prompt, 46 completion) · ~$0.000268`. Стоимость рассчитывается из `TOKEN_PRICE` (для текстовых ответов) или `VISION_TOKEN_PRICE` (для интерпретации изображений). Обычные пользователи этот футер не видят, если не включён `SHOW_USAGE=true` — в этом случае им показывается только количество токенов без цены.

Отдельных админ-команд (ban, broadcast, управление пользователями) в боте нет — права сводятся к перечисленному выше. Если `ADMIN_USER_IDS=-` (значение по умолчанию), админов в системе нет.

### Video brief (`/brief`)

The `/brief` command walks the user through a short questionnaire and then asks an LLM to produce a full video script (hook, scene-by-scene storyboard with timecodes, voice-over, CTA).

Flow:

1. **Source** — start from a text idea **or** upload a reference video (mp4 / video-note / video document).
2. If a video is uploaded, the bot extracts audio via `pydub`, transcribes it with Whisper, auto-summarises the topic in 2–3 sentences, and asks you to confirm or edit it.
3. **Platform** (YouTube Shorts / TikTok / Reels / YouTube long).
4. **Duration** — inline presets that depend on the chosen platform (e.g. 15/30/60 s for Shorts, 3/5/10/20+ min for YouTube long).
5. **Format** _(required, buttons)_ — Educational / Entertainment / Talking / News-Review.
6. **Style** _(optional, buttons)_ — platform-specific style options + Skip.
7. **Target audience** _(optional, free text)_ — or Skip.

#### Templates

At the start of `/brief` you can save the answers from a previous run as a per-user template and reuse them next time:

- **Use template** — skip the questionnaire; you'll only need to confirm / edit the topic. Available once a template has been saved.
- **Create template** — the bot will remember your current brief answers (platform, duration, format, style, audience) under `memory/<telegram_user_id>.md`. Re-selecting this overwrites the existing template.
- **Create from scratch** — ignore the saved template for this run.

Send `/cancel` at any point to abort.

#### Environment variables

| Variable              | Description                                                                                                                                                                          | Default value       |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------|
| `LLM_PROVIDER`        | Which provider generates the topic summary and final script for `/brief`. Set to `anthropic` to use Claude; any other value uses OpenAI. Transcription uses `TRANSCRIPTION_PROVIDER`. | `openai`            |
| `ANTHROPIC_API_KEY`   | Anthropic API key. Required when `LLM_PROVIDER=anthropic`; if missing, `/brief` falls back to OpenAI.                                                                                | -                   |
| `ANTHROPIC_MODEL`     | Claude model to use for `/brief`.                                                                                                                                                    | `claude-sonnet-4-5` |
| `ANTHROPIC_MAX_TOKENS`| Max tokens for Claude responses.                                                                                                                                                     | `4096`              |

`LLM_PROVIDER` affects only `/brief` and `/clips` text generation. Regular chat and vision continue to use OpenAI models configured via `OPENAI_MODEL`/`VISION_MODEL`, while transcription follows `TRANSCRIPTION_PROVIDER`.

### Transcription (`/transcribe`)

The `/transcribe` command is a guided wrapper around the existing Whisper media handler:

1. Send `/transcribe` — the bot replies with a prompt to send a voice / audio / video / video-note message.
2. Send the media; the bot extracts audio via `pydub`, sends it to the configured transcription provider (`openai` or `groq`), and replies with the transcript.
3. Works in private chats out of the box. In groups it follows `IGNORE_GROUP_TRANSCRIPTIONS`.

Toggle the whole feature with `ENABLE_TRANSCRIPTION`; tune Whisper accuracy via `WHISPER_PROMPT`.

### Auto-clips from long videos (`/clips`)

The `/clips` command turns a long video (podcast, lecture, stream, interview) into several vertical 9:16 short clips with burned-in captions — similar to opus.pro, fully inside Telegram.

Flow:

1. **Source** — paste a URL (YouTube / Vimeo / direct mp4, anything `yt-dlp` can fetch) **or** upload a video file up to 20 MB (Telegram Bot API hard limit; use URLs for long videos).
2. **Platform** (buttons) — TikTok (30 s) / Instagram Reels (30 s) / YouTube Shorts (45 s). Determines the target clip length.
3. **Count** (buttons) — 3 / 5 / 10 clips.
4. **Subtitles** (buttons) — burn SRT subtitles into each clip or render without them.
5. The bot extracts audio, transcribes with the configured transcription provider (`verbose_json` with timestamps), asks the LLM (OpenAI or Anthropic, same `LLM_PROVIDER` env as `/brief`) to pick the best self-contained highlights, then for each highlight runs a single `ffmpeg` pass that cuts the range, center-crops to 9:16 @ 1080×1920, and (optionally) burns SRT subtitles with a classic white + black-outline style.
6. Finished clips are sent back one-by-one with title + hook + timecodes.

Send `/cancel` at any point to abort; the temp workdir is cleaned up.

#### System dependencies

Both binaries must be available on `PATH`:

- `ffmpeg` (already required transitively by `pydub` for `/brief`, but `/clips` depends on it explicitly for cutting/reframing/subtitles)
- `yt-dlp` — for downloading from URLs. Installed via `requirements.txt` as a Python package that also exposes the `yt-dlp` CLI.

On Ubuntu/Debian: `apt install ffmpeg`. On macOS: `brew install ffmpeg`. On Windows: grab a static build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add it to `PATH`.

#### Known limits (MVP)

- No face-tracking auto-reframe — center-crop only. If the speaker stands to the side, they may be partially cropped.
- 25 MB Whisper limit on the extracted audio — the bot downmixes to mono 16 kHz @ 64 kbps mp3, which covers ~30 min of source video. Longer videos may fail transcription.
- Telegram Bot API 20 MB upload limit applies to file uploads; use URLs for anything longer than ~2–3 min HD.
- Processing is inline (no job queue): while `/clips` is running, the bot still handles other messages, but the clipping itself may take several minutes.

### Installing

Clone the repository and navigate to the project directory:

```shell
git clone https://github.com/n3d1117/chatgpt-telegram-bot.git
cd chatgpt-telegram-bot
```

#### From Source

1. Create a virtual environment:

```shell
python -m venv venv
```

1. Activate the virtual environment:

```shell
# For Linux or macOS:
source venv/bin/activate

# For Windows:
venv\Scripts\activate
```

1. Install the dependencies using `requirements.txt` file:

```shell
pip install -r requirements.txt
```

1. Use the following command to start the bot:

```
python bot/main.py
```

#### Using Docker Compose

Run the following command to build and run the Docker image:

```shell
docker compose up
```

#### Ready-to-use Docker images

You can also use the Docker image from [Docker Hub](https://hub.docker.com/r/n3d1117/chatgpt-telegram-bot):

```shell
docker pull n3d1117/chatgpt-telegram-bot:latest
docker run -it --env-file .env n3d1117/chatgpt-telegram-bot
```

or using the [GitHub Container Registry](https://github.com/n3d1117/chatgpt-telegram-bot/pkgs/container/chatgpt-telegram-bot/):

```shell
docker pull ghcr.io/n3d1117/chatgpt-telegram-bot:latest
docker run -it --env-file .env ghcr.io/n3d1117/chatgpt-telegram-bot
```

#### Docker manual build

```shell
docker build -t chatgpt-telegram-bot .
docker run -it --env-file .env chatgpt-telegram-bot
```

#### Heroku

Here is an example of `Procfile` for deploying using Heroku (thanks [err09r](https://github.com/err09r)!):

```
worker: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && python bot/main.py
```

## Credits

- [ChatGPT](https://chat.openai.com/chat) from [OpenAI](https://openai.com)
- [python-telegram-bot](https://python-telegram-bot.org)
- [jiaaro/pydub](https://github.com/jiaaro/pydub)

## Disclaimer

This is a personal project and is not affiliated with OpenAI in any way.

## License

This project is released under the terms of the GPL 2.0 license. For more information, see the [LICENSE](LICENSE) file included in the repository.
