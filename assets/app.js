import {sparkline, comparisonChart, palette, seriesDashes, escapeHTML as esc} from './charts.js?v=1.2.0';
import {createHome} from './home.js?v=1.2.0';

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const storage = {
  get(key, fallback) {
    try {
      const current=localStorage.getItem('lokirs:'+key);
      return JSON.parse(current===null?localStorage.getItem('openrs:'+key):current) ?? fallback;
    } catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem('lokirs:'+key,JSON.stringify(value)); } catch { /* private browsing */ } }
};
const readView = () => {const tab=new URLSearchParams(location.search).get('tab');return ['home','stocks','watchlist','compare'].includes(tab)?tab:location.hash==='#rankings'?'stocks':'home';};
const state = {data:null, view:readView(), search:'', exactSymbol:null, sector:'', sectorTop:0, metric:'score', operator:'gte', value:'', streak:false,
  long:false, resilient:false, perp:false, sort:'score', direction:-1, page:1, pageSize:50,
  watched:new Set(storage.get('watchlist',[])), compare:storage.get('compare',['SPY','NVDA','AAPL']), period:64};
const number = (v, digits=2) => Number.isFinite(v) ? v.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—';
const signed = (v,digits=2) => Number.isFinite(v) ? (v>0?'+':'')+number(v,digits) : '—';
const cls = v => Number.isFinite(v) ? v>0?'positive':v<0?'negative':'muted' : 'muted';
const pp = v => Number.isFinite(v) ? signed(v)+'%' : '—';
const hkTime = value => { try { return new Intl.DateTimeFormat('zh-HK',{timeZone:'Asia/Hong_Kong',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)); } catch { return '—'; } };
const metric = (r,key) => key==='week'||key==='month'?r[key]?.value:key==='h1'||key==='h4'?r.intra?.[key]:key==='vsSector'&&state.resilient?r.vsSectorDay:r[key];
let toastTimer, loading=false;

function toast(message) {
  $('#toast').textContent=message; $('#toast').hidden=false;
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,3000);
}
function download(text,name,type) {
  const url=URL.createObjectURL(new Blob([text],{type}));
  const anchor=document.createElement('a'); anchor.href=url; anchor.download=name; anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
}
function setTheme(theme) {
  theme=theme==='reading'||theme==='light'?'reading':'dark';
  document.documentElement.dataset.theme=theme;
  storage.set('theme',theme);
  const reading=theme==='reading', label=reading?'切換至檔案紙紋模式':'切換至純色閱讀模式';
  $('#theme-toggle').setAttribute('aria-label',label);
  $('#theme-toggle').setAttribute('aria-pressed',String(reading));
  $('#theme-toggle').title=label;
  $('#theme-label').textContent=reading?'檔案模式':'閱讀模式';
}
setTheme(storage.get('theme','dark'));

async function loadData(manual=false) {
  if(loading) return; loading=true; $('#refresh').classList.add('rotating');
  try {
    const response=await fetch(`./data/latest.json?t=${Date.now()}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const data=await response.json();
    if(data.meta?.schemaVersion!==1||!Array.isArray(data.rows)||!data.rows.length) throw new Error('數據格式不相容');
    const unchanged=state.data?.meta.generatedAt===data.meta.generatedAt;
    state.data=data;
    $('#loading-state').hidden=true; $('#dashboard').hidden=false;
    renderOverview(); renderLeaders(); renderFilters(); renderTable(); renderComparison(); renderMethodStatus(); updateWatchCount();
    const end=new Date(data.asOf+'T16:00:00-04:00'), old=(Date.now()-end.getTime())/86400000>4;
    const issues=data.meta.universeCount-data.meta.currentCount;
    $('#error-banner').hidden=!old&&!issues;
    $('#error-banner').textContent=[old?'目前顯示的是 '+data.asOf+' 的舊快照；請檢查資料更新工作流程。':'',issues?`${issues} 隻股票缺少當期有效分數，已顯示缺值並排除於當期排名。`:''].filter(Boolean).join(' ');
    $('#status-dot').classList.toggle('warning',old||issues>0);
    if(manual) toast(unchanged?'已是最新發布快照。抓價排程與頁面刷新分開運作。':'已載入最新發布數據');
  } catch(error) {
    $('#loading-state').hidden=true;
    $('#error-banner').hidden=false;
    $('#error-banner').textContent=`無法讀取數據檔（${error.message}）。請以 HTTP 伺服器開啟，或確認 GitHub Pages 已部署 data/latest.json。`;
    $('#coverage-label').textContent=state.data?'保留目前畫面':'數據載入失敗';
  } finally { loading=false; $('#refresh').classList.remove('rotating'); }
}

function renderOverview() {
  const {data}=state, meta=data.meta;
  renderHeader();
  $('#spy-price').textContent=number(data.benchmark.price);
  $('#spy-change').textContent=pp(data.benchmark.d1); $('#spy-change').className=cls(data.benchmark.d1);
  const valid=data.rows.filter(r=>Number.isFinite(r.d1)), outperform=valid.filter(r=>r.d1>0).length;
  $('#outperform-count').textContent=outperform;
  $('#outperform-pct').textContent=valid.length?`/ ${valid.length} 隻 · ${Math.round(outperform/valid.length*100)}%`:'';
  $('#positive-count').textContent=data.rows.filter(r=>r.score>0).length;
  $('#coverage-count').textContent=`${meta.currentCount} / ${meta.universeCount}`;
  $('#intra-count').textContent=`小時線 ${meta.intradayCount} 隻`;
  const last=data.breadth.at(-1);
  $('#breadth-content').innerHTML=[['above20','位於 20 日均線上'],['above50','位於 50 日均線上'],['advancing','今日上升家數'],['positive20','20 日錄得升幅']].map(([key,label])=>{
    const values=data.breadth.map(r=>r[key].value), current=last?.[key];
    const prev=data.breadth.at(-2)?.[key]?.value;
    const delta=Number.isFinite(prev)&&Number.isFinite(current?.value)?current.value-prev:null;
    return `<div class="breadth-row"><div><span>${label}</span><small title="相比前一交易日的百分點變化" class="${cls(delta)}">1D ${signed(delta,1)}</small><strong>${number(current?.value,0)}<em>%</em></strong></div><div class="breadth-chart">${sparkline(values,{width:330,height:23})}</div><small class="breadth-base">${current?.count??0} / ${current?.total??0} 隻</small></div>`;
  }).join('');
  const sentiment=data.sentiment;
  if(sentiment.status==='ok') {
    const v=sentiment.value, label=v<25?'極度恐懼':v<45?'恐懼':v<=55?'中性':v<=75?'貪婪':'極度貪婪';
    $('#sentiment-content').innerHTML=`<div class="sentiment-value ${v<45?'negative':v>55?'positive':''}">${number(v,0)}<span>${label}</span></div><div class="sentiment-track"><i style="left:${v}%"></i></div><div class="scale-labels"><span>極度恐懼</span><span>極度貪婪</span></div><div class="sentiment-history"><span>昨收 <b>${number(sentiment.previousClose,0)}</b></span><span>一週前 <b>${number(sentiment.weekAgo,0)}</b></span><span>一月前 <b>${number(sentiment.monthAgo,0)}</b></span></div><p class="panel-footnote">CNN 原指數，非本站合成。時點 ${hkTime(sentiment.asOf)} HKT。</p>`;
  } else {
    $('#sentiment-content').innerHTML='<div class="unavailable-visual"><div class="gauge-placeholder"><span>—</span></div><span class="unavailable-badge">來源暫未提供</span></div><p class="unavailable-note">CNN 公開端點未能取得有效數據。此欄保留缺值，待下次更新再試。</p><a class="external-link" href="https://www.cnn.com/markets/fear-and-greed" target="_blank" rel="noopener">到 CNN 查看 ↗</a>';
  }
  $('#macro-content').innerHTML=data.macro.length?data.macro.map(row=>{
    const stale=row.status==='stale', direction=row.changeMonth*row.direction;
    return `<div class="macro-row"><div><a href="${esc(row.url||'https://fred.stlouisfed.org/')}" target="_blank" rel="noopener">${esc(row.name)}</a><small>${esc(row.asOf?.slice(5)||'—')}${stale?' · 舊值':''}</small><strong>${number(row.value,row.id==='DTWEXBGS'?2:2)}${esc(row.unit)}</strong><span class="macro-change ${stale?'muted':cls(direction)}">${signed(row.changeMonth)}</span></div><div class="macro-scale"><span>${row.windowYears||'—'} 年寬鬆百分位</span><div><i style="width:${Math.max(0,Math.min(100,row.easePercentile||0))}%"></i></div><span>${number(row.easePercentile,0)} / 100</span></div></div>`;
  }).join(''):'<p class="unavailable-note">FRED 數據暫未取得，等待下次更新。</p>';
}

function renderHeader() {
  const d=state.view==='home'?home.data:state.data;
  if(!d){$('#asof-label').textContent=state.view==='home'?'讀取跨市場資料…':'讀取美股資料…';$('#coverage-label').textContent='正在載入';return;}
  $('#asof-label').textContent=(state.view==='home'?'跨市場資料 ':'美股收市數據 ')+d.asOf;
  $('#archive-date').textContent=d.asOf.replaceAll('-','.');
  $('#coverage-label').textContent=state.view==='home'?`${d.meta.currentCount} / ${d.meta.universeCount} 項有效 · 美股 ${d.stockAsOf}`:`${d.meta.currentCount} / ${d.meta.universeCount} 隻有效 · ${(d.meta.coverage*100).toFixed(1)}%`;
  $('#generated-label').textContent=`計算時間 ${hkTime(d.meta.generatedAt)} HKT`;
}

function renderLeaders() {
  const valid=state.data.rows.filter(r=>Number.isFinite(r.score));
  const strongest=[...valid].sort((a,b)=>b.score-a.score), weakest=[...valid].sort((a,b)=>a.score-b.score);
  const list=rows=>rows.slice(0,10).map((r,i)=>`<li><span class="leader-rank">${String(i+1).padStart(2,'0')}</span><button class="stock-link" data-symbol="${esc(r.symbol)}">${esc(r.symbol)}</button><span class="leader-name" title="${esc(r.name)}">${esc(r.name)}</span><strong class="${cls(r.score)}">${signed(r.score)}</strong></li>`).join('');
  $('#top-strong').innerHTML=list(strongest); $('#top-weak').innerHTML=list(weakest);
}
function renderFilters() {
  const select=$('#sector-filter'), value=select.value;
  select.innerHTML='<option value="">全部板塊</option>'+[...state.data.sectors].sort((a,b)=>a.name.localeCompare(b.name,'zh-Hant')).map(s=>`<option value="${esc(s.symbol)}">${esc(s.name)} · ${esc(s.symbol)}</option>`).join('');
  select.value=value;
  const available=state.data.contracts?.status==='ok';
  $('#perp-filter').disabled=!available; $('#perp-label').classList.toggle('disabled',!available);
  $('#perp-label').title=available?'Binance USDT 永續合約名單':'公開合約名單暫未取得，篩選已停用';
  if(!available) {state.perp=false;$('#perp-filter').checked=false;}
}
function filteredRows() {
  if(!state.data) return [];
  const threshold=state.value.trim()===''?null:Number(state.value);
  const contracts=new Set(state.data.contracts?.symbols||[]);
  const rows=state.data.rows.filter(r=>{
    if(state.view==='watchlist'&&!state.watched.has(r.symbol)) return false;
    if(state.exactSymbol&&r.symbol!==state.exactSymbol)return false;
    if(state.search&&!`${r.symbol} ${r.name} ${r.sectorName} ${r.sector}`.toLowerCase().includes(state.search.toLowerCase())) return false;
    if(state.sector&&r.sector!==state.sector) return false;
    if(state.sectorTop&&(!Number.isFinite(r.sectorRank)||r.sectorRank>state.sectorTop)) return false;
    if(state.streak&&!(r.streak>=7)) return false;
    if(state.long&&!(r.longRS>=50)) return false;
    if(state.perp&&!contracts.has(r.symbol)) return false;
    if(Number.isFinite(threshold)) {const v=metric(r,state.metric);if(!Number.isFinite(v)||(state.operator==='gte'?v<threshold:v>threshold))return false;}
    return true;
  });
  return rows.sort((a,b)=>{
    const x=metric(a,state.sort),y=metric(b,state.sort);
    if(!Number.isFinite(x)) return Number.isFinite(y)?1:a.symbol.localeCompare(b.symbol);
    if(!Number.isFinite(y)) return -1;
    return (x-y)*state.direction||a.symbol.localeCompare(b.symbol);
  });
}
function renderTable() {
  if(!state.data) return;
  const rows=filteredRows(), pages=Math.max(1,Math.ceil(rows.length/state.pageSize));
  state.page=Math.min(state.page,pages);
  const start=(state.page-1)*state.pageSize;
  const cell=(value,title='')=>`<td class="numeric ${cls(value)}"${title?` title="${esc(title)}"`:''}>${pp(value)}</td>`;
  $('#stock-body').innerHTML=rows.slice(start,start+state.pageSize).map(r=>{
    const watch=state.watched.has(r.symbol), delta=r.rankDelta;
    const scoreMax=Math.max(10,...state.data.rows.map(a=>Math.abs(a.score||0)));
    const range=Number.isFinite(r.score)?Math.min(100,Math.abs(r.score)/scoreMax*100):0;
    return `<tr${r.status!=='ok'?' class="stale-row"':''}><td class="numeric rank-col">${r.rank??'—'}</td><td class="numeric rank-delta ${cls(delta)}">${delta>0?'↑ '+delta:delta<0?'↓ '+Math.abs(delta):delta===0?'·':'—'}</td><td class="asset-col"><div class="asset-cell"><button class="watch-button ${watch?'watched':''}" data-watch="${esc(r.symbol)}" aria-label="${watch?'移除自選':'加入自選'} ${esc(r.symbol)}" aria-pressed="${watch}">${watch?'★':'☆'}</button><div><button class="stock-link" data-symbol="${esc(r.symbol)}">${esc(r.symbol)}</button><span class="asset-name" title="${esc(r.name)}">${esc(r.name)}</span>${r.status!=='ok'?`<span class="stale-badge">${r.asOf?esc(r.asOf):'缺數據'}</span>`:''}</div></div></td><td class="numeric price-cell">${number(r.price)}</td><td class="numeric score-col"><span class="score-cell ${cls(r.score)}"><i style="width:${range}%"></i><b>${signed(r.score)}</b></span></td>${cell(r.intra.h1,r.intra.asOf?'小時線時點 '+hkTime(r.intra.asOf)+' HKT；1H 格實際跨度 '+(r.intra.h1ElapsedHours??'—')+' 小時':'缺少完整且同步的小時數據')}${cell(r.intra.h4)}${cell(r.d1)}${cell(r.week?.value,periodTitle(r.week))}${cell(r.month?.value,periodTitle(r.month))}<td class="numeric ${r.streak>=7?'streak-good':'muted'}">${r.streak===null?'—':r.streakCapped?'65+':r.streak?r.streak+' 日':'·'}</td><td class="numeric"><span class="percentile ${r.longRS>=50?'positive':'muted'}">${number(r.longRS,0)}</span></td><td class="sector-cell"><span title="${esc(r.sectorName)} · ${esc(r.sector)}">${esc(r.sectorName)}</span><b class="${r.sectorRank<=3?'sector-top':''}">${r.sectorRank?'#'+r.sectorRank:'—'}</b></td>${cell(state.resilient?r.vsSectorDay:r.vsSector)}<td class="spark-col">${sparkline(r.rsLine)}</td></tr>`;
  }).join('');
  $('#result-count').textContent=`${rows.length} 隻 / ${state.data.rows.length}`;
  $('#ranking-title').textContent=state.view==='watchlist'?'我的自選清單':'全部排名';
  $('#empty-state').hidden=rows.length>0;
  if(state.view==='watchlist'&&!state.watched.size) {$('#empty-state h3').textContent='先收藏幾隻值得留意的股票';$('#empty-state p').textContent='在美股排名按 ☆，便會儲存到這部裝置的自選清單。';} else {$('#empty-state h3').textContent='沒有符合條件的股票';$('#empty-state p').textContent='試試減少篩選條件，或搜尋其他代號。';}
  $('#page-info').textContent=rows.length?`顯示 ${start+1}–${Math.min(start+state.pageSize,rows.length)}，共 ${rows.length} 隻`:'顯示 0 隻';
  $('#page-label').textContent=`${state.page} / ${pages}`;
  $('#prev-page').disabled=state.page===1; $('#next-page').disabled=state.page===pages;
  $$('th[data-sort]').forEach(th=>{const active=th.dataset.sort===state.sort;th.classList.toggle('sorted',active);th.setAttribute('aria-sort',active?(state.direction===1?'ascending':'descending'):'none');th.querySelector('button span').textContent=active?(state.direction===1?'↑':'↓'):'↕';});
  $('#vs-sector-th button').firstChild.textContent=state.resilient?'vs 板塊 1D ':'vs 板塊 ';
}
function periodTitle(period) {return period?.from?`${period.from} → ${period.to}；目標起日 ${period.target}`:'缺少相同起訖日數據';}
function updateWatchCount() {$('#watch-count').textContent=state.watched.size;}
function toggleWatch(symbol) {
  state.watched.has(symbol)?state.watched.delete(symbol):state.watched.add(symbol);
  storage.set('watchlist',[...state.watched]); updateWatchCount(); renderTable();
}
function resetFilters() {
  Object.assign(state,{search:'',exactSymbol:null,sector:'',sectorTop:0,metric:'score',operator:'gte',value:'',streak:false,long:false,resilient:false,perp:false,page:1});
  $('#search').value=''; $('#sector-filter').value=''; $('#metric-filter').value='score'; $('#operator-filter').value='gte'; $('#value-filter').value='';
  ['streak','long','resilient','perp'].forEach(k=>$('#'+k+'-filter').checked=false);
  $$('[data-sector-top]').forEach(b=>{const selected=b.dataset.sectorTop==='0';b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',selected);});
  renderTable();
}
function switchView(view,navigate=true) {
  view=['home','stocks','watchlist','compare'].includes(view)?view:'home';
  const changed=state.view!==view;
  state.view=view;state.page=1;
  $$('[data-view]').forEach(b=>{const active=b.dataset.view===view;b.classList.toggle('active',active);if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $('#home-section').hidden=view!=='home';$('#equity-strip').hidden=view==='home';
  $('#overview-section').hidden=view!=='stocks'; $('#top-section').hidden=view!=='stocks';
  $('#rankings').hidden=!['stocks','watchlist'].includes(view);$('#compare-section').hidden=view!=='compare';
  $('#page-title').innerHTML=view==='home'?'穿越市場時間線，<span>看清資金的方向。</span>':view==='stocks'?'在市場分岔之間，<span>找到相對強者。</span>':view==='watchlist'?'每一個變異，<span>都值得持續追蹤。</span>':'讓不同時間線，<span>在同一起點交匯。</span>';
  $('#view-file').textContent=view==='home'?'FIELD / 000':view==='stocks'?'FIELD / 001':view==='watchlist'?'FILE / 002':'PATH / 003';
  $('#view-kicker').textContent=view==='home'?'THE MULTIVERSE DESK':view==='stocks'?'THE SACRED TIMELINE':view==='watchlist'?'VARIANT SURVEILLANCE':'TIMELINE COMPARISON';
  $('#page-subtitle').textContent=view==='home'?'從全球資產到美股異動，以公開數據追蹤市場強弱與資金輪動。':view==='stocks'?'以 SPY 為基準，從不同時段觀察個股與板塊的強弱變化。':view==='watchlist'?'自選清單只儲存在此瀏覽器。所有篩選及排序照常可用。':'用共同交易日的收市價比較，最多 10 隻，首日統一為 100。';
  $('#timeline-caption').textContent=view==='home'?'MARKET SURVEILLANCE / CROSS-MARKET MEDIAN':view==='compare'?'COMMON DATES / REBASED TO 100':'MARKET SURVEILLANCE / SPY BENCHMARK';
  $('#skip-content').href=view==='home'?'#home-section':view==='compare'?'#compare-section':'#rankings';
  document.title='LokiRS — '+({home:'跨市場情報主頁',stocks:'美股相對強弱',watchlist:'自選情報檔案',compare:'市場走勢比較'}[view]);
  if(navigate&&changed&&location.protocol!=='file:'){const url=new URL(location.href);if(view==='home')url.searchParams.delete('tab');else url.searchParams.set('tab',view);url.searchParams.delete('s');url.hash='';history.pushState({},'',url);}
  renderTable();renderComparison();renderHeader();
}

function showDetail(symbol) {
  const r=state.data?.rows.find(r=>r.symbol===symbol);if(!r)return;
  const priceSeries=r.history.map(p=>({date:p.date,value:p.close}));
  const benchmarkSeries=r.history.map(p=>({date:p.date,value:p.benchmark}));
  const chart=comparisonChart([{name:symbol,points:priceSeries},{name:'SPY',points:benchmarkSeries}],{height:300,width:850});
  $('#detail-content').innerHTML=`<div class="detail-heading"><div><h2>${esc(symbol)}<span>${esc(r.name)}</span></h2><p>${esc(r.sectorName)} · ${esc(r.sector)} · 收市 ${esc(r.asOf||'—')}</p></div><div><strong>${number(r.price)}</strong><span>USD</span></div></div><div class="detail-metrics"><div><span>LokiRS · 近似</span><b class="${cls(r.score)}">${signed(r.score)}</b></div><div><span>1D 超額</span><b class="${cls(r.d1)}">${pp(r.d1)}</b></div><div><span>一週超額</span><b class="${cls(r.week?.value)}">${pp(r.week?.value)}</b></div><div><span>一月超額</span><b class="${cls(r.month?.value)}">${pp(r.month?.value)}</b></div></div><div class="detail-chart">${chart}</div><div class="detail-meta"><p>小時線時點：${r.intra.asOf?esc(hkTime(r.intra.asOf))+' HKT':'無完整同步數據'}。日線超額和小時線超額使用各自時點。</p><p>1H／4H K 線格數的實際跨度：${number(r.intra.h1ElapsedHours,1)}／${number(r.intra.h4ElapsedHours,1)} 小時。<br>精確時鐘 1H 超額：${pp(r.intra.clockH1)}；精確時鐘 4H 超額：${pp(r.intra.clockH4)}。</p><p>一週：${esc(periodTitle(r.week))}<br>一個月：${esc(periodTitle(r.month))}</p></div><div class="dialog-bottom"><button class="button" data-add-compare="${esc(symbol)}">＋ 加入走勢比較</button><a class="external-link" target="_blank" rel="noopener" href="https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}/">Yahoo Finance ↗</a></div>`;
  $('#detail-dialog').showModal();
}
function comparisonUniverse() {
  const rows=state.data?.rows||[], markets=home.data?.rows||[];
  const benchmark={symbol:'SPY',name:'SPY',history:rows.find(r=>r.history.length>10)?.history.map(p=>({...p,close:p.benchmark}))||[]};
  return [...new Map([benchmark,...markets,...rows].map(r=>[r.symbol,r])).values()];
}
function renderComparison() {
  const all=comparisonUniverse();
  if(!all.some(r=>r.history.length))return;
  const selected=state.compare.map(s=>all.find(r=>r.symbol===s)).filter(Boolean);
  $('#compare-chips').innerHTML=selected.map((r,i)=>`<button class="compare-chip" data-remove-compare="${esc(r.symbol)}" title="移除 ${esc(r.symbol)}"><i style="border-top-color:${palette[i%palette.length]};border-top-style:${i<4?'solid':i<8?'dashed':'dotted'}"></i>${esc(r.symbol)}<span>×</span></button>`).join('')+`<span class="muted small">${selected.length} / 10</span>`;
  $('#compare-chart').innerHTML=comparisonChart(selected.map((r,i)=>({name:r.symbol,color:palette[i%palette.length],points:r.history.slice(-state.period).map(p=>({date:p.date,value:p.close}))})));
}
function addCompare(symbol) {
  if(state.compare.includes(symbol)) {toast('已在比較清單中');return;}
  if(state.compare.length>=10) {toast('最多可比較 10 隻，請先移除一隻');return;}
  state.compare.push(symbol);storage.set('compare',state.compare);renderComparison();toast('已加入 '+symbol);
  $('#compare-search').value='';$('#compare-results').hidden=true;
}
function searchCompare() {
  const query=$('#compare-search').value.trim().toLowerCase();
  const hits=comparisonUniverse().filter(r=>r.symbol.toLowerCase().includes(query)||(r.name||'').toLowerCase().includes(query)).slice(0,8);
  $('#compare-results').hidden=!query;
  $('#compare-results').innerHTML=hits.length?hits.map(r=>`<button data-add-compare="${esc(r.symbol)}"><strong>${esc(r.symbol)}</strong><span>${esc(r.name)}</span><b>＋</b></button>`).join(''):'<p>沒有符合的代號</p>';
}
function renderMethodStatus() {
  const d=state.data;
  $('#method-status').innerHTML=`<table class="method-status-table"><tbody><tr><td>日線資料</td><td>${esc(d.asOf)} · ${d.meta.currentCount}/${d.meta.universeCount} 隻</td></tr><tr><td>1H 資料覆蓋</td><td>${d.meta.intradayCount} 隻（各列另附時點）</td></tr><tr><td>CNN 恐懼貪婪</td><td>${d.sentiment.status==='ok'?'已取得':'未取得，保留缺值'}</td></tr><tr><td>合約名單</td><td>${d.contracts.status==='ok'?'已取得':'未取得，停用篩選'}</td></tr><tr><td>下載失敗請求</td><td>${d.meta.errors.length} 筆（日線／小時線獨立計數）</td></tr><tr><td>FRED 更新</td><td>${d.meta.macroError?'失敗，顯示舊值或缺值':'成功，使用各列觀測日期'}</td></tr></tbody></table>`;
  const weights=d.meta.scoreWeights;
  if(weights)$('#score-formula').textContent=Object.entries(weights).map(([p,w])=>`${w} × 超額 ${p}D`).join(' + ');
  const long=d.meta.longTermWeights;
  if(long)$('#long-formula').textContent='長線值 = '+Object.entries(long).map(([p,w])=>`${w} × 超額 ${p}D`).join(' + ');
}
function exportCSV() {
  const headings=['rank','symbol','name','asOf','status','price_USD','LokiRS_approx','rank_delta','1h_excess_pp','4h_excess_pp','1d_excess_pp','week_excess_pp','month_excess_pp','week_from','month_from','streak_approx','long_RS_percentile_approx','sector','sector_rank_approx','vs_sector_approx','vs_sector_1d_pp','intraday_asOf','h1_elapsed_hours','h4_elapsed_hours','exact_clock_1h_excess_pp','exact_clock_4h_excess_pp'];
  const rows=filteredRows().map(r=>[r.rank,r.symbol,r.name,r.asOf,r.status,r.price,r.score,r.rankDelta,r.intra.h1,r.intra.h4,r.d1,r.week?.value,r.month?.value,r.week?.from,r.month?.from,r.streak,r.longRS,r.sector,r.sectorRank,r.vsSector,r.vsSectorDay,r.intra.asOf,r.intra.h1ElapsedHours,r.intra.h4ElapsedHours,r.intra.clockH1,r.intra.clockH4]);
  const quote=v=>{let value=String(v??'');if(typeof v==='string'&&/^[=+\-@]/.test(value))value="'"+value;return '"'+value.replaceAll('"','""')+'"';};
  download('\ufeff'+[headings,...rows].map(r=>r.map(quote).join(',')).join('\r\n'),`lokirs-${state.data.asOf}.csv`,'text/csv;charset=utf-8');
}

function exportComparison() {
  const svg=$('#compare-chart svg');if(!svg)return;
  const clone=svg.cloneNode(true), box=clone.getAttribute('viewBox').split(' ').map(Number);
  const legends=$$('#compare-chart .chart-legend>span'), height=box[3]+Math.ceil(legends.length/4)*25+15;
  clone.setAttribute('viewBox',`0 0 ${box[2]} ${height}`);
  const ns='http://www.w3.org/2000/svg';
  const background=document.createElementNS(ns,'rect');background.setAttribute('width',box[2]);background.setAttribute('height',height);background.setAttribute('fill','#07130f');clone.insertBefore(background,clone.firstChild);
  legends.forEach((entry,i)=>{
    const color=entry.querySelector('i').style.borderTopColor||palette[i%palette.length];
    const line=document.createElementNS(ns,'line'), x=22+(i%4)*(box[2]-40)/4, y=box[3]+18+Math.floor(i/4)*25;
    line.setAttribute('x1',x);line.setAttribute('x2',x+15);line.setAttribute('y1',y);line.setAttribute('y2',y);line.setAttribute('stroke',color);line.setAttribute('stroke-width','2');line.setAttribute('stroke-dasharray',seriesDashes[i%seriesDashes.length]);clone.append(line);
    const text=document.createElementNS(ns,'text');text.setAttribute('x',x+22);text.setAttribute('y',box[3]+22+Math.floor(i/4)*25);
    text.setAttribute('fill',color);text.setAttribute('font-family','IBM Plex Mono, Courier New, monospace');text.setAttribute('font-size','12');
    text.textContent=entry.querySelector('strong').textContent+' ';
    const change=document.createElementNS(ns,'tspan'), value=entry.querySelector('b');
    change.setAttribute('fill',value.classList.contains('negative')?'#f18a73':'#8ddd9b');change.textContent=value.textContent;text.append(change);clone.append(text);
  });
  download(clone.outerHTML,`lokirs-comparison-${state.data.asOf}.svg`,'image/svg+xml');
}

document.addEventListener('click',event=>{
  const target=event.target.closest('button');if(!target)return;
  if(target.dataset.symbol)showDetail(target.dataset.symbol);
  if(target.dataset.watch)toggleWatch(target.dataset.watch);
  if(target.dataset.view)switchView(target.dataset.view);
  if(target.dataset.sectorTop!==undefined){state.sectorTop=Number(target.dataset.sectorTop);state.page=1;$$('[data-sector-top]').forEach(b=>{const selected=b===target;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',selected);});renderTable();}
  if(target.hasAttribute('data-close-dialog'))target.closest('dialog').close();
  if(target.dataset.addCompare){addCompare(target.dataset.addCompare);if(target.closest('#detail-dialog')){$('#detail-dialog').close();switchView('compare');}}
  if(target.dataset.removeCompare){state.compare=state.compare.filter(s=>s!==target.dataset.removeCompare);storage.set('compare',state.compare);renderComparison();}
});
['method-open','notice-method','footer-method'].forEach(id=>$('#'+id).addEventListener('click',()=>$('#method-dialog').showModal()));
$$('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
$('#theme-toggle').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'reading':'dark'));
$('#refresh').addEventListener('click',()=>state.view==='home'?home.load(true):loadData(true));
$('#overview-toggle').addEventListener('click',()=>{const expanded=$('#overview-toggle').getAttribute('aria-expanded')==='true';$('#overview-grid').hidden=expanded;$('#overview-toggle').setAttribute('aria-expanded',!expanded);$('#overview-toggle').textContent=expanded?'展開 ＋':'收起 −';});
$('#search').addEventListener('input',event=>{state.search=event.target.value.trim();state.exactSymbol=null;state.page=1;renderTable();});
[['sector-filter','sector'],['metric-filter','metric'],['operator-filter','operator'],['value-filter','value']].forEach(([id,key])=>$('#'+id).addEventListener(id==='value-filter'?'input':'change',event=>{state[key]=event.target.value;state.page=1;renderTable();}));
['streak','long','resilient','perp'].forEach(key=>$('#'+key+'-filter').addEventListener('change',event=>{state[key]=event.target.checked;state.page=1;renderTable();}));
['reset-filters','empty-reset'].forEach(id=>$('#'+id).addEventListener('click',resetFilters));
$$('th[data-sort]').forEach(th=>th.querySelector('button').addEventListener('click',()=>{state.direction=state.sort===th.dataset.sort?-state.direction:['rank','sectorRank'].includes(th.dataset.sort)?1:-1;state.sort=th.dataset.sort;state.page=1;renderTable();}));
$('#page-size').addEventListener('change',event=>{state.pageSize=Number(event.target.value);state.page=1;renderTable();});
$('#prev-page').addEventListener('click',()=>{state.page--;renderTable();$('#rankings').scrollIntoView({behavior:'smooth',block:'start'});});
$('#next-page').addEventListener('click',()=>{state.page++;renderTable();$('#rankings').scrollIntoView({behavior:'smooth',block:'start'});});
$('#download-csv').addEventListener('click',exportCSV);
$('#compare-search').addEventListener('input',searchCompare);
$('#compare-period').addEventListener('change',event=>{state.period=Number(event.target.value);renderComparison();});
$('#export-chart').addEventListener('click',exportComparison);
document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!$('dialog[open]')){event.preventDefault();if(state.view==='home')home.focusSearch();else if(state.view==='compare')$('#compare-search').focus();else $('#search').focus();}});
const home=createHome({document,window,fetch:window.fetch.bind(window),download,toast,getView:()=>state.view,
  onView:view=>switchView(view),onCompare:symbol=>{addCompare(symbol);switchView('compare');},
  onStock:symbol=>{switchView('stocks');resetFilters();state.search=symbol;state.exactSymbol=symbol;state.page=1;$('#search').value=symbol;renderTable();$('#rankings').scrollIntoView({behavior:'smooth',block:'start'});},
  onUpdate:()=>{$('#loading-state').hidden=true;$('#dashboard').hidden=false;renderHeader();renderComparison();}});
window.addEventListener('popstate',()=>switchView(readView(),false));
const initialSymbol=new URLSearchParams(location.search).get('s');
if(initialSymbol){state.search=initialSymbol.replace(/^LB:/,'').replace(/\.US$/,'');state.exactSymbol=state.search;$('#search').value=state.search;}
switchView(state.view,false);
loadData();home.load();
