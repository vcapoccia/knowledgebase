const $ = (sel, p=document) => p.querySelector(sel);
const $$ = (sel, p=document) => Array.from(p.querySelectorAll(sel));

const state = {
  q: new URLSearchParams(location.search).get('q') || '',
  limit: 20,
  offset: 0,
  total: 0,
  sort: 'relevance',
  filters: {}, // es. { section: Set([...]), year: Set([...]) ... }
  excludeSections: new Set(['Documentazione']) // default
};

function encodeFilters() {
  // L'API accetta filters come JSON string (chiave -> array valori)
  const obj = {};
  for (const [k, set] of Object.entries(state.filters)) {
    if (set.size) obj[k] = Array.from(set);
  }
  return Object.keys(obj).length ? JSON.stringify(obj) : '';
}
function encodeExclude() {
  return JSON.stringify(Array.from(state.excludeSections));
}
function api(path, params={}) {
  const qs = new URLSearchParams(params);
  return fetch(`/api${path}?${qs.toString()}`, { credentials: 'same-origin' })
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
}
function renderFacets(data) {
  // data es.: { section: {Documentazione: 123, OffertaTecnica: 456}, year: {...}, ...}
  const fill = (facetName) => {
    const box = $(`.facet-list[data-facet="${facetName}"]`);
    if (!box) return;
    box.innerHTML = '';
    const buckets = data[facetName] || {};
    const active = state.filters[facetName] || new Set();
    Object.entries(buckets)
      .sort((a,b)=> String(a[0]).localeCompare(String(b[0]), 'it'))
      .forEach(([val, count]) => {
        const pill = document.createElement('button');
        pill.className = 'facet-pill';
        pill.dataset.active = active.has(val) ? 'true' : 'false';
        pill.innerHTML = `<span>${val}</span><small>(${count})</small>`;
        pill.onclick = () => {
          const set = state.filters[facetName] ||= new Set();
          if (set.has(val)) set.delete(val); else set.add(val);
          pill.dataset.active = set.has(val) ? 'true' : 'false';
        };
        box.appendChild(pill);
      });
  };
  ['section','year','client','ambito','oda_code','as_code','tags'].forEach(fill);
}

function badge(text) {
  const b = document.createElement('span');
  b.className = 'badge'; b.textContent = text;
  return b;
}
function htmlesc(s){ return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])) }
function highlight(text, q){
  if (!text) return '';
  const words = (q||'').split(/\s+/).filter(w=>w.length>2);
  let html = htmlesc(text);
  for (const w of words) {
    const re = new RegExp(`(${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`,'ig');
    html = html.replace(re, '<mark>$1</mark>');
  }
  return html;
}
function toDownloadURL(path){ return `/api/download?path=${encodeURIComponent(path)}` }
function toPreviewURL(path){ return `/api/preview?path=${encodeURIComponent(path)}` }

function renderResults(items, append=false){
  const ul = $('#results');
  const tpl = $('#tplResult');
  if (!append) ul.innerHTML = '';
  for (const it of items) {
    const li = tpl.content.firstElementChild.cloneNode(true);
    const title = it.title && it.title.trim() ? it.title : '(senza titolo)';
    const path = it.path || it.filepath || it.source || '';
    const isPDF = /\.pdf$/i.test(path);

    // titolo -> anteprima se PDF, altrimenti download
    const aTitle = $('.title', li);
    aTitle.textContent = title;
    aTitle.href = isPDF ? toPreviewURL(path) : toDownloadURL(path);

    $('.path', li).textContent = path;
    $('.score', li).textContent = (it.score!=null) ? `score ${it.score.toFixed(3)}` : '';

    $('.snippet', li).innerHTML = highlight(it.snippet || it.content || '', state.q);

    const badges = $('.badges', li);
    const meta = it.meta || it.metadata || {};
    const toBadge = ['section','year','client','ambito','oda_code','as_code'];
    for (const key of toBadge) {
      if (meta[key]) badges.appendChild(badge(`${key}:${meta[key]}`));
    }
    if (Array.isArray(meta.tags)) {
      for (const t of meta.tags) badges.appendChild(badge(`#${t}`));
    }

    const aPrev = $('.actions .btn', li);
    aPrev.textContent = isPDF ? 'Anteprima' : 'Apri';
    aPrev.href = isPDF ? toPreviewURL(path) : toDownloadURL(path);

    const aDl = $('.actions .btn.primary', li);
    aDl.textContent = 'Download';
    aDl.href = toDownloadURL(path);

    ul.appendChild(li);
  }
}

async function runSearch(opts={append:false}) {
  $('#resultCount').textContent = 'Caricamento...';
  const params = {
    q: state.q,
    limit: state.limit,
    offset: state.offset,
    sort: state.sort,
    filters: encodeFilters(),
    exclude_sections: encodeExclude(),
  };
  const [facets, results] = await Promise.all([
    api('/facets', { q: state.q, filters: encodeFilters(), exclude_sections: encodeExclude() }),
    api('/search', params)
  ]);

  renderFacets(facets || {});
  renderResults(results?.items || results?.results || [], opts.append);

  const total = results?.total ?? results?.count ?? (state.offset + (results?.items?.length||0));
  state.total = total;
  $('#resultCount').textContent = `${total} risultati`;
  $('#loadMore').style.display = (state.offset + state.limit) < total ? 'inline-flex' : 'none';
}

function applyFiltersAndSearch() {
  state.offset = 0;
  runSearch({append:false}).catch(console.error);
}

function initUI(){
  // Query iniziale
  $('#q').value = state.q;

  // Facet panel (mobile)
  const pane = $('#facetPane');
  $('#facetToggle').onclick = () => pane.dataset.open = 'true';
  $('#facetClose').onclick = () => pane.dataset.open = 'false';

  // Escludi Documentazione
  const chk = $('#excludeDoc');
  const updateExclude = () => {
    if (chk.checked) state.excludeSections.add('Documentazione');
    else state.excludeSections.delete('Documentazione');
  };
  chk.addEventListener('change', updateExclude);
  updateExclude();

  // Ordina
  const sortSel = $('#sortSel');
  sortSel.value = state.sort;
  sortSel.onchange = () => { state.sort = sortSel.value; applyFiltersAndSearch(); };

  // Cerca
  $('#searchForm').addEventListener('submit', (e)=>{
    e.preventDefault();
    state.q = $('#q').value.trim();
    state.offset = 0;
    history.replaceState(null,'', `/?q=${encodeURIComponent(state.q)}`);
    runSearch({append:false}).catch(console.error);
  });

  // Pulsanti faccette
  $('#applyFilters').onclick = () => { pane.dataset.open = 'false'; applyFiltersAndSearch(); };
  $('#resetFilters').onclick = () => { state.filters = {}; applyFiltersAndSearch(); };

  // Paginazione
  $('#loadMore').onclick = () => {
    state.offset += state.limit;
    runSearch({append:true}).catch(console.error);
  };

  // Prima ricerca (se c’è query, altrimenti carica faccette vuote)
  runSearch({append:false}).catch(console.error);
}

document.addEventListener('DOMContentLoaded', initUI);
