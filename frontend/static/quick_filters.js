/* ═══════════════════════════════════════════════════════════════
   QUICK FILTERS - VERSIONE FIXED CON DEBUG
   
   FIX:
   - Mapping corretto dei campi
   - Debug logging esteso
   - Aggiunto tipo_doc (Piano Operativo, ODA, ecc.)
   - Aggiunto sd_numero
   - Preset combo avanzati
   ═══════════════════════════════════════════════════════════════ */

(function() {
    'use strict';

    console.log('🚀 Quick Filters FIXED: Loading...');

    // ═══════════════════════════════════════════════════════════════
    // CONFIGURAZIONE - MAPPING CORRETTO!
    // ═══════════════════════════════════════════════════════════════
    
    const CONFIG = {
        // Preset combinazioni
        presets: {
            // Base combos
            'aq-offerta': {
                area: 'AQ',
                fase: 'Offerta Tecnica'
            },
            'gare-doc': {
                area: 'Gare',
                fase: 'Documentazione'
            },
            
            // Combos con tipo_doc
            'piano-operativo': {
                tipo_doc: 'Piano Operativo'
            },
            'oda': {
                tipo_doc: 'ODA'
            },
            
            // Combos avanzate con SD
            'piano-op-sd1': {
                tipo_doc: 'Piano Operativo',
                sd_numero: '1'
            },
            'oda-offerta': {
                tipo_doc: 'ODA',
                fase: 'Offerta Tecnica'
            }
        },
        
        // Mapping ID filtri sidebar (DEVE CORRISPONDERE al tuo app_v2.js!)
        sidebarIds: {
            'area': 'f-area',
            'fase': 'f-fase',
            'sd_numero': 'f-sd',
            'tipo_doc': 'f-tipo',
            'categoria': 'f-categoria'
        },
        
        // Debug mode
        debug: true
    };

    // ═══════════════════════════════════════════════════════════════
    // DEBUG HELPER
    // ═══════════════════════════════════════════════════════════════
    
    function log(...args) {
        if (CONFIG.debug) {
            console.log('🎯 QF:', ...args);
        }
    }
    
    function logError(...args) {
        console.error('❌ QF Error:', ...args);
    }

    // ═══════════════════════════════════════════════════════════════
    // INIZIALIZZAZIONE
    // ═══════════════════════════════════════════════════════════════
    
    function init() {
        log('Inizializzazione...');
        
        // Verifica dipendenze
        if (typeof currentFilters === 'undefined') {
            logError('currentFilters non trovato! Verifica che app_v2.js sia caricato prima.');
            return;
        }
        if (typeof doSearch !== 'function') {
            logError('doSearch() non trovata! Verifica che app_v2.js sia caricato prima.');
            return;
        }
        
        log('Dipendenze OK');
        log('currentFilters iniziale:', JSON.stringify(currentFilters));
        
        // Event listeners
        attachEventListeners();
        
        // Sincronizza stato iniziale
        syncUIFromFilters();
        
        log('Inizializzazione completata!');
    }

    // ═══════════════════════════════════════════════════════════════
    // EVENT LISTENERS
    // ═══════════════════════════════════════════════════════════════
    
    function attachEventListeners() {
        log('Attaching event listeners...');
        
        // Pills singoli (Area, Fase, ecc.)
        const pills = document.querySelectorAll('.qf-pill');
        log(`Trovati ${pills.length} pills singoli`);
        pills.forEach(pill => {
            pill.addEventListener('click', handlePillClick);
        });
        
        // Preset pills
        const presets = document.querySelectorAll('.qf-preset');
        log(`Trovati ${presets.length} preset pills`);
        presets.forEach(pill => {
            pill.addEventListener('click', handlePresetClick);
        });
        
        // Reset button
        const resetBtn = document.getElementById('qf-reset-btn');
        if (resetBtn) {
            resetBtn.addEventListener('click', handleReset);
            log('Reset button OK');
        } else {
            logError('Reset button non trovato!');
        }
        
        // Intercetta reset globale sidebar
        const globalResetBtn = document.getElementById('btn-reset');
        if (globalResetBtn) {
            globalResetBtn.addEventListener('click', () => {
                log('Reset globale rilevato');
                setTimeout(syncUIFromFilters, 100);
            });
        }
        
        log('Event listeners attached!');
    }

    // ═══════════════════════════════════════════════════════════════
    // HANDLERS
    // ═══════════════════════════════════════════════════════════════
    
    function handlePillClick(event) {
        const pill = event.currentTarget;
        const filterType = pill.getAttribute('data-filter-type');
        const filterValue = pill.getAttribute('data-filter-value');
        
        if (!filterType || !filterValue) {
            logError('Pill senza data attributes!', pill);
            return;
        }
        
        log('Click su pill:', filterType, '=', filterValue);
        
        const isActive = pill.classList.contains('active');
        
        if (isActive) {
            // Rimuovi filtro
            log('Rimozione filtro:', filterType);
            currentFilters[filterType] = '';
            pill.classList.remove('active');
        } else {
            // Aggiungi filtro
            log('Aggiunta filtro:', filterType, '=', filterValue);
            currentFilters[filterType] = filterValue;
            pill.classList.add('active');
        }
        
        log('currentFilters dopo click:', JSON.stringify(currentFilters));
        
        // NON sincronizzare sidebar qui per evitare problemi
        // La sidebar si sincronizzerà dopo il doSearch() tramite updateFacets()
        
        // Esegui ricerca
        log('Chiamata doSearch()...');
        doSearch();
    }
    
    function handlePresetClick(event) {
        const pill = event.currentTarget;
        const presetId = pill.getAttribute('data-preset');
        
        if (!presetId || !CONFIG.presets[presetId]) {
            logError('Preset non trovato:', presetId);
            return;
        }
        
        const preset = CONFIG.presets[presetId];
        log('Preset applicato:', presetId, preset);
        
        // RESET tutti i filtri gestiti dai quick buttons prima
        ['area', 'fase', 'sd_numero', 'tipo_doc', 'categoria'].forEach(key => {
            currentFilters[key] = '';
        });
        
        // Applica tutti i filtri del preset
        Object.entries(preset).forEach(([key, value]) => {
            currentFilters[key] = value;
            log(`  ${key} = ${value}`);
        });
        
        log('currentFilters dopo preset:', JSON.stringify(currentFilters));
        
        // Sincronizza UI
        syncUIFromFilters();
        
        // Esegui ricerca
        log('Chiamata doSearch()...');
        doSearch();
        
        // Feedback visivo
        pill.style.transform = 'scale(1.1)';
        setTimeout(() => {
            pill.style.transform = '';
        }, 200);
    }
    
    function handleReset() {
        log('Reset Quick Filters');
        
        // Rimuovi TUTTI i filtri gestiti dai quick buttons
        ['area', 'fase', 'sd_numero', 'tipo_doc', 'categoria'].forEach(key => {
            currentFilters[key] = '';
        });
        
        log('currentFilters dopo reset:', JSON.stringify(currentFilters));
        
        // Reset UI
        document.querySelectorAll('.qf-pill.active, .qf-preset.active').forEach(pill => {
            pill.classList.remove('active');
        });
        
        // Esegui ricerca (che mostrerà tutti i risultati)
        log('Chiamata doSearch()...');
        doSearch();
    }

    // ═══════════════════════════════════════════════════════════════
    // SINCRONIZZAZIONE UI
    // ═══════════════════════════════════════════════════════════════
    
    function syncUIFromFilters() {
        log('Sincronizzazione UI da currentFilters:', JSON.stringify(currentFilters));
        
        // Reset tutti i pills
        document.querySelectorAll('.qf-pill, .qf-preset').forEach(pill => {
            pill.classList.remove('active');
        });
        
        // Attiva pills corrispondenti ai filtri attivi
        let activatedCount = 0;
        Object.entries(currentFilters).forEach(([key, value]) => {
            if (value && value !== '') {
                const selector = `.qf-pill[data-filter-type="${key}"][data-filter-value="${value}"]`;
                const pill = document.querySelector(selector);
                if (pill) {
                    pill.classList.add('active');
                    activatedCount++;
                    log(`  Attivato pill: ${key}=${value}`);
                } else {
                    log(`  Pill non trovato per: ${key}=${value}`);
                }
            }
        });
        
        log(`Attivati ${activatedCount} pills`);
        
        // Sincronizza preset pills
        syncPresetPills();
        
        // Aggiorna badge contatore
        updateBadge();
    }
    
    function syncPresetPills() {
        // Per ogni preset, verifica se TUTTI i suoi filtri sono attivi
        Object.entries(CONFIG.presets).forEach(([presetId, filters]) => {
            const pill = document.querySelector(`.qf-preset[data-preset="${presetId}"]`);
            if (!pill) return;
            
            const allActive = Object.entries(filters).every(
                ([key, value]) => currentFilters[key] === value
            );
            
            if (allActive) {
                pill.classList.add('active');
                log(`  Preset attivato: ${presetId}`);
            }
        });
    }
    
    function updateBadge() {
        // Conta filtri attivi gestiti dai quick buttons
        const activeCount = ['area', 'fase', 'sd_numero', 'tipo_doc', 'categoria'].filter(
            key => currentFilters[key] !== undefined && currentFilters[key] !== ''
        ).length;
        
        const label = document.querySelector('.quick-filters-row .suggestions-label');
        if (!label) return;
        
        let badge = label.querySelector('.qf-badge');
        
        if (activeCount > 0) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'qf-badge';
                label.appendChild(badge);
            }
            badge.textContent = activeCount;
        } else if (badge) {
            badge.remove();
        }
        
        log(`Badge: ${activeCount} filtri attivi`);
    }

    // ═══════════════════════════════════════════════════════════════
    // AUTO-INIT
    // ═══════════════════════════════════════════════════════════════
    
    // Aspetta che il DOM e currentFilters siano pronti
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(init, 100); // Delay per sicurezza
        });
    } else {
        // DOM già pronto
        if (typeof currentFilters === 'undefined') {
            // currentFilters non ancora definito, aspetta
            setTimeout(init, 200);
        } else {
            init();
        }
    }
    
    log('Quick Filters FIXED module loaded!');

})();
