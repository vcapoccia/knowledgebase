# GitHub Auto-Sync

## Setup
```bash
# 1. Configura
nano scripts/config/github.conf

# 2. Test manuale
./scripts/sync_github.sh

# 3. Setup auto-sync (cron)
./scripts/setup_autosync_cron.sh

# 4. Setup git hooks (opzionale)
./scripts/setup_git_hooks.sh
```

## Uso Manuale
```bash
# Sync con messaggio auto-generato
./scripts/sync_github.sh

# Sync con messaggio custom
./scripts/sync_github.sh -m "Fixed critical bug"

# Dry-run (mostra cosa farebbe)
./scripts/sync_github.sh -d

# Force push
./scripts/sync_github.sh -f
```

## Integrazione negli Script
```bash
#!/bin/bash
source "$(dirname $0)/lib/github_sync_wrapper.sh"

# ... tuo codice ...

# Sync automatico al termine
sync_to_github "Script XYZ executed"
```

## Configurazione

`scripts/config/github.conf`:
- `AUTO_COMMIT`: Commit automatico modifiche
- `AUTO_PUSH`: Push automatico su GitHub
- `COMMIT_PREFIX`: Prefisso commit messages
- `GITHUB_BRANCH`: Branch da usare

## Log

- Manual sync: `scripts/logs/github_sync_YYYYMMDD.log`
- Auto-sync (cron): `scripts/logs/autosync.log`

