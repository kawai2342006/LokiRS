// Asset identities use neutral archive inks. Green/coral remain reserved for signed data.
export const palette = ['#cdb477','#f0e6cb','#dba15d','#a5b1a1','#cdb477','#f0e6cb','#dba15d','#a5b1a1','#cdb477','#f0e6cb'];
export const seriesDashes = ['', '', '', '', '7 4', '7 4', '7 4', '7 4', '2 4', '2 4'];
export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function sparkline(values, {width = 100, height = 28, className = '', color} = {}) {
  const valid = values.filter(Number.isFinite);
  if (valid.length < 2) return '<span class="muted">—</span>';
  const min = Math.min(...valid), max = Math.max(...valid), span = max - min || 1;
  const points = valid.map((v,i) => `${(2+i/(valid.length-1)*(width-4)).toFixed(2)},${(height-3-(v-min)/span*(height-6)).toFixed(2)}`).join(' ');
  const stroke = color || (valid.at(-1) >= valid[0] ? 'var(--positive)' : 'var(--negative)');
  return `<svg class="sparkline ${className}" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true"><polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

export function comparisonChart(series, {width = 1040, height = 340, label = '收市價定基為 100'} = {}) {
  const clean = series.filter(s => s.points.length > 1);
  if (!clean.length) return '<div class="chart-empty">選擇有足夠數據的股票以顯示走勢。</div>';
  const common = clean[0].points.map(p => p.date).filter(d => clean.every(s => s.points.some(p => p.date === d)));
  if (common.length < 2) return '<div class="chart-empty">已選資產沒有足夠的共同交易日。</div>';
  const normalized = clean.map(s => {
    const points = new Map(s.points.map(p => [p.date,p.value]));
    const base = points.get(common[0]);
    return {...s, values:common.map(d => points.get(d)/base*100)};
  });
  const all = normalized.flatMap(s => s.values);
  let lo = Math.min(100,...all), hi = Math.max(100,...all);
  const padding = (hi-lo)*.12 || 1; lo -= padding; hi += padding;
  const margin = {top:25,right:72,bottom:35,left:20};
  const w = width-margin.left-margin.right, h = height-margin.top-margin.bottom;
  const x = i => margin.left+i/(common.length-1)*w;
  const y = value => margin.top+(hi-value)/(hi-lo)*h;
  let markup = `<svg xmlns="http://www.w3.org/2000/svg" class="comparison-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(label)}"><title>${escapeHTML(label)}</title>`;
  for(let i=0;i<5;i++) {
    const value=lo+(hi-lo)*i/4;
    markup+=`<line x1="${margin.left}" x2="${width-margin.right+4}" y1="${y(value)}" y2="${y(value)}" stroke="#cdb477" opacity=".16"/><text x="${width-margin.right+14}" y="${y(value)+4}" fill="#a5b1a1" font-family="IBM Plex Mono, Courier New, monospace" font-size="10">${value.toFixed(1)}</text>`;
  }
  markup+=`<line x1="${margin.left}" x2="${width-margin.right}" y1="${y(100)}" y2="${y(100)}" stroke="#a5b1a1" opacity=".45" stroke-dasharray="4 5"/>`;
  for(let i=0;i<Math.min(5,common.length);i++) {
    const index=Math.round(i/(Math.min(5,common.length)-1)*(common.length-1));
    markup+=`<text x="${x(index)}" y="${height-8}" fill="#a5b1a1" font-family="IBM Plex Mono, Courier New, monospace" font-size="10" text-anchor="${i===0?'start':i===4?'end':'middle'}">${common[index].slice(5).replace('-','/')}</text>`;
  }
  normalized.forEach((s,i) => {
    const color=s.color||palette[i%palette.length];
    const path=s.values.map((v,j)=>`${j?'L':'M'}${x(j).toFixed(2)},${y(v).toFixed(2)}`).join(' ');
    markup+=`<path d="${path}" fill="none" stroke="${color}" stroke-dasharray="${seriesDashes[i%seriesDashes.length]}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${x(common.length-1)}" cy="${y(s.values.at(-1))}" r="3" fill="${color}"/>`;
  });
  markup+='</svg><div class="chart-legend">';
  normalized.forEach((s,i) => {
    const delta=s.values.at(-1)-100;
    markup+=`<span><i style="border-top-color:${s.color||palette[i%palette.length]};border-top-style:${i<4?'solid':i<8?'dashed':'dotted'}"></i><strong>${escapeHTML(s.name)}</strong><b class="${delta>=0?'positive':'negative'}">${delta>=0?'+':''}${delta.toFixed(2)}%</b></span>`;
  });
  return markup+'</div>';
}
