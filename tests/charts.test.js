import test from 'node:test';
import assert from 'node:assert/strict';
import {comparisonChart,escapeHTML,sparkline} from '../assets/charts.js';

test('comparison aligns all assets on common dates before rebasing',()=>{
  const html=comparisonChart([
    {name:'A',points:[{date:'2026-10-01',value:50},{date:'2026-10-02',value:100},{date:'2026-10-03',value:110}]},
    {name:'B',points:[{date:'2026-10-02',value:200},{date:'2026-10-03',value:210}]}
  ]);
  assert.ok(html.includes('+10.00%'));
  assert.ok(html.includes('+5.00%'));
  assert.ok(!html.includes('+120.00%'));
});
test('missing common dates do not create a fabricated line',()=>{
  const html=comparisonChart([{name:'A',points:[{date:'a',value:1},{date:'b',value:2}]},{name:'B',points:[{date:'c',value:1},{date:'d',value:2}]}]);
  assert.ok(!html.includes('<path'));
});
test('external names are escaped and flat sparklines remain finite',()=>{
  assert.equal(escapeHTML('<img onerror="x">'),'&lt;img onerror=&quot;x&quot;&gt;');
  const html=sparkline([100,100,100]);
  assert.ok(!html.includes('NaN'));
  assert.ok(!html.includes('Infinity'));
});
