#!/bin/bash

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$PROJECT_ROOT/.git/hooks"

# Pre-commit hook
cat > "$HOOKS_DIR/pre-commit" << 'PRECOMMIT'
#!/bin/bash

# Verifica che non ci siano file sensibili
if git diff --cached --name-only | grep -qE "\.env$|password|secret|\.key$"; then
    echo "❌ ERROR: Attempting to commit sensitive files!"
    echo "   Remove from staging: git reset HEAD <file>"
    exit 1
fi

# Verifica syntax Python
for file in $(git diff --cached --name-only | grep "\.py$"); do
    if [ -f "$file" ]; then
        python3 -m py_compile "$file" 2>/dev/null
        if [ $? -ne 0 ]; then
            echo "❌ Syntax error in $file"
            exit 1
        fi
    fi
done

exit 0
PRECOMMIT

chmod +x "$HOOKS_DIR/pre-commit"

echo "✅ Git hooks installati"
echo "   Pre-commit: verifica syntax Python e file sensibili"

