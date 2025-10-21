#!/bin/bash
set -e

echo "🚀 PUBBLICAZIONE PULITA SU GITHUB"
echo "=================================="
echo ""

# 1. Verifica git status
echo "1. Verifica stato attuale..."
git status

echo ""
echo "File da committare:"
git status --short | wc -l

# 2. Aggiungi tutto (se serve)
echo ""
echo "2. Aggiungo eventuali file nuovi..."
git add -A

# 3. Commit (se ci sono modifiche)
if ! git diff --cached --quiet; then
    echo ""
    echo "3. Commit modifiche..."
    git commit -m "Clean repository: complete kbsearch project" || true
else
    echo ""
    echo "3. Nessuna modifica da committare"
fi

# 4. Verifica remote
echo ""
echo "4. Remote configurato:"
git remote -v

# 5. Branch info
echo ""
echo "5. Branch attuale:"
git branch

# 6. Log commit
echo ""
echo "6. Ultimi commit locali:"
git log --oneline -5

echo ""
echo "================================"
echo "⚠️  ATTENZIONE"
echo "================================"
echo ""
echo "Stai per SOVRASCRIVERE completamente GitHub con il contenuto locale!"
echo ""
echo "Repo GitHub: https://github.com/vcapoccia/knowledgebase"
echo "Contenuto locale: /opt/kbsearch"
echo ""
read -p "Confermi? (scrivi 'SI' per continuare): " confirm

if [ "$confirm" != "SI" ]; then
    echo ""
    echo "❌ Operazione annullata"
    exit 1
fi

# 7. Force push
echo ""
echo "7. Force push su GitHub..."
echo ""
git push -u origin main --force

echo ""
echo "================================"
echo "✅ PUBBLICAZIONE COMPLETATA!"
echo "================================"
echo ""
echo "Repo disponibile su:"
echo "https://github.com/vcapoccia/knowledgebase"
echo ""
echo "Verifica che tutto sia OK!"

