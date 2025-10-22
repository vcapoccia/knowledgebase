/* ============================================
   KB SEARCH - APP.JS
   Gestione Interazioni UI
   ============================================ */

// ============================================
// STATE MANAGEMENT
// ============================================

const AppState = {
    currentView: 'landing', // 'landing' or 'results'
    sidebarCollapsed: false,
    currentQuery: '',
    currentMode: 'hybrid',
    currentModel: 'sentence-transformer',
    activeFilters: {},
    results: [],
    facets: {},
    totalResults: 0,
    searchTime: 0,
    loading: false,
    page: 1,
    pageSize: 20
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    loadSidebarState();
    checkUrlParams();
});

function initializeEventListeners() {
    // Landing page search
    const mainSearchBtn = document.getElementById('main-search-btn');
    const mainSearchInput = document.getElementById('main-search-input');
    
    if (mainSearchBtn) {
        mainSearchBtn.addEventListener('click', handleMainSearch);
    }
    
    if (mainSearchInput) {
        mainSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleMainSearch();
        });
    }
    
    // Results page search
    const resultsSearchInput = document.getElementById('results-search-input');
    if (resultsSearchInput) {
        resultsSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleResultsSearch();
        });
    }
    
    const searchBtnCompact = document.querySelector('.search-btn-compact');
    if (searchBtnCompact) {
        searchBtnCompact.addEventListener('click', handleResultsSearch);
    }
    
    // Search mode toggle
    const modeRadios = document.querySelectorAll('input[name="search-mode"]');
    modeRadios.forEach(radio => {
        radio.addEventListener('change', handleModeChange);
    });
    
    // Semantic model selector
    const semanticModel = document.getElementById('semantic-model');
    if (semanticModel) {
        semanticModel.addEventListener('change', (e) => {
            AppState.currentModel = e.target.value;
        });
    }
    
    // Results mode selector
    const resultsModeSelect = document.getElementById('results-mode-select');
    if (resultsModeSelect) {
        resultsModeSelect.addEventListener('change', (e) => {
            updateModeFromSelect(e.target.value);
            handleResultsSearch();
        });
    }
    
    // Suggestion pills
    const suggestionPills = document.querySelectorAll('.suggestion-pill');
    suggestionPills.forEach(pill => {
        pill.addEventListener('click', () => {
            const query = pill.getAttribute('data-query');
            handleSuggestionClick(query);
        });
    });
    
    // Advanced toggle
    const advancedToggle = document.getElementById('advanced-toggle');
    const advancedFilters = document.getElementById('advanced-filters');
    
    if (advancedToggle && advancedFilters) {
        advancedToggle.addEventListener('click', () => {
            const isVisible = advancedFilters.style.display !== 'none';
            advancedFilters.style.display = isVisible ? 'none' : 'block';
            advancedToggle.innerHTML = isVisible 
                ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line><line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line><line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line><line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line><line x1="17" y1="16" x2="23" y2="16"></line></svg> Ricerca Avanzata'
                : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg> Nascondi';
        });
    }
    
    // Back to home
    const backToHome = document.getElementById('back-to-home');
    if (backToHome) {
        backToHome.addEventListener('click', () => {
            switchView('landing');
        });
    }
    
    // Sidebar toggle
    const toggleSidebar = document.getElementById('toggle-sidebar');
    if (toggleSidebar) {
        toggleSidebar.addEventListener('click', handleSidebarToggle);
    }
    
    // Reset filters
    const resetFilters = document.getElementById('reset-filters');
    if (resetFilters) {
        resetFilters.addEventListener('click', handleResetFilters);
    }
    
    // Facet checkboxes
    document.addEventListener('change', (e) => {
        if (e.target.type === 'checkbox' && e.target.closest('.facet-item')) {
            handleFacetChange(e.target);
        }
    });
    
    // Load more
    const loadMoreBtn = document.getElementById('load-more');
    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', handleLoadMore);
    }
    
    // View toggle (list/grid)
    const viewBtns = document.querySelectorAll('.view-btn');
    viewBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            viewBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const view = btn.getAttribute('data-view');
            toggleResultsView(view);
        });
    });
}

// ============================================
// VIEW SWITCHING
// ============================================

function switchView(view) {
    const landingView = document.getElementById('landing-view');
    const resultsView = document.getElementById('results-view');
    
    if (view === 'landing') {
        landingView.style.display = 'flex';
        resultsView.style.display = 'none';
        AppState.currentView = 'landing';
        
        // Clear search
        const mainSearchInput = document.getElementById('main-search-input');
        if (mainSearchInput) mainSearchInput.value = '';
        
        // Update URL
        history.pushState({}, '', '/');
    } else {
        landingView.style.display = 'none';
        resultsView.style.display = 'block';
        AppState.currentView = 'results';
    }
}

// ============================================
// SEARCH HANDLERS
// ============================================

async function handleMainSearch() {
    const input = document.getElementById('main-search-input');
    const query = input.value.trim();
    
    if (!query) {
        alert('Inserisci una query di ricerca');
        return;
    }
    
    // Get advanced filters
    const excludeAreas = Array.from(document.querySelectorAll('#advanced-filters input[type="checkbox"]:checked'))
        .map(cb => cb.value);
    
    const folderFilter = document.getElementById('folder-filter')?.value;
    
    AppState.currentQuery = query;
    AppState.activeFilters = {
        excludeAreas,
        folder: folderFilter
    };
    
    // Switch to results view
    switchView('results');
    
    // Update results search input
    const resultsInput = document.getElementById('results-search-input');
    if (resultsInput) resultsInput.value = query;
    
    // Perform search
    await performSearch();
}

async function handleResultsSearch() {
    const input = document.getElementById('results-search-input');
    const query = input.value.trim();
    
    if (!query) return;
    
    AppState.currentQuery = query;
    AppState.page = 1;
    
    await performSearch();
}

async function performSearch() {
    AppState.loading = true;
    showLoading();
    
    try {
        const params = buildSearchParams();
        const response = await fetch(`/search?${params}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        AppState.results = data.results || [];
        AppState.facets = data.facets || {};
        AppState.totalResults = data.total || 0;
        AppState.searchTime = data.time || 0;
        
        renderResults();
        renderFacets();
        updateResultsInfo();
        updateActiveFilters();
        
    } catch (error) {
        console.error('Search error:', error);
        showError('Errore durante la ricerca. Riprova.');
    } finally {
        AppState.loading = false;
    }
}

function buildSearchParams() {
    const params = new URLSearchParams();
    
    params.append('q_text', AppState.currentQuery);
    params.append('top_k', AppState.pageSize);
    
    // Mode and model
    if (AppState.currentMode === 'hybrid') {
        params.append('mode', 'hybrid');
    } else {
        params.append('model', AppState.currentModel);
    }
    
    // Filters
    Object.entries(AppState.activeFilters).forEach(([key, value]) => {
        if (Array.isArray(value)) {
            value.forEach(v => params.append(key, v));
        } else if (value) {
            params.append(key, value);
        }
    });
    
    return params.toString();
}

// ============================================
// RENDERING
// ============================================

function renderResults() {
    const resultsList = document.getElementById('results-list');
    
    if (!AppState.results || AppState.results.length === 0) {
        resultsList.innerHTML = `
            <div class="no-results">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                    <circle cx="11" cy="11" r="8"></circle>
                    <path d="m21 21-4.35-4.35"></path>
                </svg>
                <h3>Nessun risultato trovato</h3>
                <p>Prova a modificare i filtri o usare termini diversi</p>
            </div>
        `;
        return;
    }
    
    resultsList.innerHTML = AppState.results.map(result => createResultCard(result)).join('');
}

function createResultCard(result) {
    const score = result.score || result.combined_score || 0;
    const scoreColor = getScoreColor(score);
    const scoreEmoji = getScoreEmoji(score);
    
    return `
        <div class="result-card">
            <div class="result-header">
                <div>
                    <h3 class="result-title">${escapeHtml(result.title || result.filename || 'Documento')}</h3>
                </div>
                <div class="result-score" style="background: ${scoreColor}">
                    ${scoreEmoji} ${score.toFixed(2)}
                </div>
            </div>
            
            <div class="result-metadata">
                ${result.anno ? `<span class="metadata-badge">📅 ${result.anno}</span>` : ''}
                ${result.area ? `<span class="metadata-badge">📁 ${escapeHtml(result.area)}</span>` : ''}
                ${result.cliente ? `<span class="metadata-badge">👥 ${escapeHtml(result.cliente)}</span>` : ''}
                ${result.tipo_doc ? `<span class="metadata-badge">📋 ${escapeHtml(result.tipo_doc)}</span>` : ''}
                ${result.ext ? `<span class="metadata-badge">📄 ${result.ext.toUpperCase()}</span>` : ''}
            </div>
            
            <div class="result-snippet">
                ${highlightQuery(result.snippet || result.text_content?.substring(0, 200) || 'Nessun contenuto disponibile')}
            </div>
            
            <div class="result-actions">
                <button class="result-btn result-btn-primary" onclick="openDocument('${result.id}')">
                    📂 Apri documento
                </button>
                <button class="result-btn result-btn-secondary" onclick="previewDocument('${result.id}')">
                    👁️ Preview
                </button>
                <button class="result-btn result-btn-secondary" onclick="addToFavorites('${result.id}')">
                    ⭐ Preferiti
                </button>
            </div>
        </div>
    `;
}

function getScoreColor(score) {
    if (score >= 0.8) return '#00B0AA'; // Teal light
    if (score >= 0.6) return '#2569B1'; // Blue
    if (score >= 0.4) return '#f59e0b'; // Warning
    return '#94a3b8'; // Gray
}

function getScoreEmoji(score) {
    if (score >= 0.8) return '💚';
    if (score >= 0.6) return '💙';
    if (score >= 0.4) return '💛';
    return '⚪';
}

function highlightQuery(text) {
    if (!AppState.currentQuery) return escapeHtml(text);
    
    const words = AppState.currentQuery.split(' ').filter(w => w.length > 2);
    let highlighted = escapeHtml(text);
    
    words.forEach(word => {
        const regex = new RegExp(`(${word})`, 'gi');
        highlighted = highlighted.replace(regex, '<mark>$1</mark>');
    });
    
    return highlighted;
}

function renderFacets() {
    // This would dynamically update facet counts based on results
    // For now, using static HTML from template
    
    // Update counts if facets data available
    if (AppState.facets) {
        Object.entries(AppState.facets).forEach(([facetName, values]) => {
            updateFacetCounts(facetName, values);
        });
    }
}

function updateFacetCounts(facetName, values) {
    const facetItems = document.querySelectorAll(`.facet-item input[name="${facetName}"]`);
    
    facetItems.forEach(item => {
        const value = item.value;
        const count = values[value] || 0;
        const countSpan = item.closest('.facet-item').querySelector('.facet-count');
        if (countSpan) {
            countSpan.textContent = count;
        }
        
        // Disable if count is 0
        item.disabled = count === 0;
        if (count === 0) {
            item.closest('.facet-item').style.opacity = '0.5';
        }
    });
}

function updateResultsInfo() {
    const resultsCount = document.getElementById('results-count');
    const resultsTime = document.querySelector('.results-time');
    
    if (resultsCount) {
        resultsCount.textContent = `${AppState.totalResults} risultati`;
    }
    
    if (resultsTime) {
        resultsTime.textContent = `(${AppState.searchTime.toFixed(2)}s)`;
    }
}

function updateActiveFilters() {
    const activeFiltersContainer = document.getElementById('active-filters');
    if (!activeFiltersContainer) return;
    
    // Clear existing pills
    const existingPills = activeFiltersContainer.querySelectorAll('.filter-pill');
    existingPills.forEach(pill => pill.remove());
    
    // Add filter pills
    Object.entries(AppState.activeFilters).forEach(([key, value]) => {
        if (Array.isArray(value)) {
            value.forEach(v => addFilterPill(key, v, activeFiltersContainer));
        } else if (value) {
            addFilterPill(key, value, activeFiltersContainer);
        }
    });
}

function addFilterPill(key, value, container) {
    const pill = document.createElement('span');
    pill.className = 'filter-pill';
    pill.innerHTML = `
        ${getFilterIcon(key)} ${escapeHtml(value)}
        <button class="filter-pill-close" onclick="removeFilter('${key}', '${value}')">×</button>
    `;
    container.appendChild(pill);
}

function getFilterIcon(key) {
    const icons = {
        area: '📁',
        anno: '📅',
        cliente: '👥',
        tipo_doc: '📋',
        excludeAreas: '🚫',
        folder: '🎯'
    };
    return icons[key] || '🏷️';
}

// ============================================
// FILTER HANDLERS
// ============================================

function handleFacetChange(checkbox) {
    const name = checkbox.name;
    const value = checkbox.value;
    
    if (!AppState.activeFilters[name]) {
        AppState.activeFilters[name] = [];
    }
    
    if (checkbox.checked) {
        AppState.activeFilters[name].push(value);
    } else {
        AppState.activeFilters[name] = AppState.activeFilters[name].filter(v => v !== value);
    }
    
    // Re-search with new filters
    performSearch();
}

function removeFilter(key, value) {
    if (Array.isArray(AppState.activeFilters[key])) {
        AppState.activeFilters[key] = AppState.activeFilters[key].filter(v => v !== value);
        
        // Uncheck corresponding facet
        const checkbox = document.querySelector(`.facet-item input[name="${key}"][value="${value}"]`);
        if (checkbox) checkbox.checked = false;
    } else {
        delete AppState.activeFilters[key];
    }
    
    performSearch();
}

function handleResetFilters() {
    AppState.activeFilters = {};
    
    // Uncheck all facets
    document.querySelectorAll('.facet-item input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    
    performSearch();
}

// ============================================
// SIDEBAR
// ============================================

function handleSidebarToggle() {
    const sidebar = document.getElementById('sidebar');
    const toggleText = document.getElementById('sidebar-toggle-text');
    const resultsMain = document.getElementById('results-main');
    
    AppState.sidebarCollapsed = !AppState.sidebarCollapsed;
    
    if (AppState.sidebarCollapsed) {
        sidebar.classList.add('collapsed');
        toggleText.textContent = 'Mostra filtri';
        resultsMain.style.marginLeft = '0';
    } else {
        sidebar.classList.remove('collapsed');
        toggleText.textContent = 'Nascondi filtri';
        resultsMain.style.marginLeft = '';
    }
    
    // Save state
    localStorage.setItem('sidebarCollapsed', AppState.sidebarCollapsed);
}

function loadSidebarState() {
    const saved = localStorage.getItem('sidebarCollapsed');
    if (saved === 'true') {
        AppState.sidebarCollapsed = true;
        const sidebar = document.getElementById('sidebar');
        const toggleText = document.getElementById('sidebar-toggle-text');
        if (sidebar) sidebar.classList.add('collapsed');
        if (toggleText) toggleText.textContent = 'Mostra filtri';
    }
}

// ============================================
// SUGGESTIONS
// ============================================

function handleSuggestionClick(query) {
    const mainSearchInput = document.getElementById('main-search-input');
    if (mainSearchInput) {
        mainSearchInput.value = query;
        AppState.currentQuery = query;
        handleMainSearch();
    }
}

// ============================================
// MODE HANDLERS
// ============================================

function handleModeChange(e) {
    AppState.currentMode = e.target.value;
    
    // Update results mode select if exists
    const resultsModeSelect = document.getElementById('results-mode-select');
    if (resultsModeSelect) {
        if (AppState.currentMode === 'hybrid') {
            resultsModeSelect.value = 'hybrid';
        } else {
            resultsModeSelect.value = `semantic-${AppState.currentModel}`;
        }
    }
}

function updateModeFromSelect(value) {
    if (value === 'hybrid') {
        AppState.currentMode = 'hybrid';
    } else {
        AppState.currentMode = 'semantic';
        AppState.currentModel = value.replace('semantic-', '');
    }
}

// ============================================
// DOCUMENT ACTIONS
// ============================================

window.openDocument = function(docId) {
    window.open(`/document/${docId}`, '_blank');
};

window.previewDocument = function(docId) {
    // Implement preview modal
    alert(`Preview documento: ${docId}`);
};

window.addToFavorites = function(docId) {
    // Implement favorites
    alert(`Aggiunto ai preferiti: ${docId}`);
};

// ============================================
// LOAD MORE
// ============================================

async function handleLoadMore() {
    AppState.page++;
    // Implement pagination
    alert('Caricamento altri risultati...');
}

// ============================================
// VIEW TOGGLE
// ============================================

function toggleResultsView(view) {
    const resultsList = document.getElementById('results-list');
    
    if (view === 'grid') {
        resultsList.style.display = 'grid';
        resultsList.style.gridTemplateColumns = 'repeat(auto-fill, minmax(300px, 1fr))';
        resultsList.style.gap = '1rem';
    } else {
        resultsList.style.display = 'flex';
        resultsList.style.flexDirection = 'column';
        resultsList.style.gap = '1.5rem';
    }
}

// ============================================
// URL PARAMS
// ============================================

function checkUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const query = params.get('q');
    
    if (query) {
        AppState.currentQuery = query;
        switchView('results');
        const resultsInput = document.getElementById('results-search-input');
        if (resultsInput) resultsInput.value = query;
        performSearch();
    }
}

// ============================================
// UTILITIES
// ============================================

function showLoading() {
    const resultsList = document.getElementById('results-list');
    if (resultsList) {
        resultsList.innerHTML = `
            <div class="loading">
                <div class="spinner"></div>
                <p>Caricamento risultati...</p>
            </div>
        `;
    }
}

function showError(message) {
    const resultsList = document.getElementById('results-list');
    if (resultsList) {
        resultsList.innerHTML = `
            <div class="error">
                <p>${escapeHtml(message)}</p>
            </div>
        `;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// EXPORT
// ============================================

window.AppState = AppState;

