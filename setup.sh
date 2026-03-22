#!/bin/bash

#pip install venv
#python -m venv venv
#source venv/bin/activate
#pip install pandas matplotlib openpyxl


# 1. Spostati nella cartella del tuo progetto
cd $(pwd)

# 2. Crea l'ambiente virtuale
python3 -m venv venv

# 3. Attiva l'ambiente virtuale
# Su Linux/macOS:
source venv/bin/activate
# Su Windows (cmd):
#venv\Scripts\activate.bat
# Su Windows (PowerShell):
#venv\Scripts\Activate.ps1

# 4. Installa le librerie
pip install pandas matplotlib openpyxl

# 5. Esegui il tuo script
python3 main.py

# 6. Disattiva l'ambiente virtuale (quando hai finito)
deactivate
