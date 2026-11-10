import {escapeHTML as esc} from './charts.js?v=1.2.0';

const finite=Number.isFinite;
const number=(value,digits=1)=>finite(value)?value.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits}):'—';
const signed=value=>finite(value)?(value>0?'+':'')+number(value,2):'—';
const tone=value=>finite(value)?value>0?'positive':value<0?'negative':'muted':'muted';

export function formatMarketCap(value) {
  if(!finite(value)||value<=0)return '—';
  const [scale,suffix]=value>=1e9?[1e9,'B']:value>=1e6?[1e6,'M']:value>=1e3?[1e3,'K']:[1,''];
  return number(value/scale,2)+suffix;
}

export function marketCapTitle(row) {
  if(!finite(row.marketCap)||row.marketCap<=0)return '市值資料暫未取得';
  const fetched=new Date(row.marketCapFetchedAt||'');
  const fetchedLabel=finite(fetched.valueOf())?new Intl.DateTimeFormat('zh-HK',{timeZone:'Asia/Hong_Kong',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(fetched)+' HKT':null;
  const observed=row.marketCapAsOf?`來源日期 ${row.marketCapAsOf}`:fetchedLabel?`抓取 ${fetchedLabel}`:'來源時點未提供';
  return `市值 USD ${number(row.marketCap,0)}；${observed}；Nasdaq${row.marketCapStatus==='stale'?'；保留舊值':''}。市值與收市價格可能屬不同時點。`;
}

export function metricValue(row,key,resilient=false) {
  if(['week','fortnight','month'].includes(key))return row[key]?.value;
  if(['h1','h4'].includes(key))return row.intra?.[key];
  if(key==='marketCap')return finite(row.marketCap)&&row.marketCap>0?row.marketCap:null;
  return key==='vsSector'&&resilient?row.vsSectorDay:row[key];
}

export function filterRankings(rows,state,contractSymbols=[]) {
  const raw=String(state.value??'').trim();
  const threshold=raw===''?null:Number(raw)*(state.metric==='marketCap'?(state.capUnit??1e9):1);
  const contracts=new Set(contractSymbols), search=(state.search||'').toLowerCase();
  return rows.filter(row=>{
    if(state.view==='watchlist'&&!state.watched.has(row.symbol))return false;
    if(state.exactSymbol&&row.symbol!==state.exactSymbol)return false;
    if(search&&!`${row.symbol} ${row.name} ${row.sectorName} ${row.sector}`.toLowerCase().includes(search))return false;
    if(state.sector&&row.sector!==state.sector)return false;
    if(state.sectorTop&&(!finite(row.sectorRank)||row.sectorRank>state.sectorTop))return false;
    if(state.streak&&!(row.streak>=7))return false;
    if(state.long&&!(row.longRS>=50))return false;
    if(state.perp&&!contracts.has(row.symbol))return false;
    if(finite(threshold)){
      const value=metricValue(row,state.metric,state.resilient);
      if(!finite(value)||(state.operator==='lte'?value>threshold:value<threshold))return false;
    }
    return true;
  }).sort((a,b)=>{
    const x=metricValue(a,state.sort,state.resilient),y=metricValue(b,state.sort,state.resilient);
    if(!finite(x))return finite(y)?1:a.symbol.localeCompare(b.symbol);
    if(!finite(y))return -1;
    return (x-y)*state.direction||a.symbol.localeCompare(b.symbol);
  });
}

function median(values) {
  const valid=values.filter(finite).sort((a,b)=>a-b), middle=Math.floor(valid.length/2);
  return !valid.length?null:valid.length%2?valid[middle]:(valid[middle-1]+valid[middle])/2;
}
function ratio(rows,key,predicate) {
  const valid=rows.map(row=>metricValue(row,key)).filter(finite), count=valid.filter(predicate).length;
  return {count,total:valid.length,value:valid.length?100*count/valid.length:null};
}
const periods=[['h1','1H'],['h4','4H'],['d1','1D'],['d3','3D'],['week','一週'],['fortnight','兩周'],['month','一個月']];

export function summarizeRankings(rows) {
  const groups=new Map();
  for(const row of rows){
    const key=row.sector||'unclassified';
    if(!groups.has(key))groups.set(key,{symbol:key,name:row.sectorName||'未分類',rows:[]});
    groups.get(key).rows.push(row);
  }
  const sectors=[...groups.values()].map(group=>({
    symbol:group.symbol,name:group.name,count:group.rows.length,share:rows.length?100*group.rows.length/rows.length:0,
    medians:Object.fromEntries(['score','d1','week','month'].map(key=>[key,{value:median(group.rows.map(row=>metricValue(row,key))),total:group.rows.filter(row=>finite(metricValue(row,key))).length}])),
    outperform:ratio(group.rows,'d1',value=>value>0)
  })).sort((a,b)=>b.count-a.count||a.name.localeCompare(b.name,'zh-Hant')||a.symbol.localeCompare(b.symbol));
  const scores=rows.map(row=>row.score).filter(finite);
  const bins=[
    {label:'< −5',test:value=>value< -5,tone:'negative'},
    {label:'−5 – < 0',test:value=>value>= -5&&value<0,tone:'negative'},
    {label:'0 – < 5',test:value=>value>=0&&value<5,tone:'positive'},
    {label:'5 – < 10',test:value=>value>=5&&value<10,tone:'positive'},
    {label:'≥ 10',test:value=>value>=10,tone:'positive'}
  ].map(({test,...bin})=>({...bin,count:scores.filter(test).length}));
  return {
    count:rows.length,sectors,scoreMedian:median(scores),scoreCount:scores.length,
    outperform:ratio(rows,'d1',value=>value>0),long:ratio(rows,'longRS',value=>value>=50),
    streak:ratio(rows,'streak',value=>value>=7),
    marketCapCount:rows.filter(row=>finite(row.marketCap)&&row.marketCap>0).length,
    staleMarketCapCount:rows.filter(row=>finite(row.marketCap)&&row.marketCap>0&&row.marketCapStatus==='stale').length,
    bins,periods:periods.map(([key,label])=>({key,label,...ratio(rows,key,value=>value>0)}))
  };
}

export function renderRankingDashboard(summary) {
  if(!summary.count)return '<div class="dashboard-empty"><strong>目前沒有符合條件的股票</strong><p>調整上方篩選，Dashboard 會跟隨更新。</p></div>';
  const ratioCard=(label,data,description)=>`<article class="ranking-kpi"><span>${label}</span><strong>${number(data.value)}<em>${data.total?'%':''}</em></strong><small>${data.count} / ${data.total} 隻${description?' · '+description:''}</small></article>`;
  const heat=({value,total},percent=false)=>{
    const color=value>0?'--positive':'--negative',opacity=finite(value)&&value!==0?Math.min(28,6+Math.abs(value)*2):0;
    return `<td class="dashboard-heat numeric ${tone(value)}" style="background:color-mix(in srgb,var(${color}) ${opacity}%,transparent)" title="${total} 隻有效股票的中位數">${signed(value)}${finite(value)&&percent?'%':''}</td>`;
  };
  const maxCount=Math.max(...summary.sectors.map(sector=>sector.count));
  const sectorRows=summary.sectors.map(sector=>`<tr><td class="dashboard-sector-name"><button data-dashboard-sector="${esc(sector.symbol)}" title="篩選 ${esc(sector.name)}"><strong>${esc(sector.name)}</strong><small>${esc(sector.symbol)}</small></button></td><td class="dashboard-sector-count"><div><i style="width:${100*sector.count/maxCount}%"></i><span>${sector.count} 隻 <b>${number(sector.share)}%</b></span></div></td>${heat(sector.medians.score)}${heat(sector.medians.d1,true)}${heat(sector.medians.week,true)}${heat(sector.medians.month,true)}<td class="numeric" title="${sector.outperform.count} / ${sector.outperform.total} 隻有效股票">${number(sector.outperform.value)}${sector.outperform.total?'%':''}</td></tr>`).join('');
  const maxBin=Math.max(1,...summary.bins.map(bin=>bin.count));
  return `<div class="ranking-kpis"><article class="ranking-kpi"><span>綜合分數中位數</span><strong class="${tone(summary.scoreMedian)}">${signed(summary.scoreMedian)}</strong><small>${summary.scoreCount} 隻有效 · 各股等權</small></article>${ratioCard('本日跑贏 SPY',summary.outperform,'1D 超額 > 0')}${ratioCard('長線強勢佔比',summary.long,'長線 RS ≥ 50')}${ratioCard('持續領先佔比',summary.streak,'持續 ≥ 7 日')}</div>
  <article class="ranking-chart-panel"><div class="ranking-chart-heading"><div><h3>板塊分佈與強弱</h3><p>長條比較股票數；熱圖比較板塊內股票中位數，點板塊名稱可篩選。</p></div><span>${summary.sectors.length} 個板塊</span></div><div class="dashboard-table-scroll" tabindex="0" role="region" aria-label="板塊分佈與強弱，可上下及水平捲動"><table id="dashboard-sector-table"><thead><tr><th scope="col">板塊</th><th scope="col">股票數 / 佔比</th><th scope="col">LokiRS 中位數</th><th scope="col">1D 超額</th><th scope="col">一週超額</th><th scope="col">一月超額</th><th scope="col">1D 跑贏比例</th></tr></thead><tbody>${sectorRows}</tbody></table></div><p class="ranking-chart-note"><span class="positive">■ 正值</span> <span class="negative">■ 負值</span> · 佔比以全部 ${summary.count} 隻篩選結果計算；各指標剔除缺值，非板塊 ETF 回報。完整板塊列表可捲動查看。</p></article>
  <div class="ranking-charts-bottom"><article class="ranking-chart-panel"><div class="ranking-chart-heading"><div><h3>綜合分數分佈</h3><p>觀察強弱集中程度與極端分數</p></div><span>${summary.scoreCount} 隻有效</span></div><div class="score-histogram" role="img" aria-label="綜合分數分佈：${summary.bins.map(bin=>esc(bin.label)+' 分 '+bin.count+' 隻').join('；')}">${summary.bins.map(bin=>`<div class="histogram-bin"><strong>${bin.count}<small>隻</small></strong><div class="histogram-track"><i class="${bin.tone}" style="height:${100*bin.count/maxBin}%"></i></div><span>${esc(bin.label)}</span></div>`).join('')}</div><p class="ranking-chart-note">固定分數區間 · 缺值 ${summary.count-summary.scoreCount} 隻；0 分屬打和。</p></article>
  <article class="ranking-chart-panel"><div class="ranking-chart-heading"><div><h3>各時段跑贏 SPY 比例</h3><p>由短線到中線，觀察強勢是否延續</p></div></div><div class="period-breadth">${summary.periods.map(period=>`<div class="period-breadth-row"><span>${period.label}</span><div class="period-breadth-track"><i style="width:${period.value??0}%"></i></div><strong>${number(period.value)}${period.total?'%':''}</strong><small>${period.count} / ${period.total}</small></div>`).join('')}</div><p class="ranking-chart-note">超額 > 0 才計跑贏；各時段分母只計有效數據。</p></article></div><p class="ranking-dashboard-footnote">市值有值 ${summary.marketCapCount} / ${summary.count} 隻${summary.staleMarketCapCount?'，其中 '+summary.staleMarketCapCount+' 隻保留舊值':''} · K = 千、M = 百萬、B = 十億 USD；市值時點詳見欄位提示及個股詳情。</p>`;
}
