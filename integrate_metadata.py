#!/usr/bin/env python3
"""
integrate_metadata.py - Integra automaticamente metadata_extractor.py nel worker

Questo script:
1. Copia metadata_extractor.py nel worker
2. Aggiorna worker_tasks.py con import e logica metadati
3. Aggiorna schema PostgreSQL
4. Configura Meilisearch per filtri avanzati
5. Crea backup di tutti i file modificati

Uso:
    python3 integrate_metadata.py [--dry-run]
"""

import os
import sys
import shutil
from datetime import datetime

DRY_RUN = "--dry-run" in sys.argv

def log(msg, icon="ℹ️"):
    print(f"{icon} {msg}")

def backup_file(filepath):
    """Crea backup con timestamp"""
    if not os.path.exists(filepath):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{filepath}.backup.{timestamp}"
    
    if DRY_RUN:
        log(f"[DRY-RUN] Backup: {filepath} → {backup_path}", "💾")
        return backup_path
    
    shutil.copy2(filepath, backup_path)
    log(f"Backup creato: {backup_path}", "💾")
    return backup_path

def update_worker_tasks():
    """Aggiorna worker/worker_tasks.py con estrazione metadati"""
    
    filepath = "worker/worker_tasks.py"
    
    if not os.path.exists(filepath):
        log(f"File non trovato: {filepath}", "❌")
        return False
    
    backup_file(filepath)
    
    with open(filepath, "r") as f:
        content = f.read()
    
    # 1. Aggiungi import
    import_line = "from metadata_extractor import extract_metadata\n"
    if "from metadata_extractor" not in content:
        # Aggiungi dopo altri import
        import_pos = content.find("import meilisearch")
        if import_pos != -1:
            next_line = content.find("\n", import_pos)
            content = content[:next_line+1] + import_line + content[next_line+1:]
            log("Import aggiunto", "✅")
        else:
            log("Posizione import non trovata", "⚠️")
    else:
        log("Import già presente", "ℹ️")
    
    # 2. Aggiorna schema PostgreSQL
    old_schema = '''CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT,
            content TEXT,
            mtime TIMESTAMP DEFAULT NOW()
        );'''
    
    new_schema = '''CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT,
            content TEXT,
            mtime TIMESTAMP DEFAULT NOW(),
            
            -- Metadati estratti
            area TEXT,
            anno TEXT,
            cliente TEXT,
            oggetto TEXT,
            tipo_doc TEXT,
            codice_appalto TEXT,
            categoria TEXT,
            descrizione_oggetto TEXT,
            versione TEXT,
            ext TEXT
        );
        """)
        
        -- Indici per performance ricerca
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_area ON documents(area);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_anno ON documents(anno);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_cliente ON documents(cliente);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_oggetto ON documents(oggetto);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_tipo_doc ON documents(tipo_doc);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_categoria ON documents(categoria);'''
    
    if old_schema in content:
        content = content.replace(old_schema, new_schema)
        log("Schema PostgreSQL aggiornato", "✅")
    else:
        log("Schema PostgreSQL già aggiornato o non trovato", "⚠️")
    
    # 3. Aggiorna INSERT con metadati
    old_insert = '''cur.execute("""
                    INSERT INTO documents (id, path, title, content)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE
                    SET path=EXCLUDED.path, title=EXCLUDED.title, content=EXCLUDED.content, mtime=NOW()
                """, (rel_id, path, title, text))'''
    
    new_insert = '''# Estrai metadati dal path
                metadata = extract_metadata(path, KB_ROOT)
                
                cur.execute("""
                    INSERT INTO documents (
                        id, path, title, content, 
                        area, anno, cliente, oggetto, tipo_doc, 
                        codice_appalto, categoria, descrizione_oggetto, versione, ext
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        path=EXCLUDED.path, 
                        title=EXCLUDED.title, 
                        content=EXCLUDED.content,
                        area=EXCLUDED.area,
                        anno=EXCLUDED.anno,
                        cliente=EXCLUDED.cliente,
                        oggetto=EXCLUDED.oggetto,
                        tipo_doc=EXCLUDED.tipo_doc,
                        codice_appalto=EXCLUDED.codice_appalto,
                        categoria=EXCLUDED.categoria,
                        descrizione_oggetto=EXCLUDED.descrizione_oggetto,
                        versione=EXCLUDED.versione,
                        ext=EXCLUDED.ext,
                        mtime=NOW()
                """, (
                    rel_id, path, title, text,
                    metadata.get('area'), 
                    metadata.get('anno'),
                    metadata.get('cliente'),
                    metadata.get('oggetto'),
                    metadata.get('tipo_doc'),
                    metadata.get('codice_appalto'),
                    metadata.get('categoria'),
                    metadata.get('descrizione_oggetto'),
                    metadata.get('versione'),
                    metadata.get('ext')
                ))'''
    
    if old_insert in content:
        content = content.replace(old_insert, new_insert)
        log("INSERT PostgreSQL aggiornato", "✅")
    else:
        log("INSERT già aggiornato o pattern non trovato", "⚠️")
    
    # 4. Aggiorna batch Meilisearch
    old_batch = '''batch.append({"id": rel_id, "path": path, "title": title, "content": text})'''
    
    new_batch = '''batch.append({
                    "id": rel_id, 
                    "path": path, 
                    "title": title, 
                    "content": text,
                    "area": metadata.get('area'),
                    "anno": metadata.get('anno'),
                    "cliente": metadata.get('cliente'),
                    "oggetto": metadata.get('oggetto'),
                    "tipo_doc": metadata.get('tipo_doc'),
                    "codice_appalto": metadata.get('codice_appalto'),
                    "categoria": metadata.get('categoria'),
                    "descrizione_oggetto": metadata.get('descrizione_oggetto'),
                    "ext": metadata.get('ext')
                })'''
    
    if old_batch in content:
        content = content.replace(old_batch, new_batch)
        log("Batch Meilisearch aggiornato", "✅")
    else:
        log("Batch già aggiornato o pattern non trovato", "⚠️")
    
    # Salva file aggiornato
    if DRY_RUN:
        output_path = filepath + ".NEW"
        log(f"[DRY-RUN] File salvato in: {output_path}", "📝")
    else:
        output_path = filepath + ".NEW"
        
    with open(output_path, "w") as f:
        f.write(content)
    
    log(f"File aggiornato: {output_path}", "✅")
    log(f"Verifica con: diff {filepath} {output_path}", "🔍")
    log(f"Applica con: mv {output_path} {filepath}", "🚀")
    
    return True


def update_route_admin_filters():
    """Aggiorna api/route_admin.py per endpoint /filters avanzato"""
    
    filepath = "api/route_admin.py"
    
    if not os.path.exists(filepath):
        log(f"File non trovato: {filepath}", "❌")
        return False
    
    backup_file(filepath)
    
    with open(filepath, "r") as f:
        content = f.read()
    
    new_filters_endpoint = '''@router.get("/filters")
def filters():
    """
    Estrae valori unici per TUTTI i filtri disponibili.
    
    Returns:
        Dict con: areas, anni, clienti, oggetti, tipi_doc, categorie, extensions
    """
    try:
        with pg_conn() as conn, conn.cursor() as cur:
            # Aree
            cur.execute("SELECT DISTINCT area FROM documents WHERE area IS NOT NULL ORDER BY area")
            areas = [r['area'] for r in cur.fetchall()]
            
            # Anni
            cur.execute("SELECT DISTINCT anno FROM documents WHERE anno IS NOT NULL ORDER BY anno DESC")
            anni = [r['anno'] for r in cur.fetchall()]
            
            # Clienti (top 50 più frequenti)
            cur.execute("""
                SELECT cliente, COUNT(*) as cnt 
                FROM documents 
                WHERE cliente IS NOT NULL 
                GROUP BY cliente 
                ORDER BY cnt DESC, cliente 
                LIMIT 50
            """)
            clienti = [r['cliente'] for r in cur.fetchall()]
            
            # Oggetti/Temi
            cur.execute("SELECT DISTINCT oggetto FROM documents WHERE oggetto IS NOT NULL ORDER BY oggetto")
            oggetti = [r['oggetto'] for r in cur.fetchall()]
            
            # Tipi Documento
            cur.execute("SELECT DISTINCT tipo_doc FROM documents WHERE tipo_doc IS NOT NULL ORDER BY tipo_doc")
            tipi_doc = [r['tipo_doc'] for r in cur.fetchall()]
            
            # Categorie
            cur.execute("SELECT DISTINCT categoria FROM documents WHERE categoria IS NOT NULL ORDER BY categoria")
            categorie = [r['categoria'] for r in cur.fetchall()]
            
            # Estensioni
            cur.execute("SELECT DISTINCT ext FROM documents WHERE ext IS NOT NULL ORDER BY ext")
            extensions = [r['ext'] for r in cur.fetchall()]
            
            return {
                "areas": areas,
                "anni": anni,
                "clienti": clienti,
                "oggetti": oggetti,
                "tipi_doc": tipi_doc,
                "categorie": categorie,
                "extensions": extensions
            }
    except Exception as e:
        import logging
        logging.error(f"Errore in /filters: {e}")
        return {
            "areas": [], "anni": [], "clienti": [], "oggetti": [],
            "tipi_doc": [], "categorie": [], "extensions": [],
            "error": str(e)
        }'''
    
    # Cerca e sostituisci endpoint /filters
    import re
    filters_pattern = r'@router\.get\("/filters"\).*?(?=\n@router\.|\nclass |\Z)'
    match = re.search(filters_pattern, content, re.DOTALL)
    
    if match:
        old_filters = match.group(0)
        content = content.replace(old_filters, new_filters_endpoint)
        log("Endpoint /filters aggiornato", "✅")
    else:
        log("Endpoint /filters non trovato", "⚠️")
    
    # Salva
    output_path = filepath + ".NEW"
    with open(output_path, "w") as f:
        f.write(content)
    
    log(f"File aggiornato: {output_path}", "✅")
    
    return True


def create_meilisearch_config():
    """Crea snippet configurazione Meilisearch"""
    
    config = '''
# ============================================================================
# Configurazione Meilisearch - filterableAttributes
# ============================================================================

# Aggiungi questo snippet in ensure_meili() dentro worker/worker_tasks.py

idx.update_settings({
    "searchableAttributes": [
        "title", 
        "content", 
        "path", 
        "cliente", 
        "oggetto",
        "descrizione_oggetto"
    ],
    "filterableAttributes": [
        "area",
        "anno",
        "cliente",
        "oggetto",
        "tipo_doc",
        "codice_appalto",
        "categoria",
        "ext"
    ],
    "sortableAttributes": [
        "anno",
        "cliente",
        "mtime"
    ],
    "displayedAttributes": [
        "id", "title", "area", "anno", "cliente", 
        "oggetto", "tipo_doc", "categoria", "ext"
    ]
})
'''
    
    with open("/tmp/meilisearch_config.txt", "w") as f:
        f.write(config)
    
    log("Configurazione Meilisearch salvata in /tmp/meilisearch_config.txt", "✅")
    print(config)


def main():
    print("🔧 INTEGRAZIONE METADATA EXTRACTOR")
    print("=" * 70)
    
    if DRY_RUN:
        print("⚠️  MODALITÀ DRY-RUN: Nessun file sarà modificato")
    
    print()
    
    # Verifica prerequisiti
    if not os.path.exists("worker/worker_tasks.py"):
        log("Directory worker/ non trovata. Esegui dalla root del progetto!", "❌")
        sys.exit(1)
    
    # Step 1: Copia metadata_extractor.py
    log("STEP 1: Copia metadata_extractor.py nel worker", "📋")
    if os.path.exists("metadata_extractor.py"):
        if not DRY_RUN:
            shutil.copy("metadata_extractor.py", "worker/metadata_extractor.py")
            log("File copiato in worker/", "✅")
        else:
            log("[DRY-RUN] Copia metadata_extractor.py → worker/", "📝")
    else:
        log("metadata_extractor.py non trovato nella directory corrente", "⚠️")
    
    print()
    
    # Step 2: Aggiorna worker_tasks.py
    log("STEP 2: Aggiorna worker/worker_tasks.py", "📋")
    update_worker_tasks()
    
    print()
    
    # Step 3: Aggiorna route_admin.py
    log("STEP 3: Aggiorna api/route_admin.py", "📋")
    update_route_admin_filters()
    
    print()
    
    # Step 4: Config Meilisearch
    log("STEP 4: Genera configurazione Meilisearch", "📋")
    create_meilisearch_config()
    
    print()
    print("=" * 70)
    print("✅ INTEGRAZIONE COMPLETATA!")
    print()
    
    if DRY_RUN:
        print("ℹ️  Modalità DRY-RUN attiva. Per applicare le modifiche:")
        print("   python3 integrate_metadata.py")
    else:
        print("📋 PROSSIMI PASSI:")
        print()
        print("1. Verifica modifiche:")
        print("   diff worker/worker_tasks.py worker/worker_tasks.py.NEW")
        print("   diff api/route_admin.py api/route_admin.py.NEW")
        print()
        print("2. Applica modifiche:")
        print("   mv worker/worker_tasks.py.NEW worker/worker_tasks.py")
        print("   mv api/route_admin.py.NEW api/route_admin.py")
        print()
        print("3. Test metadata extractor:")
        print("   python3 worker/metadata_extractor.py")
        print()
        print("4. Rebuild Docker:")
        print("   docker compose build worker api")
        print("   docker compose up -d")
        print()
        print("5. Reinizializza e reingest:")
        print("   curl -X POST http://localhost:8000/init_indexes")
        print("   curl -X POST http://localhost:8000/ingestion/start")
        print()
        print("6. Verifica metadati estratti:")
        print("   curl http://localhost:8000/filters")
        print()
        print("💾 Backup salvati con estensione .backup.TIMESTAMP")


if __name__ == "__main__":
    main()
