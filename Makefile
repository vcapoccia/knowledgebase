# =======================================================================
# KNOWLEDGEBASE MAKEFILE
# Sistema di automazione per il knowledge base semantico
# =======================================================================

.PHONY: help install start stop restart build clean status logs health backup restore test dev prod

# Colori per output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
PURPLE := \033[0;35m
CYAN := \033[0;36m
WHITE := \033[0;37m
NC := \033[0m # No Color

# Configurazioni
PROJECT_NAME := knowledgebase
COMPOSE_FILE := docker-compose.yml
COMPOSE_DEV_FILE := docker-compose.override.yml
ENV_FILE := .env

# =======================================================================
# HELP - Mostra tutti i comandi disponibili
# =======================================================================
help: ## Mostra questo messaggio di aiuto
	@echo "${CYAN}=======================================================================${NC}"
	@echo "${CYAN}KNOWLEDGEBASE - Sistema di Knowledge Base Semantico${NC}"
	@echo "${CYAN}=======================================================================${NC}"
	@echo ""
	@echo "${GREEN}Comandi principali:${NC}"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*?##/ { printf "  ${YELLOW}%-20s${NC} %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
	@echo "${BLUE}Esempi d'uso:${NC}"
	@echo "  ${WHITE}make install${NC}     - Prima installazione completa"
	@echo "  ${WHITE}make start${NC}       - Avvia tutti i servizi"
	@echo "  ${WHITE}make ingest${NC}      - Processo documenti"
	@echo "  ${WHITE}make status${NC}      - Controlla stato servizi"
	@echo "  ${WHITE}make logs${NC}        - Visualizza logs"
	@echo ""

# =======================================================================
# INSTALLAZIONE E SETUP
# =======================================================================
install: ## Installazione completa del sistema
	@echo "${GREEN}🚀 Installazione Knowledge Base System...${NC}"
	@./scripts/install.sh
	@echo "${GREEN}✅ Installazione completata!${NC}"

setup-dirs: ## Crea la struttura delle directory
	@echo "${BLUE}📁 Creazione struttura directory...${NC}"
	@mkdir -p data/qdrant data/logs data/backups
	@mkdir -p docs/_Gare docs/_AQ
	@mkdir -p temp/uploads
	@mkdir -p config/caddy config/nginx config/qdrant
	@mkdir -p monitoring/prometheus monitoring/grafana
	@echo "${GREEN}✅ Directory create!${NC}"

check-env: ## Controlla file di configurazione
	@echo "${BLUE}🔍 Controllo configurazione...${NC}"
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "${YELLOW}⚠️  File .env non trovato, copio da .env.example${NC}"; \
		cp .env.example .env; \
	fi
	@echo "${GREEN}✅ Configurazione OK!${NC}"

# =======================================================================
# GESTIONE SERVIZI
# =======================================================================
build: ## Build delle immagini Docker
	@echo "${BLUE}🔨 Build immagini Docker...${NC}"
	@docker-compose build --parallel
	@echo "${GREEN}✅ Build completato!${NC}"

start: check-env ## Avvia tutti i servizi
	@echo "${GREEN}🚀 Avvio servizi Knowledge Base...${NC}"
	@docker-compose up -d qdrant kb-api kb-ui caddy
	@echo "${GREEN}✅ Servizi avviati!${NC}"
	@$(MAKE) status

stop: ## Ferma tutti i servizi
	@echo "${YELLOW}⏹️  Fermando servizi...${NC}"
	@docker-compose stop
	@echo "${GREEN}✅ Servizi fermati!${NC}"

restart: ## Riavvia tutti i servizi
	@echo "${BLUE}🔄 Riavvio servizi...${NC}"
	@docker-compose restart
	@echo "${GREEN}✅ Servizi riavviati!${NC}"

down: ## Ferma e rimuove tutti i container
	@echo "${RED}🗑️  Rimozione completa container...${NC}"
	@docker-compose down
	@echo "${GREEN}✅ Container rimossi!${NC}"

# =======================================================================
# INGESTION E PROCESSING
# =======================================================================
ingest: ## Esegue il processo di ingestion documenti
	@echo "${PURPLE}📚 Avvio ingestion documenti...${NC}"
	@docker-compose run --rm kb-ingest
	@echo "${GREEN}✅ Ingestion completata!${NC}"

ingest-incremental: ## Ingestion incrementale (solo nuovi documenti)
	@echo "${PURPLE}📚 Avvio ingestion incrementale...${NC}"
	@docker-compose run --rm -e INCREMENTAL=true kb-ingest
	@echo "${GREEN}✅ Ingestion incrementale completata!${NC}"

ingest-force: ## Forza re-ingestion di tutti i documenti
	@echo "${RED}🔄 Forza re-ingestion completa...${NC}"
	@docker-compose run --rm -e FORCE_REINGEST=true kb-ingest
	@echo "${GREEN}✅ Re-ingestion forzata completata!${NC}"

# =======================================================================
# MONITORING E DEBUG
# =======================================================================
status: ## Controlla stato di tutti i servizi
	@echo "${CYAN}📊 Stato servizi:${NC}"
	@docker-compose ps
	@echo ""
	@$(MAKE) health

health: ## Controlla salute servizi
	@echo "${BLUE}🏥 Health Check servizi:${NC}"
	@./scripts/health-check.sh

logs: ## Mostra logs di tutti i servizi
	@docker-compose logs -f

logs-api: ## Mostra logs solo KB API
	@docker-compose logs -f kb-api

logs-ui: ## Mostra logs solo KB UI
	@docker-compose logs -f kb-ui

logs-ingest: ## Mostra logs ingestion
	@docker-compose logs kb-ingest

logs-qdrant: ## Mostra logs Qdrant
	@docker-compose logs -f qdrant

# =======================================================================
# BACKUP E RIPRISTINO
# =======================================================================
backup: ## Esegue backup completo del sistema
	@echo "${BLUE}💾 Avvio backup sistema...${NC}"
	@./scripts/backup.sh
	@echo "${GREEN}✅ Backup completato!${NC}"

restore: ## Ripristina backup (chiede conferma)
	@echo "${RED}⚠️  ATTENZIONE: Questo ripristinerà il backup più recente${NC}"
	@echo "${YELLOW}Continuare? [y/N]${NC}"
	@read -r REPLY; \
	if [ "$$REPLY" = "y" ] || [ "$$REPLY" = "Y" ]; then \
		./scripts/restore.sh; \
		echo "${GREEN}✅ Ripristino completato!${NC}"; \
	else \
		echo "${YELLOW}Operazione annullata${NC}"; \
	fi

list-backups: ## Lista tutti i backup disponibili
	@echo "${BLUE}📋 Backup disponibili:${NC}"
	@ls -la data/backups/

# =======================================================================
# PULIZIA E MANUTENZIONE
# =======================================================================
clean: ## Pulizia sistema (rimuove immagini, volumi, ecc.)
	@echo "${RED}🧹 Pulizia sistema Docker...${NC}"
	@./scripts/cleanup.sh
	@echo "${GREEN}✅ Pulizia completata!${NC}"

clean-logs: ## Pulisce tutti i logs
	@echo "${YELLOW}🗑️  Pulizia logs...${NC}"
	@sudo find data/logs -name "*.log" -type f -delete
	@docker-compose exec -T caddy sh -c 'find /var/log -name "*.log" -type f -delete' || true
	@echo "${GREEN}✅ Logs puliti!${NC}"

clean-temp: ## Pulisce file temporanei
	@echo "${YELLOW}🗑️  Pulizia file temporanei...${NC}"
	@sudo rm -rf temp/uploads/*
	@echo "${GREEN}✅ File temporanei puliti!${NC}"

prune: ## Pulizia Docker completa (ATTENZIONE: rimuove tutto)
	@echo "${RED}⚠️  ATTENZIONE: Questo rimuoverà TUTTE le immagini, container e volumi Docker${NC}"
	@echo "${YELLOW}Continuare? [y/N]${NC}"
	@read -r REPLY; \
	if [ "$$REPLY" = "y" ] || [ "$$REPLY" = "Y" ]; then \
		docker system prune -af; \
		docker volume prune -f; \
		echo "${GREEN}✅ Pulizia Docker completa!${NC}"; \
	else \
		echo "${YELLOW}Operazione annullata${NC}"; \
	fi

# =======================================================================
# TESTING
# =======================================================================
test: ## Esegue tutti i test
	@echo "${PURPLE}🧪 Esecuzione test...${NC}"
	@docker-compose run --rm kb-api python -m pytest
	@echo "${GREEN}✅ Test completati!${NC}"

test-api: ## Test solo API
	@echo "${PURPLE}🧪 Test KB API...${NC}"
	@docker-compose run --rm kb-api python -m pytest tests/test_api.py -v
	@echo "${GREEN}✅ Test API completati!${NC}"

test-ingest: ## Test solo ingestion
	@echo "${PURPLE}🧪 Test Ingestion...${NC}"
	@docker-compose run --rm kb-ingest python -m pytest tests/ -v
	@echo "${GREEN}✅ Test Ingestion completati!${NC}"

# =======================================================================
# SVILUPPO
# =======================================================================
dev: ## Avvia in modalità sviluppo
	@echo "${CYAN}🛠️  Avvio modalità sviluppo...${NC}"
	@docker-compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV_FILE) up -d
	@echo "${GREEN}✅ Modalità sviluppo attiva!${NC}"

dev-logs: ## Logs modalità sviluppo
	@docker-compose -f $(COMPOSE_FILE) -f $(COMPOSE_DEV_FILE) logs -f

shell-api: ## Shell nel container API
	@docker-compose exec kb-api /bin/bash

shell-ui: ## Shell nel container UI
	@docker-compose exec kb-ui /bin/sh

shell-qdrant: ## Shell nel container Qdrant
	@docker-compose exec qdrant /bin/bash

# =======================================================================
# UTILITÀ
# =======================================================================
urls: ## Mostra URL di accesso ai servizi
	@echo "${CYAN}🌐 URL Servizi:${NC}"
	@echo "  ${WHITE}Web UI:${NC}           http://localhost"
	@echo "  ${WHITE}API Docs:${NC}         http://localhost/api/docs"
	@echo "  ${WHITE}Qdrant UI:${NC}        http://localhost:6333/dashboard"
	@echo "  ${WHITE}Caddy Admin:${NC}      http://localhost:2019"
	@echo "  ${WHITE}Health Check:${NC}     http://localhost/api/health"

ps: ## Mostra container in esecuzione
	@docker-compose ps

top: ## Mostra utilizzo risorse container
	@docker stats

disk-usage: ## Mostra utilizzo disco Docker
	@docker system df

# =======================================================================
# PRODUZIONE
# =======================================================================
prod-deploy: ## Deploy in produzione
	@echo "${GREEN}🚀 Deploy produzione...${NC}"
	@$(MAKE) backup
	@$(MAKE) build
	@$(MAKE) down
	@$(MAKE) start
	@$(MAKE) ingest
	@$(MAKE) health
	@echo "${GREEN}✅ Deploy produzione completato!${NC}"

prod-update: ## Aggiorna sistema in produzione
	@echo "${BLUE}🔄 Aggiornamento produzione...${NC}"
	@$(MAKE) backup
	@git pull
	@$(MAKE) build
	@$(MAKE) restart
	@$(MAKE) health
	@echo "${GREEN}✅ Aggiornamento completato!${NC}"

# =======================================================================
# DEFAULT TARGET
# =======================================================================
.DEFAULT_GOAL := help