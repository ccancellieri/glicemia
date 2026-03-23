# GliceMia

**Open-Source T1D Intelligent Companion**

GliceMia is a personal diabetes management assistant for people with Type 1 Diabetes. It monitors CGM/pump data from Medtronic CareLink, provides AI-powered insights via Telegram, and gives actual bolus/glucose estimations with predicted values.

## Features

### Telegram Bot
- Real-time glucose status with trend arrows and predictions
- Inline keyboard menus (no copy/paste needed)
- Food photo analysis with carb estimation and bolus suggestion
- Voice message support (transcription + AI response)
- Activity planning with GPS routes, weather, calorie estimation, glucose prediction
- CareLink CSV import for historical data
- Apple Health ZIP import
- Lab results analysis from photos/PDFs
- Proactive alerts (11 types: low, high, predicted low, falling fast, etc.)
- Weekly/monthly reports with charts
- 4 languages: IT, EN, ES, FR

### Telegram Mini App (WebApp)
- Full dashboard with live glucose display, pump status, sparkline chart
- Interactive glucose charts (6h/12h/24h/3d/7d) with target range overlay
- Food camera: take photo or choose from gallery, get carb + bolus estimate
- Activity planner: choose type, duration, intensity, GPS start/end, get plan
- Reports: TIR bar, metrics cards, time-slot analysis
- Chat: talk to the AI with full glucose context
- Voice recording
- Bolus estimator and glucose predictor
- Patient profile and condition viewer
- Multilingual (IT/EN/ES/FR)

### AI Companion
- Pluggable AI via LiteLLM (Gemini, Claude, Ollama, GPT-4o, etc.)
- 12-layer context injection per message (current CGM, patterns, conditions, etc.)
- Own bolus/glucose estimations (never defers to "contact your doctor")
- Always shows final predicted glucose values
- Friendly personality that calls the patient by name

### Analytics
- TIR, GMI, CV, mean, std, bolus/day, carb stats
- Hourly/daily/monthly/yearly glucose patterns
- Time-slot analysis (night/day/evening) with recurring hypo/hyper detection
- Hypo episode analysis with preceding bolus context
- Dynamic I:C ratio and ISF from CareLink data

### MCP Server (Claude Desktop)
- 11 tools for deep analysis via Claude Desktop Pro
- get_status, get_history, get_patterns, get_metrics, get_conditions,
  get_observations, get_activities, estimate_bolus, predict_glucose,
  get_hypo_episodes, get_insulin_settings

### Data & Privacy
- FHIR-based schema (SNOMED CT, ICD, LOINC codes)
- SQLite with optional AES-256 encryption (SQLCipher)
- All patient data stays local (gitignored `private/` directory)
- GDPR compliant

## Quick Start

```bash
# 1. Install dependencies
source venv/bin/activate
pip install python-dotenv sqlalchemy "python-telegram-bot>=21.0" litellm matplotlib aiohttp

# 2. Configure
cp .env.example .env
# Edit .env: set TELEGRAM_BOT_TOKEN and GEMINI_API_KEY (minimum)

# 3. Seed data from CareLink CSVs
python scripts/seed_demo.py

# 4. Test all components
python scripts/test_demo.py

# 5. Start
python agent.py
```

See [SETUP.md](SETUP.md) for detailed instructions in IT/EN/ES/FR.

## Architecture

```
agent.py                    Entry point (async main loop)
app/
  config.py                 .env loader
  models.py                 14 SQLAlchemy tables (FHIR-based)
  database.py               SQLite + WAL mode
  ai/                       LiteLLM + system prompt + 12-layer context
    llm.py                  Pluggable AI (100+ models via LiteLLM)
    system_prompt.py        Personality + estimation rules
    context.py              12-layer context builder
  alerts/                   11 proactive alert types with cooldowns
    engine.py               Alert detection logic
    notifier.py             Multilingual alert formatting
  analytics/                Metrics, patterns, estimator
    metrics.py              TIR/GMI/CV computation
    patterns.py             Hourly/daily/monthly pattern engine
    estimator.py            Bolus estimation + glucose prediction
  activity/                 Route planner, calories, weather, GPS
    planner.py              OpenRouteService integration
    calories.py             MET/LCDA caloric formulas
    weather.py              OpenWeatherMap integration
    tracker.py              Activity lifecycle manager
  bot/                      Telegram bot handlers
    handlers.py             All message/callback handlers
    formatters.py           Data formatting for Telegram
    menus.py                Inline keyboard builders
    food.py                 Food photo analysis
    voice.py                Voice message transcription
  carelink/                 CareLink Cloud API + CSV import
    client.py               Real-time data poller
    parser.py               JSON parser
    csv_import.py           Historical CSV import
  chat/                     Chat platform abstraction
    platform.py             ABC
    telegram.py             Telegram implementation
  health/                   Health data connectors
    apple.py                Apple Health ZIP import
    fhir_client.py          FHIR server integration
    lab_analyzer.py         Lab result OCR + analysis
    conditions.py           SNOMED/ICD condition management
  i18n/                     Multilingual messages (IT/EN/ES/FR)
    messages.py             Message catalog
  mcp/                      Claude Desktop MCP server (11 tools)
    server.py               MCP tool definitions
  reports/                  Report generation
    generator.py            Text + PNG chart reports
  webapp/                   Telegram Mini App
    server.py               aiohttp web server
    api.py                  REST API (16 endpoints)
    auth.py                 Telegram initData HMAC validation
    index.html              Single-file Mini App (HTML+CSS+JS)
scripts/
  seed_demo.py              Import CSVs + seed profile + patterns
  test_demo.py              Test all 10 components
```

## How It Works

### Data Flow

```
CareLink Cloud ──(5min poll)──> DB ──> AI Context ──> Telegram Bot
                                │                      ↕
CareLink CSV ──(import)────────>│                  Mini App
                                │                      ↕
Apple Health ZIP ──(import)────>│                  REST API
                                │
Lab PDF/Photo ──(AI OCR)───────>│
```

1. **CareLink poller** fetches CGM/pump data every 5 minutes
2. **CSV import** loads historical data (months/years of glucose + bolus data)
3. **Pattern engine** computes hourly/daily/monthly aggregates on startup + daily at 04:00
4. **Alert engine** checks for dangerous situations after each poll
5. **Every message** to the AI includes 12 layers of context (current glucose, patterns, conditions, etc.)
6. **Mini App** provides a rich web UI via the same data API

### Telegram Bot Interaction

```
User sends /start
  → Waiver check → Accept → Main menu with buttons

User taps "Stato attuale"
  → Current glucose, trend, IOB, predictions

User sends food photo
  → AI analyzes: carbs breakdown, bolus suggestion, predicted glucose at 2h

User shares location for activity
  → Route, distance, elevation, calories, weather, glucose prediction, suggestions

User sends text message
  → AI responds with 12-layer context (patterns, conditions, insulin settings)
```

### Mini App (WebApp)

The Mini App runs inside Telegram as a WebApp:

| Tab | Features |
|-----|----------|
| Home | Live glucose, pump status, 3h sparkline, TIR, quick actions |
| Charts | Interactive glucose chart (6h-7d), hourly pattern bars |
| Food | Camera/gallery photo capture, AI carb analysis, bolus estimate |
| Activity | 8 activity types, duration/intensity sliders, GPS start/end, plan calculator |
| Reports | Period selector, TIR bar, metrics cards, slot analysis table |
| Chat | AI chat with full context, voice recording |
| Profile | Patient info, conditions, insulin settings |

To enable the Mini App:
```bash
# Start ngrok tunnel (free)
ngrok http 8443

# Add to .env
WEBAPP_URL=https://xxxx.ngrok-free.app/webapp
```

## Configuration

### Minimum Required

```env
TELEGRAM_BOT_TOKEN=...     # From @BotFather
GEMINI_API_KEY=...         # Free at ai.google.dev
```

### AI Models

| Model | Config | Cost |
|-------|--------|------|
| Gemini 2.5 Flash | `AI_MODEL=gemini/gemini-2.5-flash` | Free |
| Gemini 2.5 Pro | `AI_MODEL=gemini/gemini-2.5-pro` | Free (limited) |
| Claude Sonnet | `AI_MODEL=anthropic/claude-sonnet-4-20250514` | Paid |
| Ollama (local) | `AI_MODEL=ollama/llama3` | Free |
| GPT-4o | `AI_MODEL=openai/gpt-4o` | Paid |

### Optional APIs

| Service | Purpose | Free tier |
|---------|---------|-----------|
| OpenWeatherMap | Weather for activity planning | 1000 calls/day |
| OpenRouteService | Route/elevation calculation | 2000 calls/day |
| CareLink | Real-time CGM/pump data | Free (with 780G) |

## Deploy (Online)

Deploy GliceMia on Oracle Cloud Always Free (4 ARM cores, 24 GB RAM, Milan region, **free forever**).

See [DEPLOY.md](DEPLOY.md) for the full guide in IT/EN/ES/FR.

## License

Copyright (C) 2025-2026 Carlo Cancellieri

**AGPL-3.0** (open source, copyleft, attribution required)

Commercial/closed-source use requires a paid license. Contact: ccancellieri@gmail.com

See [LICENSE](LICENSE) and [NOTICE](NOTICE) for details.
