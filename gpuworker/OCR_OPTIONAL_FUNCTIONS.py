# FUNZIONE OCR OPZIONALE per worker_tasks.py
# Aggiungi questa funzione se hai PDF scansionati o immagini con testo

"""
Questa funzione usa Tesseract OCR per estrarre testo da:
1. PDF scansionati (senza layer di testo)
2. Immagini (JPG, PNG) embedded in documenti

PREREQUISITI:
- Tesseract installato (già in Dockerfile_worker)
- pytesseract e pdf2image in requirements_worker.txt

USO:
1. Copia questa funzione nel worker_tasks.py dopo _pdftotext_safe()
2. Modifica _read_text() per usarla quando pdftotext fallisce
"""

def _extract_ocr_from_pdf(path: str) -> str:
    """
    Estrae testo da PDF scansionato usando Tesseract OCR.
    Fallback quando pdftotext non trova testo.
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image
        
        log.info(f"🔍 OCR processing {os.path.basename(path)}...")
        
        # Converti PDF in immagini (max 10 pagine per non esplodere RAM)
        images = convert_from_path(
            path, 
            dpi=300,  # Alta risoluzione per OCR migliore
            first_page=1,
            last_page=10  # Limita a prime 10 pagine
        )
        
        text_parts = []
        
        for i, img in enumerate(images, 1):
            log.debug(f"  OCR pagina {i}/{len(images)}...")
            
            # OCR con italiano + inglese
            text = pytesseract.image_to_string(
                img, 
                lang='ita+eng',
                config='--psm 1'  # Auto page segmentation
            )
            
            if text.strip():
                text_parts.append(f"--- Pagina {i} ---\n{text}")
        
        result = "\n\n".join(text_parts)
        
        if result.strip():
            log.info(f"✅ OCR estratto {len(result)} caratteri da {os.path.basename(path)}")
        else:
            log.warning(f"⚠️ OCR non ha trovato testo in {os.path.basename(path)}")
        
        return _clean_text(result)
    
    except ImportError:
        log.warning("pytesseract o pdf2image non disponibili")
        return ""
    
    except Exception as e:
        log.error(f"❌ OCR fallito su {os.path.basename(path)}: {e}")
        return ""


def _extract_ocr_from_image(path: str) -> str:
    """
    Estrae testo da immagine (JPG, PNG) usando Tesseract OCR.
    """
    try:
        import pytesseract
        from PIL import Image
        
        log.info(f"🔍 OCR image processing {os.path.basename(path)}...")
        
        img = Image.open(path)
        
        # OCR con italiano + inglese
        text = pytesseract.image_to_string(
            img,
            lang='ita+eng',
            config='--psm 3'  # Fully automatic page segmentation
        )
        
        if text.strip():
            log.info(f"✅ OCR estratto {len(text)} caratteri da immagine")
        
        return _clean_text(text)
    
    except ImportError:
        log.warning("pytesseract o PIL non disponibili")
        return ""
    
    except Exception as e:
        log.error(f"❌ OCR fallito su immagine {os.path.basename(path)}: {e}")
        return ""


# MODIFICA ALLA FUNZIONE _pdftotext_safe ESISTENTE
# Sostituisci la funzione _pdftotext_safe con questa versione che usa OCR come fallback:

def _pdftotext_safe_with_ocr(path: str) -> str:
    """
    Estrazione PDF con fallback OCR se pdftotext non trova testo.
    """
    try:
        # Prova prima con pdftotext (veloce)
        out = subprocess.run(
            ["pdftotext", "-layout", "-nopgbrk", path, "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        
        if out.returncode != 0:
            log.warning(f"pdftotext fallito per {os.path.basename(path)}, provo OCR...")
            return _extract_ocr_from_pdf(path)
        
        text = _clean_text(out.stdout)
        
        # Se pdftotext non trova testo (PDF scansionato), usa OCR
        if not text or len(text) < 50:
            log.info(f"pdftotext ha trovato poco testo ({len(text)} char), provo OCR...")
            return _extract_ocr_from_pdf(path)
        
        return text
    
    except subprocess.TimeoutExpired:
        log.error(f"pdftotext timeout su {os.path.basename(path)}, provo OCR...")
        return _extract_ocr_from_pdf(path)
    
    except Exception as e:
        log.error(f"pdftotext errore su {os.path.basename(path)}: {e}, provo OCR...")
        return _extract_ocr_from_pdf(path)


# MODIFICA ALLA FUNZIONE _read_text ESISTENTE
# Aggiungi supporto immagini nella funzione _read_text:

def _read_text(path: str) -> str:
    """Estrae testo da vari formati"""
    ext = os.path.splitext(path)[1].lower()
    
    UNSUPPORTED = {
        '.mpp', '.vsd', '.mdb', '.accdb',
        '.zip', '.rar', '.7z', '.tar', '.gz',
        '.exe', '.dll', '.so',
        '.mp3', '.mp4', '.avi', '.mov', '.wav',
    }
    
    if ext in UNSUPPORTED:
        return ""
    
    try:
        if ext in (".txt", ".md", ".csv", ".log", ".ini", ".conf", ".xml", ".json"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return _clean_text(f.read())
        
        if ext == ".pdf":
            # USA LA VERSIONE CON OCR
            return _pdftotext_safe_with_ocr(path)
        
        if ext == ".docx":
            return _extract_docx(path)
        
        if ext in (".doc", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp", ".rtf"):
            return _libreoffice_convert_safe(path)
        
        # NUOVO: Supporto immagini con OCR
        if ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif"):
            return _extract_ocr_from_image(path)
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return _clean_text(f.read())
    
    except Exception as e:
        log.error(f"Errore estrazione {os.path.basename(path)}: {e}")
        return ""


"""
COME USARE:

1. Copia le funzioni OCR nel worker_tasks.py
2. Sostituisci _pdftotext_safe con _pdftotext_safe_with_ocr
3. Modifica _read_text per usare la versione aggiornata
4. Rebuild worker: docker compose build worker
5. Test con PDF scansionato

PERFORMANCE OCR:
- PDF scansionato 10 pagine: ~30-60 secondi
- Immagine singola: ~2-5 secondi
- GPU NON accelera OCR (usa CPU)

LINGUE SUPPORTATE:
- Italiano (ita)
- Inglese (eng)
- Aggiungi altre: tesseract-ocr-fra, tesseract-ocr-deu, etc.
"""
