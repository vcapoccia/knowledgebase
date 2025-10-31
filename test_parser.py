#!/usr/bin/env python3
"""
Test Parser Metadati - Verifica su Path Reali
==============================================

Script di test che mostra come il parser estrae metadati dai path reali
presenti nel database PostgreSQL, SENZA modificare nulla.

Utile per:
- Verificare che il parser funzioni correttamente
- Vedere esempi concreti di estrazione
- Identificare pattern non riconosciuti

Usage:
    python3 test_parser.py                    # Test su 50 path casuali
    python3 test_parser.py --samples 100      # Test su 100 path
    python3 test_parser.py --filter ODA       # Solo path contenenti "ODA"
    python3 test_parser.py --verbose          # Mostra dettagli per ogni path
"""

import re
import psycopg
import argparse
from collections import defaultdict, Counter
from typing import Dict, Optional

# Configurazione
POSTGRES_DSN = "postgres://kbuser:kbpass@localhost:5432/kb"

# ========================
# STESSO PARSER DA enrich_metadata.py
# ========================

class PathParser:
    """Parser avanzato per estrarre metadati dettagliati dai path"""
    
    ODA_PATTERN = re.compile(r'/98_ODA/ODA(\d)(\d)(\d{2,3})_([^/]+)', re.IGNORECASE)
    AS_PATTERN = re.compile(r'/99_AS/AS(\d)(\d)(\d{2,3})_(\d+)_([^/]+)', re.IGNORECASE)
    SD_PATTERN = re.compile(r'/_AQ/SD(\d+)/', re.IGNORECASE)
    
    FASE_PATTERNS = {
        r'/01_Documentazione/': 'Documentazione',
        r'/02_Chiarimenti/': 'Chiarimenti',
        r'/02_chiarimenti/': 'Chiarimenti',
        r'/04_OffertaTecnica/': 'Offerta Tecnica',
        r'/04_offertaTecnica/': 'Offerta Tecnica',
        r'/08_AccessoAgliAtti/': 'Accesso Atti',
        r'/01_Preliminare/': 'Preliminare',
        r'/02_PianoOperativo/': 'Piano Operativo',
    }
    
    GARE_PATTERN = re.compile(r'/_Gare/(\d{4})_([^/-]+)-([^/]+)/', re.IGNORECASE)
    
    def parse_path(self, path: str) -> Dict[str, any]:
        """Estrae tutti i metadati possibili da un path"""
        metadata = {}
        
        # SD Numero
        sd_match = self.SD_PATTERN.search(path)
        if sd_match:
            metadata['sd_numero'] = int(sd_match.group(1))
        
        # ODA Pattern
        oda_match = self.ODA_PATTERN.search(path)
        if oda_match:
            metadata['sd_numero'] = int(oda_match.group(1))
            metadata['lotto'] = int(oda_match.group(2))
            metadata['progressivo_oda'] = int(oda_match.group(3))
            cliente_raw = oda_match.group(4)
            metadata['cliente'] = self._normalize_cliente(cliente_raw)
            metadata['tipo_doc'] = 'ODA'
        
        # AS Pattern
        as_match = self.AS_PATTERN.search(path)
        if as_match:
            metadata['sd_numero'] = int(as_match.group(1))
            metadata['lotto'] = int(as_match.group(2))
            metadata['progressivo_as'] = int(as_match.group(3))
            metadata['numero_rdo'] = as_match.group(4)
            cliente_raw = as_match.group(5)
            metadata['cliente'] = self._normalize_cliente(cliente_raw)
            metadata['tipo_doc'] = 'AS'
        
        # Fase
        for pattern, fase_name in self.FASE_PATTERNS.items():
            if re.search(pattern, path):
                metadata['fase'] = fase_name
                break
        
        # Gare
        gare_match = self.GARE_PATTERN.search(path)
        if gare_match:
            metadata['anno'] = int(gare_match.group(1))
            cliente_raw = gare_match.group(2)
            metadata['cliente'] = self._normalize_cliente(cliente_raw)
            metadata['oggetto'] = gare_match.group(3).replace('-', ' ').replace('_', ' ')
            metadata['tipo_doc'] = 'GARA'
        
        return metadata
    
    def _normalize_cliente(self, raw: str) -> str:
        """Normalizza nome cliente con CamelCase splitting"""
        normalized = raw.replace('_', ' ')
        normalized = re.sub(r'([a-z])([A-Z])', r'\1 \2', normalized)
        normalized = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized


# ========================
# TEST FUNCTIONS
# ========================

def get_sample_paths(filter_str: str = None, limit: int = 50) -> list:
    """Recupera path di esempio dal database"""
    with psycopg.connect(POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            if filter_str:
                cur.execute("""
                    SELECT id, path, title 
                    FROM documents 
                    WHERE path LIKE %s
                    ORDER BY RANDOM()
                    LIMIT %s
                """, (f'%{filter_str}%', limit))
            else:
                cur.execute("""
                    SELECT id, path, title 
                    FROM documents 
                    ORDER BY RANDOM()
                    LIMIT %s
                """, (limit,))
            
            return cur.fetchall()


def test_parser_on_samples(samples: int = 50, filter_str: str = None, verbose: bool = False):
    """Testa il parser su un campione di path reali"""
    
    print("=" * 80)
    print("TEST PARSER METADATI - PATH REALI")
    print("=" * 80)
    
    # Recupera sample
    print(f"\n🔍 Recupero {samples} path dal database", end="")
    if filter_str:
        print(f" (filtro: '{filter_str}')", end="")
    print("...\n")
    
    paths = get_sample_paths(filter_str, samples)
    
    if not paths:
        print("❌ Nessun path trovato!")
        return
    
    print(f"✓ Recuperati {len(paths)} path\n")
    
    # Inizializza parser
    parser = PathParser()
    
    # Statistiche
    stats = {
        'total': len(paths),
        'with_metadata': 0,
        'without_metadata': 0,
    }
    metadata_counter = defaultdict(int)
    tipo_doc_counter = Counter()
    fase_counter = Counter()
    
    # Processa paths
    examples_by_type = defaultdict(list)
    
    for doc_id, path, title in paths:
        metadata = parser.parse_path(path)
        
        if metadata:
            stats['with_metadata'] += 1
            
            # Conta metadati estratti
            for key in metadata:
                metadata_counter[key] += 1
            
            # Conta tipi documento
            if 'tipo_doc' in metadata:
                tipo_doc_counter[metadata['tipo_doc']] += 1
            
            # Conta fasi
            if 'fase' in metadata:
                fase_counter[metadata['fase']] += 1
            
            # Salva esempi per tipo
            tipo = metadata.get('tipo_doc', 'ALTRO')
            if len(examples_by_type[tipo]) < 3:
                examples_by_type[tipo].append({
                    'path': path,
                    'title': title,
                    'metadata': metadata
                })
            
            # Verbose output
            if verbose:
                print(f"📄 {title[:60]}")
                print(f"   Path: {path[:70]}...")
                print(f"   Metadati estratti:")
                for key, value in metadata.items():
                    print(f"      • {key:20s} = {value}")
                print()
        
        else:
            stats['without_metadata'] += 1
    
    # ========================
    # REPORT
    # ========================
    
    print("\n" + "=" * 80)
    print("📊 STATISTICHE ESTRAZIONE")
    print("=" * 80)
    
    print(f"\n📁 Path totali analizzati: {stats['total']}")
    pct_with = stats['with_metadata'] / stats['total'] * 100
    pct_without = stats['without_metadata'] / stats['total'] * 100
    print(f"   ├─ Con metadati estratti:  {stats['with_metadata']:4d} ({pct_with:5.1f}%)")
    print(f"   └─ Senza metadati:         {stats['without_metadata']:4d} ({pct_without:5.1f}%)")
    
    print(f"\n📈 Coverage per tipo di metadato:")
    for key, count in sorted(metadata_counter.items(), key=lambda x: -x[1]):
        pct = count / stats['with_metadata'] * 100
        print(f"   • {key:20s}: {count:4d} / {stats['with_metadata']} ({pct:5.1f}%)")
    
    if tipo_doc_counter:
        print(f"\n📋 Distribuzione per tipo documento:")
        for tipo, count in tipo_doc_counter.most_common():
            pct = count / stats['with_metadata'] * 100
            print(f"   • {tipo:10s}: {count:4d} ({pct:5.1f}%)")
    
    if fase_counter:
        print(f"\n🗂️  Distribuzione per fase:")
        for fase, count in fase_counter.most_common():
            pct = count / stats['with_metadata'] * 100
            print(f"   • {fase:20s}: {count:4d} ({pct:5.1f}%)")
    
    # Esempi per tipo
    if not verbose and examples_by_type:
        print(f"\n" + "=" * 80)
        print("📝 ESEMPI DI ESTRAZIONE PER TIPO")
        print("=" * 80)
        
        for tipo, examples in sorted(examples_by_type.items()):
            print(f"\n🔸 {tipo}")
            print("-" * 80)
            
            for ex in examples[:2]:  # Max 2 esempi per tipo
                print(f"\n  📄 Titolo: {ex['title']}")
                print(f"     Path: {ex['path'][:70]}...")
                print(f"     Metadati estratti:")
                for key, value in ex['metadata'].items():
                    print(f"        • {key:20s} = {value}")
    
    print("\n" + "=" * 80)
    print("✓ Test completato!")
    print("=" * 80 + "\n")


def show_pattern_examples():
    """Mostra esempi di pattern riconosciuti"""
    print("=" * 80)
    print("🎯 PATTERN RICONOSCIUTI DAL PARSER")
    print("=" * 80)
    
    examples = [
        {
            "nome": "ODA (Ordine Di Acquisto)",
            "pattern": "ODA[SD][Lotto][Progressivo]_Cliente",
            "esempi": [
                {
                    "path": "_AQ/SD2/98_ODA/ODA2341_ATSBrescia/02_PianoOperativo/doc.pdf",
                    "estratto": {
                        "sd_numero": 2,
                        "lotto": 3,
                        "progressivo_oda": 41,
                        "cliente": "ATS Brescia",
                        "tipo_doc": "ODA",
                        "fase": "Piano Operativo"
                    }
                },
                {
                    "path": "_AQ/SD1/98_ODA/ODA1102_ValleOlona/01_Preliminare/doc.pdf",
                    "estratto": {
                        "sd_numero": 1,
                        "lotto": 1,
                        "progressivo_oda": 2,
                        "cliente": "Valle Olona",
                        "tipo_doc": "ODA",
                        "fase": "Preliminare"
                    }
                }
            ]
        },
        {
            "nome": "AS (Appalto Specifico)",
            "pattern": "AS[SD][Lotto][Progressivo]_[RDO]_Cliente",
            "esempi": [
                {
                    "path": "_AQ/SD1/99_AS/AS1101_3228734_AUSL_Romagna/04_OffertaTecnica/doc.pdf",
                    "estratto": {
                        "sd_numero": 1,
                        "lotto": 1,
                        "progressivo_as": 1,
                        "numero_rdo": "3228734",
                        "cliente": "AUSL Romagna",
                        "tipo_doc": "AS",
                        "fase": "Offerta Tecnica"
                    }
                }
            ]
        },
        {
            "nome": "GARA",
            "pattern": "ANNO_Cliente-Ambito",
            "esempi": [
                {
                    "path": "_Gare/2015_ULSS20VeronaAOPadova-OutsourcingSistemaICT/01_Documentazione/doc.pdf",
                    "estratto": {
                        "anno": 2015,
                        "cliente": "ULSS20 Verona AO Padova",
                        "oggetto": "Outsourcing Sistema ICT",
                        "tipo_doc": "GARA",
                        "fase": "Documentazione"
                    }
                }
            ]
        }
    ]
    
    for ex in examples:
        print(f"\n{'=' * 80}")
        print(f"🔸 {ex['nome']}")
        print(f"   Pattern: {ex['pattern']}")
        print(f"{'=' * 80}")
        
        for i, esempio in enumerate(ex['esempi'], 1):
            print(f"\n  Esempio {i}:")
            print(f"  Path: {esempio['path']}")
            print(f"  ")
            print(f"  Metadati estratti:")
            for key, value in esempio['estratto'].items():
                print(f"     • {key:20s} = {value}")
    
    print(f"\n{'=' * 80}\n")


# ========================
# CLI
# ========================

def main():
    parser_cli = argparse.ArgumentParser(
        description="Test parser metadati su path reali del database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser_cli.add_argument('--samples', type=int, default=50,
                            help='Numero di path da testare (default: 50)')
    parser_cli.add_argument('--filter', type=str, default=None,
                            help='Filtra path contenenti questa stringa (es: "ODA", "AS", "_Gare")')
    parser_cli.add_argument('--verbose', '-v', action='store_true',
                            help='Mostra dettagli per ogni path testato')
    parser_cli.add_argument('--examples', action='store_true',
                            help='Mostra esempi di pattern riconosciuti')
    
    args = parser_cli.parse_args()
    
    if args.examples:
        show_pattern_examples()
    else:
        test_parser_on_samples(
            samples=args.samples,
            filter_str=args.filter,
            verbose=args.verbose
        )


if __name__ == "__main__":
    main()
