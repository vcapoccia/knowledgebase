#!/bin/bash
#
# LibreOffice Watchdog - Kill processi zombie automaticamente
#

LOG_FILE="/opt/kbsearch/logs/libreoffice_watchdog.log"
CONTAINER="kbsearch-worker-1"
CHECK_INTERVAL=600  # 10 minuti
MAX_PROCESS_AGE=300  # 5 minuti (kill se più vecchio)

mkdir -p /opt/kbsearch/logs

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

kill_hanging_libreoffice() {
    log "🔍 Checking LibreOffice processes..."
    
    # Conta processi
    PROCESS_COUNT=$(docker exec $CONTAINER pgrep -c soffice 2>/dev/null || echo 0)
    
    if [ "$PROCESS_COUNT" -eq 0 ]; then
        log "✅ No LibreOffice processes running"
        return
    fi
    
    log "⚠️  Found $PROCESS_COUNT LibreOffice process(es)"
    
    # Kill tutti se più di 3 (sicuramente zombie)
    if [ "$PROCESS_COUNT" -gt 3 ]; then
        log "🚨 Too many processes ($PROCESS_COUNT)! Killing ALL"
        docker exec $CONTAINER pkill -9 soffice
        log "💀 Killed all LibreOffice processes"
        return
    fi
    
    # Altrimenti kill solo vecchi (>10 min)
    docker exec $CONTAINER ps -eo pid,etime,comm | grep soffice | while read pid etime comm; do
        # Estrai minuti da etime
        if [[ $etime =~ ([0-9]+):([0-9]+) ]]; then
            minutes=${BASH_REMATCH[1]}
            seconds=${BASH_REMATCH[2]}
            total_seconds=$((minutes*60 + seconds))
        elif [[ $etime =~ ([0-9]+):([0-9]+):([0-9]+) ]]; then
            hours=${BASH_REMATCH[1]}
            minutes=${BASH_REMATCH[2]}
            seconds=${BASH_REMATCH[3]}
            total_seconds=$((hours*3600 + minutes*60 + seconds))
        else
            total_seconds=0
        fi
        
        if [ $total_seconds -gt $MAX_PROCESS_AGE ]; then
            log "💀 Killing old PID $pid (age: ${etime})"
            docker exec $CONTAINER kill -9 $pid 2>/dev/null
        else
            log "⏳ PID $pid still fresh (${etime})"
        fi
    done
}

# Startup
log "=================================="
log "🚀 LibreOffice Watchdog STARTED"
log "   Check interval: ${CHECK_INTERVAL}s (20 minutes)"
log "   Max process age: ${MAX_PROCESS_AGE}s (10 minutes)"
log "   Container: $CONTAINER"
log "=================================="

# Main loop
while true; do
    kill_hanging_libreoffice
    log "😴 Sleeping for 20 minutes..."
    sleep $CHECK_INTERVAL
done
