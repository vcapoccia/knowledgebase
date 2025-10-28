#!/usr/bin/env python3
"""
Monitor real-time per ingestion knowledgebase
Mostra:
- Progress ingestion con ETA
- GPU usage e temperature
- Processi LibreOffice attivi
- Velocità processing
"""

import subprocess
import json
import time
import sys
from datetime import datetime, timedelta
from collections import deque

# Configurazione
API_URL = "http://localhost:8000/progress"
UPDATE_INTERVAL = 3  # secondi
HISTORY_SIZE = 20  # campioni per calcolare velocità

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

class IngestionMonitor:
    def __init__(self):
        self.history = deque(maxlen=HISTORY_SIZE)
        self.start_time = time.time()
        self.last_done = 0
        
    def get_progress(self):
        """Ottiene progress dall'API"""
        try:
            result = subprocess.run(
                ['curl', '-s', API_URL],
                capture_output=True,
                text=True,
                timeout=5
            )
            return json.loads(result.stdout)
        except Exception as e:
            return None
    
    def get_gpu_info(self):
        """Ottiene info GPU da nvidia-smi"""
        try:
            result = subprocess.run(
                ['docker', 'compose', 'exec', '-T', 'worker', 
                 'nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total',
                 '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=5,
                cwd='/opt/kbsearch'
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                return {
                    'usage': int(parts[0].strip()),
                    'temp': int(parts[1].strip()),
                    'mem_used': int(parts[2].strip()),
                    'mem_total': int(parts[3].strip())
                }
        except:
            pass
        return None
    
    def get_libreoffice_count(self):
        """Conta processi LibreOffice attivi"""
        try:
            result = subprocess.run(
                ['docker', 'compose', 'exec', '-T', 'worker', 
                 'ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5,
                cwd='/opt/kbsearch'
            )
            count = result.stdout.count('soffice')
            return count
        except:
            return 0
    
    def calculate_speed(self):
        """Calcola velocità di processing (file/sec)"""
        if len(self.history) < 2:
            return 0.0
        
        oldest = self.history[0]
        newest = self.history[-1]
        
        time_diff = newest['time'] - oldest['time']
        done_diff = newest['done'] - oldest['done']
        
        if time_diff > 0:
            return done_diff / time_diff
        return 0.0
    
    def estimate_eta(self, done, total, speed):
        """Stima tempo rimanente"""
        if speed <= 0 or done >= total:
            return None
        
        remaining = total - done
        seconds = remaining / speed
        return timedelta(seconds=int(seconds))
    
    def format_bar(self, percentage, width=40):
        """Crea barra di progresso colorata"""
        filled = int(width * percentage / 100)
        bar = '█' * filled + '░' * (width - filled)
        
        if percentage < 30:
            color = Colors.FAIL
        elif percentage < 70:
            color = Colors.WARNING
        else:
            color = Colors.OKGREEN
        
        return f"{color}{bar}{Colors.ENDC}"
    
    def display(self):
        """Display principale del monitor"""
        # Clear screen
        print('\033[2J\033[H', end='')
        
        # Header
        print(f"{Colors.HEADER}{Colors.BOLD}")
        print("╔════════════════════════════════════════════════════════════════════╗")
        print("║           🔍 KNOWLEDGEBASE INGESTION MONITOR 🔍                    ║")
        print("╚════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.ENDC}")
        
        # Timestamp
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = timedelta(seconds=int(time.time() - self.start_time))
        print(f"🕐 {now} | ⏱️  Uptime: {uptime}")
        print()
        
        # Progress
        progress = self.get_progress()
        if progress:
            done = progress.get('done', 0)
            total = progress.get('total', 1)
            percentage = (done / total * 100) if total > 0 else 0
            running = progress.get('running', False)
            stage = progress.get('stage', 'unknown')
            
            # Aggiungi a history
            self.history.append({
                'time': time.time(),
                'done': done
            })
            
            # Calcola velocità e ETA
            speed = self.calculate_speed()
            eta = self.estimate_eta(done, total, speed)
            
            # Display progress
            print(f"{Colors.BOLD}📊 PROGRESS:{Colors.ENDC}")
            print(f"   {self.format_bar(percentage)} {percentage:.1f}%")
            print(f"   📁 {done:,} / {total:,} files")
            
            status_icon = "🟢" if running else "🔴"
            status_text = f"{Colors.OKGREEN}RUNNING{Colors.ENDC}" if running else f"{Colors.WARNING}PAUSED{Colors.ENDC}"
            print(f"   {status_icon} Status: {status_text}")
            print(f"   📝 Stage: {stage}")
            
            if speed > 0:
                print(f"   ⚡ Speed: {speed:.2f} files/sec")
                if eta:
                    print(f"   ⏳ ETA: {eta}")
            
            # Mostra delta dall'ultimo update
            if self.last_done > 0:
                delta = done - self.last_done
                if delta > 0:
                    print(f"   {Colors.OKGREEN}📈 +{delta} files in last {UPDATE_INTERVAL}s{Colors.ENDC}")
                elif running:
                    print(f"   {Colors.WARNING}⚠️  No progress in last {UPDATE_INTERVAL}s{Colors.ENDC}")
            
            self.last_done = done
        else:
            print(f"{Colors.FAIL}❌ API non risponde{Colors.ENDC}")
        
        print()
        
        # GPU Info
        gpu = self.get_gpu_info()
        print(f"{Colors.BOLD}🎮 GPU STATUS:{Colors.ENDC}")
        if gpu:
            usage_color = Colors.OKGREEN if gpu['usage'] > 10 else Colors.FAIL
            temp_color = Colors.OKGREEN if gpu['temp'] < 80 else Colors.WARNING
            
            print(f"   {usage_color}█{Colors.ENDC} Usage: {gpu['usage']}%")
            print(f"   {temp_color}🌡️{Colors.ENDC} Temp: {gpu['temp']}°C")
            print(f"   💾 Memory: {gpu['mem_used']:,} / {gpu['mem_total']:,} MB")
            
            if gpu['usage'] < 5 and progress and progress.get('running'):
                print(f"   {Colors.WARNING}⚠️  GPU IDLE - Worker potrebbe essere bloccato!{Colors.ENDC}")
        else:
            print(f"   {Colors.FAIL}❌ GPU non disponibile o non accessibile{Colors.ENDC}")
        
        print()
        
        # LibreOffice processes
        lo_count = self.get_libreoffice_count()
        print(f"{Colors.BOLD}📄 LIBREOFFICE:{Colors.ENDC}")
        if lo_count == 0:
            print(f"   {Colors.OKGREEN}✅ Nessun processo attivo (OK){Colors.ENDC}")
        elif lo_count < 3:
            print(f"   {Colors.WARNING}⚠️  {lo_count} processi attivi{Colors.ENDC}")
        else:
            print(f"   {Colors.FAIL}❌ {lo_count} processi attivi - POSSIBILE PROBLEMA!{Colors.ENDC}")
            print(f"   {Colors.WARNING}💡 Considera di killare con: docker compose exec worker pkill -9 soffice{Colors.ENDC}")
        
        print()
        
        # Footer
        print("─" * 70)
        print(f"{Colors.OKCYAN}Press Ctrl+C to exit{Colors.ENDC}")
    
    def run(self):
        """Main loop"""
        print("Starting monitor...")
        time.sleep(1)
        
        try:
            while True:
                self.display()
                time.sleep(UPDATE_INTERVAL)
        except KeyboardInterrupt:
            print(f"\n\n{Colors.OKGREEN}Monitor stopped.{Colors.ENDC}")
            sys.exit(0)

if __name__ == '__main__':
    monitor = IngestionMonitor()
    monitor.run()
