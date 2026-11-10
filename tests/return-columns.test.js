import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

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
  const helpers=['number','signed','cls','pp','metric'].map(name=>app.split('\n').find(line=>line.startsWith(`const ${name} =`))).join('\n');
  const api=new Function('state','$','$$','esc','sparkline','comparisonChart','hkTime',
    helpers+'\n'+['filteredRows','renderTable','periodTitle','tradingPeriodTitle','showDetail'].map(declaration).join('\n')+
    '\nreturn {filteredRows,renderTable,showDetail,pp};')
    (state,$,()=>[],String,()=>'<svg></svg>',()=>'<svg></svg>',String);
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
  assert.equal(cells.length,17);
  assert.equal(cells[8],'+4.25 pp');
  assert.equal(cells[10],'-2.75 pp');
  assert.match(first,/2026-11-04 → 2026-11-09；3 個 SPY 交易日/);
  assert.match(first,/2026-10-26 → 2026-11-09；目標起日 2026-10-26/);
  assert.equal(ui.pp(null),'—');
});

test('stock details include both new periods, their dates and units',()=>{
  const ui=setup();ui.showDetail('A');
  const detail=ui.nodes.get('#detail-content').innerHTML;
  assert.match(detail,/<span>3D 超額<\/span>/);
  assert.match(detail,/<span>兩周超額<\/span>/);
  assert.match(detail,/\+4\.25 pp/);
  assert.match(detail,/-2\.75 pp/);
  assert.match(detail,/3D：2026-11-04 → 2026-11-09/);
  assert.match(detail,/兩周：2026-10-26 → 2026-11-09/);
  assert.equal(ui.nodes.get('#detail-dialog').open,true);
});
