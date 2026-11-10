import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {filterRankings, formatMarketCap, marketCapTitle, summarizeRankings, renderRankingDashboard} from '../assets/rankings.js';

const app=readFileSync(new URL('../assets/app.js',import.meta.url),'utf8');
const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
function declaration(name){
  const start=app.indexOf(`function ${name}(`);
  assert.ok(start>=0,name);
  const firstEnd=app.indexOf('\n',start);
  const end=app.slice(start,firstEnd).endsWith('}')?firstEnd:app.indexOf('\n}',start)+2;
  return app.slice(start,end);
}
function setup(){
  const row=(symbol,d3,fortnight)=>({symbol,name:symbol,rank:1,rankDelta:0,price:100,score:2,
    status:'ok',sector:'TEST',sectorName:'測試',sectorRank:1,vsSector:0,longRS:80,streak:1,
    intra:{h1:1,h4:2},d1:3,d3,d3From:'2026-11-04',week:{value:4,from:'2026-11-02'},
    fortnight:{value:fortnight,from:'2026-10-26',target:'2026-10-26',to:'2026-11-09'},
    month:{value:5,from:'2026-10-09'},rsLine:[],history:[]});
  const state={data:{asOf:'2026-11-09',rows:[row('A',4.25,-2.75),row('B',-3,6),row('C',null,null)]},
    view:'stocks',watched:new Set(),search:'',value:'',sort:'d3',direction:-1,page:1,pageSize:50};
  const nodes=new Map();
  const $=key=>{
    if(!nodes.has(key))nodes.set(key,{innerHTML:'',textContent:'',hidden:false,firstChild:{textContent:''},showModal(){this.open=true;}});
    return nodes.get(key);
  };
  const helpers=['number','signed','cls','percent'].map(name=>app.split('\n').find(line=>line.startsWith(`const ${name} =`))).join('\n');
  const api=new Function('state','$','$$','esc','sparkline','comparisonChart','hkTime','filterRankings','formatMarketCap','marketCapTitle','summarizeRankings','renderRankingDashboard',
    helpers+'\n'+['filteredRows','renderRankingsDashboard','renderTable','periodTitle','tradingPeriodTitle','showDetail'].map(declaration).join('\n')+
    '\nreturn {filteredRows,renderTable,showDetail,percent};')
    (state,$,()=>[],String,()=>'<svg></svg>',()=>'<svg></svg>',String,filterRankings,formatMarketCap,marketCapTitle,summarizeRankings,renderRankingDashboard);
  return {state,nodes,...api};
}

test('new headers and filter choices follow the requested period order',()=>{
  const table=html.slice(html.indexOf('<table id="stock-table">'),html.indexOf('<tbody id="stock-body">'));
  const keys=[...table.matchAll(/data-sort="([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(keys.slice(keys.indexOf('d1'),keys.indexOf('month')+1),['d1','d3','week','fortnight','month']);
  assert.match(html,/<option value="d3">3D 超額<\/option>/);
  assert.match(html,/<option value="fortnight">兩周超額<\/option>/);
});

test('sorting and numeric filtering handle both added metrics and missing values',()=>{
  const ui=setup();
  assert.deepEqual(ui.filteredRows().map(r=>r.symbol),['A','B','C']);
  ui.state.sort='fortnight';
  assert.deepEqual(ui.filteredRows().map(r=>r.symbol),['B','A','C']);
  ui.state.direction=1;
  assert.deepEqual(ui.filteredRows().map(r=>r.symbol),['A','B','C']);
  for(const [metric,expected] of [['d3','A'],['fortnight','B']]){
    Object.assign(ui.state,{metric,operator:'gte',value:'0'});
    assert.deepEqual(ui.filteredRows().map(r=>r.symbol),[expected]);
  }
});

test('rendered rows align added values and date tooltips with the headers',()=>{
  const ui=setup();ui.renderTable();
  const body=ui.nodes.get('#stock-body').innerHTML;
  const first=body.slice(body.indexOf('<tr'),body.indexOf('</tr>'));
  const cells=[...first.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].map(m=>m[1]);
  assert.equal(cells.length,18);
  assert.equal(cells[9],'+4.25%');
  assert.equal(cells[11],'-2.75%');
  assert.match(first,/2026-11-04 → 2026-11-09；3 個 SPY 交易日/);
  assert.match(first,/2026-10-26 → 2026-11-09；目標起日 2026-10-26/);
  assert.equal(ui.percent(null),'—');
});

test('stock details include both new periods, their dates and units',()=>{
  const ui=setup();ui.showDetail('A');
  const detail=ui.nodes.get('#detail-content').innerHTML;
  assert.match(detail,/<span>3D 超額<\/span>/);
  assert.match(detail,/<span>兩周超額<\/span>/);
  assert.match(detail,/\+4\.25%/);
  assert.match(detail,/-2\.75%/);
  assert.match(detail,/3D：2026-11-04 → 2026-11-09/);
  assert.match(detail,/兩周：2026-10-26 → 2026-11-09/);
  assert.equal(ui.nodes.get('#detail-dialog').open,true);
});

test('watch control moves from table rows to immediately after the detail ticker',()=>{
  const ui=setup();ui.renderTable();
  assert.doesNotMatch(ui.nodes.get('#stock-body').innerHTML,/data-watch=/);
  ui.showDetail('A');
  assert.match(ui.nodes.get('#detail-content').innerHTML,/<h2>A<button[^>]*data-watch="A"[^>]*aria-pressed="false"/);
  ui.state.watched.add('A');ui.showDetail('A');
  assert.match(ui.nodes.get('#detail-content').innerHTML,/<h2>A<button[^>]*aria-pressed="true"[^>]*>★<\/button>/);
});

test('table pagination and filter edits update the dashboard scope from the same complete result set',()=>{
  const ui=setup();ui.state.pageSize=1;ui.renderTable();
  assert.equal((ui.nodes.get('#stock-body').innerHTML.match(/<tr/g)||[]).length,1);
  assert.match(ui.nodes.get('#dashboard-scope').textContent,/3 \/ 3 隻/);
  const dashboard=ui.nodes.get('#ranking-dashboard-content').innerHTML;
  ui.state.page=2;ui.renderTable();
  assert.equal(ui.nodes.get('#ranking-dashboard-content').innerHTML,dashboard);
  Object.assign(ui.state,{metric:'d3',operator:'gte',value:'0'});ui.renderTable();
  assert.match(ui.nodes.get('#dashboard-scope').textContent,/1 \/ 3 隻/);
  assert.equal(ui.state.page,1);
  ui.state.view='watchlist';ui.renderTable();
  assert.equal(ui.nodes.get('#ranking-dashboard').hidden,true);
});

test('removed research banner has no dangling event binding and ranking units are percent throughout',()=>{
  assert.doesNotMatch(html,/approx-notice|notice-method|FIELD NOTE/);
  assert.doesNotMatch(app,/notice-method/);
  assert.doesNotMatch(html,/\bpp\b|近似綜合分數/);
  assert.doesNotMatch(app,/_excess_pp|\+3 pp/);
  assert.match(html,/<option value="marketCap">市值 USD<\/option>/);
});
