import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {filterRankings,formatMarketCap,marketCapTitle,summarizeRankings,renderRankingDashboard} from '../assets/rankings.js';

const state=overrides=>({view:'stocks',watched:new Set(),search:'',sector:'',sectorTop:0,metric:'score',operator:'gte',value:'',capUnit:1e9,sort:'score',direction:-1,...overrides});
const row=(symbol,values={})=>({symbol,name:symbol,sector:'TECH',sectorName:'科技',score:null,d1:null,longRS:null,streak:null,marketCap:null,intra:{h1:null,h4:null},week:{value:null},month:{value:null},...values});
const rows=[
  row('A',{score:-6,d1:-2,streak:7,marketCap:1e6}),
  row('B',{score:-5,d1:0,longRS:50,streak:6,marketCap:2e9}),
  row('C',{score:0,longRS:100}),
  row('D',{sector:'HEALTH',sectorName:'醫療',score:5,d1:3,longRS:0,streak:10,marketCap:3e9}),
  row('E',{sector:'HEALTH',sectorName:'醫療',score:10,d1:-1,streak:0,marketCap:1e12}),
  row('F',{sector:'HEALTH',sectorName:'醫療',d1:1})
];

test('market cap formatting uses only K/M/B, handles boundaries and keeps missing distinct from zero',()=>{
  for(const value of [null,undefined,NaN,Infinity,0,-1])assert.equal(formatMarketCap(value),'—');
  assert.equal(formatMarketCap(999),'999.00');
  assert.equal(formatMarketCap(1000),'1.00K');
  assert.equal(formatMarketCap(1e6),'1.00M');
  assert.equal(formatMarketCap(1.25e9),'1.25B');
  assert.equal(formatMarketCap(1e12),'1,000.00B');
  assert.match(marketCapTitle({marketCap:1e9,marketCapStatus:'stale',marketCapFetchedAt:'2026-11-10T08:00:00Z'}),/保留舊值/);
});

test('market cap comparisons are inclusive and apply selected units; missing caps fail both comparisons',()=>{
  assert.deepEqual(filterRankings(rows,state({metric:'marketCap',value:'2'})).map(r=>r.symbol),['E','D','B']);
  assert.deepEqual(filterRankings(rows,state({metric:'marketCap',value:'2',operator:'lte'})).map(r=>r.symbol),['B','A']);
  for(const [value,capUnit] of [['2',1e9],['2000',1e6],['2000000',1e3]]){
    assert.deepEqual(filterRankings(rows,state({metric:'marketCap',value,capUnit})).map(r=>r.symbol),['E','D','B']);
  }
  assert.equal(filterRankings(rows,state({metric:'marketCap',value:''})).length,6);
});

test('market cap sorting keeps unknown values last in either direction and does not mutate source order',()=>{
  assert.deepEqual(filterRankings(rows,state({sort:'marketCap',direction:1})).map(r=>r.symbol),['A','B','D','E','C','F']);
  assert.deepEqual(filterRankings(rows,state({sort:'marketCap'})).map(r=>r.symbol),['E','D','B','A','C','F']);
  assert.deepEqual(rows.map(r=>r.symbol),['A','B','C','D','E','F']);
});

test('shared filters compose search, exact symbol, sector, quick filters, contracts and numeric threshold',()=>{
  const candidates=[row('MATCH',{name:'Target',score:5,longRS:80,streak:8,sectorRank:2,marketCap:3e9}),
    row('FAIL',{name:'Target',score:6,longRS:80,streak:1,sectorRank:2,marketCap:3e9})];
  const selected=filterRankings(candidates,state({search:'target',sector:'TECH',sectorTop:3,long:true,streak:true,perp:true,metric:'marketCap',value:'2'}),['MATCH','FAIL']);
  assert.deepEqual(selected.map(r=>r.symbol),['MATCH']);
  assert.deepEqual(filterRankings(candidates,state({view:'watchlist',watched:new Set(['FAIL'])})).map(r=>r.symbol),['FAIL']);
  assert.equal(filterRankings(candidates,state({exactSymbol:'M'})).length,0);
  assert.equal(filterRankings(candidates,state({sectorTop:1})).length,0);
});

test('dashboard medians and proportions exclude missing values, include zero in denominators, and treat ties correctly',()=>{
  const summary=summarizeRankings(rows);
  assert.equal(summary.count,6);
  assert.equal(summary.scoreMedian,0);
  assert.equal(summary.scoreCount,5);
  assert.deepEqual(summary.outperform,{count:2,total:5,value:40});
  assert.deepEqual(summary.streak,{count:2,total:4,value:50});
  assert.equal(summary.long.count,2);assert.equal(summary.long.total,3);
  assert.equal(summary.sectors.find(s=>s.symbol==='TECH').medians.score.value,-5);
  assert.equal(summary.sectors.find(s=>s.symbol==='HEALTH').medians.score.value,7.5);
  assert.equal(summary.sectors.reduce((n,s)=>n+s.count,0),6);
  assert.equal(summary.sectors.reduce((n,s)=>n+s.share,0),100);
  assert.deepEqual(summary.bins.map(b=>b.count),[1,1,1,1,1]);
  assert.equal(summary.marketCapCount,4);
});

test('dashboard and export receive the full filtered set, independently of sorting and pagination',()=>{
  const first=state({metric:'marketCap',value:'2',page:1,pageSize:1});
  const firstSummary=summarizeRankings(filterRankings(rows,first));
  const laterSummary=summarizeRankings(filterRankings(rows,{...first,page:10,pageSize:100,sort:'d1',direction:1}));
  assert.deepEqual(firstSummary,laterSummary);
  assert.equal(firstSummary.count,3);
  assert.equal(firstSummary.sectors.reduce((count,sector)=>count+sector.count,0),3);
});

test('empty and missing-only universes render honest placeholders without NaN or invalid chart sizes',()=>{
  assert.match(renderRankingDashboard(summarizeRankings([])),/沒有符合條件/);
  const rendered=renderRankingDashboard(summarizeRankings([row('EMPTY')]));
  assert.doesNotMatch(rendered,/NaN|Infinity/);
  assert.match(rendered,/0 \/ 0/);
  assert.match(rendered,/0 隻有效/);
  const escaped=renderRankingDashboard(summarizeRankings([row('X',{sectorName:'<script>x</script>'})]));
  assert.doesNotMatch(escaped,/<script>/);
  assert.match(escaped,/&lt;script&gt;/);
});

test('real snapshot covers every filtered sector and does not use the first 50 rows as its universe',()=>{
  const snapshot=JSON.parse(readFileSync(new URL('../data/latest.json',import.meta.url)));
  const filtered=filterRankings(snapshot.rows,state());
  const summary=summarizeRankings(filtered);
  assert.equal(summary.count,snapshot.rows.length);
  assert.equal(summary.sectors.length,new Set(snapshot.rows.map(r=>r.sector)).size);
  const rendered=renderRankingDashboard(summary);
  assert.equal((rendered.match(/data-dashboard-sector=/g)||[]).length,summary.sectors.length);
  for(const sector of snapshot.sectors){
    const expected=snapshot.rows.filter(r=>r.sector===sector.symbol).length;
    if(expected)assert.equal(summary.sectors.find(s=>s.symbol===sector.symbol).count,expected);
  }
});

test('detail star toggles membership, persists the watchlist and updates its accessible state without closing the dialog',()=>{
  const app=readFileSync(new URL('../assets/app.js',import.meta.url),'utf8');
  const start=app.indexOf('function toggleWatch('),end=app.indexOf('\n}',start)+2;
  const membership={watched:new Set()},saved=[],attributes={};
  const button={dataset:{watch:'A'},textContent:'☆',classList:{toggle(name,value){this[name]=value;}},setAttribute(name,value){attributes[name]=value;}};
  let renders=0,counts=0;
  const toggle=new Function('state','$','$$','storage','updateWatchCount','renderTable','return ('+app.slice(start,end)+')')
    (membership,()=>{},()=>[button],{set(key,value){saved.push([key,value]);}},()=>counts++,()=>renders++);
  toggle('A');
  assert.equal(membership.watched.has('A'),true);assert.equal(button.textContent,'★');
  assert.equal(attributes['aria-pressed'],'true');assert.equal(attributes['aria-label'],'移除自選 A');
  assert.deepEqual(saved[0],['watchlist',['A']]);
  toggle('A');
  assert.equal(membership.watched.has('A'),false);assert.equal(button.textContent,'☆');
  assert.equal(attributes['aria-pressed'],'false');assert.deepEqual(saved[1],['watchlist',[]]);
  assert.equal(renders,2);assert.equal(counts,2);
});
