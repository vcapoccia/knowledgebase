# -*- coding: utf-8 -*-
"""
Regole di estrazione faccette dal percorso del file.

Ritorna un dizionario con alcune delle seguenti chiavi (compatibili con Meili):
  area, year, cliente, ambito, tipo, sottotipo, sd,
  oda_id, oda_cliente, as_id, rdo, ot, versione, ext

Esempi di path riconosciuti:
  .../_Gare/2021_ClienteX/01_Documentazione/SD123/AS0456/ODA789_ClienteY/file.pdf
  .../_AQ/2020_ClienteZ/04_OffertaTecnica/AS1234/Documento_v2.1.docx
  .../2018_ClienteA-RD/02_Chiarimenti/ODA123/ClienteB/Allegato.pdf

NB: Questo modulo **non** deve lanciare eccezioni: se qualcosa non torna,
semplicemente ritorna un dict (anche vuoto). Il worker farà merge non distruttivo.
"""

from __future__ import annotations
import re
from typing import Dict, Any

# Compiliamo tutte le regex una volta sola (performance + chiarezza)
RX = {
    # _Gare / _AQ
    "area": re.compile(r"/(_Gare|_AQ)(?:/|$)", re.IGNORECASE),

    # YYYY_ o YYYY- all'inizio di un segmento
    "year": re.compile(r"(?:^|/)(\d{4})(?:[_-])"),

    # Tipologie cartelle “forti”
    "tipo": re.compile(
        r"/(01_Documentazione|02_Chiarimenti|04_OffertaTecnica|08_AccessoAgliAtti)(?:/|$)"
    ),

    # Cliente (euristica: dopo “YYYY_…”, fermandosi prima di -Qualcosa in Maiuscolo)
    "cliente": re.compile(
        r"(?:^|/)\d{4}_([^/]+?)(?:-[A-Z][a-z0-9]+)?(?:/|$)"
    ),

    # SD### come segmento
    "sd": re.compile(r"/SD(\d+)(?:/|$)", re.IGNORECASE),

    # AS#### in diverse forme (AS1234, AS-01234, AS_999)
    "as_id": re.compile(r"/AS[-_]?(\d{3,6})(?:[_.-/]|$)", re.IGNORECASE),

    # ODA### con cliente opzionale dopo underscore o come cartella successiva
    "oda_inline": re.compile(r"/ODA(\d+)[-_]?([^/]+)?(?:/|$)", re.IGNORECASE),
    "oda_nested": re.compile(r"/ODA(\d+)/(?!$)([^/]+)(?:/|$)", re.IGNORECASE),

    # RDO / OT come segnalini (spesso nei nomi file)
    "rdo": re.compile(r"(?:^|/)(?:RDO[-_]?|RDO)([A-Za-z0-9\-_.]+)(?:/|$)"),
    "ot":  re.compile(r"(?:^|/)(?:OT[-_]?|OT)([A-Za-z0-9\-_.]+)(?:/|$)"),

    # Versioni file: v1, v1.2, v_2.0 ecc. dentro il nome
    "versione": re.compile(r"(?:^|/)[^/]*?\b[vV][\s._-]?(\d+(?:\.\d+){0,2})\b[^/]*$"),

    # Estensione file (semplice)
    "ext": re.compile(r"\.([A-Za-z0-9]{1,5})$")
}


def _safe(path: str) -> str:
    # Normalizza separatori a '/', evita maiuscole/minuscole
    return path.replace("\\", "/")

def extract_facets_from_path(path: str) -> Dict[str, Any]:
    """
    Restituisce SOLO i campi trovati (non sovrascrive nulla).
    Il worker farà un merge non distruttivo con le faccette già estratte.
    """
    out: Dict[str, Any] = {}
    if not path:
        return out

    p = _safe(path)

    # AREA
    m = RX["area"].search(p)
    if m:
        out["area"] = m.group(1)

    # YEAR
    m = RX["year"].search(p)
    if m:
        out["year"] = m.group(1)

    # TIPO
    m = RX["tipo"].search(p)
    if m:
        out["tipo"] = m.group(1)

    # CLIENTE
    m = RX["cliente"].search(p)
    if m:
        out["cliente"] = m.group(1)

    # SD
    m = RX["sd"].search(p)
    if m:
        out["sd"] = f"SD{m.group(1)}"

    # AS_ID
    m = RX["as_id"].search(p)
    if m:
        out["as_id"] = f"AS{m.group(1)}"

    # ODA (due forme: inline “ODA123_ClienteX” o annidato “/ODA123/ClienteX/”)
    m = RX["oda_inline"].search(p)
    if m:
        out["oda_id"] = f"ODA{m.group(1)}"
        if m.group(2):
            out["oda_cliente"] = m.group(2)

    if "oda_id" not in out:
        m = RX["oda_nested"].search(p)
        if m:
            out["oda_id"] = f"ODA{m.group(1)}"
            out["oda_cliente"] = m.group(2)

    # RDO / OT
    m = RX["rdo"].search(p)
    if m:
        out["rdo"] = m.group(1)
    m = RX["ot"].search(p)
    if m:
        out["ot"] = m.group(1)

    # VERSIONE
    m = RX["versione"].search(p)
    if m:
        out["versione"] = m.group(1)

    # EXT
    m = RX["ext"].search(p)
    if m:
        out["ext"] = m.group(1).lower()

    return out


# --- (facoltativo) test rapido manuale ---
if __name__ == "__main__":
    samples = [
        "/mnt/kb/_Gare/2021_ClienteX/01_Documentazione/SD123/AS0456/ODA789_ClienteY/Capitolato_v2.1.pdf",
        "/mnt/kb/_AQ/2020_ClienteZ/04_OffertaTecnica/AS1234/Documento.docx",
        "/mnt/kb/2018_ClienteA-RD/02_Chiarimenti/ODA123/ClienteB/Allegato.pdf",
        "/mnt/kb/_Gare/2019_Foo-Bar/08_AccessoAgliAtti/RDO-77/OT_15/Spec_v1.pptx",
    ]
    for s in samples:
        print(s, "=>", extract_facets_from_path(s))