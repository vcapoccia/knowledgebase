#!/bin/bash

# Uscita immediata in caso di errore
set -e

echo "[INFO] Avvio procedura per rimuovere backup.sql dal repository..."

# Vai nella root del progetto
cd /opt/kbsearch

# Attiva il virtual environment (se esiste)
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "[INFO] Virtual environment attivato."
fi

# Installa git-filter-repo via pip
echo "[INFO] Installazione git-filter-repo..."
pip install git-filter-repo

# Aggiungi backup.sql a .gitignore
echo "backup.sql" >> .gitignore
git add .gitignore
git commit -m "Add backup.sql to .gitignore"

# Rimuovi il file dalla cronologia
echo "[INFO] Rimozione backup.sql dalla cronologia..."
git filter-repo --path backup.sql --invert-paths

# Forza il push su GitHub
echo "[INFO] Push forzato su GitHub..."
git push origin main --force

echo "[SUCCESS] backup.sql rimosso e repository aggiornato!"
