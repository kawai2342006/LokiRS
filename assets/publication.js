// Publication checks read the deployed snapshot. Market downloads run in Actions.
export function validatePublishedSnapshot(data, previous=null) {
  if(data?.meta?.schemaVersion!==1||!Array.isArray(data.rows)||!data.rows.length||
     !/^\d{4}-\d{2}-\d{2}$/.test(data.asOf||'')||!Number.isFinite(Date.parse(data.meta.generatedAt))) {
    throw new Error('數據格式不相容');
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
  if(previous?.meta?.generatedAt===data.meta.generatedAt) {
    return `仍是 ${data.asOf} 已發布快照；新行情請按「抓取最新行情」。`;
  }
  return `已載入新發布版本，行情日期 ${data.asOf}。`;
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
