const $ = (s)=>document.querySelector(s);
const results = $('#results');

let state = {
  page: 1,
  per_page: 10,
  q: '',
  filters: {area:'', tipo:'', anno:''},
  reduce_server: true
};

function clampPreview(txt, lines=3){
  if(!txt) return '';
  // 3 righe circa: taglio su 280 char e aggiungo ellissi
  const s = txt.replace(/\s+/g,' ').trim();
  return s.length>280 ? s.slice(0,280) + '…' : s;
}

function renderHits(data){
  results.innerHTML = '';
  if(!data || !data.hits || data.hits.length===0){
    results.innerHTML = '<div class="empty">Nessun risultato</div>';
    return;
  }
  data.hits.forEach(h=>{
    const div = document.createElement('div');
    div.className = 'hit';
    const score = h.score ? `<span class="score" title="score">${h.score}</span>` : '';
    div.innerHTML = `
      <div class="hit-title">${h.title||h.doc_id} ${score}</div>
      <div class="hit-path">${h.path||''}</div>
      <div class="hit-preview">${clampPreview(h.preview||'')}</div>
    `;
    results.appendChild(div);
  });
}

async function loadFilters(){
  const f = await fetch('/filters').then(r=>r.json()).catch(()=>({area:[],tipo:[],anno:[]}));
  ['area','tipo'].forEach(k=>{
    const sel = k==='area' ? $('#fltArea') : $('#fltTipo');
    (f[k]||[]).forEach(v=>{
      const opt=document.createElement('option'); opt.value=v; opt.textContent=v; sel.appendChild(opt);
    })
  });
  // anno: opzionale, manuale
}

async function doSearch(resetPage=false){
  if(resetPage) state.page = 1;
  state.q = $('#q').value.trim();
  state.filters.area = $('#fltArea').value || '';
  state.filters.tipo = $('#fltTipo').value || '';
  const an = ($('#fltAnno').value||'').trim();
  state.filters.anno = an ? parseInt(an,10) : '';

  const payload = {
    q: state.q,
    page: state.page,
    per_page: state.per_page,
    filters: state.filters,
    reduce_server: $('#reduceServer').checked
  };

  try{
    const res = await fetch('/search', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    if(!res.ok) throw new Error('HTTP '+res.status);
    const data = await res.json();
    renderHits(data);
  }catch(err){
    console.error(err);
    results.innerHTML = `<div class="error">Errore durante la ricerca<br/><small>Dettagli in console</small></div>`;
  }
}

$('#btnSearch').onclick = ()=> doSearch(true);
$('#btnApply').onclick  = ()=> doSearch(true);
$('#btnReset').onclick  = ()=>{
  state = {page:1, per_page:10, q:'', filters:{area:'',tipo:'',anno:''}, reduce_server:true};
  $('#q').value=''; $('#fltArea').value=''; $('#fltTipo').value=''; $('#fltAnno').value='';
  $('#reduceServer').checked = true;
  results.innerHTML = '<div class="empty">—</div>';
};

$('#prev').onclick = ()=>{ if(state.page>1){ state.page--; doSearch(false); } };
$('#next').onclick = ()=>{ state.page++; doSearch(false); };

loadFilters();