# GliceMia — Quick Start

## 1. Install Dependencies

```bash
cd /Users/ccancellieri/work/code/diabete
source venv/bin/activate
pip install python-dotenv sqlalchemy "python-telegram-bot>=21.0" litellm matplotlib
```

## 2. Create `.env`

```bash
cp .env.example .env
```

Edit `.env` and set **at minimum**:

```env
# Required for Telegram bot
TELEGRAM_BOT_TOKEN=your_token_from_@BotFather

# Required for AI responses (pick one)
GEMINI_API_KEY=your_gemini_key          # Free at https://ai.google.dev
# or
ANTHROPIC_API_KEY=your_anthropic_key    # Claude API

# Optional: restrict bot access to specific Telegram user IDs
TELEGRAM_ALLOWED_USERS=123456789

# Patient name (default: Nuria)
PATIENT_NAME=Nuria
LANGUAGE=it
```

### How to get your Telegram user ID

1. Message `@userinfobot` on Telegram
2. It replies with your numeric user ID

### How to create a Telegram bot

1. Message `@BotFather` on Telegram
2. Send `/newbot`, follow prompts
3. Copy the token into `.env`

## 3. Seed Data

Import CareLink CSV files from `private/data/`:

```bash
python scripts/seed_demo.py
```

This will:
- Create the database (`glicemia.db`)
- Import glucose readings + bolus events from CSV files
- Seed patient profile + conditions
- Compute glucose patterns (hourly, daily, monthly)

## 4. Test Everything

```bash
python scripts/test_demo.py
```

Verifies all 10 components work: database, metrics, patterns, context, AI prompt, reports, estimator, alerts, i18n, AI call.

## 5. Start the Bot

```bash
python agent.py
```

Then open Telegram and message your bot:
- `/start` — Accept waiver, see main menu
- `/stato` — Current glucose status
- `/menu` — Full button menu
- Send a food photo — Get carb estimate + bolus suggestion
- Send text — Chat with GliceMia about diabetes management

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + waiver |
| `/menu` | Main menu with buttons |
| `/stato` / `/status` | Current glucose + pump status |
| `/help` / `/aiuto` | Help message |

## Button Menu

From `/menu`:
- **Stato attuale** — Live glucose, IOB, trend, predictions
- **Report** — Today / Week / Month with chart
- **Pianifica attivita** — GPS route planning with glucose prediction
- **Importa dati** — CareLink CSV, Apple Health ZIP, lab results PDF
- **Impostazioni** — Language, AI model
- **Aiuto** — Help

## Architecture

```
agent.py                    Entry point
app/
  config.py                 .env loader
  models.py                 14 SQLAlchemy tables (FHIR-based)
  database.py               SQLite with WAL mode
  ai/                       LiteLLM + system prompt + 12-layer context
  alerts/                   11 proactive alert types
  analytics/                Metrics (TIR/GMI/CV), patterns, estimator
  activity/                 Route planner, calories, weather, GPS tracker
  bot/                      Handlers, menus, food photo, voice
  carelink/                 CareLink client + CSV import
  chat/                     Telegram platform
  health/                   Apple Health, FHIR, lab analyzer, conditions
  i18n/                     IT/EN/ES/FR messages
  mcp/                      Claude Desktop MCP server (11 tools)
  reports/                  Text + chart report generator
scripts/
  seed_demo.py              Import CSV data + compute patterns
  test_demo.py              Test all components
```

## Data in Database

After seeding:
- **64,002 glucose readings** (Feb 2025 - Mar 2026)
- **1,233 bolus events**
- **41 pattern records** (24 hourly + daily + monthly)
- **Patient profile** with T1D condition (SNOMED: 46635009)

## Without Telegram (Testing AI Only)

```python
import asyncio
from app.database import init_db, get_session
from app.ai.llm import chat
from app.ai.system_prompt import build_system_prompt
from app.ai.context import build_context

init_db()
s = get_session()
ctx = build_context(s)
prompt = build_system_prompt("Nuria", "it", ctx)

response = asyncio.run(chat([
    {"role": "system", "content": prompt},
    {"role": "user", "content": "Come sto oggi?"},
]))
print(response)
```
