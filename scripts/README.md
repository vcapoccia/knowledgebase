# KBSearch Backup Scripts

## Setup Iniziale
```bash
# 1. Configura path backup
nano scripts/config/backup.conf

# 2. Setup cron giornaliero
sudo ./scripts/setup_cron.sh

# 3. Test backup manuale
./scripts/backup_full.sh
```

## Comandi

### Backup Completo
```bash
./scripts/backup_full.sh
```

### Cleanup Database
```bash
./scripts/cleanup_databases.sh
```

### Restore
```bash
./scripts/restore.sh <timestamp>
```

## Configurazione

Modifica `scripts/config/backup.conf`:
- `BACKUP_ROOT`: Directory backup principale
- `RETENTION_DAYS`: Giorni retention backup
- `COMPRESSION`: Tipo compressione (gzip/zstd/none)

