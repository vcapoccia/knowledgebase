# =======================================================================
# KNOWLEDGEBASE UI DOCKERFILE (Multi-stage)
# Frontend statico con Nginx per l'interfaccia web
# =======================================================================

# -----------------------------------------------------------------------
# STAGE 1: Build environment (Node.js)
# -----------------------------------------------------------------------
FROM node:18-alpine AS builder

LABEL maintainer="vcapoccia@example.com"
LABEL version="2.0.0"
LABEL description="Knowledge Base UI - Frontend Build Stage"

WORKDIR /build

# Installa dipendenze di sistema
RUN apk add --no-cache \
    git \
    python3 \
    make \
    g++

# Copia package files per cache delle dipendenze
COPY package*.json ./
COPY yarn.lock* ./

# Installa dipendenze (preferisce yarn se disponibile)
RUN if [ -f yarn.lock ]; then \
        yarn install --frozen-lockfile --production=false; \
    elif [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

# Copia codice sorgente
COPY src/ ./src/
COPY public/ ./public/
COPY *.config.js ./
COPY *.json ./

# Build produzione
ENV NODE_ENV=production
RUN if [ -f yarn.lock ]; then \
        yarn build; \
    else \
        npm run build; \
    fi

# Ottimizzazioni finali
RUN find dist/ -name "*.js" -exec gzip -9 -k {} \; && \
    find dist/ -name "*.css" -exec gzip -9 -k {} \; && \
    find dist/ -name "*.html" -exec gzip -9 -k {} \;

# -----------------------------------------------------------------------
# STAGE 2: Nginx base con configurazioni
# -----------------------------------------------------------------------
FROM nginx:1.25-alpine AS nginx-base

# Installa dipendenze aggiuntive
RUN apk add --no-cache \
    curl \
    jq \
    tzdata

# Crea utente nginx se non esiste
RUN addgroup -g 101 -S nginx 2>/dev/null || true && \
    adduser -S -D -H -u 101 -h /var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx 2>/dev/null || true

# -----------------------------------------------------------------------
# STAGE 3: Development (con hot reload e dev tools)
# -----------------------------------------------------------------------
FROM nginx-base AS development

# Configurazione sviluppo
COPY config/nginx/nginx.dev.conf /etc/nginx/nginx.conf
COPY config/nginx/default.dev.conf /etc/nginx/conf.d/default.conf

# Copia assets di sviluppo
COPY --from=builder /build/dist/ /usr/share/nginx/html/
COPY --from=builder /build/src/ /usr/share/nginx/html/src/

# Script per development
COPY scripts/dev-entrypoint.sh /docker-entrypoint.d/99-dev-setup.sh
RUN chmod +x /docker-entrypoint.d/99-dev-setup.sh

# Health check per sviluppo
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

EXPOSE 80

# -----------------------------------------------------------------------
# STAGE 4: Production (ottimizzato per performance)
# -----------------------------------------------------------------------
FROM nginx-base AS production

# Configurazione produzione ottimizzata
COPY config/nginx/nginx.prod.conf /etc/nginx/nginx.conf
COPY config/nginx/default.prod.conf /etc/nginx/conf.d/default.conf
COPY config/nginx/gzip.conf /etc/nginx/conf.d/gzip.conf
COPY config/nginx/security.conf /etc/nginx/conf.d/security.conf

# Copia assets ottimizzati
COPY --from=builder --chown=nginx:nginx /build/dist/ /usr/share/nginx/html/

# Template per configurazioni dinamiche
COPY config/nginx/templates/ /etc/nginx/templates/

# Script di avvio personalizzato
COPY scripts/entrypoint.sh /docker-entrypoint.d/99-custom-setup.sh
RUN chmod +x /docker-entrypoint.d/99-custom-setup.sh

# Ottimizzazioni di sicurezza
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    find /usr/share/nginx/html -type f -exec chmod 644 {} \; && \
    find /usr/share/nginx/html -type d -exec chmod 755 {} \;

# Health check ottimizzato
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

EXPOSE 80

USER nginx

CMD ["nginx", "-g", "daemon off;"]