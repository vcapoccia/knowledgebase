const $ = (sel, p=document) => p.querySelector(sel);
const $$ = (sel, p=document) => Array.from(p.querySelectorAll(sel));

const state = {
  q: new URLSearchParams(location.search).get('q') || '',
  limit: 20,
  offset: 0,
  total: 0,
  sort: 'relevance',
  filters: {},
  excludeSections: new Set(['documentazione'])
};

function api(path, params={}) {
  const qs = new URLSearchParams(params);
  return fetch(`/api${path}?${qs.toString()}`, { credentials: 'same-origin' })
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}: ${r.statusText}`);
      return r.json();
    });
}

function renderFacets(data) {
  console.log('Facets data received:', data);
  
  const fieldMapping = {
    'sezione': 'sezione',
    'anno': 'anno', 
    'cliente': 'cliente',
    'ambito': 'ambito',
    'kb_area': 'kb_area',
    'livello': 'livello',
    'oda_code': 'oda_code',
    'as_code': 'as_code'
  };

  const strongFacets = data?.strong || {};
  
  Object.entries(fieldMapping).forEach(([uiField, apiField]) => {
    const box = $(`.facet-sec[data-key="${uiField}"] .facet-list`);
    if (!box) return;
    
    box.innerHTML = '';
    const buckets = strongFacets[apiField] || {};
    const active = state.filters[uiField] || new Set();
    
    const sortedEntries = Object.entries(buckets).sort((a,b) => {
      if (uiField === 'anno') {
        return parseInt(a[0]) - parseInt(b[0]);
      }
      return String(a[0]).localeCompare(String(b[0]), 'it');
    });
    
    sortedEntries.forEach(([val, count]) => {
      if (!val || count === 0) return;
      
      const pill = document.createElement('button');
      pill.className = 'chip';
      pill.dataset.key = uiField;
      pill.dataset.value = val;
      pill.dataset.on = active.has(val) ? '1' : '0';
      pill.innerHTML = `<span>${val}</span><span class="cnt">(${count})</span>`;
      
      pill.onclick = (e) => {
        e.preventDefault();
        toggleFacet(uiField, val);
      };
      
      box.appendChild(pill);
    });
  });
}

function toggleFacet(key, value) {
  const set = state.filters[key] ||= new Set();
  if (set.has(value)) {
    set.delete(value);
    if (set.size === 0) delete state.filters[key];
  } else {
    set.add(value);
  }
  state.offset = 0;
  performSearch();
}

function renderResults(items, append=false) {
  const ul = $('#list');
  if (!append) ul.innerHTML = '';
  
  if (!Array.isArray(items) || items.length === 0) {
    if (!append) ul.innerHTML = '<div class="empty muted">Nessun risultato trovato.</div>';
    return;
  }
  
  items.forEach(hit => {
    const resultDiv = document.createElement('div');
    resultDiv.className = 'result';
    
    const title = hit.title || '(senza titolo)';
    const pathRel = hit.path_rel || '';
    const score = hit.score ? hit.score.toFixed(3) : 'N/A';
    const snippet = hit.snippet || '';
    
    const metaTags = [];
    ['sezione', 'cliente', 'anno', 'ambito', 'kb_area', 'livello'].forEach(field => {
      if (hit[field]) {
        metaTags.push(`<span class="tag"><b>${field}:</b> ${hit[field]}</span>`);
      }
    });
    
    resultDiv.innerHTML = `
      <div style="flex:1;min-width:0">
        <h4><a href="/files/${encodeURIComponent(pathRel)}" target="_blank">${title}</a></h4>
        <div class="meta">${metaTags.join(' ')}</div>
        <div class="snippet">${snippet}</div>
        <div class="path">${pathRel}</div>
      </div>
      <div class="score">score: <b>${score}</b></div>
      <div class="open">
        <a class="btn" href="/files/${encodeURIComponent(pathRel)}" target="_blank" rel="noopener">Apri</a>
      </div>
    `;
    
    ul.appendChild(resultDiv);
  });
}

async function performSearch(append=false) {
  if (state.fetching) return;
  state.fetching = true;
  
  try {
    $('#resinfo').textContent = 'Caricamento...';
    
    let queryWithFilters = state.q;
    for (const [key, valueSet] of Object.entries(state.filters)) {
      for (const value of valueSet) {
        queryWithFilters += ` ${key}:${value}`;
      }
    }
    
    const searchParams = { q: queryWithFilters, k: state.limit };
    const facetParams = { q: queryWithFilters, k: 200 };
    
    const [facetsData, searchData] = await Promise.all([
      api('/facets', facetParams),
      api('/search', searchParams)
    ]);
    
    renderFacets(facetsData);
    
    const hits = searchData?.hits || [];
    renderResults(hits, append);
    
    const total = hits.length;
    state.total = total;
    $('#resinfo').textContent = `${total} risultati`;
    
  } catch (error) {
    console.error('Search error:', error);
    $('#list').innerHTML = `<div class="error">Errore durante la ricerca: ${error.message}</div>`;
  } finally {
    state.fetching = false;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const $q = $('#q');
  const $go = $('#go');
  const $clear = $('#clear');
  const $excludeDoc = $('#excludeDoc');
  const $reset = $('#reset');
  
  $go.addEventListener('click', () => {
    state.q = $q.value.trim();
    state.offset = 0;
    performSearch();
  });
  
  $q.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      $go.click();
    }
  });
  
  $clear.addEventListener('click', () => {
    $q.value = '';
    state.q = '';
    state.filters = {};
    state.offset = 0;
    performSearch();
  });
  
  $reset.addEventListener('click', () => {
    state.filters = {};
    state.offset = 0;
    performSearch();
  });
  
  $excludeDoc.addEventListener('change', () => {
    if ($excludeDoc.checked) {
      state.excludeSections.add('documentazione');
    } else {
      state.excludeSections.delete('documentazione');
    }
    state.offset = 0;
    performSearch();
  });
  
  api('/facets', {}).then(renderFacets).catch(console.error);
});