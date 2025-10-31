// frontend/static/app_v2_fixed.js - FIX + USER TAGS
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
  ext: '',
  sd_numero: '',
  lotto: '',
  progressivo_oda: '',
  progressivo_as: '',
  fase: ''
};
let excludeFilters = new Set();
let allResults = [];
let currentPage = 1;
let totalPages = 1;
let sidebarVisible = true;

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
  console.log('🚀 App v2.7 FIXED inizializzata');
  
  // Load stato sidebar da localStorage
  const savedState = localStorage.getItem('sidebarVisible');
  if (savedState !== null) {
    sidebarVisible = savedState === 'true';
    applySidebarState();
  }
  
  loadInitialFacets();
  
  document.getElementById('btn-search')?.addEventListener('click', doSearch);
  document.getElementById('q')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') doSearch();
  });
  
  document.getElementById('btn-apply')?.addEventListener('click', doSearch);
  document.getElementById('btn-reset')?.addEventListener('click', resetFilters);
  
  document.getElementById('btn-prev')?.addEventListener('click', () => changePage(-1));
  document.getElementById('btn-next')?.addEventListener('click', () => changePage(1));
  
  ['f-area', 'f-anno', 'f-cliente', 'f-oggetto', 'f-tipo', 'f-categoria', 'f-ext', 'f-sd', 'f-lotto', 'f-prog-oda', 'f-prog-as', 'f-fase'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('change', () => {
        let key = id.replace('f-', '').replace('tipo', 'tipo_doc');
        
        // Map dei nuovi filtri
        if (id === 'f-sd') key = 'sd_numero';
        if (id === 'f-prog-oda') key = 'progressivo_oda';
        if (id === 'f-prog-as') key = 'progressivo_as';
        
        currentFilters[key] = el.value;
      });
    }
  });
  
  // Toggle sidebar - UNICO HANDLER
  const advancedToggle = document.getElementById('advanced-toggle');
  if (advancedToggle) {
    advancedToggle.addEventListener('click', toggleSidebar);
  }
  
  const sidebarToggle = document.getElementById('btn-toggle-sidebar');
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', toggleSidebar);
  }
});

// ===== Sidebar Toggle - FIXED =====
function toggleSidebar() {
  sidebarVisible = !sidebarVisible;
  applySidebarState();
  localStorage.setItem('sidebarVisible', sidebarVisible);
}

function applySidebarState() {
  const sidebar = document.getElementById('sidebar');
  const advancedBtn = document.getElementById('advanced-toggle');
  
  if (!sidebar) return;
  
  if (sidebarVisible) {
    sidebar.classList.remove('collapsed');
    
    if (advancedBtn) {
      advancedBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="15 18 9 12 15 6"></polyline>
        </svg>
        Nascondi Filtri
      `;
      advancedBtn.title = 'Nascondi pannello filtri';
    }
  } else {
    sidebar.classList.add('collapsed');
    
    if (advancedBtn) {
      advancedBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="4" y1="21" x2="4" y2="14"></line>
          <line x1="4" y1="10" x2="4" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12" y2="3"></line>
          <line x1="20" y1="21" x2="20" y2="16"></line>
          <line x1="20" y1="12" x2="20" y2="3"></line>
        </svg>
        Mostra Filtri
      `;
      advancedBtn.title = 'Mostra pannello filtri';
    }
  }
}

// ===== Load Facets =====
async function loadInitialFacets() {
  try {
    const response = await fetch(`${API_BASE}/facets`);
    if (!response.ok) return;
    const data = await response.json();
    updateFacets(data.facets || data || {});
  } catch (e) {
    console.error('Errore facets:', e);
  }
}

// ===== Search =====
async function doSearch() {
  const query = document.getElementById('q').value.trim();
  
  if (!query) {
    showHint('⚠️ Inserisci una query');
    return;
  }
  
  currentQuery = query;
  currentPage = 1;
  
  const filtersArray = [];
  for (const [key, value] of Object.entries(currentFilters)) {
    if (value && !excludeFilters.has(`${key}:${value}`)) {
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
    
    allResults = searchData.hits || searchData || [];
    totalPages = Math.ceil(allResults.length / RESULTS_PER_PAGE);
    
    try {
      const facetsParams = new URLSearchParams({ q_text: query });
      if (filtersStr) facetsParams.append('filters', filtersStr);
      
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
    showError(`Errore: ${err.message}`);
  }
}

// ===== Update Facets =====
function updateFacets(facets) {
  populateSelect('f-area', facets.area || {});
  populateSelect('f-anno', facets.anno || {});
  populateSelect('f-cliente', facets.cliente || {});
  populateSelect('f-oggetto', facets.oggetto || {});
  populateSelect('f-tipo', facets.tipo_doc || {});
  populateSelect('f-categoria', facets.categoria || {});
  populateSelect('f-ext', facets.ext || {});
  
  // Nuovi metadati
  populateSelectArray('f-sd', facets.sd_numero || []);
  populateSelectArray('f-lotto', facets.lotto || []);
  populateSelectArray('f-prog-oda', facets.progressivo_oda || []);
  populateSelectArray('f-prog-as', facets.progressivo_as || []);
  populateSelectArray('f-fase', facets.fase || []);
}

function populateSelect(selectId, facetData) {
  const select = document.getElementById(selectId);
  if (!select) return;
  
  const currentValue = select.value;
  
  while (select.options.length > 1) {
    select.remove(1);
  }
  
  // Converti in array se è un oggetto
  let entries = [];
  
  if (Array.isArray(facetData)) {
    // Formato API: [{value: "X", count: N}, ...]
    entries = facetData.map(item => [item.value, item.count]);
  } else if (typeof facetData === 'object' && facetData !== null) {
    // Formato vecchio: {value: count, ...}
    entries = Object.entries(facetData);
  }
  
  entries.sort((a, b) => (b[1] || 0) - (a[1] || 0));
  
  if (entries.length === 0) {
    select.disabled = true;
    return;
  }
  
  select.disabled = false;
  
  entries.forEach(([value, count]) => {
    if (!value || value === 'null') return;
    
    const option = document.createElement('option');
    option.value = value;
    option.textContent = `${value} (${count})`;
    select.appendChild(option);
  });
  
  if (currentValue) {
    const stillExists = entries.some(([val]) => val === currentValue);
    if (stillExists) {
      select.value = currentValue;
    }
  }
}

function populateSelectArray(selectId, values) {
  const select = document.getElementById(selectId);
  if (!select) return;
  
  const currentValue = select.value;
  
  // Rimuovi tutte le opzioni tranne la prima (default "Tutti/Tutte")
  while (select.options.length > 1) {
    select.remove(1);
  }
  
  if (!Array.isArray(values) || values.length === 0) {
    select.disabled = true;
    return;
  }
  
  select.disabled = false;
  
  values.forEach(value => {
    if (value === null || value === undefined) return;
    
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  
  // Ripristina valore selezionato se ancora presente
  if (currentValue && values.includes(parseInt(currentValue)) || values.includes(currentValue)) {
    select.value = currentValue;
  }
}

// ===== Pagination =====
function changePage(delta) {
  const newPage = currentPage + delta;
  if (newPage < 1 || newPage > totalPages) return;
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
      <div class="welcome-card">
        <h2>😕 Nessun risultato</h2>
        <p>Prova termini diversi o modifica i filtri.</p>
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

// ===== Create Result Card - WITH USER TAGS =====
function createResultCard(hit) {
  const article = document.createElement('article');
  article.className = 'hit';
  
  const title = escapeHtml(hit.title || hit.filename || 'Documento');
  const score = hit.score != null ? fmtScore(hit.score) : '-';
  const snippet = escapeHtml((hit.text || hit.text_content || '').substring(0, 300));
  const filePath = hit.path || hit.file_path || '';
  const docId = hit.id || hit.doc_id || '';
  
  const tags = [];
  if (hit.area) tags.push(createBadgeWithExclude('area', hit.area, '📍'));
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
    
    <div class="user-tags-section" data-doc-id="${escapeHtml(docId)}">
      <div class="user-tags-header">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path>
          <line x1="7" y1="7" x2="7.01" y2="7"></line>
        </svg>
        <span class="user-tags-title">I Tuoi Tag</span>
      </div>
      
      <div class="user-tags-list"></div>
      
      <div class="user-tags-input-wrapper">
        <input 
          type="text" 
          class="user-tags-input" 
          placeholder="Aggiungi un tag personale..."
          maxlength="50"
        >
        <button class="btn-add-tag" title="Aggiungi tag">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
        </button>
      </div>
    </div>
    
    <div class="hit-actions">
      <span class="small muted">📂 ${escapeHtml(filePath)}</span>
      <div class="hit-buttons">
        <button class="btn-action btn-download" data-path="${escapeHtml(filePath)}" title="Scarica documento">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="7 10 12 15 17 10"></polyline>
            <line x1="12" y1="15" x2="12" y2="3"></line>
          </svg>
          Download
        </button>
        <button class="btn-action btn-copy" data-path="${escapeHtml(filePath)}" title="Copia percorso file">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          Copia Path
        </button>
      </div>
    </div>
  `;
  
  // Event listeners
  const btnDownload = article.querySelector('.btn-download');
  const btnCopy = article.querySelector('.btn-copy');
  const btnAddTag = article.querySelector('.btn-add-tag');
  const tagInput = article.querySelector('.user-tags-input');
  
  btnDownload.addEventListener('click', () => downloadDocument(filePath));
  btnCopy.addEventListener('click', () => copyPath(filePath));
  
  // User tags
  if (docId) {
    loadUserTags(docId, article);
    
    btnAddTag.addEventListener('click', () => addUserTag(docId, tagInput.value.trim(), article));
    tagInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter' && tagInput.value.trim()) {
        addUserTag(docId, tagInput.value.trim(), article);
      }
    });
  }
  
  return article;
}

function createBadgeWithExclude(key, value, icon) {
  const isExcluded = excludeFilters.has(`${key}:${value}`);
  const excludeClass = isExcluded ? 'excluded' : '';
  const excludeIcon = isExcluded ? '✓' : '−';
  const escapedValue = escapeHtml(value);
  
  return `
    <span class="tag-group">
      <span class="tag ${excludeClass}">${icon} ${escapedValue}</span>
      <button class="tag-exclude ${excludeClass}" 
              onclick="toggleExclude('${key}', '${escapedValue.replace(/'/g, "\\'")}' )" 
              title="${isExcluded ? 'Rimuovi esclusione' : 'Escludi'}">
        ${excludeIcon}
      </button>
    </span>
  `;
}

// ===== USER TAGS FUNCTIONS =====

async function loadUserTags(docId, articleElement) {
  if (!docId) return;
  
  const tagsList = articleElement.querySelector('.user-tags-list');
  if (!tagsList) return;
  
  try {
    const response = await fetch(`${API_BASE}/users_tags?doc_id=${encodeURIComponent(docId)}`);
    if (!response.ok) {
      // Se endpoint non esiste ancora, mostra placeholder
      if (response.status === 404) {
        tagsList.innerHTML = '<div class="user-tags-empty">Nessun tag. Aggiungi il primo!</div>';
        return;
      }
      throw new Error(`HTTP ${response.status}`);
    }
    
    const data = await response.json();
    const tags = data.tags || [];
    
    if (tags.length === 0) {
      tagsList.innerHTML = '<div class="user-tags-empty">Nessun tag. Aggiungi il primo!</div>';
      return;
    }
    
    renderUserTags(tags, tagsList, articleElement);
    
  } catch (err) {
    console.warn('Errore caricamento user tags:', err);
    // Se API non disponibile, mostra placeholder
    tagsList.innerHTML = '<div class="user-tags-empty">Nessun tag. Aggiungi il primo!</div>';
  }
}

function renderUserTags(tags, tagsList, articleElement) {
  tagsList.innerHTML = tags.map(tag => `
    <span class="user-tag" data-tag-id="${escapeHtml(tag.id || '')}">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"></path>
        <line x1="7" y1="7" x2="7.01" y2="7"></line>
      </svg>
      ${escapeHtml(tag.tag_text || tag.text || '')}
      <button class="user-tag-remove" data-tag-id="${escapeHtml(tag.id || '')}" title="Rimuovi tag">
        ×
      </button>
    </span>
  `).join('');
  
  // Event listeners per rimozione
  tagsList.querySelectorAll('.user-tag-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const tagId = btn.getAttribute('data-tag-id');
      const docId = articleElement.querySelector('.user-tags-section').getAttribute('data-doc-id');
      removeUserTag(tagId, docId, articleElement);
    });
  });
}

async function addUserTag(docId, tagText, articleElement) {
  if (!docId || !tagText) return;
  
  const tagInput = articleElement.querySelector('.user-tags-input');
  const btnAddTag = articleElement.querySelector('.btn-add-tag');
  
  // Disabilita input durante l'operazione
  tagInput.disabled = true;
  btnAddTag.disabled = true;
  
  try {
    const response = await fetch(`${API_BASE}/users_tags`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        doc_id: docId,
        tag_text: tagText
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    // Ricarica i tag
    await loadUserTags(docId, articleElement);
    
    // Pulisci input
    tagInput.value = '';
    
  } catch (err) {
    console.error('Errore aggiunta tag:', err);
    alert('❌ Errore durante l\'aggiunta del tag. Verifica che il backend sia configurato.');
  } finally {
    tagInput.disabled = false;
    btnAddTag.disabled = false;
    tagInput.focus();
  }
}

async function removeUserTag(tagId, docId, articleElement) {
  if (!tagId) return;
  
  try {
    const response = await fetch(`${API_BASE}/users_tags/${encodeURIComponent(tagId)}`, {
      method: 'DELETE'
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    // Ricarica i tag
    await loadUserTags(docId, articleElement);
    
  } catch (err) {
    console.error('Errore rimozione tag:', err);
    alert('❌ Errore durante la rimozione del tag.');
  }
}

// ===== Document Actions =====
function downloadDocument(path) {
  if (!path) {
    alert('❌ Path non disponibile');
    return;
  }
  
  const url = `${API_BASE}/download_file?path=${encodeURIComponent(path)}`;
  console.log('⬇️ Download:', url);
  window.open(url, '_blank');
}

function copyPath(path) {
  if (!path) {
    alert('❌ Path non disponibile');
    return;
  }
  
  navigator.clipboard.writeText(path).then(() => {
    alert('✅ Percorso copiato negli appunti:\n' + path);
  }).catch(() => {
    alert('❌ Errore durante la copia');
  });
}

window.toggleExclude = function(key, value) {
  const filterKey = `${key}:${value}`;
  
  if (excludeFilters.has(filterKey)) {
    excludeFilters.delete(filterKey);
  } else {
    excludeFilters.add(filterKey);
  }
  
  doSearch();
};

// ===== UI States =====
function showLoading() {
  document.getElementById('results').innerHTML = `
    <div class="welcome-card">
      <h2>🔍 Ricerca in corso...</h2>
    </div>
  `;
  document.getElementById('pagination').style.display = 'none';
}

function showHint(message) {
  document.getElementById('results').innerHTML = `
    <div class="welcome-card"><p>${message}</p></div>
  `;
  document.getElementById('pagination').style.display = 'none';
}

function showError(message) {
  document.getElementById('results').innerHTML = `
    <div class="welcome-card">
      <h2>❌ Errore</h2>
      <p class="error">${message}</p>
    </div>
  `;
  document.getElementById('pagination').style.display = 'none';
}

// ===== Reset =====
function resetFilters() {
  ['f-area', 'f-anno', 'f-cliente', 'f-oggetto', 'f-tipo', 'f-categoria', 'f-ext', 'f-sd', 'f-lotto', 'f-prog-oda', 'f-prog-as', 'f-fase'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  
  currentFilters = {
    area: '',
    anno: '',
    cliente: '',
    oggetto: '',
    tipo_doc: '',
    categoria: '',
    ext: '',
    sd_numero: '',
    lotto: '',
    progressivo_oda: '',
    progressivo_as: '',
    fase: ''
  };
  
  excludeFilters.clear();
  allResults = [];
  currentPage = 1;
  totalPages = 1;
  
  document.getElementById('q').value = '';
  currentQuery = '';
  
  document.getElementById('results').innerHTML = `
    <div class="welcome-card">
      <h2>👋 Benvenuto!</h2>
      <p>Inserisci una query per iniziare.</p>
    </div>
  `;
  
  document.getElementById('search-stats').style.display = 'none';
  document.getElementById('pagination').style.display = 'none';
  
  loadInitialFacets();
}