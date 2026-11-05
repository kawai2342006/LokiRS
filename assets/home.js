import {sparkline, comparisonChart, escapeHTML as esc} from './charts.js?v=1.2.0';

export function createHome(options) {
  const doc=options.document, win=options.window, root=doc.querySelector('#home-section');
  const groups={equity:'美股指數',region:'地區市場',sector:'產業板塊',bond:'債券',fx:'外匯',commodity:'商品及相關 ETF',crypto:'加密貨幣'};
  const state={data:null,search:'',group:'',sort:'score',direction:-1,loading:false,auto:read('auto',true),expandedPulse:false};
  const $=selector=>root.querySelector(selector);
  const finite=Number.isFinite;
  const number=(v,n=2)=>finite(v)?v.toLocaleString('en-US',{minimumFractionDigits:n,maximumFractionDigits:n}):'—';
  const signed=(v,n=2)=>finite(v)?(v>0?'+':'')+number(v,n):'—';
  const pp=v=>finite(v)?signed(v)+'%':'—';
  const cls=v=>finite(v)?v>0?'positive':v<0?'negative':'':'muted';
  const stamp=value=>{if(!value)return '日期未提供';if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;try{return new Intl.DateTimeFormat('zh-HK',{timeZone:'Asia/Hong_Kong',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(value))+' HKT';}catch{return '日期未提供';}};
  function read(key,fallback){try{return JSON.parse(win.localStorage.getItem('lokirs:home:'+key))??fallback;}catch{return fallback;}}
  function save(key,value){try{win.localStorage.setItem('lokirs:home:'+key,JSON.stringify(value));}catch{/* storage unavailable */}}
  const open=key=>read(key,true)?' open':'';
  const safeURL=url=>{try{const parsed=new URL(url);return parsed.protocol==='https:'?parsed.href:'#';}catch{return '#';}};
  const source=(row,label)=>safeURL(row?.url)==='#'?`<span class="home-source">${esc(label||row?.source||'來源')}</span>`:`<a class="home-source" href="${esc(safeURL(row?.url))}" target="_blank" rel="noopener">${esc(label||row?.source||'來源')} ↗</a>`;
  const status=row=>row?.status==='stale'?'<span class="home-stale">舊值／快照</span>':row?.status==='unavailable'?'<span class="home-stale">暫未取得</span>':'';

  function render() {
    const d=state.data;if(!d)return;
    root.innerHTML=`<div class="home-toolbar"><div class="home-index"><a href="#home-brief">今日重點</a><a href="#home-pulse">市場異動</a><a href="#home-flows">資金流</a><a href="#cross-market-rankings">跨市場排名 ↓</a></div><button class="button quiet home-auto" id="home-auto" aria-pressed="${state.auto}" title="每 60 秒檢查已發布快照；抓價由 GitHub 更新流程執行">${state.auto?'自動檢查 60s':'自動檢查已暫停'}</button></div>
      <div class="home-tiles" aria-label="六項市場快照">${d.tiles.map(tile=>`<button class="panel home-tile" data-home-market="${esc(tile.symbol)}" aria-label="查看 ${esc(tile.name)}"><span class="home-tile-label">${esc(tile.name)} <b>${esc(tile.symbol)}</b></span><strong class="numeric" title="${tile.dailyCloseReconstructed?'日線缺值，使用同日已完成小時線收市價。':'日線收市價'}">${number(tile.price,tile.symbol==='BTC'?0:2)}</strong><div class="home-tile-returns"><span>1D <b class="${cls(tile.returns['1'])}">${pp(tile.returns['1'])}</b></span><span>5D <b class="${cls(tile.returns['5'])}">${pp(tile.returns['5'])}</b></span></div><span class="home-tile-chart">${sparkline(tile.history,{width:180,height:27})}</span><small>${esc(tile.asOf||'缺資料')} / ${esc(tile.currency||'—')}${tile.session==='utc24h'?' · UTC 日線':''}</small></button>`).join('')}</div>
      <details class="home-block" id="home-brief" data-home-fold="brief"${open('brief')}><summary class="home-block-title"><span><span class="panel-code">DISPATCH / 01</span><h2>今日行情重點</h2></span><span class="home-summary-extra">規則生成 <i>−</i></span></summary><div class="home-block-body" id="home-brief-content"></div></details>
      <details class="home-block" id="home-pulse" data-home-fold="pulse"${open('pulse')}><summary class="home-block-title"><span><span class="panel-code">VARIANT WATCH / 02</span><h2>RS Pulse <span class="home-title-aside">市場異動</span></h2></span><span class="home-summary-extra">美股 ${d.pulse.universeCount} 隻 <i>−</i></span></summary><div class="home-block-body"><div id="home-pulse-content"></div><p class="panel-footnote">目前掃描現有美股股票池，日期 ${esc(d.pulse.asOf||'—')}。排名及門檻由 LokiRS 重算。</p></div></details>
      <details class="home-block" id="home-flows" data-home-fold="flows"${open('flows')}><summary class="home-block-title"><span><span class="panel-code">CAPITAL FLOW / 03</span><h2>資金流資料</h2></span><span class="home-summary-extra">穩定幣 · BTC · 南向 <i>−</i></span></summary><div class="home-block-body" id="home-flows-content"></div></details>
      <section class="home-matrix" id="cross-market-rankings"><div class="section-heading"><div><span class="section-number">04</span><h2>跨市場資金流向</h2></div><button class="button quiet" id="home-export">↓ 匯出 CSV</button></div><div class="home-matrix-intro"><span class="file-tab">vs 32 項資產中位數</span><p>比較相同起訖日期的表現差距。跨市場收市時間不同，排名反映相對動能。${d.meta.reconstructedDailyCount?`其中 ${d.meta.reconstructedDailyCount} 項使用已完成小時線重建收市。`:''}</p></div><div class="home-matrix-controls"><label class="search-box"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4 4"/></svg><input id="home-search" type="search" value="${esc(state.search)}" placeholder="搜尋市場、代號…" aria-label="搜尋跨市場資產"><kbd>/</kbd></label><select id="home-group" aria-label="跨市場分類"><option value="">全部市場</option>${Object.entries(groups).map(([key,label])=>`<option value="${key}"${state.group===key?' selected':''}>${label}</option>`).join('')}</select><span class="home-result-count" id="home-result-count"></span></div><div class="table-hint"><span>點欄名排序 · 點代號查看走勢 · 複製 TradingView 代號</span><span>超額單位：百分點（pp） · Δ5D：五個交易日的名次差</span></div><div class="table-scroll home-table-scroll" role="region" tabindex="0" aria-label="可捲動的跨市場排名"><table id="home-table"><thead><tr>${[['rank','#'],['rankDelta5d','Δ5D']].map(([key,label])=>`<th data-home-sort="${key}"><button>${label} <span>↕</span></button></th>`).join('')}<th class="asset-col">市場 / 資產</th>${[['score','LokiRS'],['1','1D'],['5','5D'],['20','20D'],['60','60D']].map(([key,label])=>`<th data-home-sort="${key}" title="${key==='score'?'公開替代公式，並非原站 LazyRS 分數':'相同日期回報減去當期有效資產中位數'}"><button>${label} <span>↕</span></button><span class="column-sub">${key==='score'?'近似綜合分數':'超額'}</span></th>`).join('')}<th class="spark-col">RS 線<span class="column-sub">21 個 SPY 交易日</span></th></tr></thead><tbody id="home-market-body"></tbody></table></div><div id="home-no-results" class="empty-state" hidden><h3>沒有符合條件的市場</h3><p>試試其他名稱或清除分類。</p><button class="button" id="home-reset">重設篩選</button></div><p class="panel-footnote">跨市場資料 ${esc(d.asOf)} · 有效 ${d.meta.currentCount}/${d.meta.universeCount}。各時段樣本數：1D ${d.sampleCounts['1']} · 5D ${d.sampleCounts['5']} · 20D ${d.sampleCounts['20']} · 60D ${d.sampleCounts['60']}。</p></section>
      <div class="home-reading-grid"><section class="home-reading"><div class="section-heading"><div><span class="section-number">05</span><h2>市場閱讀檔案</h2></div>${source(d.articles,'Lazybeanz 原文')}</div><p class="home-reading-note">外部作者文章 · ${d.articles.status==='ok'?'公開 RSS':'標題快照，來源暫未更新'}</p><div class="home-articles">${(d.articles.items||[]).map((a,i)=>`<a href="${esc(safeURL(a.url))}" target="_blank" rel="noopener"><span class="home-article-index">${String(i+1).padStart(2,'0')}</span><span><strong>${esc(a.title)}</strong><small>${esc(a.date)} / SUBSTACK</small></span><span class="home-article-arrow">↗</span></a>`).join('')||'<p class="unavailable-note">文章來源暫未提供，請到原作者網站閱讀。</p>'}</div></section><section class="home-faq"><div class="section-heading"><div><span class="section-number">06</span><h2>情報使用說明</h2></div></div><details open><summary>LokiRS 主頁應該點睇？</summary><p>先看市場寬度及波動，再觀察跨市場排名與五日輪動；想研究個股，可由異動卡進入美股排名。</p></details><details><summary>RS 同 RSI 有咩分別？</summary><p>RS 比較資產與基準的回報差距；RSI 量度單一資產自身的升跌速度，兩者用途不同。</p></details><details><summary>「資金流向」係真實成交資金嗎？</summary><p>跨市場表以相對表現呈現輪動，並非資金淨流入的直接量度。南向欄才是買入減賣出的成交數據；穩定幣欄反映供應變化。</p></details><details><summary>分數同原站會完全一樣嗎？</summary><p>原站完整權重未公開核實。LokiRS 使用可查核的獨立公式、32 項資產池及日線錨點；來源、時點和公式差異都可能影響名次。</p></details><details><summary>網站會幾耐更新？</summary><p>自動檢查每 60 秒重讀已發布快照。真正抓價由 Python／GitHub Actions 執行，預設每天一次；每項資料保留自己的觀測日期。</p></details><button class="button home-stock-cta" data-home-view="stocks">進入全部美股排名 <span>→</span></button></section></div>
      <details class="home-rules"><summary>公開公式、時段及資料來源</summary><div><p><strong>主頁分數：</strong>${Object.entries(d.meta.scoreWeights).map(([p,w])=>`${w} × 超額 ${p}D`).join(' + ')}。超額 = 資產回報 − 當期有效資產回報中位數；至少 80% 有效樣本才計算。</p><p>1D／5D／20D／60D 的共同起日：${Object.entries(d.periodFrom).map(([p,date])=>`${p}D ${date}`).join(' · ')}；終日 ${d.asOf}。缺相同起訖資料不填補。Δ5D 對照 ${d.previousRankDate}，固定使用目前 32 項資產。</p><p>報價採原貨幣，回報以 Yahoo 股息及拆股調整日線計算。香港、外匯與加密收市時間不同。日線缺值時，只有完整同日小時線及價格調整紀錄可核對，才重建收市價並另列標示。行情卡各用自己的收市資料；BTC 卡採 UTC 日。RS 線以每日中位數回報建立參考指數，再計價格比值。</p><p>資料來源：Yahoo Finance、CBOE VIX、CoinGecko、DefiLlama、HKEX。文章只保留原作者公開標題與連結。原站會員項目不在本頁範圍。</p></div></details>`;
    renderBrief();renderPulse();renderFlows();renderMatrix();
    const formula=doc.querySelector('#home-score-formula');if(formula)formula.textContent='主頁 LokiRS = '+Object.entries(d.meta.scoreWeights).map(([p,w])=>`${w} × 超額 ${p}D`).join(' + ');
  }

  function renderBrief() {
    const d=state.data, current=d.breadth.at(-1), prev=d.breadth.at(-2);
    const breadth=current?.above20?.value, long=current?.above50?.value;
    const delta=finite(breadth)&&finite(prev?.above20?.value)?breadth-prev.above20.value:null;
    const vix=d.vix, crypto=d.crypto;
    const synchronized=finite(breadth)&&finite(vix.value)&&d.stockAsOf===vix.asOf;
    const score=synchronized?(breadth>=60?1:breadth<=40?-1:0)+(vix.value<=15?1:vix.value>=25?-1:0):null;
    const regime=score===null?'資料未同步':score>0?'偏 risk-on':score<0?'偏 risk-off':'訊號中性';
    const valid=d.rows.filter(r=>finite(r.score)), best=valid[0], worst=valid.at(-1);
    const rotating=[...valid].filter(r=>finite(r.rankDelta5d));
    const incoming=rotating.sort((a,b)=>b.rankDelta5d-a.rankDelta5d)[0];
    const outgoing=[...rotating].sort((a,b)=>a.rankDelta5d-b.rankDelta5d)[0];
    $('#home-brief-content').innerHTML=`<div class="home-regime"><span class="home-regime-badge ${score>0?'positive':score<0?'negative':''}" title="寬度 ≥60% 加一分，≤40% 減一分；VIX ≤15 加一分，≥25 減一分。只在兩者交易日相同時計算。">${regime}</span><span>美股寬度 ${!finite(breadth)?'未取得':breadth>=70?'偏強':breadth<=30?'偏弱':'中性'} · VIX ${!finite(vix.value)?'缺資料':vix.value>=25?'偏高':vix.value<=15?'偏低':'中性'} · 最強 ${esc(best?.name||'—')} · 最弱 ${esc(worst?.name||'—')}</span></div><div class="home-brief-grid">
      <button class="home-brief-card" data-home-view="stocks" title="20 日均線上比例：≥70% 偏強，≤30% 偏弱；目前美股股票池"><span class="home-card-label">美股寬度 <i>↗</i></span><strong class="numeric">${number(breadth,0)}<em>%</em></strong><p>${!finite(breadth)?'來源暫未提供':breadth>=70?'多數個股站上短期均線':breadth<=30?'短期均線下的個股佔多':'升跌股分化，觀察個股強弱'}</p><small>20MA · 1D <b class="${cls(delta)}">${signed(delta,1)}pp</b><br>50MA ${number(long,0)}% · ${esc(d.stockAsOf||'—')}</small></button>
      <div class="home-brief-card"><span class="home-card-label">VIX 恐慌指數 ${status(vix)}</span><strong class="numeric ${!finite(vix.value)?'':vix.value>=25?'negative':vix.value<=15?'positive':''}">${number(vix.value,1)}</strong><p>${!finite(vix.value)?'來源暫未提供':vix.value>=25?'波動處於較高區間':vix.value<=15?'波動處於較低區間':'情緒無極端，持續觀察強弱'}</p><small>1D <b class="${cls(-vix.changeDay)}">${signed(vix.changeDay,1)} 點</b><br>20D ${number(vix.low20,1)}–${number(vix.high20,1)} · ${esc(vix.asOf||'—')}</small></div>
      <div class="home-brief-card"><span class="home-card-label">Crypto 總市值 ${status(crypto)}</span><strong class="numeric">${finite(crypto.value)?'$'+number(crypto.value/1e12,2)+'T':'—'}</strong><p>${!finite(crypto.btcDominance)?'來源暫未提供':crypto.btcDominance>=55?'BTC 市佔較高，資金集中大幣':crypto.btcDominance<50?'BTC 市佔較低，觀察其他幣種':'BTC 市佔處於中間區間'}</p><small>24h <b class="${cls(crypto.change24h)}">${pp(crypto.change24h)}</b> · BTC ${number(crypto.btcDominance,1)}%<br>${esc(stamp(crypto.asOf))}</small></div>
      <a class="home-brief-card" href="#cross-market-rankings"><span class="home-card-label">跨市場最強 <i>↓</i></span><strong class="home-brief-asset">${esc(best?.name||'—')}</strong><p>其次 ${esc(valid[1]?.name||'—')}、${esc(valid[2]?.name||'—')}</p><small>20D 超額 <b class="${cls(best?.excess['20'])}">${pp(best?.excess['20'])}</b><br>${esc(d.asOf)} · 32 項資產池</small></a>
      <a class="home-brief-card" href="#cross-market-rankings"><span class="home-card-label">5 日輪動最大 <i>↓</i></span><strong class="numeric ${cls(incoming?.rankDelta5d)}">${incoming?.rankDelta5d>=2?'↑'+incoming.rankDelta5d:'—'}</strong><p>${incoming?.rankDelta5d>=2?esc(incoming.name)+'相對轉強':'未有上升兩名的資產'}</p><small>${outgoing?.rankDelta5d<=-2?esc(outgoing.name)+' ↓'+Math.abs(outgoing.rankDelta5d)+' 名':'未有下跌兩名的資產'}<br>相比 ${esc(d.previousRankDate)}</small></a>
      </div><p class="panel-footnote">摘要以公開規則生成。相對動能與供應變化不等同實際資金淨流入；各卡保留各自時點。</p>`;
  }

  function renderPulse() {
    const pulse=state.data.pulse;
    const blocks=[['sudden','突然走強',pulse.sudden,'positive'],['leaders','持續領先',pulse.leaders,''],['weak','走弱警示',pulse.weak,'negative']];
    $('#home-pulse-content').innerHTML='<div class="home-pulse-grid">'+blocks.map(([key,label,rows,tone])=>`<article class="panel home-pulse-card"><div class="panel-code">VARIANT / ${key.toUpperCase()}</div><div class="panel-heading"><h3>${label}</h3><span class="home-pulse-count numeric ${tone}">${rows.length}</span></div><ol class="home-pulse-list">${rows.map((r,i)=>`<li${key==='sudden'&&i>=5&&!state.expandedPulse?' hidden':''}><button class="home-pulse-identity" data-home-stock="${esc(r.symbol)}"><strong>${esc(r.symbol)}</strong><small title="${esc(r.name)}">${esc(r.name)}</small></button><span class="home-pulse-measure"><b class="numeric ${key==='leaders'?'':cls(r.d1)}">${key==='leaders'?r.streak+(r.streakCapped?'+ 日':' 日'):pp(r.d1)}</b><small class="numeric">#${r.rank} · <span class="${cls(r.rankDelta)}">${r.rankDelta>0?'↑'+r.rankDelta:r.rankDelta<0?'↓'+Math.abs(r.rankDelta):'—'}</span>${key==='sudden'?' · 4H '+pp(r.h4):''}</small></span></li>`).join('')||'<li class="home-pulse-empty">本次沒有符合條件的個股。</li>'}</ol>${key==='sudden'&&rows.length>5?`<button class="text-button home-pulse-more" id="home-pulse-more" aria-expanded="${state.expandedPulse}">${state.expandedPulse?'收起 −':'再顯示 '+(rows.length-5)+' 項 +'}</button>`:''}<details class="home-pulse-rules"><summary>篩選規則</summary><p>${key==='sudden'?`名次升幅 ≥${pulse.rules.minimumRankJump}，目前名次 ≤${pulse.rules.suddenRankCutoff}，1D 與 4H 超額均為正；最多 8 項。`:key==='leaders'?`持續在美股前 20% 至少 ${pulse.rules.minimumStreak} 日，按持續日數排序；最多 5 項。`:`名次跌幅 ≥${pulse.rules.minimumRankJump}，1D 超額為負；最多 5 項。`}</p></details></article>`).join('')+'</div>';
  }

  function renderFlows() {
    const {stablecoins:stable,crypto,southbound:south}=state.data;
    $('#home-flows-content').innerHTML=`<div class="home-flow-grid"><article class="panel home-flow-card"><div class="panel-code">SUPPLY / USD STABLECOINS</div><h3>美元穩定幣流通市值</h3><div class="home-flow-value numeric">${finite(stable.value)?'$'+number(stable.value/1e9,1)+'B':'—'}</div><div class="home-flow-metrics"><span>30D <b class="numeric ${cls(stable.change30d)}">${finite(stable.change30d)?signed(stable.change30d/1e9,1)+'B':'—'}</b></span><span>7D <b class="numeric ${cls(stable.change7d)}">${finite(stable.change7d)?signed(stable.change7d/1e9,1)+'B':'—'}</b></span></div><div class="home-flow-chart">${sparkline((stable.history||[]).map(r=>r.value),{width:350,height:40})}</div><p>按已換算美元的供應計，增減不等於即時買入風險資產。</p><footer>${source(stable,'DefiLlama')}<span>${esc(stamp(stable.asOf))} ${status(stable)}</span></footer></article>
      <article class="panel home-flow-card"><div class="panel-code">DOMINANCE / BTC</div><h3>BTC 市佔率</h3><div class="home-flow-value numeric">${number(crypto.btcDominance,1)}<em>%</em></div><div class="home-dominance-track" role="img" aria-label="BTC 市佔 ${number(crypto.btcDominance,1)}%"><i style="width:${finite(crypto.btcDominance)?Math.max(0,Math.min(100,crypto.btcDominance)):0}%"></i></div><div class="home-flow-metrics"><span>BTC <b class="numeric">${number(crypto.btcDominance,1)}%</b></span><span>其他 <b class="numeric">${finite(crypto.btcDominance)?number(100-crypto.btcDominance,1)+'%':'—'}</b></span></div><p>佔整體加密市值比例，用作觀察幣圈內部集中程度。</p><footer>${source(crypto,'CoinGecko')}<span>${esc(stamp(crypto.asOf))} ${status(crypto)}</span></footer></article>
      <article class="panel home-flow-card"><div class="panel-code">STOCK CONNECT / SOUTHBOUND</div><h3>港股通南向淨買入</h3><div class="home-flow-value numeric ${cls(south.value)}">${finite(south.value)?signed(south.value/1e8,1):'—'}<em>億 HKD</em></div><div class="home-flow-metrics"><span>近 5 個交易日 <b class="numeric ${cls(south.sum5d)}">${finite(south.sum5d)?signed(south.sum5d/1e8,1)+' 億':'—'}</b></span></div><div class="home-southbound-bars">${(south.history||[]).map(r=>{const max=Math.max(...south.history.map(p=>Math.abs(p.net)),1);return `<div title="${r.date}：${signed(r.net/1e8,2)} 億 HKD"><span>${r.date.slice(5)}</span><i class="${cls(r.net)}" style="--bar-size:${Math.abs(r.net)/max*100}%"></i><b class="numeric ${cls(r.net)}">${signed(r.net/1e8,1)}</b></div>`;}).join('')}</div><p>滬港通與深港通南向買入成交額減賣出成交額。</p><footer>${source(south,'HKEX')}<span>${esc(south.asOf||'日期未提供')} ${status(south)}</span></footer></article></div>`;
  }

  function measure(row,key){return ['1','5','20','60'].includes(key)?row.excess[key]:row[key];}
  function filtered(){
    return state.data.rows.filter(r=>(!state.group||r.group===state.group)&&(!state.search||`${r.symbol} ${r.name} ${groups[r.group]}`.toLowerCase().includes(state.search.toLowerCase()))).sort((a,b)=>{
      const x=measure(a,state.sort), y=measure(b,state.sort);
      if(!finite(x))return finite(y)?1:a.symbol.localeCompare(b.symbol);
      if(!finite(y))return -1;
      return (x-y)*state.direction||a.symbol.localeCompare(b.symbol);
    });
  }
  function renderMatrix(){
    const rows=filtered();
    $('#home-market-body').innerHTML=rows.map(r=>`<tr><td class="rank-col numeric">${r.rank??'—'}</td><td class="numeric rank-delta ${cls(r.rankDelta5d)}">${r.rankDelta5d>0?'↑'+r.rankDelta5d:r.rankDelta5d<0?'↓'+Math.abs(r.rankDelta5d):r.rankDelta5d===0?'·':'—'}</td><td class="asset-col"><div class="home-market-identity"><div><button class="home-market-name" data-home-market="${esc(r.symbol)}">${esc(r.name)}</button><span class="home-market-symbol"><button data-home-market="${esc(r.symbol)}">${esc(r.symbol)}</button><small>${groups[r.group]||''}${r.status!=='ok'?' · 缺值':''}${r.dailyCloseReconstructed?' · 收市重建':''}</small></span></div><button class="home-copy" data-home-copy="${esc(r.tradingViewSymbol)}" aria-label="複製 ${esc(r.symbol)} TradingView 代號" title="複製 ${esc(r.tradingViewSymbol)}"><svg viewBox="0 0 18 18" aria-hidden="true"><path d="M6 6h9v9H6zM3 12V3h9"/></svg></button></div></td><td class="numeric score-col ${cls(r.score)}"><b>${signed(r.score)}</b></td>${['1','5','20','60'].map(p=>`<td class="numeric ${cls(r.excess[p])}" title="${esc(state.data.periodFrom[p])} → ${esc(state.data.asOf)}；樣本 ${state.data.sampleCounts[p]}">${pp(r.excess[p])}</td>`).join('')}<td class="spark-col" title="${r.rsLine.length?'最近 21 個共同交易日的相對強弱線':'最近 21 個共同交易日未齊資料，不跨休市日補值'}">${sparkline(r.rsLine,{width:110,height:29})}</td></tr>`).join('');
    $('#home-result-count').textContent=`${rows.length} / ${state.data.rows.length} 項`;
    $('#home-no-results').hidden=rows.length!==0;
    root.querySelectorAll('[data-home-sort]').forEach(th=>{const active=th.dataset.homeSort===state.sort;th.classList.toggle('sorted',active);th.setAttribute('aria-sort',active?(state.direction===1?'ascending':'descending'):'none');th.querySelector('button span').textContent=active?(state.direction===1?'↑':'↓'):'↕';});
  }

  function showMarket(symbol){
    const r=state.data?.rows.find(row=>row.symbol===symbol);if(!r)return;
    const content=doc.querySelector('#market-content');
    content.innerHTML=`<div class="detail-heading"><div><h2>${esc(r.symbol)}<span>${esc(r.name)}</span></h2><p>${esc(groups[r.group]||'')} · ${esc(r.asOf||'缺資料')} · ${esc(r.timezone||'—')}</p></div><div><strong>${number(r.price,r.group==='fx'&&r.symbol!=='UUP'?4:r.symbol==='BTC'?0:2)}</strong><span>${esc(r.currency||'—')}</span></div></div><div class="detail-metrics">${['1','5','20','60'].map(p=>`<div><span>${p}D 超額</span><b class="${cls(r.excess[p])}">${pp(r.excess[p])}</b></div>`).join('')}</div>${comparisonChart([{name:r.symbol,points:r.history.map(p=>({date:p.date,value:p.close}))}],{width:850,height:300,label:'資產股息及拆股調整收市價，首日為 100'})}<div class="detail-meta">${r.dailyCloseReconstructed?'<p>收市重建：日線缺值，使用同日已完成小時線收市價。</p>':''}<p>本詳情使用跨市場共同日期，行情卡可能採較新的完整日線。圖表顯示此資產自身回報；表格超額另減去 32 項資產池的當期中位數。不同資產的本地收市時間不一致。</p><p>1D／5D／20D／60D 的絕對回報：${['1','5','20','60'].map(p=>pp(r.absolute[p])).join(' / ')}。跨市場綜合分數 ${signed(r.score)}，屬公開近似公式。</p></div><div class="dialog-bottom"><button class="button" id="home-add-compare" data-market-symbol="${esc(r.symbol)}">＋ 加入走勢比較</button><a class="external-link" href="https://finance.yahoo.com/quote/${encodeURIComponent(r.providerSymbol)}/" target="_blank" rel="noopener">Yahoo Finance ↗</a></div>`;
    content.querySelector('#home-add-compare').addEventListener('click',()=>{doc.querySelector('#market-dialog').close();options.onCompare(r.symbol);});
    doc.querySelector('#market-dialog').showModal();
  }
  function exportCSV(){
    const headings=['rank','symbol','name','group','asOf','status','daily_close_reconstructed','daily_close_source_time','currency','price','LokiRS_approx','rankDelta5d','excess1D_pp','excess5D_pp','excess20D_pp','excess60D_pp','absolute1D_pct','absolute5D_pct','absolute20D_pct','absolute60D_pct'];
    const rows=filtered().map(r=>[r.rank,r.symbol,r.name,r.group,r.asOf,r.status,!!r.dailyCloseReconstructed,r.dailyCloseSourceTime,r.currency,r.price,r.score,r.rankDelta5d,...['1','5','20','60'].map(p=>r.excess[p]),...['1','5','20','60'].map(p=>r.absolute[p])]);
    const quote=value=>{let text=String(value??'');if(typeof value==='string'&&/^[=+\-@]/.test(value))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};
    options.download('\ufeff'+[headings,...rows].map(r=>r.map(quote).join(',')).join('\r\n'),`lokirs-cross-markets-${state.data.asOf}.csv`,'text/csv;charset=utf-8');
  }
  async function load(manual=false){
    if(state.loading)return;state.loading=true;
    try{
      const response=await options.fetch(`./data/home.json?t=${Date.now()}`,{cache:'no-store',signal:win.AbortSignal.timeout(20000)});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const data=await response.json();
      if(data.meta?.schemaVersion!==1||!Array.isArray(data.rows)||!data.rows.length||!Array.isArray(data.tiles))throw new Error('首頁資料格式不相容');
      const unchanged=state.data?.meta.generatedAt===data.meta.generatedAt;
      state.data=data;if(!unchanged)render();options.onUpdate();
      if(manual)options.toast('已檢查首頁發布快照；各來源時點見卡片。');
    }catch(error){
      if(!state.data)root.innerHTML=`<div class="error-banner" role="alert">首頁數據暫未能讀取（${esc(error.message)}）。請確認已上傳 data/home.json。美股排名仍可由上方進入。<button class="button" id="home-retry">重新讀取首頁</button></div>`;
      else if(manual)options.toast('首頁更新暫未成功，保留原有快照。');
      options.onUpdate();
    }finally{state.loading=false;}
  }

  root.addEventListener('click',event=>{
    const button=event.target.closest('button');if(!button)return;
    if(button.dataset.homeView)options.onView(button.dataset.homeView);
    if(button.dataset.homeStock)options.onStock(button.dataset.homeStock);
    if(button.dataset.homeMarket)showMarket(button.dataset.homeMarket);
    if(button.dataset.homeCopy){
      if(win.navigator.clipboard?.writeText)win.navigator.clipboard.writeText(button.dataset.homeCopy).then(()=>options.toast('已複製 '+button.dataset.homeCopy),()=>options.toast('請手動複製：'+button.dataset.homeCopy));
      else options.toast('請手動複製：'+button.dataset.homeCopy);
    }
    const th=button.closest('[data-home-sort]');
    if(th){const key=th.dataset.homeSort;state.direction=state.sort===key?-state.direction:key==='rank'?1:-1;state.sort=key;renderMatrix();}
    if(button.id==='home-auto'){state.auto=!state.auto;save('auto',state.auto);button.setAttribute('aria-pressed',String(state.auto));button.textContent=state.auto?'自動檢查 60s':'自動檢查已暫停';}
    if(button.id==='home-pulse-more'){state.expandedPulse=!state.expandedPulse;renderPulse();}
    if(button.id==='home-export')exportCSV();
    if(button.id==='home-retry')load(true);
    if(button.id==='home-reset'){state.search='';state.group='';$('#home-search').value='';$('#home-group').value='';renderMatrix();}
  });
  root.addEventListener('input',event=>{if(event.target.id==='home-search'){state.search=event.target.value.trim();renderMatrix();}});
  root.addEventListener('change',event=>{if(event.target.id==='home-group'){state.group=event.target.value;renderMatrix();}});
  root.addEventListener('toggle',event=>{if(event.target.dataset.homeFold)save(event.target.dataset.homeFold,event.target.open);},true);
  const timer=win.setInterval(()=>{if(state.auto&&options.getView()==='home'&&doc.visibilityState==='visible')load(false);},60000);
  return {load, get data(){return state.data;}, focusSearch(){const input=$('#home-search');if(input)input.focus();}, destroy(){win.clearInterval(timer);}};
}
