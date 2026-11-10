import test from 'node:test';
import assert from 'node:assert/strict';
import {validatePublishedSnapshot, publicationAge, reloadMessage, createAutoRefresh} from '../assets/publication.js';

const snapshot=(asOf,generatedAt)=>({asOf,meta:{schemaVersion:1,generatedAt},rows:[{symbol:'SPY'}]});

test('stale CDN responses cannot replace a newer session or newer revision',()=>{
  const current=snapshot('2026-11-09','2026-11-10T01:00:00Z');
  assert.throws(()=>validatePublishedSnapshot(snapshot('2026-11-06','2026-11-10T02:00:00Z'),current),/較舊版本/);
  assert.throws(()=>validatePublishedSnapshot(snapshot('2026-11-09','2026-11-09T23:00:00Z'),current),/較舊版本/);
  assert.equal(validatePublishedSnapshot(current,current),current);
  assert.throws(()=>validatePublishedSnapshot(snapshot('2026-11-09','invalid')),/不相容/);
});

test('unchanged published data is described by date without claiming current market data',()=>{
  const old=snapshot('2026-11-06','2026-11-07T10:23:47Z');
  const text=reloadMessage(old,old);
  assert.match(text,/2026-11-06/);
  assert.match(text,/抓取最新行情/);
  assert.doesNotMatch(text,/已是最新/);
  assert.equal(publicationAge(old,Date.parse('2026-11-10T02:00:00Z')),63);
});

function setup(load) {
  let enabled=true,active=true,tick,listener,cleared=false;
  const document={visibilityState:'visible',addEventListener(type,fn){listener=fn;},removeEventListener(type,fn){assert.equal(fn,listener);listener=null;}};
  const window={setInterval(fn,ms){assert.equal(ms,60000);tick=fn;return 7;},clearInterval(id){assert.equal(id,7);cleared=true;}};
  const monitor=createAutoRefresh({window,document,enabled:()=>enabled,active:()=>active,load});
  return {monitor,document,tick:()=>tick(),visible:()=>listener(),pause:()=>enabled=false,inactive:()=>active=false,cleared:()=>cleared};
}

test('60-second checks honor pause, hidden tabs, current view, and dispose',async()=>{
  let calls=0;
  const ui=setup(async()=>{calls++;});
  ui.tick();await Promise.resolve();assert.equal(calls,1);
  ui.document.visibilityState='hidden';await ui.monitor.check();assert.equal(calls,1);
  ui.document.visibilityState='visible';ui.visible();await Promise.resolve();assert.equal(calls,2);
  ui.pause();await ui.monitor.check();assert.equal(calls,2);
  ui.monitor.dispose();assert.equal(ui.cleared(),true);await ui.monitor.check();assert.equal(calls,2);
  const other=setup(async()=>{calls++;});other.inactive();await other.monitor.check();assert.equal(calls,2);other.monitor.dispose();
});

test('reappearing tabs and timer ticks share one in-flight read and recover after failure',async()=>{
  let calls=0,release;
  const ui=setup(()=>{calls++;return new Promise(resolve=>{release=resolve;});});
  const pending=ui.monitor.check();ui.visible();ui.tick();assert.equal(calls,1);
  release();await pending;const again=ui.monitor.check();assert.equal(calls,2);release();await again;ui.monitor.dispose();
  let failed=0;const retry=setup(async()=>{failed++;if(failed===1)throw new Error('network');});
  await assert.rejects(retry.monitor.check(),/network/);await retry.monitor.check();assert.equal(failed,2);retry.monitor.dispose();
});
