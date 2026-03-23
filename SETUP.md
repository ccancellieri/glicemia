# GliceMia — Setup Guide

> [Italiano](#-italiano) | [English](#-english) | [Espanol](#-español) | [Francais](#-français)

---

## Italiano

### Prerequisiti

- Python 3.11+ installato
- Un account Telegram
- Connessione internet

### Passo 1: Crea il bot Telegram

1. Apri Telegram e cerca **@BotFather**
2. Invia `/newbot`
3. Scegli un nome per il bot: es. `GliceMia`
4. Scegli un username: es. `glicemia_nuria_bot` (deve finire con `bot`)
5. BotFather risponde con un **token** — copialo e conservalo

### Passo 2: Trova il tuo ID Telegram

1. Cerca **@userinfobot** su Telegram
2. Invia un messaggio qualsiasi
3. Ti risponde con il tuo **ID numerico** (es. `987654321`)
4. Ripeti per ogni persona che deve usare il bot

### Passo 3: Ottieni la chiave API Gemini (gratuita)

1. Vai su https://ai.google.dev
2. Accedi con il tuo account Google
3. Clicca "Get API key" o "Crea chiave API"
4. Copia la chiave (inizia con `AIzaSy...`)

### Passo 4: Installa le dipendenze

```bash
cd /Users/ccancellieri/work/code/diabete
source venv/bin/activate
pip install python-dotenv sqlalchemy "python-telegram-bot>=21.0" litellm matplotlib
```

### Passo 5: Configura il file `.env`

Copia il template:

```bash
cp .env.example .env
```

Apri `.env` e modifica queste righe con i tuoi valori reali:

```env
# Chiave Gemini (gratuita da ai.google.dev)
GEMINI_API_KEY=AIzaSy...la_tua_chiave...

# Token del bot Telegram (da @BotFather)
TELEGRAM_BOT_TOKEN=7123456789:AAH...il_tuo_token...

# ID Telegram autorizzati (separati da virgola)
# Metti l'ID di Nuria e il tuo
TELEGRAM_ALLOWED_USERS=987654321,123456789

# Nome della paziente
PATIENT_NAME=Nuria

# Lingua
LANGUAGE=it
```

Le altre impostazioni sono opzionali per il primo avvio:
- `CARELINK_*` — servono solo se hai le credenziali CareLink attive
- `OPENWEATHER_API_KEY` — serve per le previsioni meteo nelle attivita
- `ORS_API_KEY` — serve per la pianificazione percorsi
- `DB_PASSPHRASE` — cambiala con una passphrase sicura per criptare il database

### Passo 6: Importa i dati e avvia

```bash
# Importa i CSV di CareLink e calcola i pattern
python scripts/seed_demo.py

# Verifica che tutto funzioni
python scripts/test_demo.py

# Avvia il bot
python agent.py
```

### Passo 7: Usa il bot

1. Apri Telegram e cerca il nome del tuo bot
2. Invia `/start`
3. Accetta il consenso informato
4. Usa il menu con i pulsanti:
   - **Stato attuale** — glicemia, IOB, trend, previsioni
   - **Report** — oggi / settimana / mese con grafico
   - **Pianifica attivita** — percorsi GPS con previsione glicemica
   - **Importa dati** — CSV CareLink, ZIP Apple Health, PDF esami
   - **Impostazioni** — lingua, modello AI

### Comandi disponibili

| Comando | Descrizione |
|---------|-------------|
| `/start` | Benvenuto + consenso |
| `/menu` | Menu principale |
| `/stato` | Stato glicemia attuale |
| `/aiuto` | Guida |

### Cosa puoi fare

- **Scrivi un messaggio** — GliceMia risponde con contesto glicemico completo
- **Manda una foto di cibo** — stima carboidrati + suggerimento bolo
- **Manda un messaggio vocale** — trascritto e analizzato
- **Condividi la posizione** — pianifica attivita con percorso e previsione
- **Manda un CSV** — importa dati CareLink
- **Manda un PDF** — analizza risultati esami di laboratorio

### Risoluzione problemi

| Problema | Soluzione |
|----------|----------|
| Il bot non risponde | Verifica `TELEGRAM_BOT_TOKEN` in `.env` |
| "Non autorizzato" | Aggiungi il tuo ID in `TELEGRAM_ALLOWED_USERS` |
| Errore AI | Verifica `GEMINI_API_KEY` in `.env` |
| Nessun dato | Esegui `python scripts/seed_demo.py` |
| Import CSV fallisce | Verifica che i file CSV siano in `private/data/` |

---

## English

### Prerequisites

- Python 3.11+ installed
- A Telegram account
- Internet connection

### Step 1: Create the Telegram bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name: e.g. `GliceMia`
4. Choose a username: e.g. `glicemia_nuria_bot` (must end with `bot`)
5. BotFather replies with a **token** — copy and save it

### Step 2: Find your Telegram user ID

1. Search for **@userinfobot** on Telegram
2. Send any message
3. It replies with your **numeric ID** (e.g. `987654321`)
4. Repeat for each person who needs to use the bot

### Step 3: Get a Gemini API key (free)

1. Go to https://ai.google.dev
2. Sign in with your Google account
3. Click "Get API key"
4. Copy the key (starts with `AIzaSy...`)

### Step 4: Install dependencies

```bash
cd /Users/ccancellieri/work/code/diabete
source venv/bin/activate
pip install python-dotenv sqlalchemy "python-telegram-bot>=21.0" litellm matplotlib
```

### Step 5: Configure `.env`

Copy the template:

```bash
cp .env.example .env
```

Open `.env` and set these values:

```env
# Gemini key (free from ai.google.dev)
GEMINI_API_KEY=AIzaSy...your_key...

# Telegram bot token (from @BotFather)
TELEGRAM_BOT_TOKEN=7123456789:AAH...your_token...

# Authorized Telegram user IDs (comma-separated)
TELEGRAM_ALLOWED_USERS=987654321,123456789

# Patient name
PATIENT_NAME=Nuria

# Language
LANGUAGE=en
```

Other settings are optional for first run:
- `CARELINK_*` — only needed with active CareLink credentials
- `OPENWEATHER_API_KEY` — needed for weather in activity planning
- `ORS_API_KEY` — needed for route planning
- `DB_PASSPHRASE` — change to a strong passphrase to encrypt the database

### Step 6: Import data and start

```bash
# Import CareLink CSVs and compute patterns
python scripts/seed_demo.py

# Verify everything works
python scripts/test_demo.py

# Start the bot
python agent.py
```

### Step 7: Use the bot

1. Open Telegram and search for your bot's name
2. Send `/start`
3. Accept the liability waiver
4. Use the button menu:
   - **Current status** — glucose, IOB, trend, predictions
   - **Report** — today / week / month with chart
   - **Plan activity** — GPS routes with glucose prediction
   - **Import data** — CareLink CSV, Apple Health ZIP, lab PDF
   - **Settings** — language, AI model

### Available commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + waiver |
| `/menu` | Main menu |
| `/status` | Current glucose status |
| `/help` | Help guide |

### What you can do

- **Send a text message** — GliceMia responds with full glucose context
- **Send a food photo** — carb estimate + bolus suggestion
- **Send a voice message** — transcribed and analyzed
- **Share your location** — plan activity with route and prediction
- **Send a CSV** — import CareLink data
- **Send a PDF** — analyze lab results

### Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot doesn't respond | Check `TELEGRAM_BOT_TOKEN` in `.env` |
| "Not authorized" | Add your ID to `TELEGRAM_ALLOWED_USERS` |
| AI error | Check `GEMINI_API_KEY` in `.env` |
| No data | Run `python scripts/seed_demo.py` |
| CSV import fails | Check CSV files are in `private/data/` |

---

## Espanol

### Requisitos previos

- Python 3.11+ instalado
- Una cuenta de Telegram
- Conexion a internet

### Paso 1: Crea el bot de Telegram

1. Abre Telegram y busca **@BotFather**
2. Envia `/newbot`
3. Elige un nombre: ej. `GliceMia`
4. Elige un username: ej. `glicemia_nuria_bot` (debe terminar en `bot`)
5. BotFather responde con un **token** — copialo y guardalo

### Paso 2: Encuentra tu ID de Telegram

1. Busca **@userinfobot** en Telegram
2. Envia cualquier mensaje
3. Responde con tu **ID numerico** (ej. `987654321`)
4. Repite para cada persona que necesite usar el bot

### Paso 3: Obtiene la clave API de Gemini (gratuita)

1. Ve a https://ai.google.dev
2. Inicia sesion con tu cuenta de Google
3. Haz clic en "Get API key"
4. Copia la clave (empieza con `AIzaSy...`)

### Paso 4: Instala las dependencias

```bash
cd /Users/ccancellieri/work/code/diabete
source venv/bin/activate
pip install python-dotenv sqlalchemy "python-telegram-bot>=21.0" litellm matplotlib
```

### Paso 5: Configura el archivo `.env`

Copia la plantilla:

```bash
cp .env.example .env
```

Abre `.env` y modifica estos valores:

```env
# Clave Gemini (gratuita de ai.google.dev)
GEMINI_API_KEY=AIzaSy...tu_clave...

# Token del bot de Telegram (de @BotFather)
TELEGRAM_BOT_TOKEN=7123456789:AAH...tu_token...

# IDs de Telegram autorizados (separados por coma)
TELEGRAM_ALLOWED_USERS=987654321,123456789

# Nombre de la paciente
PATIENT_NAME=Nuria

# Idioma
LANGUAGE=es
```

Las demas configuraciones son opcionales para el primer inicio:
- `CARELINK_*` — solo necesario con credenciales CareLink activas
- `OPENWEATHER_API_KEY` — necesario para el clima en planificacion de actividades
- `ORS_API_KEY` — necesario para planificacion de rutas
- `DB_PASSPHRASE` — cambiala por una frase segura para encriptar la base de datos

### Paso 6: Importa datos e inicia

```bash
# Importa los CSV de CareLink y calcula patrones
python scripts/seed_demo.py

# Verifica que todo funcione
python scripts/test_demo.py

# Inicia el bot
python agent.py
```

### Paso 7: Usa el bot

1. Abre Telegram y busca el nombre de tu bot
2. Envia `/start`
3. Acepta el consentimiento informado
4. Usa el menu con botones:
   - **Estado actual** — glucosa, IOB, tendencia, predicciones
   - **Informe** — hoy / semana / mes con grafico
   - **Planificar actividad** — rutas GPS con prediccion de glucosa
   - **Importar datos** — CSV CareLink, ZIP Apple Health, PDF analisis
   - **Ajustes** — idioma, modelo AI

### Comandos disponibles

| Comando | Descripcion |
|---------|-------------|
| `/start` | Bienvenida + consentimiento |
| `/menu` | Menu principal |
| `/status` | Estado actual de glucosa |
| `/help` | Guia de ayuda |

### Que puedes hacer

- **Escribe un mensaje** — GliceMia responde con contexto glucemico completo
- **Envia una foto de comida** — estimacion de carbohidratos + sugerencia de bolo
- **Envia un mensaje de voz** — transcrito y analizado
- **Comparte tu ubicacion** — planifica actividad con ruta y prediccion
- **Envia un CSV** — importa datos de CareLink
- **Envia un PDF** — analiza resultados de laboratorio

### Solucion de problemas

| Problema | Solucion |
|----------|----------|
| El bot no responde | Verifica `TELEGRAM_BOT_TOKEN` en `.env` |
| "No autorizado" | Agrega tu ID en `TELEGRAM_ALLOWED_USERS` |
| Error de AI | Verifica `GEMINI_API_KEY` en `.env` |
| Sin datos | Ejecuta `python scripts/seed_demo.py` |
| Falla importacion CSV | Verifica que los CSV esten en `private/data/` |

---

## Francais

### Prerequis

- Python 3.11+ installe
- Un compte Telegram
- Connexion internet

### Etape 1 : Creer le bot Telegram

1. Ouvrez Telegram et cherchez **@BotFather**
2. Envoyez `/newbot`
3. Choisissez un nom : ex. `GliceMia`
4. Choisissez un username : ex. `glicemia_nuria_bot` (doit finir par `bot`)
5. BotFather repond avec un **token** — copiez-le et conservez-le

### Etape 2 : Trouver votre ID Telegram

1. Cherchez **@userinfobot** sur Telegram
2. Envoyez n'importe quel message
3. Il repond avec votre **ID numerique** (ex. `987654321`)
4. Repetez pour chaque personne qui doit utiliser le bot

### Etape 3 : Obtenir une cle API Gemini (gratuite)

1. Allez sur https://ai.google.dev
2. Connectez-vous avec votre compte Google
3. Cliquez sur "Get API key"
4. Copiez la cle (commence par `AIzaSy...`)

### Etape 4 : Installer les dependances

```bash
cd /Users/ccancellieri/work/code/diabete
source venv/bin/activate
pip install python-dotenv sqlalchemy "python-telegram-bot>=21.0" litellm matplotlib
```

### Etape 5 : Configurer le fichier `.env`

Copiez le modele :

```bash
cp .env.example .env
```

Ouvrez `.env` et modifiez ces valeurs :

```env
# Cle Gemini (gratuite de ai.google.dev)
GEMINI_API_KEY=AIzaSy...votre_cle...

# Token du bot Telegram (de @BotFather)
TELEGRAM_BOT_TOKEN=7123456789:AAH...votre_token...

# IDs Telegram autorises (separes par virgule)
TELEGRAM_ALLOWED_USERS=987654321,123456789

# Nom de la patiente
PATIENT_NAME=Nuria

# Langue
LANGUAGE=fr
```

Les autres parametres sont optionnels pour le premier demarrage :
- `CARELINK_*` — necessaire uniquement avec des identifiants CareLink actifs
- `OPENWEATHER_API_KEY` — necessaire pour la meteo dans la planification d'activites
- `ORS_API_KEY` — necessaire pour la planification d'itineraires
- `DB_PASSPHRASE` — changez-la pour une phrase securisee pour chiffrer la base de donnees

### Etape 6 : Importer les donnees et demarrer

```bash
# Importer les CSV CareLink et calculer les patterns
python scripts/seed_demo.py

# Verifier que tout fonctionne
python scripts/test_demo.py

# Demarrer le bot
python agent.py
```

### Etape 7 : Utiliser le bot

1. Ouvrez Telegram et cherchez le nom de votre bot
2. Envoyez `/start`
3. Acceptez le consentement
4. Utilisez le menu avec les boutons :
   - **Etat actuel** — glycemie, IOB, tendance, predictions
   - **Rapport** — aujourd'hui / semaine / mois avec graphique
   - **Planifier activite** — itineraires GPS avec prediction glycemique
   - **Importer donnees** — CSV CareLink, ZIP Apple Health, PDF analyses
   - **Parametres** — langue, modele IA

### Commandes disponibles

| Commande | Description |
|----------|-------------|
| `/start` | Bienvenue + consentement |
| `/menu` | Menu principal |
| `/status` | Etat actuel de la glycemie |
| `/help` | Guide d'aide |

### Ce que vous pouvez faire

- **Ecrivez un message** — GliceMia repond avec le contexte glycemique complet
- **Envoyez une photo de repas** — estimation des glucides + suggestion de bolus
- **Envoyez un message vocal** — transcrit et analyse
- **Partagez votre position** — planifiez une activite avec itineraire et prediction
- **Envoyez un CSV** — importez les donnees CareLink
- **Envoyez un PDF** — analysez les resultats de laboratoire

### Depannage

| Probleme | Solution |
|----------|----------|
| Le bot ne repond pas | Verifiez `TELEGRAM_BOT_TOKEN` dans `.env` |
| "Non autorise" | Ajoutez votre ID dans `TELEGRAM_ALLOWED_USERS` |
| Erreur IA | Verifiez `GEMINI_API_KEY` dans `.env` |
| Pas de donnees | Executez `python scripts/seed_demo.py` |
| Import CSV echoue | Verifiez que les CSV sont dans `private/data/` |

---

## Alternative AI Models

GliceMia supports any model via LiteLLM. Change `AI_MODEL` in `.env`:

| Model | `.env` config | Cost |
|-------|--------------|------|
| Gemini 2.5 Flash | `AI_MODEL=gemini/gemini-2.5-flash` | Free |
| Gemini 2.5 Pro | `AI_MODEL=gemini/gemini-2.5-pro` | Free (limited) |
| Claude Sonnet | `AI_MODEL=anthropic/claude-sonnet-4-20250514` | Paid |
| Claude Haiku | `AI_MODEL=anthropic/claude-haiku-4-5-20251001` | Paid |
| Ollama (local) | `AI_MODEL=ollama/llama3` | Free (local) |
| GPT-4o | `AI_MODEL=openai/gpt-4o` | Paid |

For Ollama (runs entirely on your machine, no internet needed):

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3
# In .env:
# AI_MODEL=ollama/llama3
# OLLAMA_API_BASE=http://localhost:11434
```

## Optional: CareLink Real-Time Data

For live CGM/pump data from the MiniMed 780G:

```bash
pip install carelink-python-client
```

Then set in `.env`:
```env
CARELINK_COUNTRY=it
CARELINK_USERNAME=your_carelink_email
CARELINK_PASSWORD=your_carelink_password
```

Note: CareLink authentication expires weekly. The bot will warn you when it needs re-authentication.

## Optional: MCP Server (Claude Desktop)

For deep analysis via Claude Desktop Pro:

```bash
pip install mcp
```

The MCP server exposes 11 tools: glucose status, history, patterns, metrics, conditions, observations, activities, bolus estimation, glucose prediction, hypo episodes, insulin settings.

## Data Security

- Database is SQLite with optional AES-256 encryption (set `DB_PASSPHRASE`)
- All patient data stays in `private/` (gitignored, never committed)
- `TELEGRAM_ALLOWED_USERS` restricts bot access to specific users
- No data is sent to external services except the configured AI model
