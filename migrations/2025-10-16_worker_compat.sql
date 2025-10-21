-- Enable UUID generator (pgcrypto) per gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1) Imposta un default su id (tipo text) così l'INSERT ... RETURNING id del worker funziona
ALTER TABLE public.documents
  ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;

-- 2) Aggiungi le colonne attese dal worker
ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS file_path    text,
  ADD COLUMN IF NOT EXISTS file_hash    text,
  ADD COLUMN IF NOT EXISTS text_content text,
  ADD COLUMN IF NOT EXISTS model        text;

-- 3) Backfill minimo per retrocompatibilità (non tocca righe già valorizzate)
UPDATE public.documents SET file_path = path
WHERE file_path IS NULL AND path IS NOT NULL;

UPDATE public.documents SET text_content = content
WHERE text_content IS NULL AND content IS NOT NULL;

-- 4) Indici utili per le query del worker
CREATE INDEX IF NOT EXISTS idx_documents_file_path ON public.documents (file_path);
CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON public.documents (file_hash);
CREATE INDEX IF NOT EXISTS idx_documents_model     ON public.documents (model);

-- 5) Dedup/lookup rapido usato dal worker:
--    SELECT id FROM documents WHERE file_path = $1 AND file_hash = $2 AND model = $3
--    NOTA: i NULL in Postgres sono "distinct", quindi la UNIQUE non blocca righe con NULL.
--    Se vuoi evitare duplicati solo quando TUTTI e 3 sono non-NULL, va bene così.
CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_file_hash_model
ON public.documents (file_path, file_hash, model);

-- (Facoltativo) Se vuoi forzare che almeno file_path sia sempre presente sui nuovi insert:
-- ALTER TABLE public.documents ALTER COLUMN file_path SET NOT NULL;

