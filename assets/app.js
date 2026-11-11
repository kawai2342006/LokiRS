import {sparkline, comparisonChart, palette, seriesDashes, escapeHTML as esc} from './charts.js?v=1.2.0';
import {filterRankings, formatMarketCap, marketCapTitle, summarizeRankings, renderRankingDashboard} from './rankings.js?v=1.5.2';
import {createRankingUI} from './ranking-ui.js?v=1.5.2';
import {createHome} from './home.js?v=1.4.0';
import {createSentiment} from './sentiment.js?v=1.3.3';
import {createSnapshotLoader, publicationAge, reloadMessage, createAutoRefresh} from './publication.js?v=1.6.1';

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
const state = {data:null, snapshotMode:storage.get('snapshot-mode','close')==='intraday'?'intraday':'close', view:readView(), search:'', exactSymbol:null, sector:'', sectorTop:0, metric:'score', operator:'gte', value:'', capUnit:1e9, streak:false,
  long:false, resilient:false, perp:false, sort:'score', direction:-1, page:1, pageSize:50, dashboardSort:'count', dashboardDirection:-1,
  watched:new Set(storage.get('watchlist',[])), compare:storage.get('compare',['SPY','NVDA','AAPL']), period:64,
  auto:storage.get('stocks-auto',true)};
const number = (v, digits=2) => Number.isFinite(v) ? v.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—';
const signed = (v,digits=2) => Number.isFinite(v) ? (v>0?'+':'')+number(v,digits) : '—';
const cls = v => Number.isFinite(v) ? v>0?'positive':v<0?'negative':'muted' : 'muted';
const percent = v => Number.isFinite(v) ? signed(v)+'%' : '—';
const hkTime = value => { try { return new Intl.DateTimeFormat('zh-HK',{timeZone:'Asia/Hong_Kong',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value)); } catch { return '—'; } };
let toastTimer, loadSequence=0, snapshotLoading=false, snapshotError=null, checkedAt=null;

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
const rankingUI=createRankingUI({document,window,getView:()=>state.view,getRows:()=>filteredRows(),getResilient:()=>state.resilient});
const snapshotLoader=createSnapshotLoader({fetch:(...args)=>fetch(...args)});
const closeColumnTitles=new Map($$('#stock-table th[data-sort]').map(th=>[th.dataset.sort,th.title]));

async function loadData(manual=false) {
  const mode=state.snapshotMode, request=++loadSequence;
  snapshotLoading=true; snapshotError=null; $('#refresh').classList.add('rotating'); renderHeader();
  try {
    const {data,previous}=await snapshotLoader.load(mode);
    if(request!==loadSequence||state.snapshotMode!==mode)return;
    state.data=data; checkedAt=new Date().toISOString();
    renderOverview(); renderLeaders(); renderFilters(); renderTable(); renderComparison(); renderMethodStatus(); updateWatchCount();
    if(manual) toast(reloadMessage(data,previous));
  } catch(error) {
    if(request!==loadSequence||state.snapshotMode!==mode)return;
    snapshotError=error;
  } finally {
    if(request===loadSequence&&state.snapshotMode===mode) {
      snapshotLoading=false; $('#refresh').classList.remove('rotating'); renderHeader();
    }
  }
}

function switchSnapshot(mode) {
  if(!['close','intraday'].includes(mode)||mode===state.snapshotMode)return;
  state.snapshotMode=mode; storage.set('snapshot-mode',mode); state.page=1;
  state.data=snapshotLoader.cached(mode); snapshotError=null; checkedAt=null;
  $('#detail-dialog').close();
  if(state.data){renderOverview();renderLeaders();renderFilters();renderTable();renderComparison();renderMethodStatus();}
  loadData();
}

function renderSnapshotControls() {
  const isHome=state.view==='home', intraday=state.snapshotMode==='intraday', d=state.data;
  const available=!!d, meta=d?.meta;
  $('#snapshot-controls').hidden=isHome;
  $$('[data-snapshot-mode]').forEach(button=>{
    const active=button.dataset.snapshotMode===state.snapshotMode;
    button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));
  });
  $('#dashboard').hidden=isHome?!home.data:!available;
  $('#loading-state').hidden=isHome?!!home.data:available||!snapshotLoading;
  $('#loading-message').textContent=isHome?'正在讀取跨市場快照':intraday?'正在讀取已發布盤中 60m 快照':'正在讀取收市快照';
  $('#snapshot-empty').hidden=isHome||available||snapshotLoading;
  $('#snapshot-empty-title').textContent=intraday?'尚未能載入盤中快照':'未能載入收市快照';
  $('#snapshot-empty-text').textContent=intraday?
    '等待下一次盤中自動排程發布，或在 GitHub Actions 按 Run workflow，選 snapshot_mode = intraday，保留 refresh_data 勾選。正常交易日於紐約 10:40–15:40 每小時更新；完成部署後再檢查。':
    '請檢查 GitHub Pages 已部署 data/latest.json，再按「檢查更新」。';
  $('#stocks-bookmarks').hidden=state.view!=='stocks'||!available;
  const windowText=intraday&&meta?`完整 K 線 ${hkTime(meta.snapshotBarStart)}–${hkTime(meta.snapshotAt)} HKT`:'完整 60m K 線';
  $('#snapshot-note').textContent=intraday&&meta?
    `${windowText} · 1D 至一個月均截至此時點。Δ 對比 ${meta.referenceCloseDate||'未提供'} 收市排名；長線 RS／持續日數沿用 ${meta.closedMetricsAsOf||'未提供'} 收市值；市值沿用原有來源時點。`:
    intraday?'紐約交易日 10:40–15:40 每小時自動抓取，正常全日 6 次；僅用已完成的完整 60m K 線。網頁每 60 秒只檢查發布版本。':'每日收市後自動抓取及重算；可切換至按小時自動發布的盤中 60m 快照。';
  const titles=intraday?{
    rankDelta:`${meta?.referenceCloseDate||'參考日'} 收市名次 − 盤中名次；沒有先前收市參考便留空`,
    h1:'1 根完整 60m K 線的收盤點之差；跨夜按 K 線格數計，詳情列實際跨度。',
    h4:'4 根完整 60m K 線的收盤點之差；收市半小時短 K 不計，跨夜按 K 線格數計。',
    d1:`${meta?.dailyBaselineDate||'上一交易日'} 收市至盤中快照：個股回報 − SPY 回報`,
    streak:`沿用 ${meta?.closedMetricsAsOf||'未提供'} 收市持續日數；盤中不增加日數`,
    longRS:`沿用 ${meta?.closedMetricsAsOf||'未提供'} 收市長線 RS 百分位`
  }:{};
  $$('#stock-table th[data-sort]').forEach(th=>{th.title=titles[th.dataset.sort]??closeColumnTitles.get(th.dataset.sort)??'';});
  $('#compare-note').textContent=intraday?
    '美股歷史調整價換算至上一原始收市價基準，末點為盤中 60m 快照；跨市場資產沿用各自收市資料。只比較共同日期。':
    '使用 Yahoo 股息及拆股調整收市價。只用所有已選資產均有數據的日期。';
  $('#publication-help').textContent=intraday?
    '盤中於紐約交易日 10:40–15:40 每小時自動抓取；休市或沒有新 K 線便跳過。亦可手動執行 intraday 更新。網頁每 60 秒只檢查已發布版本。':
    '每日美股收市後由排程抓取及重算；本頁每 60 秒檢查已發布版本。';
  $('#update-workflow').title='Run workflow：snapshot_mode 選 close（收市）或 intraday（完整 60m 盤中），保留 refresh_data 勾選；部署完成後檢查更新。';
  const age=publicationAge(d), old=age!==null&&age>=36, issues=meta?meta.universeCount-meta.currentCount:0, reconstructed=meta?.reconstructedDailyCount||0;
  const messages=isHome?[]:[snapshotError?`${intraday?'盤中':'收市'}快照讀取失敗（${snapshotError.message}）。${available?'保留此模式已載入的快照。':intraday&&snapshotError.status===404?'尚未發布，請等待自動排程或手動執行盤中更新。':'請檢查部署或稍後重試。'}`:'',
    old?`此${intraday?'盤中':'收市'}快照已 ${age} 小時未發布新版本；快照時點見上方標示。`:'',
    issues?`${issues} 隻股票缺少當期有效分數，已排除於當期排名。`:'',
    reconstructed?`${reconstructed} 隻股票日線缺值，以同日完整小時線核對收市。`:''].filter(Boolean);
  $('#error-banner').hidden=!messages.length;$('#error-banner').textContent=messages.join(' ');
  $('#status-dot').classList.toggle('warning',!isHome&&(!!snapshotError||old||issues>0||reconstructed>0));
}

function renderOverview() {
  const {data}=state, meta=data.meta;
  renderHeader();
  $('#spy-price').textContent=number(data.benchmark.price);
  $('#spy-change').textContent=Number.isFinite(data.benchmark.d1)?signed(data.benchmark.d1)+'%':'—'; $('#spy-change').className=cls(data.benchmark.d1);
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
  sentimentPanel.setFallback(data.sentiment);
  $('#macro-content').innerHTML=data.macro.length?data.macro.map(row=>{
    const stale=row.status==='stale', direction=row.changeMonth*row.direction;
    return `<div class="macro-row"><div><a href="${esc(row.url||'https://fred.stlouisfed.org/')}" target="_blank" rel="noopener">${esc(row.name)}</a><small>${esc(row.asOf?.slice(5)||'—')}${stale?' · 舊值':''}</small><strong>${number(row.value,row.id==='DTWEXBGS'?2:2)}${esc(row.unit)}</strong><span class="macro-change ${stale?'muted':cls(direction)}">${signed(row.changeMonth)}</span></div><div class="macro-scale"><span>${row.windowYears||'—'} 年寬鬆百分位</span><div><i style="width:${Math.max(0,Math.min(100,row.easePercentile||0))}%"></i></div><span>${number(row.easePercentile,0)} / 100</span></div></div>`;
  }).join(''):'<p class="unavailable-note">FRED 數據暫未取得，等待下次更新。</p>';
}

function renderHeader() {
  renderSnapshotControls();
  $('#stocks-auto').hidden=state.view==='home';
  $('#stocks-auto').setAttribute('aria-pressed',String(state.auto));
  $('#stocks-auto').textContent=state.auto?'美股自動檢查 60s':'美股自動檢查已暫停';
  const d=state.view==='home'?home.data:state.data;
  const intraday=state.view!=='home'&&state.snapshotMode==='intraday';
  if(!d){$('#asof-label').textContent=state.view==='home'?'讀取跨市場資料…':intraday?'盤中 60m · 尚未載入':'收市快照 · 尚未載入';$('#coverage-label').textContent=snapshotLoading?'正在載入':'等待發布快照';$('#generated-label').textContent='';if(state.view!=='home')$('#publication-status').textContent=intraday?'盤中 60m 快照尚未載入':'收市快照尚未載入';return;}
  $('#asof-label').textContent=state.view==='home'?'跨市場資料 '+d.asOf:intraday?`盤中 60m · ${hkTime(d.meta.snapshotAt)} HKT`:'美股收市數據 '+d.asOf;
  if(state.view==='home')$('#publication-status').textContent=`首頁發布 ${hkTime(d.meta.generatedAt)} HKT · 美股行情 ${d.stockAsOf}`;
  else $('#publication-status').textContent=(checkedAt?`已檢查 ${hkTime(checkedAt)} HKT · `:'')+(intraday?`盤中 K 線 ${hkTime(d.meta.snapshotAt)} HKT`:`收市行情 ${d.asOf}`)+` · 發布 ${hkTime(d.meta.generatedAt)} HKT`;
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
  return filterRankings(state.data?.rows||[],state,state.data?.contracts?.symbols||[]);
}
function renderRankingsDashboard(rows) {
  $('#ranking-dashboard').hidden=state.view!=='stocks';
  if(state.view!=='stocks')return;
  const summary=summarizeRankings(rows);
  $('#dashboard-scope').textContent=`${rows.length} / ${state.data.rows.length} 隻 · ${summary.sectors.length} 個板塊 · 統計全部篩選結果`;
  $('#ranking-dashboard-content').innerHTML=renderRankingDashboard(summary,state.sector,state.dashboardSort,state.dashboardDirection);
}
function sortDashboard(key) {
  state.dashboardDirection=state.dashboardSort===key?-state.dashboardDirection:key==='name'?1:-1;
  state.dashboardSort=key;renderRankingsDashboard(filteredRows());
  $$('[data-dashboard-sort]').find(button=>button.dataset.dashboardSort===key)?.focus({preventScroll:true});
}
function toggleDashboardSector(symbol) {
  state.sector=state.sector===symbol?'':symbol;
  $('#sector-filter').value=state.sector;
  state.page=1;renderTable();
}
function updateMetricControl() {
  const marketCap=state.metric==='marketCap';
  $('#cap-unit-filter').hidden=!marketCap;
  $('#numeric-filter').classList.toggle('has-market-cap',marketCap);
  $('#cap-unit-filter').value=String(state.capUnit??1e9);
  $('#value-filter').placeholder=marketCap?'例：10':'數值';
  $('#value-filter').setAttribute('aria-label',marketCap?'市值篩選數值，單位由右方選擇':'篩選數值');
  $('#value-filter').title=marketCap?'K = 千、M = 百萬、B = 十億 USD；例如 10 B = 100 億美元':'';
}

function renderTable() {
  if(!state.data) return;
  const rows=filteredRows(); renderRankingsDashboard(rows);
  const pages=Math.max(1,Math.ceil(rows.length/state.pageSize));
  state.page=Math.min(state.page,pages);
  const start=(state.page-1)*state.pageSize;
  const cell=(value,title='')=>`<td class="numeric ${cls(value)}"${title?` title="${esc(title)}"`:''}>${percent(value)}</td>`;
  $('#stock-body').innerHTML=rows.slice(start,start+state.pageSize).map(r=>{
    const delta=r.rankDelta;
    const scoreMax=Math.max(10,...state.data.rows.map(a=>Math.abs(a.score||0)));
    const range=Number.isFinite(r.score)?Math.min(100,Math.abs(r.score)/scoreMax*100):0;
    return `<tr${r.status!=='ok'?' class="stale-row"':''}><td class="numeric rank-col">${r.rank??'—'}</td><td class="numeric rank-delta ${cls(delta)}">${delta>0?'↑ '+delta:delta<0?'↓ '+Math.abs(delta):delta===0?'·':'—'}</td><td class="asset-col"><div class="asset-cell"><div><button class="stock-link" data-symbol="${esc(r.symbol)}">${esc(r.symbol)}</button><span class="asset-name" title="${esc(r.name)}">${esc(r.name)}</span>${r.dailyCloseReconstructed?'<span class="stale-badge" title="日線缺值，使用完整小時線核對的同日收市資料；來源詳見 CSV。">收市重建</span>':''}${r.dividendBackfill?`<span class="stale-badge" title="${r.dividendBackfill.sourceStatus==='provisional'?'存託銀行公開的暫定總派息，尚未定案。':'獨立來源核實派息，Yahoo 日線尚未調整。'}">${r.dividendBackfill.sourceStatus==='provisional'?'暫定派息':'派息補正'}</span>`:''}${r.status!=='ok'?`<span class="stale-badge" title="${esc(r.intradayNote||'缺少當期有效分數')}">${r.asOf?esc(r.asOf):'缺數據'}</span>`:''}</div></div></td><td class="numeric price-cell">${number(r.price)}</td><td class="numeric market-cap-cell" title="${esc(marketCapTitle(r))}">${formatMarketCap(r.marketCap)}${r.marketCapStatus==='stale'?'<small>舊值</small>':''}</td><td class="numeric score-col"><span class="score-cell ${cls(r.score)}"><i style="width:${range}%"></i><b>${signed(r.score)}</b></span></td>${cell(r.intra.h1,r.intra.asOf?'小時線時點 '+hkTime(r.intra.asOf)+' HKT；1H 格實際跨度 '+(r.intra.h1ElapsedHours??'—')+' 小時':'缺少完整且同步的小時數據')}${cell(r.intra.h4)}${cell(r.d1)}${cell(r.d3,tradingPeriodTitle(r.d3From,state.data.asOf))}${cell(r.week?.value,periodTitle(r.week))}${cell(r.fortnight?.value,periodTitle(r.fortnight))}${cell(r.month?.value,periodTitle(r.month))}<td class="numeric ${r.streak>=7?'streak-good':'muted'}">${r.streak===null?'—':r.streakCapped?r.streak+'+':r.streak?r.streak+' 日':'·'}</td><td class="numeric"><span class="percentile ${r.longRS>=50?'positive':'muted'}">${number(r.longRS,0)}</span></td><td class="sector-cell"><button class="sector-filter-button ${state.sector===r.sector?'selected':''}" data-dashboard-sector="${esc(r.sector)}" aria-pressed="${state.sector===r.sector}" title="${esc(r.sectorName)} · ${esc(r.sector)}；${state.sector===r.sector?'再按一次取消板塊篩選，保留其他條件':'按下篩選此板塊'}"><span>${esc(r.sectorName)}</span><b class="${r.sectorRank<=3?'sector-top':''}">${r.sectorRank?'#'+r.sectorRank:'—'}</b></button></td>${cell(state.resilient?r.vsSectorDay:r.vsSector)}<td class="spark-col">${sparkline(r.rsLine,{width:320,height:34})}</td></tr>`;
  }).join('');
  $('#result-count').textContent=`${rows.length} 隻 / ${state.data.rows.length}`;
  $('#ranking-title').textContent=state.view==='watchlist'?'我的自選清單':'全部排名';
  $('#empty-state').hidden=rows.length>0;
  if(state.view==='watchlist'&&!state.watched.size) {$('#empty-state h3').textContent='先收藏幾隻值得留意的股票';$('#empty-state p').textContent='在美股排名點入股票代號，再按視窗左上角代號旁的 ☆，即可加入自選。';} else {$('#empty-state h3').textContent='沒有符合條件的股票';$('#empty-state p').textContent='試試減少篩選條件，或搜尋其他代號。';}
  $('#page-info').textContent=rows.length?`顯示 ${start+1}–${Math.min(start+state.pageSize,rows.length)}，共 ${rows.length} 隻`:'顯示 0 隻';
  $('#page-label').textContent=`${state.page} / ${pages}`;
  $('#prev-page').disabled=state.page===1; $('#next-page').disabled=state.page===pages;
  $$('th[data-sort]').forEach(th=>{const active=th.dataset.sort===state.sort;th.classList.toggle('sorted',active);th.setAttribute('aria-sort',active?(state.direction===1?'ascending':'descending'):'none');th.querySelector('button span').textContent=active?(state.direction===1?'↑':'↓'):'↕';});
  $('#vs-sector-th button').firstChild.textContent=state.resilient?'vs 板塊 1D ':'vs 板塊 ';
}
function tradingPeriodTitle(from,to) {return from?`${from} → ${to}；3 個 SPY 交易日`:'缺少相同起訖日數據';}
function periodTitle(period) {return period?.from?`${period.from} → ${period.to}；目標起日 ${period.target}`:'缺少相同起訖日數據';}
function updateWatchCount() {$('#watch-count').textContent=state.watched.size;}
function toggleWatch(symbol) {
  state.watched.has(symbol)?state.watched.delete(symbol):state.watched.add(symbol);
  storage.set('watchlist',[...state.watched]); updateWatchCount(); renderTable();
  $$('[data-watch]').forEach(button=>{
    const watched=state.watched.has(button.dataset.watch);
    button.classList.toggle('watched',watched);button.textContent=watched?'★':'☆';
    button.setAttribute('aria-pressed',String(watched));
    button.setAttribute('aria-label',`${watched?'移除自選':'加入自選'} ${button.dataset.watch}`);
  });
}
function resetFilters() {
  Object.assign(state,{search:'',exactSymbol:null,sector:'',sectorTop:0,metric:'score',operator:'gte',value:'',capUnit:1e9,streak:false,long:false,resilient:false,perp:false,page:1});
  $('#search').value=''; $('#sector-filter').value=''; $('#metric-filter').value='score'; $('#operator-filter').value='gte'; $('#value-filter').value=''; $('#cap-unit-filter').value='1000000000'; updateMetricControl();
  ['streak','long','resilient','perp'].forEach(k=>$('#'+k+'-filter').checked=false);
  $$('[data-sector-top]').forEach(b=>{const selected=b.dataset.sectorTop==='0';b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',selected);});
  renderTable();
}
function switchView(view,navigate=true) {
  view=['home','stocks','watchlist','compare'].includes(view)?view:'home';
  const changed=state.view!==view;
  state.view=view;state.page=1;$('#stocks-bookmarks').hidden=view!=='stocks'||!state.data;
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
  const intraday=state.data?.meta?.snapshotMode==='intraday';
  // Primary listings checked against Nasdaq Trader symbol directories, 2026-11-10.
  // TradingView uses CBOE:CBOE; unverified/new listings use its bare-symbol resolver.
  // Class-B shares use dots on TradingView while Yahoo keeps the original hyphen.
  const tradingViewListings = {
    NYSE: [
      "A ABBV ABT ACN ADM AEE AES AFL AIG AIZ AJG ALB ALL ALLE AMCR AME AMP AMT AMX ANET AON AOS APD APH APO APTV ARE ARES",
      "ASX ATO AU AVY AWK AXP AZN AZO BA BABA BAC BALL BAM BAX BB BBY BCS BDX BE BEN BF-B BG BHP BLDR BLK BMY BNY BP BR",
      "BRK-B BRO BSX BTI BUD BX BXP C CAG CAH CARR CAT CB CBRE CCI CCL CF CFG CHD CI CIEN CL CLX CMG CMI CMS CNC CNP COF",
      "COHR COP COR CPAY CPT CRH CRL CRM CTVA CVNA CVS CVX D DAL DD DE DECK DELL DEO DG DGX DHI DHR DIS DLR DOC DOV DOW",
      "DRI DTE DUK DVA DVN ECL ED EFX EG EIX EL ELV EME EMR EOG EPD EQNR EQT ES ESS ETN ETR EW EXPD EXR F FCX FDS FDX FDXF",
      "FE FERG FICO FIS FITB FIX FRT FTV GD GDDY GE GEV GIS GL GLW GM GNRC GPC GPN GRMN GS GSK GWW HAL HCA HD HDB HIG HII",
      "HIMS HPE HPQ HRL HSBC HSY HUBB HUM HWM IBM IBN ICE IEX IFF INFY INVH IONQ IP IQV IR IRM IT ITUB ITW IVZ J JBL JCI",
      "JNJ JPM KEY KEYS KHC KIM KKR KMI KO KR L LDOS LEN LH LHX LII LLY LMT LNG LOW LUV LVS LYB LYG LYV MA MAA MAS MCD MCK",
      "MCO MDT MET MGM MKC MLM MMM MO MOS MPC MRK MRSH MS MSCI MSI MTB MTD NCLH NEE NEM NET NI NKE NOC NOK NOW NRG NSC NU",
      "NUE NVO NVR NVS O OKE OKLO OMC ORCL OTIS OXY P PBR PCG PEG PFE PG PGR PH PHM PKG PLD PM PNC PNR PNW PPG PPL PRU PSA",
      "PSX PWR Q RACE RCL RDDT RF RIO RJF RL RMD ROK ROL RSG RTX RVTY SAN SAP SCCO SCHW SE SHEL SHW SJM SKYD SLB SMR SNA",
      "SNOW SO SOLV SOMN SONY SPG SPGI SPOT SRE STE STT STZ SW SWK SYF SYK SYY T TAP TDG TDY TEL TFC TGT TJX TKO TM TMO",
      "TPL TPR TRGP TRV TSM TSN TT TTE TWLO TXT TYL UBER UBS UDR UHS UL UMC UNH UNP UPS URI USB V VALE VEEV VICI VLO VLTO",
      "VMC VMRK VRT VST VTR VYLR VZ WAB WAT WEC WELL WFC WM WMB WRB WSM WST WY XOM XYL XYZ YUM ZBH ZTS",
    ].join(' '),
    NASDAQ: [
      "AAPL ABNB ACGL ADBE ADI ADP ADSK AEP AFRM AKAM ALAB ALGN AMAT AMD AMGN AMZN APA APP ARGX ARM ASML ASTS AVGO AXON",
      "BIIB BKNG BKR CASY CBRS CCEP CDNS CDW CEG CHRW CHTR CINF CLSK CMCSA CME COIN COO COST CPRT CRWD CRWV CSCO CSGP CSX",
      "CTAS CTSH DASH DDOG DKNG DLTR DPZ DXCM EBAY ECHO EQIX ERIE EVRG EXC EXE EXPE FANG FAST FFIV FISV FLEX FOX FOXA FSLR",
      "FTNT GEHC GEN GILD GOOG GOOGL GOOGM GOOGN HAS HBAN HLT HON HONA HOOD HSIC HST IBKR IDXX ILMN INCY INTC INTU IREN",
      "ISRG JBHT JKHY KDP KLAC KMB LIN LITE LNT LRCX LULU MAR MARA MCHP MDB MDLN MDLZ MELI META MNST MPWR MRNA MRVL MSFT",
      "MSTR MU NBIS NDAQ NDSN NFLX NTAP NTRA NTRS NVDA NWS NWSA NXPI ODFL OKTA ON ORLY PANW PAYX PCAR PDD PEP PFG PLTR",
      "PODD PTC PYPL QBTS QCOM REG REGN RGTI RIOT RIVN RKLB ROP ROST SBAC SBUX SHOP SKHY SMCI SNDK SNPS SNY SOFI SPCX STLD",
      "STX SWKS TEAM TECH TEM TER TMUS TRI TRMB TROW TSCO TSLA TTD TTWO TXN UAL ULTA VRSK VRSN VRTX VTRS WDAY WDC WMT WTW",
      "WYNN XEL ZBRA ZS",
    ].join(' '),
    CBOE: [
      "CBOE",
    ].join(' '),
  };
  const tradingViewExchange=Object.entries(tradingViewListings).find(([,tickers])=>tickers.split(' ').includes(symbol))?.[0];
  const tradingViewSymbol=(tradingViewExchange?tradingViewExchange+':':'')+symbol.replace(/-/g,'.');
  const tradingViewURL='https://tw.tradingview.com/chart/7BRksICf/?symbol='+encodeURIComponent(tradingViewSymbol);
  const priceSeries=r.history.map(p=>({date:p.date,value:p.close}));
  const benchmarkSeries=r.history.map(p=>({date:p.date,value:p.benchmark}));
  const chart=comparisonChart([{name:symbol,points:priceSeries},{name:'SPY',points:benchmarkSeries}],{height:300,width:850});
  $('#detail-content').innerHTML=`<div class="detail-heading"><div><h2>${esc(symbol)}<button class="watch-button detail-watch ${state.watched.has(symbol)?'watched':''}" data-watch="${esc(symbol)}" aria-label="${state.watched.has(symbol)?'移除自選':'加入自選'} ${esc(symbol)}" aria-pressed="${state.watched.has(symbol)}" title="加入或移除 02 自選清單">${state.watched.has(symbol)?'★':'☆'}</button><span>${esc(r.name)}</span></h2><p>${esc(r.sectorName)} · ${esc(r.sector)} · ${intraday?'盤中 60m '+(r.snapshotAt?esc(hkTime(r.snapshotAt))+' HKT':'缺少同步 K 線'):'收市 '+esc(r.asOf||'—')}</p><p class="detail-market-cap" title="${esc(marketCapTitle(r))}">市值 <b>${formatMarketCap(r.marketCap)}</b> USD${r.marketCapStatus==='stale'?' · 舊值':''}<small>${esc(marketCapTitle(r))}</small></p></div><div><strong>${number(r.price)}</strong><span>USD</span></div></div><div class="detail-metrics equity-detail-metrics"><div><span>LokiRS 綜合分數</span><b class="${cls(r.score)}">${signed(r.score)}</b></div><div><span>1D 超額</span><b class="${cls(r.d1)}">${percent(r.d1)}</b></div><div><span>3D 超額</span><b class="${cls(r.d3)}">${percent(r.d3)}</b></div><div><span>一週超額</span><b class="${cls(r.week?.value)}">${percent(r.week?.value)}</b></div><div><span>兩周超額</span><b class="${cls(r.fortnight?.value)}">${percent(r.fortnight?.value)}</b></div><div><span>一月超額</span><b class="${cls(r.month?.value)}">${percent(r.month?.value)}</b></div></div><div class="detail-chart">${chart}</div><div class="detail-meta">${intraday?`<p>完整 60m K 線：${esc(hkTime(state.data.meta.snapshotBarStart))}–${esc(hkTime(state.data.meta.snapshotAt))} HKT。所有盤中回報均截至此時點；1D 基準為 ${esc(state.data.meta.dailyBaselineDate)} 收市。</p><p>Δ 對比 ${esc(state.data.meta.referenceCloseDate||'未提供')} 收市排名。長線 RS／持續日數沿用 ${esc(r.closedMetricsAsOf||'未提供')} 收市值。${esc(r.intradayNote||'')}</p>`:`<p>小時線時點：${r.intra.asOf?esc(hkTime(r.intra.asOf))+' HKT':'無完整同步數據'}。日線超額和小時線超額使用各自時點。</p>`}${r.dailyCloseReconstructed?'<p class="panel-footnote">收市重建：日線缺值，使用完整小時線核對的同日收市資料；來源詳見 CSV。</p>':''}${r.dividendBackfill?`<p class="panel-footnote">${r.dividendBackfill.sourceStatus==='provisional'?'暫定派息補正（存託銀行未定案）':'派息補正'}：${number(r.dividendBackfill.amountUSD,6)} USD／股；除淨日 ${esc(r.dividendBackfill.exDate)}。來源網址記錄於 CSV。</p>`:''}<p>1H／4H K 線格數的實際跨度：${number(r.intra.h1ElapsedHours,1)}／${number(r.intra.h4ElapsedHours,1)} 小時。<br>精確時鐘 1H 超額：${percent(r.intra.clockH1)}；精確時鐘 4H 超額：${percent(r.intra.clockH4)}。</p><p>3D：${esc(tradingPeriodTitle(r.d3From,state.data.asOf))}<br>一週：${esc(periodTitle(r.week))}<br>兩周：${esc(periodTitle(r.fortnight))}<br>一個月：${esc(periodTitle(r.month))}</p><p>超額 = 個股同期回報 − SPY 同期回報；以 % 顯示回報差（百分點），正數表示跑贏 SPY，負數表示跑輸。</p></div><div class="dialog-bottom"><button class="button" data-add-compare="${esc(symbol)}">＋ 加入走勢比較</button><div class="detail-source-links"><a class="external-link" target="_blank" rel="noopener noreferrer" href="https://finance.yahoo.com/quote/${encodeURIComponent(symbol)}/">Yahoo Finance ↗</a><a class="external-link" target="_blank" rel="noopener noreferrer" href="${esc(tradingViewURL)}" title="在 TradingView 查看 ${esc(tradingViewSymbol)}" aria-label="在 TradingView 查看 ${esc(symbol)}（新分頁）">TradingView ↗</a></div></div>`;
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
  const sentiment=sentimentPanel.data||d.sentiment;
  $('#method-status').innerHTML=`<table class="method-status-table"><tbody><tr><td>${d.meta.snapshotMode==='intraday'?'盤中 60m':'日線資料'}</td><td>${esc(d.asOf)} · ${d.meta.currentCount}/${d.meta.universeCount} 隻</td></tr><tr><td>1H 資料覆蓋</td><td>${d.meta.intradayCount} 隻（各列另附時點）</td></tr><tr><td>板塊計分覆蓋</td><td>${d.sectors.filter(r=>Number.isFinite(r.score)).length}/${d.sectors.length} 項；缺值：${esc(d.sectors.filter(r=>!Number.isFinite(r.score)).map(r=>r.symbol).join('、')||'無')}</td></tr><tr><td>暫定派息補正</td><td>${d.meta.provisionalDividendCount||0} 隻；存託銀行金額未定案，保留標記。</td></tr><tr><td>CNN 恐懼貪婪</td><td>${sentiment&&['ok','stale'].includes(sentiment.status)?esc(sentiment.source)+' · '+esc(sentiment.observationDate||sentiment.asOf?.slice(0,10)||'—')+(sentiment.status==='stale'?' · 舊值':''):'未取得，保留缺值'}</td></tr><tr><td>合約名單</td><td>${d.contracts.status==='ok'?'已取得':'未取得，停用篩選'}</td></tr><tr><td>下載失敗請求</td><td>${d.meta.errors.length} 筆（日線／小時線獨立計數）</td></tr><tr><td>FRED 更新</td><td>${d.meta.macroUpdateStatus==='retained'?'保留原有資料及日期':d.meta.macroError?'失敗，顯示舊值或缺值':'成功，使用各列觀測日期'}</td></tr></tbody></table>`;
  const weights=d.meta.scoreWeights;
  if(weights)$('#score-formula').textContent=Object.entries(weights).map(([p,w])=>`${w} × 超額 ${p==='h1'?'1H':p==='h4'?'4H':p+'D'}`).join(' + ');
  const long=d.meta.longTermWeights;
  if(long)$('#long-formula').textContent='長線值 = '+Object.entries(long).map(([p,w])=>`${w} × 超額 ${p}D`).join(' + ');
}
function exportCSV() {
  const headings=['rank','symbol','name','asOf','status','daily_close_reconstructed','daily_close_source_time','daily_close_source','dividend_backfill_amount_usd','dividend_backfill_ex_date','dividend_backfill_source','dividend_source_status','price_USD','market_cap_USD','market_cap_currency','market_cap_status','market_cap_asOf','market_cap_fetchedAt','market_cap_source','LokiRS_score','rank_delta','1h_excess_pct','4h_excess_pct','1d_excess_pct','3d_excess_pct','week_excess_pct','fortnight_excess_pct','month_excess_pct','3d_from','week_from','fortnight_from','month_from','streak_approx','long_RS_percentile_approx','sector','sector_rank_approx','vs_sector_approx','vs_sector_1d_pct','intraday_asOf','h1_elapsed_hours','h4_elapsed_hours','exact_clock_1h_excess_pct','exact_clock_4h_excess_pct','snapshot_mode','snapshot_at','snapshot_bar_start','daily_baseline_date','closed_metrics_asOf','intraday_note'];
  const rows=filteredRows().map(r=>[r.rank,r.symbol,r.name,r.asOf,r.status,!!r.dailyCloseReconstructed,r.dailyCloseSourceTime,r.dailyCloseSource,r.dividendBackfill?.amountUSD,r.dividendBackfill?.exDate,r.dividendBackfill?.source,r.dividendBackfill?.sourceStatus,r.price,r.marketCap,r.marketCapCurrency,r.marketCapStatus,r.marketCapAsOf,r.marketCapFetchedAt,r.marketCapSource,r.score,r.rankDelta,r.intra.h1,r.intra.h4,r.d1,r.d3,r.week?.value,r.fortnight?.value,r.month?.value,r.d3From,r.week?.from,r.fortnight?.from,r.month?.from,r.streak,r.longRS,r.sector,r.sectorRank,r.vsSector,r.vsSectorDay,r.intra.asOf,r.intra.h1ElapsedHours,r.intra.h4ElapsedHours,r.intra.clockH1,r.intra.clockH4,state.data.meta?.snapshotMode||'close',r.snapshotAt,r.snapshotBarStart,state.data.meta?.dailyBaselineDate,r.closedMetricsAsOf,r.intradayNote]);
  const quote=v=>{let value=String(v??'');if(typeof v==='string'&&/^[=+\-@]/.test(value))value="'"+value;return '"'+value.replaceAll('"','""')+'"';};
  download('\ufeff'+[headings,...rows].map(r=>r.map(quote).join(',')).join('\r\n'),`lokirs-${state.data.meta?.snapshotMode==='intraday'?'intraday-60m-':''}${state.data.asOf}.csv`,'text/csv;charset=utf-8');
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
  if(target.dataset.dashboardSector)toggleDashboardSector(target.dataset.dashboardSector);
  if(target.dataset.dashboardSort)sortDashboard(target.dataset.dashboardSort);
  if(target.dataset.jump)rankingUI.jumpTo(target.dataset.jump);
  if(target.dataset.view)switchView(target.dataset.view);
  if(target.dataset.snapshotMode)switchSnapshot(target.dataset.snapshotMode);
  if(target.dataset.sectorTop!==undefined){state.sectorTop=Number(target.dataset.sectorTop);state.page=1;$$('[data-sector-top]').forEach(b=>{const selected=b===target;b.classList.toggle('selected',selected);b.setAttribute('aria-pressed',selected);});renderTable();}
  if(target.hasAttribute('data-close-dialog'))target.closest('dialog').close();
  if(target.dataset.addCompare){addCompare(target.dataset.addCompare);if(target.closest('#detail-dialog')){$('#detail-dialog').close();switchView('compare');}}
  if(target.dataset.removeCompare){state.compare=state.compare.filter(s=>s!==target.dataset.removeCompare);storage.set('compare',state.compare);renderComparison();}
});
['method-open','footer-method'].forEach(id=>$('#'+id).addEventListener('click',()=>$('#method-dialog').showModal()));
$$('dialog').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
$('#theme-toggle').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'reading':'dark'));
$('#refresh').addEventListener('click',()=>state.view==='home'?home.load(true):Promise.allSettled([loadData(true),sentimentPanel.load(true)]));
$('#snapshot-check').addEventListener('click',()=>loadData(true));
$('#stocks-auto').addEventListener('click',()=>{state.auto=!state.auto;storage.set('stocks-auto',state.auto);renderHeader();});
$('#overview-toggle').addEventListener('click',()=>{const expanded=$('#overview-toggle').getAttribute('aria-expanded')==='true';$('#overview-grid').hidden=expanded;$('#overview-toggle').setAttribute('aria-expanded',!expanded);$('#overview-toggle').textContent=expanded?'展開 ＋':'收起 −';});
$('#search').addEventListener('input',event=>{state.search=event.target.value.trim();state.exactSymbol=null;state.page=1;renderTable();});
[['sector-filter','sector'],['metric-filter','metric'],['operator-filter','operator'],['value-filter','value']].forEach(([id,key])=>$('#'+id).addEventListener(id==='value-filter'?'input':'change',event=>{state[key]=event.target.value;updateMetricControl();state.page=1;renderTable();}));
$('#cap-unit-filter').addEventListener('change',event=>{state.capUnit=Number(event.target.value);state.page=1;renderTable();});
$('#ranking-dashboard-toggle').addEventListener('click',()=>{
  const expanded=$('#ranking-dashboard-toggle').getAttribute('aria-expanded')==='true';
  $('#ranking-dashboard-content').hidden=expanded;
  $('#ranking-dashboard-toggle').setAttribute('aria-expanded',String(!expanded));
  $('#ranking-dashboard-toggle').textContent=expanded?'展開 ＋':'收起 −';
});
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
const sentimentPanel=createSentiment({document,fetch:window.fetch.bind(window),toast,onUpdate:()=>{if(state.data)renderMethodStatus();}});
const home=createHome({document,window,fetch:window.fetch.bind(window),download,toast,getView:()=>state.view,
  onView:view=>switchView(view),onCompare:symbol=>{addCompare(symbol);switchView('compare');},
  onStock:symbol=>{switchView('stocks');resetFilters();state.search=symbol;state.exactSymbol=symbol;state.page=1;$('#search').value=symbol;renderTable();$('#rankings').scrollIntoView({behavior:'smooth',block:'start'});},
  onUpdate:()=>{renderHeader();renderComparison();}});
createAutoRefresh({window,document,enabled:()=>state.auto,active:()=>state.view!=='home',
  load:()=>Promise.allSettled([loadData(),sentimentPanel.load()])});
window.addEventListener('popstate',()=>switchView(readView(),false));
const initialSymbol=new URLSearchParams(location.search).get('s');
if(initialSymbol){state.search=initialSymbol.replace(/^LB:/,'').replace(/\.US$/,'');state.exactSymbol=state.search;$('#search').value=state.search;}
switchView(state.view,false);
loadData();home.load();sentimentPanel.load();
