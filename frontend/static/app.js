(() => {
  const $ = (sel) => document.querySelector(sel);
  const api = (path, opts={}) => fetch(path, opts).then(r => r.ok ? r.json() : Promise.reject(r));

  // ---------- HOME ----------
  function renderResults(items) {
    const wrap = $('#results');
    if (!wrap) return;
    if (!items || !items.length) {
      wrap.innerHTML = '<div class="muted">Nessun risultato</div>';
      return;
    }
    wrap.innerHTML = items.map(h => `
      <article class="hit">
        <header class="hit-head">
          <h4 class="hit-title">${escapeHtml(h.title || h.doc_id)}</h4>
          <span class="score">score: ${fmtScore(h.score)}</span>
        </header>
        <div class="meta">
          ${h.area ? `<span class="tag">${h.area}</span>` : ''}
          ${h.tipo ? `<span class="tag">${h.tipo}</span>` : ''}
          ${h.year ? `<span class="tag">${h.year}</span>` : ''}
          ${h.ext ? `<span class="tag">.${h.ext}</span>` : ''}
        </div>
        <p class="snippet clamp-3">${h.content_snippet || ''}</p>
        ${h.url ? `<a class="small" href="${h.url}" target="_blank" rel="noopener">Apri</a>` : ''}
      </article>
    `).join('');
  }

  function fmtScore(s) {
    if (s == null) return '-';
    const n = Number(s);
    if (Number.isNaN(n)) return String(s);
    return n.toFixed(3);
  }

  function escapeHtml(x) {
    return (x ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
  }

  async function doSearch() {
    const q = $('#q').value.trim();
    const area = $('#f-area').value || '';
    const tipo = $('#f-tipo').value || '';
    const year = $('#f-year').value || '';
    if (!q) { $('#results').innerHTML = '<div class="muted">Inserisci un testo di ricerca</div>'; return; }

    const qs = new URLSearchParams({ q_text: q, top_k: '10' });
    if (area) qs.set('area', area);
    if (tipo) qs.set('tipo', tipo);
    if (year) qs.set('year', year);

    $('#results').innerHTML = '<div class="muted">Ricerca in corso…</div>';
    try {
      const res = await api('/search?' + qs.toString());
      renderResults(res.hits || []);
    } catch (e) {
      $('#results').innerHTML = '<div class="error">Errore nella ricerca</div>';
    }
  }

  function resetFilters() {
    $('#q').value = '';
    $('#f-area').value = '';
    $('#f-tipo').value = '';
    $('#f-year').value = '';
    $('#results').innerHTML = '';
  }

  function applyFilters() {
    // non persiste nulla: legge lo stato attuale e lancia
    doSearch();
  }

  function bootHome() {
    if (!$('#results')) return;
    $('#btn-search')?.addEventListener('click', doSearch);
    $('#btn-apply')?.addEventListener('click', applyFilters);
    $('#btn-reset')?.addEventListener('click', resetFilters);
    $('#q')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
  }

  // ---------- ADMIN ----------
  async function refreshQueue() {
    try {
      const s = await api('/queue');
      $('#q-name').textContent = s.queue;
      $('#q-count').textContent = s.count ?? 0;
      $('#q-workers').textContent = (s.workers || []).length;
      $('#q-started').textContent = s.started_jobs ?? 0;
      $('#q-deferred').textContent = s.deferred ?? 0;
      $('#q-scheduled').textContent = s.scheduled ?? 0;
      $('#q-failed').textContent = s.failed ?? 0;
    } catch {}
  }
  async function refreshHealth() {
    try {
      const h = await api('/health');
      $('#health').textContent = JSON.stringify(h, null, 2);
    } catch { $('#health').textContent = 'Errore'; }
  }
  async function refreshFailed() {
    const list = $('#failed-list');
    if (!list) return;
    try {
      const rows = await api('/failed_docs?limit=100');
      if (!rows.length) { list.innerHTML = '<div class="muted">Nessun documento fallito</div>'; return; }
      list.innerHTML = rows.map(r => `
        <div class="failed-row">
          <div class="failed-head">
            <b>${escapeHtml(r.filename || r.doc_id || '-')}</b>
            <span class="muted">${new Date((r.ts||0)*1000).toLocaleString()}</span>
          </div>
          <div class="clamp-3">${escapeHtml(r.error || '')}</div>
          ${r.path ? `<div class="small muted">${escapeHtml(r.path)}</div>` : ''}
        </div>
      `).join('');
    } catch {
      list.innerHTML = '<div class="error">Errore nel caricare la lista</div>';
    }
  }
  function bootAdmin() {
    if (!$('#failed-list')) return;
    $('#btn-init')?.addEventListener('click', async () => {
      $('#ingest-status').textContent = 'Inizializzazione…';
      try { await api('/init_indexes', { method: 'POST' }); $('#ingest-status').textContent = 'OK'; }
      catch { $('#ingest-status').textContent = 'Errore'; }
      refreshHealth(); refreshQueue();
    });
    $('#btn-ingest')?.addEventListener('click', async () => {
      $('#ingest-status').textContent = 'Avvio job…';
      try {
        const r = await api('/ingestion/start', { method: 'POST' });
        $('#ingest-status').textContent = 'Job ' + (r.job_id || '');
      } catch { $('#ingest-status').textContent = 'Errore'; }
      refreshQueue();
    });
    refreshHealth(); refreshQueue(); refreshFailed();
    setInterval(() => { refreshQueue(); refreshFailed(); }, 5000);
  }

  document.addEventListener('DOMContentLoaded', () => { bootHome(); bootAdmin(); });
})();