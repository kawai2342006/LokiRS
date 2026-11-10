import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

test('stock CSV keeps price and score aligned after adding source and provisional status',()=>{
  const app=readFileSync(new URL('../assets/app.js',import.meta.url),'utf8');
  const start=app.indexOf('function exportCSV() {')+'function exportCSV() {'.length;
  const body=app.slice(start,app.indexOf('\n}',start));
  const row={symbol:'INFY',rank:2,price:12.39,score:1.37,intra:{},dailyCloseSource:'completed-regular-session-quote',
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
});
