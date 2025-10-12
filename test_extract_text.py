#!/usr/bin/env python3
"""
test_extract_text.py - Test estrazione testo da vari formati

Uso:
    python3 test_extract_text.py /path/to/test/files/
"""

import sys
import os
from pathlib import Path

# Importa funzione modificata
sys.path.insert(0, 'worker')
from worker_tasks import _read_text

def test_extraction(test_dir):
    """Testa estrazione da tutti i file nella directory"""
    
    test_dir = Path(test_dir)
    if not test_dir.exists():
        print(f"❌ Directory non trovata: {test_dir}")
        return
    
    # Trova file di test
    files = [f for f in test_dir.rglob("*") if f.is_file()]
    
    if not files:
        print(f"⚠️  Nessun file trovato in {test_dir}")
        return
    
    print(f"🧪 Test estrazione su {len(files)} file\n")
    
    results = {
        "success": [],
        "failed": []
    }
    
    for filepath in files:
        ext = filepath.suffix.lower()
        try:
            text = _read_text(str(filepath))
            text_len = len(text)
            preview = text[:100].replace("\n", " ")
            
            print(f"✅ {filepath.name}")
            print(f"   Ext: {ext}, Lunghezza: {text_len} char")
            print(f"   Preview: {preview}...")
            print()
            
            results["success"].append((filepath.name, ext, text_len))
            
        except Exception as e:
            print(f"❌ {filepath.name}")
            print(f"   Errore: {e}")
            print()
            results["failed"].append((filepath.name, ext, str(e)))
    
    # Riepilogo
    print("\n" + "="*60)
    print("📊 RIEPILOGO TEST")
    print("="*60)
    print(f"✅ Successi: {len(results['success'])}")
    print(f"❌ Fallimenti: {len(results['failed'])}")
    
    if results["success"]:
        print("\n✅ File estratti con successo:")
        for name, ext, length in results["success"]:
            print(f"   - {name} ({ext}): {length} char")
    
    if results["failed"]:
        print("\n❌ File falliti:")
        for name, ext, error in results["failed"]:
            print(f"   - {name} ({ext}): {error}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 test_extract_text.py /path/to/test/files/")
        sys.exit(1)
    
    test_extraction(sys.argv[1])
