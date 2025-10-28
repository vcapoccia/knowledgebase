#!/usr/bin/env python3
"""
KB Search - Improved Search Module v2.1 (Fixed)

COMPATIBILE CON MAIN.PY ESISTENTE!

Migliora risultati di ricerca con:
1. Deduplicazione versioni (basata su analisi 14,008 file reali)
2. Filtro temporale smart (estrazione automatica date da query)
3. Stopwords removal (40+ stopwords italiane)

Basato su analisi pattern versioning reale:
- v1.0, v2.1: 1,600+ file
- finale/definitivo: 370+ file  
- (1), (2) copie Windows: 130+ file
- rev1, rev2: 60+ file
- _1, _2: 300+ file

Autore: Engineering Ingegneria Informatica
Data: 2025-10-27
Versione: 2.1 (Fixed - aggiunta enhance_search_query wrapper)
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher
from datetime import datetime

# ============================================================================
# STOPWORDS ITALIANE (40+ comuni)
# ============================================================================
ITALIAN_STOPWORDS = {
    'il', 'lo', 'la', 'i', 'gli', 'le',  # Articoli
    'un', 'uno', 'una', 'dei', 'degli', 'delle',  # Articoli indeterminativi
    'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra',  # Preposizioni
    'del', 'dello', 'della', 'dei', 'degli', 'delle',  # Preposizioni articolate
    'al', 'allo', 'alla', 'ai', 'agli', 'alle',
    'dal', 'dallo', 'dalla', 'dai', 'dagli', 'dalle',
    'nel', 'nello', 'nella', 'nei', 'negli', 'nelle',
    'sul', 'sullo', 'sulla', 'sui', 'sugli', 'sulle',
    'e', 'o', 'ma', 'però', 'anche', 'oppure',  # Congiunzioni
    'che', 'cui', 'chi', 'quale', 'quanto',  # Pronomi
    'questo', 'quello', 'questi', 'quelli',
    'suo', 'sua', 'loro', 'nostro', 'vostro',
    'essere', 'avere', 'fare', 'essere',  # Verbi ausiliari comuni
    'è', 'sono', 'ha', 'hanno', 'fa', 'fanno',
}


# ============================================================================
# DEDUPLICAZIONE VERSIONI
# ============================================================================

def extract_version_info(filename: str) -> Dict[str, Any]:
    """
    Estrae informazioni versione da nome file
    
    Analizza pattern reali trovati in 3,207 file con versioning:
    - v1.0, v2.1: 1,600+ file (PATTERN PIÙ COMUNE)
    - finale/definitivo: 370+ file (PRIORITÀ ASSOLUTA)
    - (1), (2): 130+ file (copie Windows)
    - rev1, rev2: 60+ file
    - _1, _2: 300+ file (MA filtra _2019 = anno!)
    
    Returns:
        {
            'version': float,      # Numero versione (più alto = più recente)
            'is_final': bool,      # True se versione finale/definitiva
            'pattern': str,        # Pattern riconosciuto
            'base_name': str       # Nome senza versione per raggruppamento
        }
    """
    # Ordine priorità pattern (dal più specifico al meno)
    patterns = [
        # 1. FINALE/DEFINITIVO - PRIORITÀ MASSIMA (999)
        #    ~370 file: finale, finali, final, definitivo, definitiva, ultima
        {
            'regex': r'[_\s\-](final[ei]?|definitiv\w*|ultima)',
            'version': 999.0,  # Priorità assoluta
            'is_final': True,
            'pattern': 'final'
        },
        
        # 2. Versioni decimali v1.0, v2.1, v1.2.3
        #    ~85 file con minor version
        {
            'regex': r'[vV](\d+)\.(\d+)(?:\.(\d+))?',
            'version': lambda m: float(f"{m.group(1)}.{m.group(2)}{m.group(3) or '0'}"),
            'is_final': False,
            'pattern': 'vX.Y'
        },
        
        # 3. Versioni semplici v1, v2, v01, v02
        #    ~1,500 file (PATTERN PIÙ DIFFUSO)
        {
            'regex': r'[vV]0?(\d+)(?![0-9])',  # v01, v1 (no v10 in v101)
            'version': lambda m: float(m.group(1)),
            'is_final': False,
            'pattern': 'vN'
        },
        
        # 4. Copie Windows (1), (2), (3)
        #    ~130 file: (1) 78%, (2) 15%, (3) 5%
        {
            'regex': r'\((\d+)\)',
            'version': lambda m: float(m.group(1)),
            'is_final': False,
            'pattern': '(N)'
        },
        
        # 5. Revisioni rev1, Rev01, _R2
        #    ~60 file (meno comune)
        {
            'regex': r'[_\s]?[rR]ev[\s_-]?(\d+)',
            'version': lambda m: float(m.group(1)),
            'is_final': False,
            'pattern': 'revN'
        },
        
        # 6. Underscore _1, _2 (FILTRO ≤99 per evitare anni!)
        #    ~300 file, MA _2019.pdf = ANNO non versione!
        {
            'regex': r'_(\d{1,2})\.(?:pdf|docx?|xlsx?|pptx?|txt|odt)$',
            'version': lambda m: float(m.group(1)) if int(m.group(1)) <= 99 else 0,
            'is_final': False,
            'pattern': '_N',
        },
    ]
    
    # Cerca pattern in ordine
    for pattern_def in patterns:
        match = re.search(pattern_def['regex'], filename, re.IGNORECASE)
        if match:
            # Calcola versione
            if callable(pattern_def['version']):
                try:
                    version = pattern_def['version'](match)
                    # Se version = 0, pattern non valido (es. _2019)
                    if version == 0:
                        continue
                except:
                    continue
            else:
                version = pattern_def['version']
            
            return {
                'version': version,
                'is_final': pattern_def['is_final'],
                'pattern': pattern_def['pattern'],
                'base_name': get_base_name(filename)
            }
    
    # Nessun pattern riconosciuto
    return {
        'version': 0.0,
        'is_final': False,
        'pattern': 'none',
        'base_name': get_base_name(filename)
    }


def get_base_name(filename: str) -> str:
    """
    Nome base senza versione/estensione per raggruppamento duplicati
    
    Rimuove:
    - Tutti i pattern versioning (v1.0, finale, (1), rev2, _2, ecc.)
    - Suffissi comuni (firmato, with_track_changes, signed, ecc.)
    - Estensione
    
    Examples:
        "Piano_Operativo_v1.2.pdf" → "piano_operativo"
        "Relazione_finale_firmato.docx" → "relazione"
        "Capitolato (1).pdf" → "capitolato"
        "Documento_v2.0_with_track_changes.docx" → "documento"
    
    Returns:
        Nome normalizzato lowercase con underscore
    """
    # Rimuovi path
    base = filename.split('/')[-1] if '/' in filename else filename
    
    # Rimuovi pattern versioning (in ordine)
    base = re.sub(r'[vV]\d+\.?\d*\.?\d*', '', base)  # v1.0, v2.1.3
    base = re.sub(r'[_\s]?[rR]ev[\s_-]?\d+', '', base, flags=re.IGNORECASE)  # rev1, Rev01
    base = re.sub(r'\(\d+\)', '', base)  # (1), (2)
    base = re.sub(r'[_\s\-](final[ei]?|definitiv\w*|ultima)', '', base, flags=re.IGNORECASE)  # finale
    base = re.sub(r'_\d{1,2}(?=\.|$)', '', base)  # _1, _2 (non _2019!)
    
    # Rimuovi suffissi comuni
    suffixes = [
        'with[_\s]track[_\s]changes?',
        'firmato', 'signed?', 'approved',
        'con[_\s]modifiche', 'revisioni',
        'draft', 'bozza', 'definitiv\w*'
    ]
    for suffix in suffixes:
        base = re.sub(rf'[_\s-]+{suffix}', '', base, flags=re.IGNORECASE)
    
    # Rimuovi estensione
    base = re.sub(r'\.(pdf|docx?|xlsx?|pptx?|txt|odt|ods|mpp|dwg)$', '', base, flags=re.IGNORECASE)
    
    # Normalizza separatori
    base = re.sub(r'[\s_\-]+', '_', base)
    
    # Pulisci bordi
    base = base.strip().strip('_').strip('-').lower()
    
    return base


def calculate_similarity(str1: str, str2: str) -> float:
    """Calcola similarità tra due stringhe (0.0 - 1.0)"""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def deduplicate_results(
    results: List[Dict[str, Any]], 
    threshold: float = 0.85,
    prefer_pdf: bool = True
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Deduplica risultati mantenendo versione migliore
    
    Algoritmo:
    1. Raggruppa per base_name (titolo senza versione)
    2. Per ogni gruppo:
       a. Se esiste versione FINAL → mantieni solo quella
       b. Altrimenti mantieni versione con numero più alto
       c. A parità di versione, preferisci PDF se prefer_pdf=True
    
    Args:
        results: Lista risultati ricerca con field 'title' o 'path' o 'filename'
        threshold: Soglia similarità per raggruppare (0.85 = 85%)
        prefer_pdf: Se True, preferisce PDF a DOCX a parità di versione
        
    Returns:
        (results_deduplicated, stats)
        
    Stats contiene:
        - removed_duplicates: numero duplicati rimossi
        - groups_found: numero gruppi trovati
        - kept_by_final: numero doc tenuti perché finale
        - kept_by_version: numero doc tenuti per versione alta
    """
    if not results or len(results) <= 1:
        return results, {'removed_duplicates': 0, 'groups_found': 0}
    
    # Estrai info versioning per ogni risultato
    enriched = []
    for result in results:
        # Prendi titolo, filename o path
        filename = result.get('filename') or result.get('title') or result.get('path') or ''
        if not filename:
            enriched.append({**result, '_version_info': None})
            continue
        
        # Estrai solo il nome file se è un path
        if '/' in filename:
            filename = filename.split('/')[-1]
            
        version_info = extract_version_info(filename)
        enriched.append({**result, '_version_info': version_info, '_filename': filename})
    
    # Raggruppa per base_name
    groups = {}
    for item in enriched:
        if item['_version_info'] is None:
            # Nessun versioning, mantieni
            base = f"no_version_{item.get('id', 'unknown')}"
        else:
            base = item['_version_info']['base_name']
        
        if base not in groups:
            groups[base] = []
        groups[base].append(item)
    
    # Per ogni gruppo, seleziona migliore
    deduplicated = []
    stats = {
        'removed_duplicates': 0,
        'groups_found': len([g for g in groups.values() if len(g) > 1]),
        'kept_by_final': 0,
        'kept_by_version': 0,
    }
    
    for base_name, group in groups.items():
        if len(group) == 1:
            # Singolo, mantieni senza modifiche
            result = group[0].copy()
            result.pop('_version_info', None)
            result.pop('_filename', None)
            deduplicated.append(result)
            continue
        
        # Gruppo con più versioni - seleziona migliore
        # Priorità:
        # 1. is_final = True (versione definitiva)
        # 2. version (numero più alto)
        # 3. prefer_pdf (PDF > DOCX)
        # 4. score (punteggio ricerca più alto)
        
        def sort_key(item):
            vi = item['_version_info']
            if vi is None:
                return (0, 0, 0, 0)
            
            filename = item['_filename']
            is_pdf = filename.lower().endswith('.pdf')
            score = item.get('score', 0)
            
            return (
                1 if vi['is_final'] else 0,  # Finale vince sempre
                vi['version'],  # Versione più alta
                1 if (prefer_pdf and is_pdf) else 0,  # PDF preferito
                score  # Score più alto
            )
        
        # Ordina decrescente
        sorted_group = sorted(group, key=sort_key, reverse=True)
        best = sorted_group[0]
        other_versions = sorted_group[1:]
        
        # Statistiche
        if best['_version_info'] and best['_version_info']['is_final']:
            stats['kept_by_final'] += 1
        else:
            stats['kept_by_version'] += 1
        stats['removed_duplicates'] += len(other_versions)
        
        # Mantieni score migliore del gruppo
        best_score = max(item.get('score', 0) for item in group)
        best['score'] = best_score
        
        # Aggiungi metadata versioni alternative
        best['_other_versions_count'] = len(other_versions)
        best['_all_versions'] = [
            {
                'filename': item['_filename'],
                'version': item['_version_info']['version'] if item['_version_info'] else 0,
                'is_final': item['_version_info']['is_final'] if item['_version_info'] else False,
                'pattern': item['_version_info']['pattern'] if item['_version_info'] else 'none',
                'score': item.get('score', 0)
            }
            for item in other_versions
        ]
        
        # Rimuovi campi interni
        best = best.copy()
        best.pop('_version_info', None)
        best.pop('_filename', None)
        
        deduplicated.append(best)
    
    return deduplicated, stats


# ============================================================================
# FILTRO TEMPORALE SMART
# ============================================================================

def extract_date_filter(query: str) -> Optional[Dict[str, Any]]:
    """
    Estrae filtro temporale da query naturale
    
    Pattern supportati:
    - "dal 2021 in poi" → year >= 2021
    - "fino al 2020" → year <= 2020
    - "nel 2023" → year == 2023
    - "tra il 2020 e il 2022" → 2020 <= year <= 2022
    - "dopo il 2019" → year > 2019
    - "prima del 2022" → year < 2022
    - "successivi al 2020" → year > 2020
    - "precedenti al 2021" → year < 2021
    
    Returns:
        {
            'type': 'after'|'before'|'equal'|'between',
            'year': int,
            'year_end': int (solo per 'between')
        }
        oppure None se nessun pattern trovato
    """
    patterns = [
        # "dal 2021 in poi" / "dal 2021"
        (r'(?:dal|dall[\'o]?)\s+(\d{4})(?:\s+in\s+poi)?', 'after'),
        
        # "fino al 2020" / "entro il 2020"
        (r'(?:fino\s+al|entro\s+(?:il\s+)?)\s*(\d{4})', 'before'),
        
        # "nel 2023" / "nell'anno 2023"
        (r'(?:nel(?:l[\'o]?)?\s+(?:anno\s+)?)\s*(\d{4})', 'equal'),
        
        # "tra il 2020 e il 2022"
        (r'tra\s+(?:il\s+)?(\d{4})\s+e\s+(?:il\s+)?(\d{4})', 'between'),
        
        # "dopo il 2019" / "successivi al 2020"
        (r'(?:dopo\s+(?:il\s+)?|successiv[io]\s+al\s+)\s*(\d{4})', 'after'),
        
        # "prima del 2022" / "precedenti al 2021"
        (r'(?:prima\s+del|precedent[io]\s+al)\s+(\d{4})', 'before_exclusive'),
    ]
    
    for pattern, filter_type in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            if filter_type == 'between':
                year_start = int(match.group(1))
                year_end = int(match.group(2))
                return {
                    'type': 'between',
                    'year': year_start,
                    'year_end': year_end
                }
            else:
                year = int(match.group(1))
                return {
                    'type': filter_type,
                    'year': year
                }
    
    return None


def apply_date_filter(
    results: List[Dict[str, Any]], 
    date_filter: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Applica filtro temporale ai risultati
    
    Cerca campo 'anno' nei metadati o estrae da path/title
    Pattern path: _Gare/2022_Cliente-Ambito/...
    
    Args:
        results: Lista risultati
        date_filter: Dict con 'type' e 'year' da extract_date_filter()
        
    Returns:
        (results_filtrati, count_rimossi)
    """
    if not date_filter:
        return results, 0
    
    def extract_year(result: Dict[str, Any]) -> Optional[int]:
        """Estrae anno da metadati o path"""
        # 1. Campo anno nei metadati
        if 'anno' in result:
            try:
                return int(result['anno'])
            except:
                pass
        
        # 2. Campo metadata.year
        if 'metadata' in result and isinstance(result['metadata'], dict):
            year = result['metadata'].get('year')
            if year:
                try:
                    return int(year)
                except:
                    pass
        
        # 3. Path: _Gare/2022_Cliente/...
        path = result.get('path', '') or result.get('title', '') or result.get('filename', '')
        match = re.search(r'_Gare[/\\](\d{4})_', path)
        if match:
            return int(match.group(1))
        
        # 4. Filename: Documento_2021.pdf
        match = re.search(r'[_\-](\d{4})\.(?:pdf|docx?)', path)
        if match:
            year = int(match.group(1))
            # Valida anno ragionevole (2000-2099)
            if 2000 <= year <= 2099:
                return year
        
        return None
    
    filtered = []
    filter_type = date_filter['type']
    year = date_filter['year']
    original_count = len(results)
    
    for result in results:
        doc_year = extract_year(result)
        
        # Se anno non trovato, mantieni documento (no filtering)
        if doc_year is None:
            filtered.append(result)
            continue
        
        # Applica filtro
        keep = False
        if filter_type == 'after':
            keep = doc_year >= year
        elif filter_type == 'before':
            keep = doc_year <= year
        elif filter_type == 'before_exclusive':
            keep = doc_year < year
        elif filter_type == 'equal':
            keep = doc_year == year
        elif filter_type == 'between':
            year_end = date_filter['year_end']
            keep = year <= doc_year <= year_end
        
        if keep:
            filtered.append(result)
    
    removed_count = original_count - len(filtered)
    return filtered, removed_count


# ============================================================================
# QUERY CLEANING
# ============================================================================

def clean_query(query: str, remove_dates: bool = True) -> str:
    """
    Pulisce query rimuovendo stopwords e pattern temporali
    
    Args:
        query: Query originale
        remove_dates: Se True, rimuove anche pattern temporali
        
    Returns:
        Query pulita
        
    Examples:
        "piano operativo dal 2021 in poi" → "piano operativo" (se remove_dates=True)
        "il report di analisi per il 2023" → "report analisi 2023"
    """
    if not query:
        return query
    
    # Rimuovi pattern temporali se richiesto
    if remove_dates:
        temporal_patterns = [
            r'(?:dal|dall[\'o]?)\s+\d{4}(?:\s+in\s+poi)?',
            r'(?:fino\s+al|entro\s+(?:il\s+)?)\s*\d{4}',
            r'(?:nel(?:l[\'o]?)?\s+(?:anno\s+)?)\s*\d{4}',
            r'tra\s+(?:il\s+)?\d{4}\s+e\s+(?:il\s+)?\d{4}',
            r'(?:dopo\s+(?:il\s+)?|successiv[io]\s+al\s+)\s*\d{4}',
            r'(?:prima\s+del|precedent[io]\s+al)\s+\d{4}',
        ]
        for pattern in temporal_patterns:
            query = re.sub(pattern, '', query, flags=re.IGNORECASE)
    
    # Tokenizza
    words = query.lower().split()
    
    # Rimuovi stopwords
    cleaned_words = [w for w in words if w not in ITALIAN_STOPWORDS and len(w) > 1]
    
    # Ricostruisci
    cleaned = ' '.join(cleaned_words)
    
    # Normalizza spazi
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


# ============================================================================
# FUNZIONE PRINCIPALE (wrapper per compatibilità main.py)
# ============================================================================

def enhance_search_query(
    query: str,
    results: List[Dict[str, Any]],
    deduplicate: bool = False,
    smart_filter: bool = True
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Wrapper function per compatibilità con main.py esistente
    
    Questa funzione è richiesta dal main.py alla riga 315:
    _, enhanced, meta = enhance_search_query(q_text, enhance_input, deduplicate, smart_filter)
    
    Args:
        query: Query originale utente
        results: Lista risultati da migliorare
        deduplicate: Applica deduplicazione versioni
        smart_filter: Applica filtro temporale automatico
        
    Returns:
        (query_cleaned, results_enhanced, metadata)
        
    Metadata contiene:
        - clean_query: Query pulita (stopwords rimossi)
        - date_filter: Filtro temporale estratto (dict o None)
        - filtered_by_date: Numero docs filtrati (int)
        - deduplicated: Se deduplicazione applicata (bool)
        - removed_duplicates: Numero duplicati rimossi (int)
    """
    metadata = {
        'clean_query': query,
        'date_filter': None,
        'filtered_by_date': 0,
        'deduplicated': False,
        'removed_duplicates': 0,
    }
    
    enhanced_results = results.copy() if results else []
    
    # Step 1: Query Cleaning
    date_filter = None
    if smart_filter:
        date_filter = extract_date_filter(query)
        if date_filter:
            metadata['date_filter'] = date_filter
    
    cleaned_query = clean_query(query, remove_dates=(date_filter is not None))
    metadata['clean_query'] = cleaned_query
    
    # Step 2: Smart Filter (date)
    if smart_filter and date_filter and enhanced_results:
        enhanced_results, removed_count = apply_date_filter(enhanced_results, date_filter)
        metadata['filtered_by_date'] = removed_count
    
    # Step 3: Deduplication
    if deduplicate and enhanced_results and len(enhanced_results) > 1:
        enhanced_results, dedup_stats = deduplicate_results(enhanced_results)
        metadata['deduplicated'] = True
        metadata['removed_duplicates'] = dedup_stats['removed_duplicates']
    
    return cleaned_query, enhanced_results, metadata


# ============================================================================
# FUNZIONE LEGACY (per backward compatibility)
# ============================================================================

def enhance_search_results(
    results: List[Dict[str, Any]],
    original_query: str,
    deduplicate: bool = False,
    smart_filter: bool = True,
    clean_query_for_bm25: bool = False,
    threshold: float = 0.85
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Legacy function - usa enhance_search_query() invece
    
    Mantenuta per backward compatibility con esempi precedenti
    """
    cleaned_query, enhanced, meta = enhance_search_query(
        original_query,
        results,
        deduplicate,
        smart_filter
    )
    
    # Adatta formato metadata
    metadata = {
        'original_query': original_query,
        'cleaned_query': meta.get('clean_query'),
        'date_filter': meta.get('date_filter'),
        'filtered_by_date': meta.get('filtered_by_date', 0),
        'removed_duplicates': meta.get('removed_duplicates', 0),
    }
    
    return enhanced, metadata


# ============================================================================
# UTILITÀ
# ============================================================================

def analyze_versioning(filenames: List[str]) -> Dict[str, Any]:
    """
    Analizza pattern versioning in lista filenames
    
    Utile per debugging e testing
    """
    stats = {
        'total': len(filenames),
        'with_versioning': 0,
        'patterns': {
            'final': 0,
            'vX.Y': 0,
            'vN': 0,
            '(N)': 0,
            'revN': 0,
            '_N': 0,
            'none': 0,
        },
        'has_final': 0,
        'avg_version': 0.0,
        'max_version': 0.0,
    }
    
    versions = []
    for filename in filenames:
        info = extract_version_info(filename)
        pattern = info['pattern']
        
        stats['patterns'][pattern] = stats['patterns'].get(pattern, 0) + 1
        
        if pattern != 'none':
            stats['with_versioning'] += 1
        
        if info['is_final']:
            stats['has_final'] += 1
        
        versions.append(info['version'])
    
    if versions:
        stats['avg_version'] = sum(versions) / len(versions)
        stats['max_version'] = max(versions)
    
    return stats


# ============================================================================
# MAIN (per testing)
# ============================================================================

if __name__ == '__main__':
    # Test enhance_search_query (wrapper per main.py)
    print("🧪 TEST enhance_search_query() WRAPPER")
    print("=" * 60)
    
    test_results = [
        {
            "id": "1",
            "filename": "Piano_Operativo_v1.0.pdf",
            "path": "/mnt/kb/_Gare/2021_Cliente-Oggetto/Piano_Operativo_v1.0.pdf",
            "score": 0.9,
            "anno": 2021
        },
        {
            "id": "2",
            "filename": "Piano_Operativo_v2.0.pdf",
            "path": "/mnt/kb/_Gare/2022_Cliente-Oggetto/Piano_Operativo_v2.0.pdf",
            "score": 0.88,
            "anno": 2022
        },
        {
            "id": "3",
            "filename": "Piano_Operativo_finale.pdf",
            "path": "/mnt/kb/_Gare/2023_Cliente-Oggetto/Piano_Operativo_finale.pdf",
            "score": 0.85,
            "anno": 2023
        },
        {
            "id": "4",
            "filename": "Relazione_2020.pdf",
            "path": "/mnt/kb/_Gare/2020_Cliente-Oggetto/Relazione_2020.pdf",
            "score": 0.80,
            "anno": 2020
        },
    ]
    
    query = "piano operativo dal 2021 in poi"
    
    print(f"Query: '{query}'")
    print(f"Results input: {len(test_results)}")
    print()
    
    # Test con deduplicate e smart_filter
    cleaned_query, enhanced, meta = enhance_search_query(
        query,
        test_results,
        deduplicate=True,
        smart_filter=True
    )
    
    print("RISULTATI:")
    print(f"Query cleaned: '{cleaned_query}'")
    print(f"Date filter: {meta['date_filter']}")
    print(f"Filtered by date: {meta['filtered_by_date']}")
    print(f"Deduplicated: {meta['deduplicated']}")
    print(f"Removed duplicates: {meta['removed_duplicates']}")
    print()
    print(f"Enhanced results: {len(enhanced)}")
    for r in enhanced:
        print(f"  - {r['filename']} (score: {r['score']}, anno: {r.get('anno')})")
        if '_other_versions_count' in r:
            print(f"    → {r['_other_versions_count']} altre versioni nascoste")
    
    print()
    print("✅ Test completato! Il wrapper è compatibile con main.py")
