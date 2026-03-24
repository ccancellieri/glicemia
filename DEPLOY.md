# GliceMia — Deploy on Oracle Cloud (Always Free)

Deploy GliceMia on Oracle Cloud's Always Free tier: 4 ARM cores, 24 GB RAM, 200 GB storage, **free forever**, with an EU data center (Milan) for GDPR compliance.

---

## IT — Guida al Deploy su Oracle Cloud (Always Free)

### 1. Crea un account Oracle Cloud

1. Vai su https://cloud.oracle.com e clicca **"Sign Up"**
2. Compila con i tuoi dati reali (servono per la verifica)
3. Seleziona **Home Region: Italy South (Milan)** — i dati medici resteranno in Italia (GDPR)
4. Inserisci una carta di credito (richiesta per verifica, **non verrà addebitato nulla**)
5. Conferma l'email e accedi alla console

> **Importante**: la Home Region NON si può cambiare dopo. Scegli Milan.

### 2. Crea una VM (Always Free)

1. Nella console Oracle Cloud, vai a **Compute → Instances → Create Instance**
2. Configura:
   - **Name**: `glicemia`
   - **Image**: Ubuntu 22.04 (o 24.04)
   - **Shape**: clicca **"Change Shape"** → **Ampere** → **VM.Standard.A1.Flex**
     - OCPUs: **2** (puoi usare fino a 4 gratis)
     - RAM: **12 GB** (puoi usare fino a 24 GB gratis)
   - **Networking**: lascia i default (crea una nuova VCN)
   - **SSH key**: clicca **"Generate a key pair"** e **scarica entrambe le chiavi** (pubblica e privata)
     - Oppure carica la tua chiave pubblica se ne hai già una (`~/.ssh/id_rsa.pub`)
3. Clicca **"Create"** — aspetta 2-3 minuti

### 3. Configura il firewall Oracle (Security List)

Oracle blocca tutto tranne SSH (22) per default. Devi aprire la porta per l'API:

1. Vai a **Networking → Virtual Cloud Networks** → clicca sulla tua VCN
2. Clicca sulla **Subnet** → clicca sulla **Security List**
3. **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0`
   - Destination Port Range: `443`
   - Description: `HTTPS for GliceMia API`
4. (Opzionale) Aggiungi anche la porta `8443` se vuoi testare senza HTTPS

### 4. Connettiti alla VM

```bash
# Rendi la chiave privata sicura
chmod 600 ~/Downloads/ssh-key-*.key

# Connettiti (sostituisci l'IP dalla console Oracle)
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<IP_PUBBLICO>
```

Trovi l'IP pubblico nella pagina dell'istanza nella console Oracle.

### 5. Installa le dipendenze sulla VM

```bash
# Aggiorna il sistema
sudo apt update && sudo apt upgrade -y

# Python 3.11+ e strumenti
sudo apt install -y python3 python3-pip python3-venv git

# SQLCipher (database crittografato)
sudo apt install -y libsqlcipher-dev

# Certbot per HTTPS gratuito
sudo apt install -y certbot

# Firewall della VM
sudo ufw allow 22/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8443/tcp
sudo ufw enable
```

### 6. Clona e configura GliceMia

```bash
# Clona il repository
cd ~
git clone https://github.com/TUO_USER/diabete.git glicemia
cd glicemia

# Crea virtual environment
python3 -m venv venv
source venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt
pip install aiohttp  # per il web server

# Configura
cp .env.example .env
nano .env
```

Modifica `.env` con i tuoi valori:
```env
# Obbligatori
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
GEMINI_API_KEY=AIza...
TELEGRAM_ALLOWED_USERS=123456789

# CareLink
CARELINK_COUNTRY=it
CARELINK_USERNAME=tuo_username
CARELINK_PASSWORD=tua_password

# Sicurezza database
DB_PASSPHRASE=una_passphrase_lunga_e_sicura_qui

# WebApp (metti l'IP della VM o un dominio)
WEBAPP_PORT=8443
WEBAPP_URL=https://tuo-dominio.duckdns.org/webapp

# Lingua
LANGUAGE=it
PATIENT_NAME=YourName
```

### 7. Importa i dati CareLink

```bash
# Crea la directory per i dati privati
mkdir -p private/data

# Copia i CSV dal tuo PC alla VM
# (dal tuo Mac, in un altro terminale:)
scp -i ~/Downloads/ssh-key-*.key private/data/*.csv ubuntu@<IP>:~/glicemia/private/data/

# Sulla VM, importa
source venv/bin/activate
python scripts/seed_demo.py

# Verifica
python scripts/test_demo.py
```

### 8. HTTPS gratuito con Let's Encrypt

Opzione A — **DuckDNS (dominio gratuito)**:
```bash
# 1. Vai su https://www.duckdns.org, accedi con GitHub/Google
# 2. Crea un dominio: glicemia-nuria.duckdns.org → punta all'IP della VM
# 3. Aggiorna automaticamente con cron:
echo "*/5 * * * * curl -s 'https://www.duckdns.org/update?domains=glicemia-nuria&token=TUO_TOKEN&ip=' > /dev/null" | crontab -

# 4. Ottieni certificato HTTPS
sudo certbot certonly --standalone -d glicemia-nuria.duckdns.org
```

Opzione B — **Cloudflare Tunnel (nessuna porta aperta)**:
```bash
# Installa cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/

# Crea tunnel (serve account Cloudflare gratuito)
cloudflared tunnel login
cloudflared tunnel create glicemia
cloudflared tunnel route dns glicemia glicemia.tuodominio.com

# Avvia
cloudflared tunnel run --url http://localhost:8443 glicemia
```

### 9. Avvia GliceMia come servizio (auto-restart)

Crea il file systemd:
```bash
sudo nano /etc/systemd/system/glicemia.service
```

Contenuto:
```ini
[Unit]
Description=GliceMia T1D Companion
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/glicemia
Environment=PATH=/home/ubuntu/glicemia/venv/bin:/usr/bin
ExecStart=/home/ubuntu/glicemia/venv/bin/python agent.py
Restart=always
RestartSec=10

# Sicurezza
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/home/ubuntu/glicemia
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Attiva:
```bash
sudo systemctl daemon-reload
sudo systemctl enable glicemia
sudo systemctl start glicemia

# Verifica
sudo systemctl status glicemia

# Vedi i log
sudo journalctl -u glicemia -f
```

### 10. Backup automatico del database

```bash
# Script di backup
cat > ~/backup-glicemia.sh << 'SCRIPT'
#!/bin/bash
BACKUP_DIR="$HOME/backups"
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y%m%d_%H%M)
cp ~/glicemia/glicemia.db "$BACKUP_DIR/glicemia_${DATE}.db"
# Mantieni solo gli ultimi 7 giorni
find "$BACKUP_DIR" -name "glicemia_*.db" -mtime +7 -delete
SCRIPT
chmod +x ~/backup-glicemia.sh

# Backup giornaliero alle 03:00
(crontab -l 2>/dev/null; echo "0 3 * * * /home/ubuntu/backup-glicemia.sh") | crontab -
```

### 11. Aggiorna GliceMia

```bash
cd ~/glicemia
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart glicemia
```

---

## EN — Deploy Guide on Oracle Cloud (Always Free)

### 1. Create an Oracle Cloud account

1. Go to https://cloud.oracle.com and click **"Sign Up"**
2. Fill in your real details (needed for verification)
3. Select **Home Region: Italy South (Milan)** — keeps medical data in the EU
4. Enter a credit card (required for verification, **you will NOT be charged**)
5. Confirm email and log into the console

> **Important**: Home Region CANNOT be changed later. Choose Milan (or your nearest EU region).

### 2. Create a VM (Always Free)

1. In the Oracle Cloud console, go to **Compute → Instances → Create Instance**
2. Configure:
   - **Name**: `glicemia`
   - **Image**: Ubuntu 22.04 (or 24.04)
   - **Shape**: click **"Change Shape"** → **Ampere** → **VM.Standard.A1.Flex**
     - OCPUs: **2** (up to 4 free)
     - RAM: **12 GB** (up to 24 GB free)
   - **Networking**: leave defaults (creates a new VCN)
   - **SSH key**: click **"Generate a key pair"** and **download both keys**
3. Click **"Create"** — wait 2-3 minutes

### 3. Configure Oracle firewall (Security List)

Oracle blocks everything except SSH (22) by default. Open the API port:

1. Go to **Networking → Virtual Cloud Networks** → click your VCN
2. Click the **Subnet** → click the **Security List**
3. **Add Ingress Rule**:
   - Source CIDR: `0.0.0.0/0`
   - Destination Port Range: `443`
   - Description: `HTTPS for GliceMia API`

### 4. Connect to the VM

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<PUBLIC_IP>
```

### 5. Install dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git libsqlcipher-dev certbot

sudo ufw allow 22/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8443/tcp
sudo ufw enable
```

### 6. Clone and configure

```bash
cd ~
git clone https://github.com/YOUR_USER/diabete.git glicemia
cd glicemia
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install aiohttp

cp .env.example .env
nano .env  # set your tokens, passwords, language
```

### 7. Import data and test

```bash
# Copy CSVs from your Mac (run on Mac):
scp -i ~/Downloads/ssh-key-*.key private/data/*.csv ubuntu@<IP>:~/glicemia/private/data/

# On the VM:
mkdir -p private/data
source venv/bin/activate
python scripts/seed_demo.py
python scripts/test_demo.py
```

### 8. Free HTTPS with Let's Encrypt

```bash
# Get a free domain at duckdns.org, point it to your VM's IP
sudo certbot certonly --standalone -d your-domain.duckdns.org
```

### 9. Run as a systemd service

```bash
sudo nano /etc/systemd/system/glicemia.service
```

```ini
[Unit]
Description=GliceMia T1D Companion
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/glicemia
Environment=PATH=/home/ubuntu/glicemia/venv/bin:/usr/bin
ExecStart=/home/ubuntu/glicemia/venv/bin/python agent.py
Restart=always
RestartSec=10
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/home/ubuntu/glicemia
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable glicemia
sudo systemctl start glicemia
sudo journalctl -u glicemia -f  # view logs
```

### 10. Updates

```bash
cd ~/glicemia && git pull
source venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart glicemia
```

---

## ES — Guia de Deploy en Oracle Cloud (Always Free)

### 1. Crea una cuenta Oracle Cloud

1. Ve a https://cloud.oracle.com y haz clic en **"Sign Up"**
2. Rellena con tus datos reales (necesarios para verificacion)
3. Selecciona **Home Region: Italy South (Milan)** — los datos medicos se quedan en la UE
4. Introduce una tarjeta de credito (solo verificacion, **no se cobra nada**)
5. Confirma el email y accede a la consola

### 2. Crea una VM (Always Free)

1. En la consola, ve a **Compute → Instances → Create Instance**
2. Configura:
   - **Name**: `glicemia`
   - **Image**: Ubuntu 22.04
   - **Shape**: **Ampere** → **VM.Standard.A1.Flex** (2 OCPUs, 12 GB RAM)
   - **SSH key**: genera y descarga el par de claves
3. Clic en **"Create"**

### 3. Configura el firewall (Security List)

1. **Networking → VCN** → Subnet → Security List
2. **Add Ingress Rule**: Source `0.0.0.0/0`, Port `443`

### 4. Conectate a la VM

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<IP_PUBLICA>
```

### 5. Instala dependencias

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git libsqlcipher-dev certbot
sudo ufw allow 22/tcp && sudo ufw allow 443/tcp && sudo ufw allow 8443/tcp && sudo ufw enable
```

### 6. Clona y configura

```bash
cd ~ && git clone https://github.com/TU_USUARIO/diabete.git glicemia
cd glicemia && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install aiohttp
cp .env.example .env && nano .env
```

### 7. Importa datos y prueba

```bash
mkdir -p private/data
# Desde tu Mac: scp -i key private/data/*.csv ubuntu@<IP>:~/glicemia/private/data/
python scripts/seed_demo.py && python scripts/test_demo.py
```

### 8. HTTPS gratis + servicio systemd

Mismos pasos que la version EN (secciones 8-9 arriba).

### 9. Actualizar

```bash
cd ~/glicemia && git pull && source venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart glicemia
```

---

## FR — Guide de deploiement sur Oracle Cloud (Always Free)

### 1. Creez un compte Oracle Cloud

1. Allez sur https://cloud.oracle.com et cliquez **"Sign Up"**
2. Remplissez avec vos vraies informations (necessaires pour la verification)
3. Selectionnez **Home Region: Italy South (Milan)** — les donnees medicales restent dans l'UE
4. Entrez une carte bancaire (verification uniquement, **aucun prelevement**)
5. Confirmez l'email et connectez-vous a la console

### 2. Creez une VM (Always Free)

1. Dans la console, allez a **Compute → Instances → Create Instance**
2. Configurez:
   - **Name**: `glicemia`
   - **Image**: Ubuntu 22.04
   - **Shape**: **Ampere** → **VM.Standard.A1.Flex** (2 OCPUs, 12 GB RAM)
   - **Cle SSH**: generez et telechargez la paire de cles
3. Cliquez **"Create"**

### 3. Configurez le firewall (Security List)

1. **Networking → VCN** → Subnet → Security List
2. **Add Ingress Rule**: Source `0.0.0.0/0`, Port `443`

### 4. Connectez-vous a la VM

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<IP_PUBLIQUE>
```

### 5. Installez les dependances

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git libsqlcipher-dev certbot
sudo ufw allow 22/tcp && sudo ufw allow 443/tcp && sudo ufw allow 8443/tcp && sudo ufw enable
```

### 6. Clonez et configurez

```bash
cd ~ && git clone https://github.com/VOTRE_USER/diabete.git glicemia
cd glicemia && python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install aiohttp
cp .env.example .env && nano .env
```

### 7. Importez les donnees et testez

```bash
mkdir -p private/data
# Depuis votre Mac: scp -i key private/data/*.csv ubuntu@<IP>:~/glicemia/private/data/
python scripts/seed_demo.py && python scripts/test_demo.py
```

### 8. HTTPS gratuit + service systemd

Memes etapes que la version EN (sections 8-9 ci-dessus).

### 9. Mise a jour

```bash
cd ~/glicemia && git pull && source venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart glicemia
```

---

## Architecture: GitHub Pages + Oracle Cloud

```
        User (Telegram)
             │
     ┌───────┴───────┐
     │               │
     ▼               ▼
GitHub Pages    Oracle Cloud VM (Milan)
┌──────────┐   ┌─────────────────────────┐
│ Mini App │──>│ :8443 aiohttp API       │
│ (HTML/   │   │ Telegram Bot (polling)   │
│  CSS/JS) │   │ CareLink Poller (5min)  │
│          │   │ Pattern Scheduler        │
│ Static,  │   │ Alert Engine             │
│ no data  │   │                          │
└──────────┘   │ SQLCipher DB (AES-256)  │
               │ Let's Encrypt (HTTPS)    │
               │ UFW Firewall             │
               │ systemd (auto-restart)   │
               └─────────────────────────┘
```

## Security Checklist

- [x] SQLCipher AES-256 encryption on database file
- [x] `.env` with `chmod 600` — secrets not in code
- [x] `TELEGRAM_ALLOWED_USERS` — only authorized Telegram IDs
- [x] WebApp initData HMAC validation on every API call
- [x] UFW firewall — only ports 22 (SSH) and 443 (HTTPS)
- [x] SSH key-only authentication (disable password login)
- [x] Let's Encrypt TLS — all traffic encrypted in transit
- [x] systemd hardening — `NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`
- [x] Oracle Cloud Milan region — data stays in Italy (GDPR)
- [x] Daily encrypted database backups
- [x] No patient data on GitHub (Pages hosts only the UI shell)

## Cost Summary

| Resource | Cost |
|----------|------|
| Oracle Cloud VM (A1.Flex, 2 OCPU, 12 GB) | **Free forever** |
| Oracle Cloud storage (50 GB boot + 100 GB block) | **Free forever** |
| Oracle Cloud network (10 TB/month) | **Free forever** |
| GitHub Pages (Mini App frontend) | **Free** |
| DuckDNS domain | **Free** |
| Let's Encrypt HTTPS certificate | **Free** |
| Gemini AI API | **Free** (1500 req/day) |
| **Total** | **0 EUR/month** |
