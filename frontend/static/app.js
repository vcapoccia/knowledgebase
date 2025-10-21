// frontend/static/app.js v3.1 - Con Thumbnail + Numero Pagina
const API_BASE = '';
const RESULTS_PER_PAGE = 20;
const MAX_FACET_ITEMS = 10;

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
let quickExclusions = new Set();
let allResults = [];
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

function highlightText(text, query) {
  if (!query || !text) return escapeHtml(text);
  
  const terms = query.toLowerCase().split(/\s+/).filter(t => t.length > 2);
  let result = escapeHtml(text);
  
  terms.forEach(term => {
    const regex = new RegExp(`(${term})`, 'gi');
    result = result.replace(regex, '<mark>$1</mark>');
  });
  
  return result;
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
  loadInitialFacets();
  
  document.getElementById('btn-search')?.addEventListener('click', doSearch);
  document.getElementById('q')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') doSearch();
  });
  
  document.getElementById('btn-reset-filters')?.addEventListener('click', resetFilters);
  document.getElementById('btn-prev')?.addEventListener('click', () => changePage(-1));
  document.getElementById('btn-next')?.addEventListener('click', () => changePage(1));
  
  document.querySelectorAll('.quick-chip').forEach(chip => {
    chip.addEventListener('click', () => toggleQuickExclusion(chip));
  });
});

// ===== Quick Exclusion Toolbar =====
function toggleQuickExclusion(chip) {
  const category = chip.dataset.category;
  
  if (quickExclusions.has(category)) {
    quickExclusions.delete(category);
    chip.classList.remove('excluded');
  } else {
    quickExclusions.add(category);
    chip.classList.add('excluded');
  }
  
  if (currentQuery) {
    doSearch();
  }
}

// ===== Load Facets =====
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
  currentPage = 1;
  
  document.getElementById('quick-filters').style.display = 'flex';
  
  const filtersArray = [];
  for (const [key, value] of Object.entries(currentFilters)) {
    if (value) {
      filtersArray.push(`${key}:${value}`);
    }
  }
  
  const filtersStr = filtersArray.join(',');
  
  const params = new URLSearchParams({
    q_text: query,
    top_k: 100
  });
  
  if (filtersStr) {
    params.append('filters', filtersStr);
  }
  
  try {
    showLoading();
    
    const searchResponse = await fetch(`${API_BASE}/search?${params}`);
    if (!searchResponse.ok) {
      throw new Error(`HTTP ${searchResponse.status}`);
    }
    const searchData = await searchResponse.json();
    
    // Filtra esclusioni client-side
    let hits = searchData.hits || [];
    if (quickExclusions.size > 0) {
      hits = hits.filter(hit => !quickExclusions.has(hit.categoria));
    }
    
    allResults = hits;
    totalPages = Math.ceil(allResults.length / RESULTS_PER_PAGE);
    
    // Carica faccette dinamiche
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
      console.warn('Faccette dinamiche non disponibili');
    }
    
    displayCurrentPage(searchData);
    
  } catch (err) {
    console.error('Errore ricerca:', err);
    showError(`Errore durante la ricerca: ${err.message}`);
  }
}

// ===== Update Facets =====
function updateFacets(facets) {
  populateChips('chips-area', 'area', facets.area || {});
  populateChips('chips-anno', 'anno', facets.anno || {});
  populateChips('chips-cliente', 'cliente', facets.cliente || {});
  populateChips('chips-oggetto', 'oggetto', facets.oggetto || {});
  populateChips('chips-tipo', 'tipo_doc', facets.tipo_doc || {});
  populateChips('chips-categoria', 'categoria', facets.categoria || {});
  populateChips('chips-ext', 'ext', facets.ext || {});
}

function populateChips(containerId, filterKey, facetData) {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  container.innerHTML = '';
  
  const entries = Object.entries(facetData).sort((a, b) => b[1] - a[1]);
  
  if (entries.length === 0) {
    container.innerHTML = '<span class="muted small">Nessun valore</span>';
    return;
  }
  
  const visibleEntries = entries.slice(0, MAX_FACET_ITEMS);
  
  visibleEntries.forEach(([value, count]) => {
    if (!value) return;
    
    const chip = document.createElement('button');
    chip.className = 'facet-chip';
    chip.textContent = `${value} (${count})`;
    chip.dataset.key = filterKey;
    chip.dataset.value = value;
    
    if (currentFilters[filterKey] === value) {
      chip.classList.add('active');
    }
    
    chip.addEventListener('click', () => toggleFilter(filterKey, value, chip));
    
    container.appendChild(chip);
  });
  
  if (entries.length > MAX_FACET_ITEMS) {
    const moreBtn = document.createElement('span');
    moreBtn.className = 'muted small';
    moreBtn.textContent = `+${entries.length - MAX_FACET_ITEMS} altri...`;
    container.appendChild(moreBtn);
  }
}

function toggleFilter(key, value, chipElement) {
  if (currentFilters[key] === value) {
    currentFilters[key] = '';
    chipElement.classList.remove('active');
  } else {
    document.querySelectorAll(`[data-key="${key}"]`).forEach(c => c.classList.remove('active'));
    currentFilters[key] = value;
    chipElement.classList.add('active');
  }
  
  if (currentQuery) {
    doSearch();
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
  
  totalSpan.textContent = allResults.length;
  if (searchData && searchData.processing_time_ms) {
    timeSpan.textContent = `(${searchData.processing_time_ms}ms)`;
  }
  statsDiv.style.display = 'block';
  
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
  
  const startIdx = (currentPage - 1) * RESULTS_PER_PAGE;
  const endIdx = Math.min(startIdx + RESULTS_PER_PAGE, allResults.length);
  const pageResults = allResults.slice(startIdx, endIdx);
  
  pageResults.forEach(hit => {
    const card = createResultCard(hit);
    resultsDiv.appendChild(card);
  });
  
  if (totalPages > 1) {
    paginationDiv.style.display = 'flex';
    pageInfo.textContent = `Pagina ${currentPage} di ${totalPages} (${startIdx + 1}-${endIdx} di ${allResults.length})`;
    btnPrev.disabled = currentPage === 1;
    btnNext.disabled = currentPage === totalPages;
  } else {
    paginationDiv.style.display = 'none';
  }
  
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ===== Create Result Card CON THUMBNAIL =====
function createResultCard(hit) {
  const article = document.createElement('article');
  article.className = 'hit';
  
  const title = escapeHtml(hit.title || 'Documento');
  const score = hit.score != null ? fmtScore(hit.score) : '-';
  const snippet = highlightText(hit.text || '', currentQuery);
  const pageNum = hit.page_number;
  const isPdf = hit.ext === 'pdf';
  
  // Badge metadati CON NUMERO PAGINA
  const tags = [];
  if (hit.area) tags.push(`<span class="badge">📁 ${escapeHtml(hit.area)}</span>`);
  if (hit.anno) tags.push(`<span class="badge">📅 ${hit.anno}</span>`);
  if (hit.cliente) tags.push(`<span class="badge">👥 ${escapeHtml(hit.cliente)}</span>`);
  if (hit.oggetto) tags.push(`<span class="badge">🎯 ${escapeHtml(hit.oggetto)}</span>`);
  if (hit.tipo_doc) tags.push(`<span class="badge">📄 ${escapeHtml(hit.tipo_doc)}</span>`);
  if (hit.categoria) tags.push(`<span class="badge">🏷️ ${escapeHtml(hit.categoria)}</span>`);
  if (pageNum) tags.push(`<span class="badge page-badge">📄 Pagina ${pageNum}</span>`);
  if (hit.ext) tags.push(`<span class="badge">📎 .${escapeHtml(hit.ext)}</span>`);
  
  // Thumbnail (solo PDF)
  let thumbnailHtml = '';
  if (isPdf && pageNum && hit.path) {
    const thumbUrl = `${API_BASE}/thumbnail?path=${encodeURIComponent(hit.path)}&page=${pageNum}&width=150`;
    thumbnailHtml = `
      <div class="hit-thumbnail">
        <div class="thumbnail-preview">
          <img src="${thumbUrl}" alt="Preview pagina ${pageNum}" 
               onerror="this.style.display='none'"
               loading="lazy">
          <span class="thumb-label">Pag. ${pageNum}</span>
        </div>
      </div>
    `;
  }
  
  article.innerHTML = `
    <div class="hit-content">
      ${thumbnailHtml}
      
      <div class="hit-main">
        <header class="hit-head">
          <h4 class="hit-title">${title}</h4>
          ${score !== '-' ? `<span class="score">score: ${score}</span>` : ''}
        </header>
        
        ${tags.length > 0 ? `<div class="meta">${tags.join('')}</div>` : ''}
        
        ${snippet ? `<p class="snippet">${snippet}</p>` : ''}
        
        <div class="hit-actions">
          <span class="small muted">📂 ${escapeHtml(hit.path || '')}</span>
          <div class="hit-buttons">
            ${hit.path ? `<a href="${API_BASE}/download_file?path=${encodeURIComponent(hit.path)}" class="btn small primary" download>📥 Download</a>` : ''}
            ${isPdf && pageNum && hit.path ? `<a href="${API_BASE}/download_file?path=${encodeURIComponent(hit.path)}#page=${pageNum}" class="btn small" target="_blank">🔗 Pag. ${pageNum}</a>` : ''}
          </div>
        </div>
      </div>
    </div>
  `;
  
  return article;
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
  currentFilters = {
    area: '',
    anno: '',
    cliente: '',
    oggetto: '',
    tipo_doc: '',
    categoria: '',
    ext: ''
  };
  
  quickExclusions.clear();
  document.querySelectorAll('.quick-chip').forEach(chip => {
    chip.classList.remove('excluded');
  });
  
  document.querySelectorAll('.facet-chip').forEach(chip => {
    chip.classList.remove('active');
  });
  
  allResults = [];
  currentPage = 1;
  totalPages = 1;
  
  document.getElementById('q').value = '';
  currentQuery = '';
  
  document.getElementById('quick-filters').style.display = 'none';
  
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
  
  loadInitialFacets();
}
