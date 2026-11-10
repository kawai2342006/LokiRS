import {formatMarketCap,metricValue} from './rankings.js?v=1.5.2';

const finite=Number.isFinite;
const number=(value,digits=2)=>finite(value)?value.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits}):'—';
const signed=value=>finite(value)?(value>0?'+':'')+number(value):'—';
const percent=value=>finite(value)?signed(value)+'%':'—';
const nameLimit=176;
const percentageColumns=new Set([6,7,8,9,10,11,12,16]);
const centralPercentages=[6,7,8,9,10,11,12];

// Some browsers return an empty `font` shorthand for variable-font styles.
// Compose the canvas font from the actual longhand properties instead.
export function canvasFontFromStyle(style) {
  return `${style.fontStyle||'normal'} ${style.fontWeight||'400'} ${style.fontSize||'13px'} ${style.fontFamily||'monospace'}`;
}

// Measure the entire filtered cohort so paging and sorting do not move columns.
export function measureRankingColumns(rows,headers,measure,resilient=false) {
  const widths=headers.slice(0,17).map((header,index)=>Math.max(percentageColumns.has(index)?88:0,Math.ceil(measure(header,'header')+(percentageColumns.has(index)?30:22))));
  const fit=(index,text,font='number',extra=0)=>{
    const content=measure(text,font);
    const gutter=percentageColumns.has(index)?28:16;
    widths[index]=Math.max(widths[index],Math.ceil((font==='name'?Math.min(nameLimit,content):content)+gutter+extra));
  };
  for(const row of rows){
    fit(0,row.rank??'—');
    fit(1,row.rankDelta>0?'↑ '+row.rankDelta:row.rankDelta<0?'↓ '+Math.abs(row.rankDelta):row.rankDelta===0?'·':'—');
    fit(2,row.symbol,'ticker');fit(2,row.name,'name');
    fit(3,number(row.price));fit(4,formatMarketCap(row.marketCap));fit(5,signed(row.score),'number',8);
    ['h1','h4','d1','d3','week','fortnight','month'].forEach((key,index)=>fit(index+6,percent(metricValue(row,key))));
    fit(13,row.streak===null?'—':row.streakCapped?row.streak+'+':row.streak?row.streak+' 日':'·');
    fit(14,number(row.longRS,0),'number',8);
    fit(15,`${row.sectorName||''} ${row.sectorRank?'#'+row.sectorRank:'—'}`,'sector',4);
    fit(16,percent(metricValue(row,'vsSector',resilient)));
  }
  return widths;
}

export function allocateRankingWidths(contentWidths,availableWidth,sparkWidth=128) {
  const widths=contentWidths.map(width=>Math.max(1,Math.ceil(width)));
  const chart=Math.max(100,Math.min(160,Math.ceil(sparkWidth)));
  const total=widths.reduce((sum,width)=>sum+width,0)+chart;
  const surplus=Math.max(0,Math.floor(availableWidth)-total);
  const targets=centralPercentages.filter(index=>index<widths.length);
  if(targets.length){
    const extra=Math.floor(surplus/targets.length),remainder=surplus%targets.length;
    targets.forEach((index,i)=>widths[index]+=extra+(i<remainder?1:0));
  }
  return [...widths,chart];
}

export function createRankingUI({document:doc,window:win,getView,getRows,getResilient}) {
  const bookmarks=doc.querySelector('#stocks-bookmarks');
  const filter=doc.querySelector('#ranking-filters');
  const table=doc.querySelector('#stock-table');
  const region=doc.querySelector('#stock-table-region');
  const links=[...bookmarks.querySelectorAll('[data-jump]')];
  const canvas=doc.createElement('canvas'),context=canvas.getContext('2d');
  let rows=[],resilient=false,layoutFrame=0,scrollFrame=0;
  const visible=()=>['stocks','watchlist'].includes(getView())&&!doc.querySelector('#dashboard').hidden;
  const behavior=()=>win.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth';

  function updateNavigation() {
    bookmarks.hidden=getView()!=='stocks'||doc.querySelector('#dashboard').hidden;
    if(!visible())return;
    const filterRect=filter.getBoundingClientRect();
    const filterHeight=Math.ceil(filterRect.height);
    doc.documentElement.style.setProperty('--ranking-filter-height',filterHeight+'px');
    filter.classList.toggle('is-stuck',filterRect.top<=1&&filterRect.height>0);
    const line=filterRect.top<=1?filterHeight+24:32;
    let active='page-top';
    for(const id of ['overview-section','strongest-panel','rankings','stock-table-region']){
      const target=doc.getElementById(id);
      if(target&&target.getBoundingClientRect().top<=line)active=id;
    }
    links.forEach(link=>{
      const selected=link.dataset.jump===active;
      link.classList.toggle('active',selected);
      if(selected)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');
    });
  }
  function scheduleNavigation() {
    if(!scrollFrame)scrollFrame=win.requestAnimationFrame(()=>{scrollFrame=0;updateNavigation();});
  }
  function resizeTable() {
    if(!visible()||!region.clientWidth)return;
    if(getRows)rows=getRows();
    if(getResilient)resilient=getResilient();
    const first=table.querySelector('tbody tr');
    const font=selector=>canvasFontFromStyle(win.getComputedStyle(first?.querySelector(selector)||table));
    const fonts={number:font('.numeric'),name:font('.asset-name'),ticker:font('.stock-link'),sector:font('.sector-cell'),header:canvasFontFromStyle(win.getComputedStyle(table.querySelector('th button')))};
    const measure=(value,type)=>{
      if(!context)return String(value??'').length*(type==='name'?6:8);
      context.font=fonts[type];return context.measureText(String(value??'')).width;
    };
    const headers=[...table.querySelectorAll('thead th')].map(th=>(th.querySelector('button')||th).textContent.trim().replace(/\s+/g,' '));
    const content=measureRankingColumns(rows,headers,measure,resilient);
    const widths=allocateRankingWidths(content,region.clientWidth-2);
    const columns=[...table.querySelectorAll('colgroup col')];
    columns.forEach((column,index)=>column.style.width=widths[index]+'px');
    table.style.width=widths.reduce((sum,width)=>sum+width,0)+'px';
    table.querySelectorAll('.spark-col svg').forEach(svg=>svg.setAttribute('preserveAspectRatio','none'));
    updateNavigation();
  }
  function scheduleLayout() {
    if(!layoutFrame)layoutFrame=win.requestAnimationFrame(()=>{layoutFrame=0;resizeTable();});
  }
  function jumpTo(id) {
    if(id==='page-top'){win.scrollTo({top:0,behavior:behavior()});return;}
    const target=doc.getElementById(id);if(!target)return;
    const offset=id==='stock-table-region'?Math.ceil(filter.getBoundingClientRect().height)+12:12;
    if(id==='stock-table-region')region.scrollTop=0;
    win.scrollTo({top:Math.max(0,target.getBoundingClientRect().top+win.scrollY-offset),behavior:behavior()});
    target.focus({preventScroll:true});
  }
  win.addEventListener('scroll',scheduleNavigation,{passive:true});
  win.addEventListener('resize',scheduleLayout);
  const observer=win.ResizeObserver?new win.ResizeObserver(scheduleLayout):null;
  observer?.observe(region);observer?.observe(filter);
  const mutations=win.MutationObserver?new win.MutationObserver(scheduleLayout):null;
  mutations?.observe(table.querySelector('tbody'),{childList:true});
  doc.fonts?.ready.then(scheduleLayout);
  return {
    jumpTo,
    refresh(){updateNavigation();scheduleLayout();},
    syncRows(nextRows,useDay=false){rows=nextRows;resilient=useDay;scheduleLayout();},
    dispose(){win.removeEventListener('scroll',scheduleNavigation);win.removeEventListener('resize',scheduleLayout);observer?.disconnect();mutations?.disconnect();if(layoutFrame)win.cancelAnimationFrame(layoutFrame);if(scrollFrame)win.cancelAnimationFrame(scrollFrame);}
  };
}
