#!/usr/bin/env python3
"""
Metadata Enrichment Script - KB Search
======================================

Arricchisce i metadati dei documenti già ingeriti analizzando i path esistenti
nel database PostgreSQL, senza dover re-ingestare tutti i file.

Pattern Supportati:
- ODA: ODA[SD][Lotto][Progressivo]_Cliente  (es. ODA2341_ATSBrescia)
- AS:  AS[SD][Lotto][Progressivo]_Cliente   (es. AS1101_AUSL_Romagna)
- SD:  _AQ/SD{n}/                           (es. SD2 → sd_numero=2)
- Fase: 01_Documentazione, 02_PianoOperativo, etc.

Nuovi Metadati Estratti:
- sd_numero: Numero Sanità Digitale (1,2,3...)
- lotto: Numero lotto (1,2,3...)
- progressivo_oda: Progressivo ODA (41, 1102...)
- progressivo_as: Progressivo AS (1101...)
- numero_rdo: Numero RDO per AS
- fase: Fase documento (Documentazione, Piano Operativo, etc.)

Usage:
    python enrich_metadata.py --analyze              # Solo analisi, no modifiche
    python enrich_metadata.py --update-schema        # Aggiorna schema DB
    python enrich_metadata.py --enrich               # Arricchisce metadati
    python enrich_metadata.py --reindex              # Reindex Meilisearch
    python enrich_metadata.py --all                  # Esegue tutto
"""

import re
import psycopg
import meilisearch
import argparse
from typing import Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime

# ========================
# CONFIGURAZIONE
# ========================

POSTGRES_DSN = "postgres://kbuser:kbpass@localhost:5432/kb"
MEILI_URL = "http://localhost:7700"
MEILI_KEY = "change_me_meili_key"

# ========================
# PATTERN REGEX
# ========================

class PathParser:
    """Parser avanzato per estrarre metadati dettagliati dai path"""
    
    # Pattern ODA: ODA[SD][Lotto][Progressivo]_Cliente
    # Progressivo: da 01 a 999 (2-3 cifre)
    # Esempi: ODA2341_ATSBrescia (prog: 41)
    #         ODA23100_ATSBrescia (prog: 100)
    #         ODA [2] [3] [41] _ATSBrescia
    #             SD  Lotto Prog  Cliente
    ODA_PATTERN = re.compile(
        r'/98_ODA/ODA(\d)(\d)(\d{2,3})_([^/]+)',
        re.IGNORECASE
    )
    
    # Pattern AS: AS[SD][Lotto][Progressivo]_[numeroRDO]_Cliente
    # Progressivo: da 01 a 999 (2-3 cifre)
    # Esempi: AS1101_3228734_AUSL_Romagna (prog: 01)
    #         AS11100_3228734_AUSL_Romagna (prog: 100)
    #         AS [1] [1] [01] _3228734_AUSL_Romagna
    #            SD  Lotto Prog  N.rdo    Cliente
    AS_PATTERN = re.compile(
        r'/99_AS/AS(\d)(\d)(\d{2,3})_(\d+)_([^/]+)',
        re.IGNORECASE
    )
    
    # Pattern SD: _AQ/SDn/
    SD_PATTERN = re.compile(r'/_AQ/SD(\d+)/', re.IGNORECASE)
    
    # Pattern Fase/Categoria
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
    
    # Pattern Anno_Cliente-Ambito (Gare)
    GARE_PATTERN = re.compile(
        r'/_Gare/(\d{4})_([^/-]+)-([^/]+)/',
        re.IGNORECASE
    )
    
    def parse_path(self, path: str) -> Dict[str, any]:
        """
        Estrae tutti i metadati possibili da un path.
        
        Returns:
            Dict con metadati estratti (solo campi popolati)
        """
        metadata = {}
        
        # 1. SD Numero (da _AQ/SDn/)
        sd_match = self.SD_PATTERN.search(path)
        if sd_match:
            metadata['sd_numero'] = int(sd_match.group(1))
        
        # 2. ODA Pattern
        oda_match = self.ODA_PATTERN.search(path)
        if oda_match:
            metadata['sd_numero'] = int(oda_match.group(1))  # Sovrascrive se presente
            metadata['lotto'] = int(oda_match.group(2))
            metadata['progressivo_oda'] = int(oda_match.group(3))
            cliente_raw = oda_match.group(4)
            metadata['cliente'] = self._normalize_cliente(cliente_raw)
            metadata['tipo_doc'] = 'ODA'
        
        # 3. AS Pattern
        as_match = self.AS_PATTERN.search(path)
        if as_match:
            metadata['sd_numero'] = int(as_match.group(1))
            metadata['lotto'] = int(as_match.group(2))
            metadata['progressivo_as'] = int(as_match.group(3))
            metadata['numero_rdo'] = as_match.group(4)
            cliente_raw = as_match.group(5)
            metadata['cliente'] = self._normalize_cliente(cliente_raw)
            metadata['tipo_doc'] = 'AS'
        
        # 4. Fase/Categoria
        for pattern, fase_name in self.FASE_PATTERNS.items():
            if re.search(pattern, path):
                metadata['fase'] = fase_name
                break
        
        # 5. Gare Pattern (Anno_Cliente-Ambito)
        gare_match = self.GARE_PATTERN.search(path)
        if gare_match:
            metadata['anno'] = int(gare_match.group(1))
            cliente_raw = gare_match.group(2)
            metadata['cliente'] = self._normalize_cliente(cliente_raw)
            metadata['oggetto'] = gare_match.group(3).replace('-', ' ').replace('_', ' ')
            metadata['tipo_doc'] = 'GARA'
        
        return metadata
    
    def _normalize_cliente(self, raw: str) -> str:
        """
        Normalizza nome cliente con CamelCase splitting.
        
        Esempi:
            ATSBrescia → ATS Brescia
            ULSS20VeronaAOPadova → ULSS20 Verona AO Padova
            AUSL_Romagna → AUSL Romagna
        """
        # Sostituisci underscore con spazi
        normalized = raw.replace('_', ' ')
        
        # Split CamelCase: inserisci spazio prima di maiuscole
        normalized = re.sub(r'([a-z])([A-Z])', r'\1 \2', normalized)
        normalized = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', normalized)
        
        # Pulisci spazi multipli
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized


# ========================
# DATABASE OPERATIONS
# ========================

class DatabaseManager:
    """Gestione operazioni su PostgreSQL"""
    
    def __init__(self, dsn: str):
        self.dsn = dsn
    
    def check_schema(self) -> Dict[str, bool]:
        """Verifica quali colonne esistono nel DB"""
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'documents'
                """)
                existing_columns = {row[0] for row in cur.fetchall()}
        
        required_columns = {
            'sd_numero': 'INTEGER',
            'lotto': 'INTEGER',
            'progressivo_oda': 'INTEGER',
            'progressivo_as': 'INTEGER',
            'numero_rdo': 'TEXT',
            'fase': 'TEXT'
        }
        
        return {
            col: col in existing_columns 
            for col in required_columns
        }
    
    def update_schema(self) -> Tuple[int, list]:
        """
        Aggiunge colonne mancanti al database.
        
        Returns:
            (num_added, list_of_added_columns)
        """
        schema_status = self.check_schema()
        missing_columns = [col for col, exists in schema_status.items() if not exists]
        
        if not missing_columns:
            return 0, []
        
        column_definitions = {
            'sd_numero': 'INTEGER',
            'lotto': 'INTEGER',
            'progressivo_oda': 'INTEGER',
            'progressivo_as': 'INTEGER',
            'numero_rdo': 'TEXT',
            'fase': 'TEXT'
        }
        
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                for col in missing_columns:
                    col_type = column_definitions[col]
                    print(f"  → Aggiungo colonna: {col} ({col_type})")
                    cur.execute(f"ALTER TABLE documents ADD COLUMN IF NOT EXISTS {col} {col_type}")
                
                # Crea indici per performance
                print(f"  → Creo indici...")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_sd_numero ON documents(sd_numero)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_lotto ON documents(lotto)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_progressivo_oda ON documents(progressivo_oda)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_fase ON documents(fase)")
                
                conn.commit()
        
        return len(missing_columns), missing_columns
    
    def get_all_documents(self) -> list:
        """Recupera tutti i documenti con i loro path"""
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, path, title, cliente, tipo_doc, anno, ext
                    FROM documents
                    ORDER BY id
                """)
                return cur.fetchall()
    
    def update_document_metadata(self, doc_id: str, metadata: Dict[str, any]) -> bool:
        """Aggiorna metadati di un singolo documento"""
        if not metadata:
            return False
        
        # Costruisci query dinamica con solo campi popolati
        set_clauses = []
        values = []
        
        for key, value in metadata.items():
            if value is not None:
                set_clauses.append(f"{key} = %s")
                values.append(value)
        
        if not set_clauses:
            return False
        
        values.append(doc_id)  # Per WHERE clause
        
        query = f"""
            UPDATE documents 
            SET {', '.join(set_clauses)}
            WHERE id = %s
        """
        
        with psycopg.connect(self.dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
                conn.commit()
        
        return True


# ========================
# MEILISEARCH OPERATIONS
# ========================

class MeilisearchManager:
    """Gestione reindex in Meilisearch"""
    
    def __init__(self, url: str, key: str):
        self.client = meilisearch.Client(url, key)
    
    def reindex_documents(self, index_name: str = "kb_docs") -> Tuple[int, int]:
        """
        Reindexizza tutti i documenti da PostgreSQL a Meilisearch.
        
        Returns:
            (success_count, error_count)
        """
        db = DatabaseManager(POSTGRES_DSN)
        docs = db.get_all_documents()
        
        # Prepara documenti per Meilisearch
        meili_docs = []
        for doc in docs:
            doc_id, path, title, cliente, tipo_doc, anno, ext = doc
            
            # Leggi tutti i metadati aggiornati
            with psycopg.connect(POSTGRES_DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            id, path, title, content, area, anno, cliente, oggetto,
                            tipo_doc, categoria, ext, codice_appalto, versione,
                            sd_numero, lotto, progressivo_oda, progressivo_as, numero_rdo, fase
                        FROM documents
                        WHERE id = %s
                    """, (doc_id,))
                    row = cur.fetchone()
            
            if not row:
                continue
            
            # Costruisci documento Meilisearch
            meili_doc = {
                'id': row[0],
                'path': row[1],
                'title': row[2],
                'content': row[3][:5000] if row[3] else '',  # Limita contenuto
            }
            
            # Aggiungi metadati se presenti
            fields = [
                'area', 'anno', 'cliente', 'oggetto', 'tipo_doc', 'categoria',
                'ext', 'codice_appalto', 'versione', 'sd_numero', 'lotto',
                'progressivo_oda', 'progressivo_as', 'numero_rdo', 'fase'
            ]
            
            for i, field in enumerate(fields, start=4):
                if row[i] is not None:
                    meili_doc[field] = row[i]
            
            meili_docs.append(meili_doc)
        
        # Invia batch a Meilisearch
        try:
            index = self.client.index(index_name)
            
            # Configura filterable attributes
            index.update_filterable_attributes([
                'area', 'anno', 'cliente', 'tipo_doc', 'categoria', 'ext',
                'sd_numero', 'lotto', 'fase', 'progressivo_oda', 'progressivo_as'
            ])
            
            # Batch insert
            batch_size = 100
            success = 0
            errors = 0
            
            for i in range(0, len(meili_docs), batch_size):
                batch = meili_docs[i:i+batch_size]
                try:
                    index.add_documents(batch)
                    success += len(batch)
                    print(f"  → Indicizzati {success}/{len(meili_docs)} documenti")
                except Exception as e:
                    errors += len(batch)
                    print(f"  ✗ Errore batch {i}: {e}")
            
            return success, errors
        
        except Exception as e:
            print(f"✗ Errore Meilisearch: {e}")
            return 0, len(meili_docs)


# ========================
# MAIN ENRICHMENT LOGIC
# ========================

def analyze_paths(db: DatabaseManager, parser: PathParser):
    """Analizza tutti i path e mostra statistiche sui metadati estratti"""
    print("\n🔍 ANALISI PATH E METADATI\n")
    
    docs = db.get_all_documents()
    total = len(docs)
    
    stats = defaultdict(int)
    metadata_coverage = defaultdict(int)
    examples = defaultdict(list)
    
    for doc in docs:
        doc_id, path, title, cliente, tipo_doc, anno, ext = doc
        
        # Parsa metadati
        metadata = parser.parse_path(path)
        
        # Statistiche
        if metadata:
            stats['has_metadata'] += 1
            for key in metadata:
                metadata_coverage[key] += 1
                
                # Salva esempi
                if len(examples[key]) < 3:
                    examples[key].append({
                        'path': path,
                        'value': metadata[key]
                    })
        else:
            stats['no_metadata'] += 1
    
    # Report
    print(f"📊 Documenti totali: {total}")
    print(f"   ├─ Con metadati estratti: {stats['has_metadata']} ({stats['has_metadata']/total*100:.1f}%)")
    print(f"   └─ Senza metadati: {stats['no_metadata']} ({stats['no_metadata']/total*100:.1f}%)")
    
    print(f"\n📈 Coverage per tipo di metadato:")
    for key, count in sorted(metadata_coverage.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"   • {key:20s}: {count:5d} documenti ({pct:5.1f}%)")
    
    print(f"\n📝 Esempi di estrazione:")
    for key, example_list in examples.items():
        print(f"\n   {key}:")
        for ex in example_list[:2]:
            print(f"      Path: {ex['path'][:80]}...")
            print(f"      →  {key} = {ex['value']}")


def enrich_all_documents(db: DatabaseManager, parser: PathParser, dry_run: bool = False):
    """
    Arricchisce tutti i documenti con nuovi metadati.
    
    Args:
        dry_run: Se True, non modifica il DB (solo simula)
    """
    print(f"\n{'🔄 SIMULAZIONE' if dry_run else '✍️  ENRICHMENT'} METADATI\n")
    
    docs = db.get_all_documents()
    total = len(docs)
    
    updated = 0
    skipped = 0
    
    for i, doc in enumerate(docs, 1):
        doc_id, path, title, cliente, tipo_doc, anno, ext = doc
        
        # Parsa metadati
        metadata = parser.parse_path(path)
        
        if metadata:
            if not dry_run:
                db.update_document_metadata(doc_id, metadata)
            updated += 1
            
            if i % 100 == 0:
                print(f"  → Processati {i}/{total} documenti ({updated} aggiornati)")
        else:
            skipped += 1
    
    print(f"\n{'✓' if not dry_run else 'ℹ'} Completato:")
    print(f"   • Documenti aggiornati: {updated}")
    print(f"   • Documenti saltati: {skipped}")
    
    if dry_run:
        print(f"\n⚠️  MODALITÀ DRY-RUN: Nessuna modifica effettuata al database")


# ========================
# CLI
# ========================

def main():
    parser_cli = argparse.ArgumentParser(
        description="Enrichment metadati KB Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser_cli.add_argument('--analyze', action='store_true',
                            help='Analizza path e mostra statistiche (sola lettura)')
    parser_cli.add_argument('--update-schema', action='store_true',
                            help='Aggiorna schema PostgreSQL aggiungendo colonne')
    parser_cli.add_argument('--enrich', action='store_true',
                            help='Arricchisce metadati esistenti')
    parser_cli.add_argument('--dry-run', action='store_true',
                            help='Simula enrichment senza modificare DB')
    parser_cli.add_argument('--reindex', action='store_true',
                            help='Reindexizza Meilisearch con nuovi metadati')
    parser_cli.add_argument('--all', action='store_true',
                            help='Esegue: update-schema + enrich + reindex')
    
    args = parser_cli.parse_args()
    
    # Inizializza managers
    db = DatabaseManager(POSTGRES_DSN)
    parser = PathParser()
    meili = MeilisearchManager(MEILI_URL, MEILI_KEY)
    
    print("=" * 60)
    print("KB SEARCH - METADATA ENRICHMENT")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Azioni
    if args.all:
        args.update_schema = True
        args.enrich = True
        args.reindex = True
    
    # 1. Analisi
    if args.analyze or not any([args.update_schema, args.enrich, args.reindex]):
        analyze_paths(db, parser)
    
    # 2. Update schema
    if args.update_schema:
        print("\n🔧 UPDATE SCHEMA POSTGRESQL\n")
        num_added, columns = db.update_schema()
        if num_added > 0:
            print(f"✓ Aggiunte {num_added} colonne: {', '.join(columns)}")
        else:
            print("✓ Schema già aggiornato, nessuna modifica necessaria")
    
    # 3. Enrichment
    if args.enrich:
        enrich_all_documents(db, parser, dry_run=args.dry_run)
    
    # 4. Reindex
    if args.reindex and not args.dry_run:
        print("\n🔄 REINDEX MEILISEARCH\n")
        success, errors = meili.reindex_documents()
        print(f"\n✓ Reindex completato:")
        print(f"   • Successi: {success}")
        print(f"   • Errori: {errors}")
    
    print("\n" + "=" * 60)
    print("✓ Operazione completata!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
