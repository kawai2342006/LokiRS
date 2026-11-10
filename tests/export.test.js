import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('stock CSV keeps price and score aligned after adding source and provisional status',()=>{
  const app=readFileSync(new URL('../assets/app.js',import.meta.url),'utf8');
  const start=app.indexOf('function exportCSV() {')+'function exportCSV() {'.length;
  const body=app.slice(start,app.indexOf('\n}',start));
  const row={symbol:'INFY',rank:2,price:12.39,score:1.37,intra:{},dailyCloseSource:'completed-regular-session-quote',
    d1:1,d3:4.25,d3From:'2026-11-04',week:{value:3,from:'2026-11-02'},
    fortnight:{value:-2.75,from:'2026-10-26'},month:{value:8,from:'2026-10-09'},
    dividendBackfill:{amountUSD:.274815,exDate:'2026-11-03',source:'https://adr.db.com/',sourceStatus:'provisional'}};
  let csv;
  new Function('filteredRows','download','state',body)(()=>[row],text=>csv=text,{data:{asOf:'2026-11-09'}});
  const [header,values]=csv.slice(1).split('\r\n').map(line=>line.slice(1,-1).split('\",\"'));
  assert.equal(header.length,values.length);
  const record=Object.fromEntries(header.map((key,i)=>[key,values[i]]));
  assert.equal(record.price_USD,'12.39');
  assert.equal(record.LokiRS_approx,'1.37');
  assert.equal(record.daily_close_source,'completed-regular-session-quote');
  assert.equal(record.dividend_source_status,'provisional');
  assert.equal(record['3d_excess_pp'],'4.25');
  assert.equal(record.fortnight_excess_pp,'-2.75');
  assert.equal(record['3d_from'],'2026-11-04');
  assert.equal(record.fortnight_from,'2026-10-26');
  assert.deepEqual(header.slice(header.indexOf('1d_excess_pp'),header.indexOf('month_excess_pp')+1),
    ['1d_excess_pp','3d_excess_pp','week_excess_pp','fortnight_excess_pp','month_excess_pp']);
});
