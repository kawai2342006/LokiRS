// CNN's US-stock index only. Date-only observations never get an invented clock time.
export function createSentiment(options) {
  const doc=options.document, win=doc.defaultView;
  const target=doc.querySelector('#sentiment-content');
  const state={file:null,fallback:null,error:false,loading:false};
  const macroURL='https://en.macromicro.me/charts/50108/cnn-fear-and-greed';
  const cnnURL='https://www.cnn.com/markets/fear-and-greed';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const numeric=value=>Number.isFinite(value)&&value>=0&&value<=100;
  const format=value=>numeric(value)?value.toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:2}):'—';
  const day=data=>data?.observationDate||data?.asOf?.slice(0,10);
  function usable(data){
    const observed=day(data),stamp=Date.parse(observed),today=new Date().toISOString().slice(0,10);
    return data&&['ok','stale'].includes(data.status)&&numeric(data.value)&&['MacroMicro','CNN'].includes(data.source)&&
      (data.indexId==='cnn-us-fear-greed'||(!data.indexId&&data.source==='CNN'))&&
      typeof observed==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(observed)&&Number.isFinite(stamp)&&
      new Date(stamp).toISOString().slice(0,10)===observed&&observed<=today;
  }
  function selected(){
    const candidates=[state.file,state.fallback].filter(usable);
    const result=candidates.sort((a,b)=>day(b).localeCompare(day(a)))[0];
    if(!result)return null;
    const old=Math.floor(Date.now()/86400000)-Math.floor(Date.parse(day(result))/86400000)>7;
    return state.error||old?{...result,status:'stale'}:result;
  }
  function sourceLabel(data){return data?.source==='MacroMicro'?'MacroMicro（轉載 CNN）':'CNN';}
  function dateLabel(data){
    const observed=day(data);
    if(data.asOfPrecision==='date'||/^\d{4}-\d{2}-\d{2}$/.test(data.asOf||''))return '資料日期 '+observed;
    try{
      const time=new Intl.DateTimeFormat('zh-HK',{timeZone:'Asia/Hong_Kong',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(data.asOf));
      return '資料日期 '+observed+' · '+time+' HKT';
    }catch{return '資料日期 '+observed;}
  }
  function render(){
    const data=selected();
    const tag=doc.querySelector('#sentiment-source')||doc.querySelector('.sentiment-panel .source-tag');
    if(tag){tag.textContent='CNN · 0–100';tag.title=data?'來源：'+sourceLabel(data):'公開來源暫未提供';}
    if(data){
      const value=data.value;
      const labels={'extreme fear':'極度恐懼',fear:'恐懼',neutral:'中性',greed:'貪婪','extreme greed':'極度貪婪'};
      const label=labels[String(data.rating||'').toLowerCase()]||(value<=25?'極度恐懼':value<45?'恐懼':value<=55?'中性':value<=75?'貪婪':'極度貪婪');
      const url=data.source==='MacroMicro'?macroURL:cnnURL;
      const stale=data.status==='stale'||state.error;
      const previousLabel=data.previousLabel==='上一筆'?'上一筆':'前收';
      const history=[
        [previousLabel,data.previousClose,data.previousAsOf],['一週前',data.weekAgo,data.weekAgoAsOf],['一月前',data.monthAgo,data.monthAgoAsOf]
      ];
      target.innerHTML=`<div class="sentiment-value ${value<45?'negative':value>55?'positive':''}">${format(value)}<span>${label}</span></div><div class="sentiment-track"><i style="left:${value}%"></i></div><div class="scale-labels"><span>極度恐懼</span><span>極度貪婪</span></div><div class="sentiment-history">${history.map(([label,v,date])=>`<span title="${numeric(v)?esc(date||'來源提供的參考值'):'來源未提供'}">${label} <b>${format(v)}</b></span>`).join('')}</div>${stale?'<p class="panel-footnote"><span class="unavailable-badge">舊值</span> 暫未更新，保留上次資料。</p>':''}<p class="panel-footnote">CNN 原指數，非本站合成。<br>${esc(dateLabel(data))}。<br><a class="external-link" href="${url}" target="_blank" rel="noopener">來源：${esc(sourceLabel(data))} ↗</a></p>`;
    }else{
      target.innerHTML=`<div class="unavailable-visual"><div class="gauge-placeholder"><span>—</span></div><span class="unavailable-badge">來源暫未提供</span></div><p class="unavailable-note">公開來源暫未能取得有效數據。已有觀測值時會保留原日期；缺值不會自行合成。</p><a class="external-link" href="${macroURL}" target="_blank" rel="noopener">到 MacroMicro 查看 ↗</a><br><a class="external-link" href="${cnnURL}" target="_blank" rel="noopener">到 CNN 查看 ↗</a>`;
    }
    options.onUpdate?.();
  }
  async function load(manual=false){
    if(state.loading)return;state.loading=true;
    try{
      const response=await options.fetch(`./data/sentiment.json?t=${Date.now()}`,{cache:'no-store',signal:win.AbortSignal.timeout(20000)});
      if(!response.ok)throw new Error('Sentiment snapshot not available');
      const data=await response.json();
      if(data.schemaVersion!==1||data.indexId!=='cnn-us-fear-greed'||(!usable(data)&&data.status!=='unavailable'))throw new Error('Invalid sentiment snapshot');
      state.file=data;state.error=false;render();
      if(manual)options.toast?.('已檢查情緒資料發布快照。');
    }catch{
      state.error=true;render();
      if(manual&&selected())options.toast?.('情緒資料暫未更新，已保留原有觀測值。');
    }finally{state.loading=false;}
  }
  return {load,setFallback(data){state.fallback=data;render();},get data(){return selected();}};
}
