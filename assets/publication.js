// Publication checks read the deployed snapshot. Market downloads run in Actions.
export function snapshotMode(data) {
  return data?.meta?.snapshotMode||'close';
}

export function snapshotFile(mode) {
  if(!['close','intraday'].includes(mode))throw new Error('未知快照類型');
  return mode==='intraday'?'intraday.json':'latest.json';
}

export function validatePublishedSnapshot(data, previous=null, expectedMode=null) {
  if(data?.meta?.schemaVersion!==1||!Array.isArray(data.rows)||!data.rows.length||
     !/^\d{4}-\d{2}-\d{2}$/.test(data.asOf||'')||!Number.isFinite(Date.parse(data.meta.generatedAt))) {
    throw new Error('數據格式不相容');
  }
  const mode=snapshotMode(data), meta=data.meta;
  if(!['close','intraday'].includes(mode)||(expectedMode&&mode!==expectedMode)||
     (previous&&snapshotMode(previous)!==mode))throw new Error('快照類型不相符');
  if(mode==='intraday') {
    const end=Date.parse(meta.snapshotAt), start=Date.parse(meta.snapshotBarStart);
    const sessionEnd=Date.parse(meta.sessionClose), downloaded=Date.parse(meta.downloadStartedAt);
    const parts=Number.isFinite(end)?Object.fromEntries(new Intl.DateTimeFormat('en-CA',{
      timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'
    }).formatToParts(new Date(end)).map(p=>[p.type,p.value])):{};
    if(meta.intervalMinutes!==60||!Number.isFinite(end)||end-start!==3600000||
       !Number.isFinite(sessionEnd)||end>sessionEnd||!Number.isFinite(downloaded)||end>downloaded||downloaded>Date.parse(meta.generatedAt)||
       `${parts.year}-${parts.month}-${parts.day}`!==data.asOf||parts.minute!=='30'||+parts.hour<10||+parts.hour>15||
       !(meta.dailyBaselineDate<data.asOf)||
       (meta.referenceCloseDate!=null&&!(meta.referenceCloseDate<data.asOf))||
       data.benchmark?.snapshotAt!==meta.snapshotAt||
       data.rows.some(row=>row.price!=null&&(row.snapshotAt!==meta.snapshotAt||row.snapshotBarStart!==meta.snapshotBarStart))) {
      throw new Error('盤中快照不是同步的完整 60 分鐘 K 線');
    }
    if(previous&&end<Date.parse(previous.meta.snapshotAt))throw new Error('伺服器傳回較舊 K 線，已保留目前數據');
  }
  if(previous&&(data.asOf<previous.asOf||Date.parse(data.meta.generatedAt)<Date.parse(previous.meta.generatedAt))) {
    throw new Error('伺服器傳回較舊版本，已保留目前數據');
  }
  return data;
}

export function publicationAge(data, now=Date.now()) {
  const elapsed=now-Date.parse(data?.meta?.generatedAt);
  return Number.isFinite(elapsed)?Math.max(0,Math.floor(elapsed/3600000)):null;
}

export function reloadMessage(data, previous=null) {
  if(snapshotMode(data)==='intraday') {
    const time=new Intl.DateTimeFormat('zh-HK',{timeZone:'Asia/Hong_Kong',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(data.meta.snapshotAt));
    return previous?.meta?.generatedAt===data.meta.generatedAt?
      `仍是 ${time} HKT 的盤中快照；下一支 K 線需手動抓取並發布。`:
      `已載入盤中 60m 快照，K 線截至 ${time} HKT。`;
  }
  if(previous?.meta?.generatedAt===data.meta.generatedAt) {
    return `仍是 ${data.asOf} 已發布快照；新行情請按「抓取最新行情」。`;
  }
  return `已載入新發布版本，行情日期 ${data.asOf}。`;
}

// Each mode has its own validated cache and in-flight read. Switching modes
// cannot compare a newer intraday publication with an older canonical close.
export function createSnapshotLoader({fetch:fetchData, now=Date.now}) {
  const cache=new Map(), pending=new Map();
  return {
    cached:mode=>cache.get(mode)||null,
    load(mode) {
      const filename=snapshotFile(mode);
      if(pending.has(mode))return pending.get(mode);
      const request=Promise.resolve().then(async()=>{
        const response=await fetchData(`./data/${filename}?t=${now()}`,{cache:'no-store',signal:AbortSignal.timeout(20000)});
        if(!response.ok){const error=new Error(`HTTP ${response.status}`);error.status=response.status;throw error;}
        const previous=cache.get(mode)||null;
        const data=validatePublishedSnapshot(await response.json(),previous,mode);
        cache.set(mode,data);
        return {data,previous};
      }).finally(()=>pending.delete(mode));
      pending.set(mode,request);
      return request;
    }
  };
}

export function createAutoRefresh({window:win, document:doc, enabled, active, load}) {
  let pending=false, disposed=false;
  async function check() {
    if(disposed||pending||!enabled()||!active()||doc.visibilityState!=='visible')return;
    pending=true;
    try {await load();} finally {pending=false;}
  }
  const timer=win.setInterval(()=>{check().catch(()=>{});},60000);
  const visible=()=>{check().catch(()=>{});};
  doc.addEventListener('visibilitychange',visible);
  return {check,dispose(){disposed=true;win.clearInterval(timer);doc.removeEventListener('visibilitychange',visible);}};
}
