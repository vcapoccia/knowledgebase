// frontend/static/app.js v2.1 - Con Paginazione + Faccette Dinamiche + Esclusioni
const API_BASE = '';
const RESULTS_PER_PAGE = 20;

let currentQuery = '';
let currentFilters = {
  area: '',
  anno: '',
  cliente: '',
  oggetto: '',
  tipo_doc: '',
  categoria: '',
  ext: ''
};
let excludeFilters = new Set(); // Filtri da escludere
let allResults = []; // Tutti i risultati caricati
let currentPage = 1;
let totalPages = 1;

// ===== Utility =====
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function fmtScore(score) {
  if (score == null) return '-';
  const n = Number(score);
  return Number.isNaN(n) ? String(score) : (n * 100).toFixed(0) + '%';
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
  // Carica faccette globali all'avvio
  loadInitialFacets();
  
  // Search handlers
  document.getElementById('btn-search')?.addEventListener('click', doSearch);
  document.getElementById('q')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') doSearch();
  });
  
  // Filter handlers
  document.getElementById('btn-apply')?.addEventListener('click', doSearch);
  document.getElementById('btn-reset')?.addEventListener('click', resetFilters);
  
  // Pagination handlers
  document.getElementById('btn-prev')?.addEventListener('click', () => changePage(-1));
  document.getElementById('btn-next')?.addEventListener('click', () => changePage(1));
  
  // Filter change listeners
  ['f-area', 'f-anno', 'f-cliente', 'f-oggetto', 'f-tipo', 'f-categoria', 'f-ext'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => {
        const key = id.replace('f-', '').replace('tipo', 'tipo_doc');
        currentFilters[key] = el.value;
      });
    }
  });
});

// ===== Load Facets (Globali) =====
async function loadInitialFacets() {
  try {
    const response = await fetch(`${API_BASE}/facets`);
    if (!response.ok) return;
    
    const data = await response.json();
    updateFacets(data.facets || {});
  } catch (e) {
    console.error('Errore caricamento faccette:', e);
  }
}

// ===== Search =====
async function doSearch() {
  const query = document.getElementById('q').value.trim();
  
  if (!query) {
    showHint('⚠️ Inserisci una query di ricerca');
    return;
  }
  
  currentQuery = query;
  currentPage = 1; // Reset a pagina 1
  
  // Build filters string (escludendo quelli esclusi)
  const filtersArray = [];
  for (const [key, value] of Object.entries(currentFilters)) {
    if (value && !excludeFilters.has(`${key}:${value}`)) {
      filtersArray.push(`${key}:${value}`);
    }
  }
  
  const filtersStr = filtersArray.join(',');
  
  // Build URL
  const params = new URLSearchParams({
    q_text: query,
    top_k: 100 // Carica fino a 100 risultati
  });
  
  if (filtersStr) {
    params.append('filters', filtersStr);
  }
  
  try {
    showLoading();
    
    // 1. Esegui ricerca
    const searchResponse = await fetch(`${API_BASE}/search?${params}`);
    if (!searchResponse.ok) {
      throw new Error(`HTTP ${searchResponse.status}`);
    }
    const searchData = await searchResponse.json();
    
    // Salva tutti i risultati
    allResults = searchData.hits || [];
    totalPages = Math.ceil(allResults.length / RESULTS_PER_PAGE);
    
    // 2. Carica faccette DINAMICHE basate sui risultati
    const facetsParams = new URLSearchParams({
      q_text: query
    });
    if (filtersStr) {
      facetsParams.append('filters', filtersStr);
    }
    
    try {
      const facetsResponse = await fetch(`${API_BASE}/search_facets?${facetsParams}`);
      if (facetsResponse.ok) {
        const facetsData = await facetsResponse.json();
        updateFacets(facetsData.facets || {});
      }
    } catch (e) {
      console.warn('Faccette dinamiche non disponibili, uso quelle globali');
    }
    
    // 3. Mostra prima pagina
    displayCurrentPage(searchData);
    
  } catch (err) {
    console.error('Errore ricerca:', err);
    showError(`Errore durante la ricerca: ${err.message}`);
  }
}

// ===== Update Facets (DINAMICO) =====
function updateFacets(facets) {
  populateSelect('f-area', facets.area || {});
  populateSelect('f-anno', facets.anno || {});
  populateSelect('f-cliente', facets.cliente || {});
  populateSelect('f-oggetto', facets.oggetto || {});
  populateSelect('f-tipo', facets.tipo_doc || {});
  populateSelect('f-categoria', facets.categoria || {});
  populateSelect('f-ext', facets.ext || {});
}

function populateSelect(selectId, facetData) {
  const select = document.getElementById(selectId);
  if (!select) return;
  
  const currentValue = select.value;
  
  // Mantieni solo l'opzione "Tutte/Tutti"
  while (select.options.length > 1) {
    select.remove(1);
  }
  
  const entries = Object.entries(facetData).sort((a, b) => b[1] - a[1]);
  
  if (entries.length === 0) {
    select.disabled = true;
    return;
  }
  
  select.disabled = false;
  
  entries.forEach(([value, count]) => {
    if (!value) return;
    
    const option = document.createElement('option');
    option.value = value;
    option.textContent = `${value} (${count})`;
    select.appendChild(option);
  });
  
  // Ripristina valore se ancora presente
  if (currentValue && facetData[currentValue]) {
    select.value = currentValue;
  }
}

// ===== Pagination =====
function changePage(delta) {
  const newPage = currentPage + delta;
  
  if (newPage < 1 || newPage > totalPages) {
    return;
  }
  
  currentPage = newPage;
  displayCurrentPage();
}

function displayCurrentPage(searchData) {
  const resultsDiv = document.getElementById('results');
  const statsDiv = document.getElementById('search-stats');
  const totalSpan = document.getElementById('total-results');
  const timeSpan = document.getElementById('search-time');
  const paginationDiv = document.getElementById('pagination');
  const pageInfo = document.getElementById('page-info');
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  
  // Update stats
  totalSpan.textContent = allResults.length;
  if (searchData && searchData.processing_time_ms) {
    timeSpan.textContent = `(${searchData.processing_time_ms}ms)`;
  }
  statsDiv.style.display = 'block';
  
  // Clear results
  resultsDiv.innerHTML = '';
  
  if (allResults.length === 0) {
    resultsDiv.innerHTML = `
      <div class="hint card">
        <p>😕 Nessun risultato trovato per "<strong>${escapeHtml(currentQuery)}</strong>"</p>
        <p>Prova a modificare i filtri o usare termini diversi.</p>
      </div>
    `;
    paginationDiv.style.display = 'none';
    return;
  }
  
  // Calcola range risultati per pagina corrente
  const startIdx = (currentPage - 1) * RESULTS_PER_PAGE;
  const endIdx = Math.min(startIdx + RESULTS_PER_PAGE, allResults.length);
  const pageResults = allResults.slice(startIdx, endIdx);
  
  // Render results
  pageResults.forEach(hit => {
    const card = createResultCard(hit);
    resultsDiv.appendChild(card);
  });
  
  // Update pagination
  if (totalPages > 1) {
    paginationDiv.style.display = 'flex';
    pageInfo.textContent = `Pagina ${currentPage} di ${totalPages} (${startIdx + 1}-${endIdx} di ${allResults.length})`;
    btnPrev.disabled = currentPage === 1;
    btnNext.disabled = currentPage === totalPages;
  } else {
    paginationDiv.style.display = 'none';
  }
  
  // Scroll to top
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ===== Create Result Card =====
function createResultCard(hit) {
  const article = document.createElement('article');
  article.className = 'hit';
  
  const title = escapeHtml(hit.title || 'Documento');
  const score = hit.score != null ? fmtScore(hit.score) : '-';
  const snippet = escapeHtml(hit.text || '').substring(0, 300);
  
  // Costruisci tag metadati CON OPZIONE ESCLUSIONE
  const tags = [];
  if (hit.area) tags.push(createBadgeWithExclude('area', hit.area, '📁'));
  if (hit.anno) tags.push(createBadgeWithExclude('anno', hit.anno, '📅'));
  if (hit.cliente) tags.push(createBadgeWithExclude('cliente', hit.cliente, '👥'));
  if (hit.oggetto) tags.push(createBadgeWithExclude('oggetto', hit.oggetto, '🎯'));
  if (hit.tipo_doc) tags.push(createBadgeWithExclude('tipo_doc', hit.tipo_doc, '📄'));
  if (hit.categoria) tags.push(createBadgeWithExclude('categoria', hit.categoria, '🏷️'));
  if (hit.ext) tags.push(createBadgeWithExclude('ext', hit.ext, '📎'));
  
  article.innerHTML = `
    <header class="hit-head">
      <h4 class="hit-title">${title}</h4>
      ${score !== '-' ? `<span class="score">score: ${score}</span>` : ''}
    </header>
    
    ${tags.length > 0 ? `<div class="meta">${tags.join('')}</div>` : ''}
    
    ${snippet ? `<p class="snippet clamp-3">${snippet}...</p>` : ''}
    
    <div class="hit-actions">
      ${hit.path ? `<span class="small muted">📂 ${escapeHtml(hit.path)}</span>` : ''}
    </div>
  `;
  
  return article;
}

function createBadgeWithExclude(key, value, icon) {
  const isExcluded = excludeFilters.has(`${key}:${value}`);
  const excludeClass = isExcluded ? 'excluded' : '';
  const excludeIcon = isExcluded ? '✕' : '—';
  const escapedValue = escapeHtml(value);
  
  return `
    <span class="tag-group">
      <span class="tag ${excludeClass}">${icon} ${escapedValue}</span>
      <button class="tag-exclude ${excludeClass}" 
              onclick="toggleExclude('${key}', '${escapedValue.replace(/'/g, "\\'")}' )" 
              title="${isExcluded ? 'Rimuovi esclusione' : 'Escludi dai risultati'}">
        ${excludeIcon}
      </button>
    </span>
  `;
}

function toggleExclude(key, value) {
  const filterKey = `${key}:${value}`;
  
  if (excludeFilters.has(filterKey)) {
    excludeFilters.delete(filterKey);
  } else {
    excludeFilters.add(filterKey);
  }
  
  // Rilancia ricerca con nuovi filtri
  doSearch();
}

// ===== UI States =====
function showLoading() {
  const resultsDiv = document.getElementById('results');
  resultsDiv.innerHTML = `
    <div class="hint card">
      <p>🔍 Ricerca in corso...</p>
    </div>
  `;
  document.getElementById('pagination').style.display = 'none';
}

function showHint(message) {
  const resultsDiv = document.getElementById('results');
  resultsDiv.innerHTML = `
    <div class="hint card">
      <p>${message}</p>
    </div>
  `;
  document.getElementById('pagination').style.display = 'none';
}

function showError(message) {
  const resultsDiv = document.getElementById('results');
  resultsDiv.innerHTML = `
    <div class="hint card">
      <p class="error">❌ ${message}</p>
    </div>
  `;
  document.getElementById('pagination').style.display = 'none';
}

// ===== Reset =====
function resetFilters() {
  // Reset select values
  ['f-area', 'f-anno', 'f-cliente', 'f-oggetto', 'f-tipo', 'f-categoria', 'f-ext'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  
  // Reset filters object
  currentFilters = {
    area: '',
    anno: '',
    cliente: '',
    oggetto: '',
    tipo_doc: '',
    categoria: '',
    ext: ''
  };
  
  // Reset esclusioni
  excludeFilters.clear();
  
  // Reset risultati
  allResults = [];
  currentPage = 1;
  totalPages = 1;
  
  // Clear search
  document.getElementById('q').value = '';
  currentQuery = '';
  
  // Reset UI
  const resultsDiv = document.getElementById('results');
  resultsDiv.innerHTML = `
    <div class="hint card">
      <p>👋 Benvenuto nella ricerca Knowledge Base!</p>
      <p>Inserisci una parola chiave per iniziare la ricerca.</p>
      <p>Usa i filtri laterali per affinare i risultati.</p>
    </div>
  `;
  
  document.getElementById('search-stats').style.display = 'none';
  document.getElementById('pagination').style.display = 'none';
  
  // Ricarica faccette globali
  loadInitialFacets();
}
