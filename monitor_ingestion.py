#!/usr/bin/env python3
"""
monitor_ingestion.py - Monitor ingestion con statistiche real-time

Mostra:
- Progress ingestion
- Documenti processati / totali
- Errori raggruppati per tipo
- Velocità di processamento
- Formati file processati

Uso:
    python3 monitor_ingestion.py [--interval 2]
"""

import sys
import time
import requests
from collections import Counter
from datetime import datetime

API_BASE = "http://localhost:8000"
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--interval" else 2


def clear_screen():
    """Clear terminal"""
    print("\033[2J\033[H", end="")


def get_progress():
    """Ottieni progress da API"""
    try:
        r = requests.get(f"{API_BASE}/progress", timeout=2)
        return r.json()
    except:
        return {"running": False, "done": 0, "total": 0, "stage": "unavailable"}


def get_failed_docs():
    """Ottieni documenti falliti"""
    try:
        r = requests.get(f"{API_BASE}/failed_docs?limit=200", timeout=2)
        return r.json()
    except:
        return []


def get_queue_status():
    """Ottieni stato queue"""
    try:
        r = requests.get(f"{API_BASE}/queue", timeout=2)
        return r.json()
    except:
        return {}


def analyze_errors(failed_docs):
    """Analizza errori per categoria"""
    error_types = Counter()
    format_errors = Counter()
    
    for doc in failed_docs:
        error = doc.get("error", "")
        path = doc.get("path", "")
        
        # Categorizza errore
        if "File convertito non trovato" in error:
            error_types["LibreOffice conversione fallita"] += 1
            # Estrai estensione
            if path:
                import os
                ext = os.path.splitext(path)[1].lower()
                format_errors[f"LibreOffice fail: {ext}"] += 1
        
        elif "Formato non supportato" in error:
            error_types["Formato non supportato"] += 1
            # Estrai formato
            import re
            match = re.search(r'Formato non supportato: (\.\w+)', error)
            if match:
                format_errors[f"Non supportato: {match.group(1)}"] += 1
        
        elif "NUL (0x00) bytes" in error:
            error_types["PostgreSQL NULL bytes"] += 1
        
        elif "timeout" in error.lower():
            error_types["Timeout"] += 1
        
        else:
            error_types["Altri errori"] += 1
    
    return error_types, format_errors


def format_time(seconds):
    """Formatta tempo in HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def format_speed(docs_per_sec):
    """Formatta velocità"""
    if docs_per_sec > 1:
        return f"{docs_per_sec:.1f} docs/s"
    elif docs_per_sec > 0:
        secs_per_doc = 1 / docs_per_sec
        return f"{secs_per_doc:.1f} s/doc"
    else:
        return "N/A"


def draw_progress_bar(percentage, width=40):
    """Disegna progress bar"""
    filled = int(width * percentage / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {percentage:.1f}%"


def monitor():
    """Monitor loop principale"""
    
    start_time = time.time()
    last_done = 0
    last_time = start_time
    
    print("🚀 Monitor Ingestion KnowledgeBase")
    print("   Premi Ctrl+C per uscire")
    print()
    time.sleep(1)
    
    try:
        while True:
            clear_screen()
            
            current_time = time.time()
            elapsed = current_time - start_time
            
            # Ottieni dati
            progress = get_progress()
            failed = get_failed_docs()
            queue = get_queue_status()
            
            running = progress.get("running", False)
            done = progress.get("done", 0)
            total = progress.get("total", 0)
            stage = progress.get("stage", "unknown")
            
            # Calcola percentuale
            percentage = (done / total * 100) if total > 0 else 0
            
            # Calcola velocità
            docs_since_last = done - last_done
            time_since_last = current_time - last_time
            
            if time_since_last > 0:
                speed = docs_since_last / time_since_last
            else:
                speed = 0
            
            last_done = done
            last_time = current_time
            
            # ETA
            if speed > 0 and done < total:
                remaining_docs = total - done
                eta_seconds = remaining_docs / speed
                eta_str = format_time(eta_seconds)
            else:
                eta_str = "N/A"
            
            # Header
            print("=" * 80)
            print("🔍 KNOWLEDGE BASE INGESTION MONITOR")
            print("=" * 80)
            print()
            
            # Status
            status_icon = "🟢" if running else "⚪"
            print(f"{status_icon} Status: {'RUNNING' if running else 'STOPPED'}")
            print(f"📊 Stage: {stage}")
            print(f"⏱️  Elapsed: {format_time(elapsed)}")
            print()
            
            # Progress
            print("📈 PROGRESS")
            print("-" * 80)
            print(f"   {draw_progress_bar(percentage)}")
            print(f"   Documents: {done:,} / {total:,}")
            print(f"   Speed: {format_speed(speed)}")
            print(f"   ETA: {eta_str}")
            print()
            
            # Queue
            print("📋 QUEUE STATUS")
            print("-" * 80)
            if queue:
                print(f"   Count: {queue.get('count', 0)}")
                print(f"   Started: {queue.get('started', 0)}")
                print(f"   Failed: {queue.get('failed', 0)}")
            else:
                print("   N/A")
            print()
            
            # Errori
            if failed:
                error_types, format_errors = analyze_errors(failed)
                
                print("❌ ERRORS")
                print("-" * 80)
                print(f"   Total Failed: {len(failed)}")
                print()
                
                print("   By Type:")
                for error_type, count in error_types.most_common(10):
                    pct = (count / len(failed) * 100)
                    print(f"      • {error_type:40s} {count:4d} ({pct:5.1f}%)")
                
                if format_errors:
                    print()
                    print("   By Format:")
                    for fmt, count in format_errors.most_common(10):
                        print(f"      • {fmt:40s} {count:4d}")
                
                print()
                print(f"   📝 Ultimi 3 errori:")
                for i, doc in enumerate(failed[-3:], 1):
                    path = doc.get("path", "unknown")
                    error = doc.get("error", "")[:60]
                    import os
                    filename = os.path.basename(path) if path else "unknown"
                    print(f"      {i}. {filename}")
                    print(f"         {error}...")
            else:
                print("✅ NO ERRORS")
            
            print()
            print("=" * 80)
            print(f"🔄 Refresh every {INTERVAL}s | Press Ctrl+C to exit")
            
            time.sleep(INTERVAL)
    
    except KeyboardInterrupt:
        print("\n\n👋 Monitor stopped")
        
        # Summary finale
        progress = get_progress()
        failed = get_failed_docs()
        
        done = progress.get("done", 0)
        total = progress.get("total", 0)
        elapsed = time.time() - start_time
        
        print()
        print("📊 FINAL SUMMARY")
        print("=" * 80)
        print(f"   Total processed: {done:,} / {total:,}")
        print(f"   Failed: {len(failed):,}")
        print(f"   Success rate: {(done - len(failed)) / done * 100:.1f}%" if done > 0 else "N/A")
        print(f"   Total time: {format_time(elapsed)}")
        print(f"   Avg speed: {format_speed(done / elapsed if elapsed > 0 else 0)}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        sys.exit(0)
    
    monitor()
