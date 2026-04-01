# GliceMia — Quick Start (Local Testing)

## Prerequisites

- **macOS** with Homebrew (or Linux with equivalent packages)
- **Python 3.11+**
- **Ollama** installed and running (`ollama serve`)
- A **Telegram account**

## Step 1: Install System Dependencies

```bash
# macOS
brew install sqlcipher

# Ollama (if not installed)
# Download from https://ollama.ai
```

## Step 2: Set Up Python Environment

```bash
cd /path/to/diabete
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `sqlcipher3` fails, install it separately:
```bash
LDFLAGS="-L$(brew --prefix sqlcipher)/lib" \
CPPFLAGS="-I$(brew --prefix sqlcipher)/include" \
pip install sqlcipher3
```

## Step 3: Pull AI Models into Ollama

```bash
# General-purpose model (14B, good for chat)
ollama pull qwen2.5:14b-instruct-q4_K_M

# Medical model (Diabetica-7B, specialized for diabetes)
# If you have the GGUF file + Modelfile in models/:
cd models && ollama create diabetica:7b -f Modelfile && cd ..

# Verify
ollama list
```

## Step 4: Create a Telegram Bot

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, choose a name (e.g. `GliceMia`) and username (e.g. `glicemia_test_bot`)
3. Copy the **token** (looks like `1234567890:AAH...`)

## Step 5: Find Your Telegram User ID

1. Search for **@userinfobot** on Telegram
2. Send any message — it replies with your numeric ID (e.g. `987654321`)

## Step 6: Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# === AI Backend (local Ollama) ===
AI_MODEL=ollama/qwen2.5:14b-instruct-q4_K_M
OLLAMA_API_BASE=http://localhost:11434

# Medical queries route to specialized Diabetica-7B (sovereign)
AI_MEDICAL_MODEL=ollama/diabetica:7b

# Fallback chain (optional — enable if you have API keys)
AI_FALLBACK_ENABLED=true
AI_TIMEOUT_SECONDS=60
# AI_FALLBACK_MODEL=gemini/gemini-2.5-flash

# === Telegram Bot ===
TELEGRAM_BOT_TOKEN=your_token_from_botfather
TELEGRAM_ALLOWED_USERS=your_telegram_id

# === Database ===
DB_PASSPHRASE=test_passphrase_change_in_production
DB_PATH=glicemia.db

# === Optional API Keys ===
# GEMINI_API_KEY=       # Free at https://ai.google.dev (enables cloud fallback)
# GROQ_API_KEY=         # Free at https://console.groq.com (GPU-fast inference)
# OPENROUTER_API_KEY=   # Free at https://openrouter.ai/keys (29 free models)
```

## Step 7: Start the Bot

```bash
source .venv/bin/activate
python agent.py
```

You should see:
```
Starting GliceMia...
Database tables initialized
Bootstrap admin seeded: tg_id=YOUR_ID
CareLink multi-patient poller started
Pattern scheduler started (daily at 04:00 UTC)
Telegram bot started and polling
GliceMia is running! Press Ctrl+C to stop.
```

## Step 8: Test in Telegram

### First-time Setup

1. Open your bot in Telegram
2. Send `/start` — Accept the **liability waiver**
3. Accept **GDPR consent** if prompted (needed for AI processing)

### Basic Chat (General AI)

Send a text message:
```
Ciao! Come funzioni?
```
This routes to your local Ollama model (qwen2.5:14b).

### Medical Query (Diabetica-7B Routing)

Send a diabetes-related message:
```
La mia glicemia e' 250 dopo pranzo, ho preso 4 unita' 2 ore fa. Cosa dovrei fare?
```
Watch the terminal — you'll see:
```
Medical query detected — routing to ollama/diabetica:7b
```

### Per-User Configuration

| Command | What it does |
|---------|-------------|
| `/settings` | View all your settings (name, language, AI model, CareLink, API keys) |
| `/carelink <email> <password> <country>` | Set your CareLink credentials (stored encrypted, message auto-deleted) |
| `/apikey gemini AIza...` | Set your personal Gemini API key |
| `/apikey groq gsk_...` | Set your personal Groq API key |
| `/apikey openrouter sk-or-...` | Set your personal OpenRouter API key |
| `/model ollama/qwen2.5:14b` | Choose your preferred AI model |

### Memory System

The bot **learns from your conversations** automatically. After chatting:

| Command | What it does |
|---------|-------------|
| `/memory` | See what the bot has learned about you |
| `/memory decision` | Filter by type: `decision`, `action`, `preference`, `health_insight`, `learned_fact` |
| `/forget 42` | Delete memory #42 |
| `/forget all` | Delete all memories |

### Import CareLink Data

**Option A**: Send a CareLink CSV file directly in Telegram chat — the bot imports it automatically.

**Option B**: If you have CSV files in `private/data/`:
```bash
python scripts/seed_demo.py
```

### All Commands

| Command | Alias (IT) | Description |
|---------|-----------|-------------|
| `/start` | | Welcome + waiver |
| `/menu` | | Main menu with buttons |
| `/status` | `/stato` | Current glucose, IOB, pump status |
| `/help` | `/aiuto` | Help guide |
| `/settings` | `/impostazioni` | User settings |
| `/carelink` | | Set CareLink credentials |
| `/apikey` | | Set per-user API keys |
| `/model` | `/modello` | Choose AI model |
| `/usage` | | Token usage counters |
| `/memory` | `/memoria` | View learned memories |
| `/forget` | `/dimentica` | Delete memories |
| `/privacy` | | GDPR consent management |

### What You Can Do

- **Send text** — AI responds with full glucose context (13 layers)
- **Send a food photo** — Carb estimate + bolus suggestion
- **Send a voice message** — Transcribed + AI response
- **Share GPS location** — Plan activity with route + glucose prediction
- **Send a CareLink CSV** — Import historical data
- **Send a lab PDF** — AI analyzes lab results

## Architecture (for Developers)

```
User sends message
    |
    v
handle_text() --> build_context() [13 layers including memories]
    |                  |
    v                  v
ai_chat()        build_system_prompt()
    |
    +-- Medical keywords? --> ollama/diabetica:7b (sovereign)
    |
    +-- General query ----> ollama/qwen2.5:14b (or user's model)
    |
    +-- Fallback chain ---> Groq -> OpenRouter -> Gemini
    |
    v
Save ChatMessage + extract_memories() [background]
    |
    v
Daily consolidation at 04:00 UTC (merge/prune memories)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot doesn't respond | Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` in `.env` |
| "Not registered" | Your Telegram ID must be in `TELEGRAM_ALLOWED_USERS` |
| AI timeout | Check Ollama is running: `ollama list` |
| Medical routing not working | Verify `AI_MEDICAL_MODEL=ollama/diabetica:7b` and model exists |
| `sqlcipher3` install fails | Run with brew flags: `LDFLAGS=... CPPFLAGS=... pip install sqlcipher3` |
| Memory extraction fails | Non-critical; bot works fine, memories just won't accumulate |
| No CareLink data | Use `/carelink` command or import CSV files |

## Next Steps

- **Add CareLink credentials**: `/carelink your_email your_password IT` in Telegram
- **Get a free Gemini key**: https://ai.google.dev — enables cloud fallback
- **Deploy to server**: See [DEPLOY.md](DEPLOY.md) for Contabo/cloud deployment
