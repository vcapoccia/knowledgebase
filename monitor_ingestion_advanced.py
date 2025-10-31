#!/usr/bin/env python3
"""
Monitor Ingestion Avanzato
Monitora in tempo reale l'ingestion con statistiche dettagliate
"""

import sys
import time
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class IngestionMonitor:
    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url
        self.start_time = None
        self.last_done = 0
        self.speed_samples = []
        
    def clear_screen(self):
        """Pulisce lo schermo"""
        print("\033[2J\033[H", end="")
    
    def get_progress(self) -> Optional[Dict]:
        """Ottiene progress da API"""
        try:
            response = requests.get(f"{self.api_url}/progress", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_stats(self) -> Optional[Dict]:
        """Ottiene stats da API"""
        try:
            response = requests.get(f"{self.api_url}/stats", timeout=5)
            response.raise_for_status()
            return response.json()
        except:
            return {}
    
    def get_failed_docs(self, limit: int = 5) -> list:
        """Ottiene ultimi documenti falliti"""
        try:
            response = requests.get(f"{self.api_url}/failed_docs?limit={limit}", timeout=5)
            response.raise_for_status()
            return response.json()
        except:
            return []
    
    def format_time(self, seconds: float) -> str:
        """Formatta secondi in formato leggibile"""
        if seconds < 0:
            return "N/A"
        
        hours, remainder = divmod(int(seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def calculate_speed(self, done: int, elapsed: float) -> float:
        """Calcola velocità docs/sec"""
        if elapsed <= 0:
            return 0.0
        return done / elapsed
    
    def calculate_eta(self, done: int, total: int, speed: float) -> float:
        """Calcola tempo rimanente stimato"""
        if speed <= 0 or done >= total:
            return -1
        remaining = total - done
        return remaining / speed
    
    def draw_progress_bar(self, percent: float, width: int = 50) -> str:
        """Disegna progress bar"""
        filled = int(width * percent / 100)
        empty = width - filled
        
        if percent < 25:
            color = Colors.RED
        elif percent < 50:
            color = Colors.YELLOW
        elif percent < 75:
            color = Colors.CYAN
        else:
            color = Colors.GREEN
        
        bar = color + "█" * filled + Colors.END + "░" * empty
        return f"[{bar}] {percent:.1f}%"
    
    def format_number(self, num: int) -> str:
        """Formatta numero con separatori"""
        return f"{num:,}".replace(",", ".")
    
    def render_dashboard(self, progress: Dict, stats: Dict, failed: list):
        """Renderizza dashboard completa"""
        self.clear_screen()
        
        # Header
        print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.HEADER}🚀 KNOWLEDGEBASE INGESTION MONITOR{Colors.END}".center(80))
        print(f"{Colors.BOLD}{Colors.HEADER}{'=' * 80}{Colors.END}")
        print()
        
        # Check error
        if "error" in progress:
            print(f"{Colors.RED}❌ Errore connessione API: {progress['error']}{Colors.END}")
            print()
            print(f"Verifica che l'API sia running:")
            print(f"  docker compose ps api")
            print(f"  curl {self.api_url}/health")
            return
        
        # Status
        running = progress.get("running", False)
        done = progress.get("done", 0)
        total = progress.get("total", 0)
        status = progress.get("status", "unknown")
        current_doc = progress.get("current_doc", "N/A")
        
        # Calcola metriche
        percent = (done / total * 100) if total > 0 else 0
        
        # Tempo trascorso
        if running and self.start_time is None:
            self.start_time = datetime.now()
        elif not running:
            self.start_time = None
        
        elapsed = 0
        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
        
        # Velocità
        speed = self.calculate_speed(done, elapsed) if elapsed > 0 else 0
        
        # ETA
        eta_seconds = self.calculate_eta(done, total, speed)
        
        # Status indicator
        if running:
            status_icon = f"{Colors.GREEN}●{Colors.END} RUNNING"
        elif status == "done":
            status_icon = f"{Colors.BLUE}✓{Colors.END} COMPLETED"
        elif status == "failed":
            status_icon = f"{Colors.RED}✗{Colors.END} FAILED"
        else:
            status_icon = f"{Colors.YELLOW}○{Colors.END} IDLE"
        
        print(f"{Colors.BOLD}Status:{Colors.END} {status_icon}  |  {Colors.BOLD}Mode:{Colors.END} {progress.get('mode', 'N/A')}")
        print()
        
        # Progress bar
        print(f"{Colors.BOLD}Progress:{Colors.END}")
        print(self.draw_progress_bar(percent, width=60))
        print()
        
        # Statistiche principali
        print(f"{Colors.BOLD}📊 Statistics:{Colors.END}")
        print(f"  Documents:  {Colors.CYAN}{self.format_number(done)}{Colors.END} / {self.format_number(total)}")
        print(f"  Elapsed:    {Colors.CYAN}{self.format_time(elapsed)}{Colors.END}")
        print(f"  Speed:      {Colors.CYAN}{speed:.2f}{Colors.END} docs/sec")
        if eta_seconds >= 0:
            print(f"  ETA:        {Colors.GREEN}{self.format_time(eta_seconds)}{Colors.END}")
        else:
            print(f"  ETA:        {Colors.YELLOW}Calculating...{Colors.END}")
        print()
        
        # Dettagli processing
        if stats:
            print(f"{Colors.BOLD}🔍 Processing Details:{Colors.END}")
            success = stats.get("success", 0)
            failed_count = stats.get("failed", 0)
            chunked = stats.get("chunked", 0)
            meili_indexed = stats.get("meili_indexed", 0)
            qdrant_vectorized = stats.get("qdrant_vectorized", 0)
            
            success_rate = (success / done * 100) if done > 0 else 0
            
            print(f"  ✅ Success:         {Colors.GREEN}{self.format_number(success)}{Colors.END} ({success_rate:.1f}%)")
            print(f"  ❌ Failed:          {Colors.RED}{self.format_number(failed_count)}{Colors.END}")
            print(f"  📄 Chunks created:  {Colors.CYAN}{self.format_number(chunked)}{Colors.END}")
            print(f"  🔍 Meili indexed:   {Colors.CYAN}{self.format_number(meili_indexed)}{Colors.END}")
            print(f"  🎯 Qdrant vectors:  {Colors.CYAN}{self.format_number(qdrant_vectorized)}{Colors.END}")
            print()
        
        # Documento corrente
        if running and current_doc and current_doc != "N/A":
            print(f"{Colors.BOLD}📄 Current Document:{Colors.END}")
            # Tronca path se troppo lungo
            if len(current_doc) > 70:
                display_doc = "..." + current_doc[-67:]
            else:
                display_doc = current_doc
            print(f"  {Colors.YELLOW}{display_doc}{Colors.END}")
            print()
        
        # Documenti falliti
        if failed and len(failed) > 0:
            print(f"{Colors.BOLD}⚠️  Recent Failed Documents:{Colors.END}")
            for i, doc in enumerate(failed[:5], 1):
                path = doc.get("path", "N/A")
                error = doc.get("error", "Unknown error")
                
                # Tronca path
                if len(path) > 50:
                    path = "..." + path[-47:]
                
                # Tronca error
                if len(error) > 60:
                    error = error[:57] + "..."
                
                print(f"  {i}. {Colors.RED}{path}{Colors.END}")
                print(f"     {Colors.YELLOW}{error}{Colors.END}")
            print()
        
        # Footer
        print(f"{Colors.BOLD}{'─' * 80}{Colors.END}")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Last update: {timestamp}  |  Refresh: 2s  |  Press Ctrl+C to exit")
        
        # Update tracking
        self.last_done = done
    
    def run(self, interval: float = 2.0):
        """Loop principale di monitoraggio"""
        print(f"{Colors.BOLD}Starting monitor...{Colors.END}")
        print(f"Connecting to API at {self.api_url}")
        print()
        time.sleep(1)
        
        try:
            while True:
                progress = self.get_progress()
                stats = self.get_stats()
                failed = self.get_failed_docs(limit=5)
                
                self.render_dashboard(progress, stats, failed)
                
                time.sleep(interval)
        
        except KeyboardInterrupt:
            print()
            print(f"{Colors.YELLOW}Monitor stopped by user{Colors.END}")
            print()
        
        except Exception as e:
            print()
            print(f"{Colors.RED}Error: {e}{Colors.END}")
            print()

def main():
    """Entry point"""
    # Parse args
    api_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    monitor = IngestionMonitor(api_url)
    monitor.run(interval=2.0)

if __name__ == "__main__":
    main()
