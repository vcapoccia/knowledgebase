"""
metadata_extractor.py - Estrazione metadati avanzata per Knowledge Base

Struttura supportata:
/mnt/kb/
├── _AQ/SD{N}/99_AS/AS{codice}/04_OffertaTecnica/documento.docx
├── _Gare/{ANNO}_{Cliente}-{Oggetto}/01_Documentazione/documento.pdf

Metadati estratti:
- area: AQ, Gare
- anno: 2012-2025, SD1-SD6
- cliente: Nome ente/azienda
- oggetto: Tipo di gara (LIS, SIO, AMC, HR, etc.)
- tipo_doc: Documentazione, Chiarimenti, OffertaTecnica, etc.
- codice_appalto: AS1440, AS1881, etc. (per AQ)
- categoria: Dedotto dall'oggetto (ERP, Sanità, etc.)
- versione: v1.0, v2.3, etc.
- ext: Estensione file
"""

import re
import os
from typing import Dict, Optional, List
from pathlib import Path


# Mappature intelligenti
STRALCIO_TO_ANNO = {
    "SD1": "2021",
    "SD2": "2022", 
    "SD3": "2023",
    "SD4": "2024",
    "SD5": "2025",
    "SD6": "2026"
}

TIPO_DOC_ALIASES = {
    "01_Documentazione": "Documentazione",
    "02_Chiarimenti": "Chiarimenti",
    "04_OffertaTecnica": "Offerta Tecnica",
    "04_Offerta Tecnica": "Offerta Tecnica",
    "08_AccessoAgliAtti": "Accesso Atti",
    "98_ODA": "Ordine Acquisto",
    "99_AS": "Appalto Specifico",
    "03_Risposta tecnica": "Risposta Tecnica",
    "05_OffertaTempo": "Offerta Tempi",
    "Contributi": "Contributi",
    "Meeting": "Meeting",
    "Progetto": "Progetto"
}

# Temi/Oggetti comuni (per categorizzazione)
TEMI_CATEGORIE = {
    # ERP/Gestionali
    "AMC": {"categoria": "Gestionale", "descrizione": "Amministrazione Contabilità"},
    "HR": {"categoria": "Gestionale", "descrizione": "Risorse Umane"},
    "Logistica": {"categoria": "Gestionale", "descrizione": "Logistica"},
    "Inventario": {"categoria": "Gestionale", "descrizione": "Inventario"},
    
    # Clinico
    "SIO": {"categoria": "Sanità", "descrizione": "Sistema Informativo Ospedaliero"},
    "SIA": {"categoria": "Sanità", "descrizione": "Sistema Informativo Aziendale"},
    "CCE": {"categoria": "Sanità", "descrizione": "Cartella Clinica Elettronica"},
    "LIS": {"categoria": "Sanità", "descrizione": "Laboratory Information System"},
    "RIS": {"categoria": "Sanità", "descrizione": "Radiology Information System"},
    "PACS": {"categoria": "Sanità", "descrizione": "Picture Archiving System"},
    "AP": {"categoria": "Sanità", "descrizione": "Anatomia Patologica"},
    "PS": {"categoria": "Sanità", "descrizione": "Pronto Soccorso"},
    "CUP": {"categoria": "Sanità", "descrizione": "Centro Unico Prenotazioni"},
    "118": {"categoria": "Emergenza", "descrizione": "Emergenza Sanitaria"},
    
    # Territory/FSE
    "SIT": {"categoria": "Territoriale", "descrizione": "Sistema Informativo Territoriale"},
    "FSE": {"categoria": "Territoriale", "descrizione": "Fascicolo Sanitario Elettronico"},
    "Telemedicina": {"categoria": "Territoriale", "descrizione": "Telemedicina"},
    
    # Specialistici
    "DWH": {"categoria": "Analytics", "descrizione": "Data Warehouse"},
    "GDPR": {"categoria": "Compliance", "descrizione": "Privacy e GDPR"},
}


def extract_metadata(filepath: str, kb_root: str = "/mnt/kb") -> Dict[str, Optional[str]]:
    """
    Estrae metadati strutturati da path e nome file.
    
    Args:
        filepath: Path completo del file
        kb_root: Root della knowledge base
    
    Returns:
        Dict con tutti i metadati estratti
    """
    metadata = {
        "area": None,
        "anno": None,
        "cliente": None,
        "oggetto": None,
        "tipo_doc": None,
        "codice_appalto": None,
        "categoria": None,
        "descrizione_oggetto": None,
        "versione": None,
        "ext": None,
        "path_relativo": None
    }
    
    # Path relativo e parti
    rel_path = filepath.replace(kb_root, "").lstrip("/")
    metadata["path_relativo"] = rel_path
    parts = rel_path.split("/")
    
    if len(parts) < 2:
        return metadata
    
    # Estensione
    _, ext = os.path.splitext(filepath)
    metadata["ext"] = ext.lstrip(".").lower()
    
    # --- AREA ---
    area_folder = parts[0]
    if area_folder.startswith("_"):
        metadata["area"] = area_folder.lstrip("_")
    
    # --- PATTERN AQ ---
    if metadata["area"] == "AQ":
        metadata = _extract_aq_metadata(parts, metadata, filepath)
    
    # --- PATTERN GARE ---
    elif metadata["area"] == "Gare":
        metadata = _extract_gare_metadata(parts, metadata, filepath)
    
    # --- VERSIONE (indipendente da pattern) ---
    filename = os.path.basename(filepath)
    version_pattern = r'[vV]\.?\d+\.\d+(?:\.\d+)?'
    match = re.search(version_pattern, filename)
    if match:
        metadata["versione"] = match.group(0)
    
    return metadata


def _extract_aq_metadata(parts: List[str], metadata: Dict, filepath: str) -> Dict:
    """
    Estrae metadati specifici per area AQ.
    
    Struttura: _AQ/SD{N}/XX_Categoria/AS{codice}/YY_TipoDoc/file.ext
    """
    if len(parts) < 3:
        return metadata
    
    # Stralcio Documentale → Anno
    if len(parts) > 1 and parts[1].startswith("SD"):
        sd_code = parts[1]
        metadata["anno"] = STRALCIO_TO_ANNO.get(sd_code, None)
    
    # Codice Appalto (AS{numero})
    for part in parts:
        match = re.search(r'\b(AS\d{4}[_A-Z0-9]*)\b', part)
        if match:
            metadata["codice_appalto"] = match.group(1)
            # Cerca anche il cliente nel nome (es: AS1440_ESTAR)
            if "_" in part:
                possible_cliente = part.split("_")[1:]
                if possible_cliente:
                    metadata["cliente"] = "_".join(possible_cliente)
            break
    
    # Tipo Documento (dalle cartelle numeriche)
    for part in parts:
        if re.match(r'^\d{2}_', part):
            tipo_normalizzato = TIPO_DOC_ALIASES.get(part, part)
            metadata["tipo_doc"] = tipo_normalizzato
            break
    
    # Oggetto/Tema (cerca acronimi noti nel path)
    for part in parts + [os.path.basename(filepath)]:
        for tema, info in TEMI_CATEGORIE.items():
            # Match più flessibile (case-insensitive, con separatori)
            if re.search(rf'\b{tema}\b', part, re.IGNORECASE):
                metadata["oggetto"] = tema
                metadata["categoria"] = info["categoria"]
                metadata["descrizione_oggetto"] = info["descrizione"]
                break
        if metadata["oggetto"]:
            break
    
    return metadata


def _extract_gare_metadata(parts: List[str], metadata: Dict, filepath: str) -> Dict:
    """
    Estrae metadati specifici per area Gare.
    
    Struttura: _Gare/{ANNO}_{Cliente}-{Oggetto}/XX_TipoDoc/file.ext
    """
    if len(parts) < 2:
        return metadata
    
    gara_folder = parts[1]
    
    # Pattern: ANNO_Cliente-Oggetto
    # Esempi:
    # - 2024_ESTAR-Logistica
    # - 2023_RegioneLazio-AQServiziDigitali
    # - 2017_Malaysia
    
    match = re.match(r'^(\d{4})_(.+?)(?:-(.+))?$', gara_folder)
    if match:
        metadata["anno"] = match.group(1)
        cliente_raw = match.group(2)
        oggetto_raw = match.group(3) if match.group(3) else ""
        
        # Pulisci cliente (rimuovi prefissi ripetitivi)
        metadata["cliente"] = _clean_cliente_name(cliente_raw)
        
        # Oggetto
        if oggetto_raw:
            # Cerca tema noto
            for tema, info in TEMI_CATEGORIE.items():
                if re.search(rf'\b{tema}\b', oggetto_raw, re.IGNORECASE):
                    metadata["oggetto"] = tema
                    metadata["categoria"] = info["categoria"]
                    metadata["descrizione_oggetto"] = info["descrizione"]
                    break
            
            # Se non trovato tema, usa oggetto raw pulito
            if not metadata["oggetto"]:
                metadata["oggetto"] = oggetto_raw.replace("_", " ")
    
    # Tipo Documento
    for part in parts:
        if re.match(r'^\d{2}_', part):
            tipo_normalizzato = TIPO_DOC_ALIASES.get(part, part)
            metadata["tipo_doc"] = tipo_normalizzato
            break
    
    return metadata


def _clean_cliente_name(cliente: str) -> str:
    """
    Pulisce il nome cliente rimuovendo prefissi comuni.
    
    Esempi:
    - AOUOrbassano → Orbassano
    - ASLRoma4 → Roma 4
    - RegioneToscana → Toscana
    """
    # Rimuovi prefissi comuni
    prefixes = [
        r'^AOU\s*', r'^AO\s*', r'^ASL\s*', r'^AUSL\s*', 
        r'^ASP\s*', r'^AORN\s*', r'^ARNAS\s*',
        r'^Regione\s*', r'^Provincia\s*'
    ]
    
    cleaned = cliente
    for prefix in prefixes:
        cleaned = re.sub(prefix, '', cleaned, flags=re.IGNORECASE)
    
    # Gestisci CamelCase → spazi (opzionale)
    # cleaned = re.sub(r'([a-z])([A-Z])', r'\1 \2', cleaned)
    
    return cleaned.strip()


def extract_metadata_batch(filepaths: List[str], kb_root: str = "/mnt/kb") -> List[Dict]:
    """
    Estrae metadati da una lista di file.
    
    Args:
        filepaths: Lista di path completi
        kb_root: Root della knowledge base
    
    Returns:
        Lista di dict con metadati
    """
    results = []
    for filepath in filepaths:
        try:
            meta = extract_metadata(filepath, kb_root)
            meta["filepath"] = filepath
            results.append(meta)
        except Exception as e:
            results.append({
                "filepath": filepath,
                "error": str(e)
            })
    
    return results


# ============================================================================
# TEST SUITE
# ============================================================================

def test_extractor():
    """Test completo dell'estrattore con casi reali"""
    
    test_cases = [
        # AQ
        "/mnt/kb/_AQ/SD1/99_AS/AS1440_ESTAR/04_OffertaTecnica/Relazione_Tecnica_v1.0.docx",
        "/mnt/kb/_AQ/SD2/01_Documentazione/Capitolato.pdf",
        "/mnt/kb/_AQ/SD3/99_AS/AS1881_Municipia/04_OffertaTecnica/SIO_Offerta.docx",
        
        # Gare
        "/mnt/kb/_Gare/2024_ESTAR-Logistica/01_Documentazione/Bando.pdf",
        "/mnt/kb/_Gare/2023_RegioneLazio-AQServiziDigitali/04_OffertaTecnica/Proposta_v2.1.docx",
        "/mnt/kb/_Gare/2018_IOR-SIO/02_Chiarimenti/Risposta_01.pdf",
        "/mnt/kb/_Gare/2021_AOUModenaAUSLRomagna-CCE_ICU/04_OffertaTecnica/CCE_Tecnica.docx",
        "/mnt/kb/_Gare/2019_RegionePiemonte-SIRVA/01_Documentazione/Capitolato.pdf",
    ]
    
    print("🧪 TEST ESTRAZIONE METADATI AVANZATA")
    print("=" * 80)
    print()
    
    for i, filepath in enumerate(test_cases, 1):
        print(f"📄 Test #{i}: {Path(filepath).name}")
        print(f"📂 Path: {filepath}")
        
        meta = extract_metadata(filepath)
        
        print("📊 Metadati estratti:")
        for key, value in meta.items():
            if value is not None:
                icon = "✅"
                print(f"   {icon} {key:20s}: {value}")
        
        print("-" * 80)
        print()
    
    # Statistics
    print("📈 STATISTICHE TEST")
    print("=" * 80)
    all_meta = [extract_metadata(fp) for fp in test_cases]
    
    fields = ["area", "anno", "cliente", "oggetto", "tipo_doc", "categoria"]
    for field in fields:
        count = sum(1 for m in all_meta if m.get(field))
        pct = (count / len(all_meta)) * 100
        print(f"   {field:20s}: {count}/{len(all_meta)} ({pct:.0f}%)")


def generate_integration_snippet():
    """Genera snippet per integrazione nel worker"""
    
    snippet = '''
# ============================================================================
# INTEGRAZIONE IN worker/worker_tasks.py
# ============================================================================

# 1. Import all'inizio del file
from metadata_extractor import extract_metadata

# 2. Modifica schema PostgreSQL in ensure_pg_schema()
def ensure_pg_schema():
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            title TEXT,
            content TEXT,
            mtime TIMESTAMP DEFAULT NOW(),
            
            -- 🆕 Metadati estratti
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
        
        -- 🆕 Indici per performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_area ON documents(area);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_anno ON documents(anno);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_cliente ON documents(cliente);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_oggetto ON documents(oggetto);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_tipo_doc ON documents(tipo_doc);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_docs_categoria ON documents(categoria);")

# 3. Modifica loop ingestion in run_ingestion()
for path in all_files:
    rel_id = os.path.relpath(path, KB_ROOT)
    try:
        text = _read_text(path)
        title = os.path.basename(path)
        
        # 🆕 Estrai metadati
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
        ))

        # 🆕 Aggiungi metadati a Meilisearch
        batch.append({
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
            "ext": metadata.get('ext')
        })

# 4. Configura Meilisearch per filtrare su metadati
def ensure_meili():
    c = meili_client()
    try:
        c.get_raw_index(MEILI_INDEX)
    except Exception:
        c.create_index(MEILI_INDEX, {"primaryKey": "id"})
    
    idx = c.index(MEILI_INDEX)
    idx.update_settings({
        "searchableAttributes": ["title", "content", "path", "cliente", "oggetto"],
        "filterableAttributes": [
            "area", "anno", "cliente", "oggetto", 
            "tipo_doc", "categoria", "ext"
        ],
        "sortableAttributes": ["anno", "cliente"]
    })
    return idx
'''
    
    print("\n📝 SNIPPET INTEGRAZIONE:")
    print(snippet)
    
    with open("/tmp/integration_snippet.py", "w") as f:
        f.write(snippet)
    
    print("\n✅ Snippet salvato in: /tmp/integration_snippet.py")


if __name__ == "__main__":
    test_extractor()
    print("\n")
    generate_integration_snippet()
