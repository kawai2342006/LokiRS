import test from 'node:test';
import assert from 'node:assert/strict';
import {createSentiment} from '../assets/sentiment.js';

test('the dated CNN mirror is displayed with distinct provenance', async () => {
  const target={innerHTML:''},tag={textContent:'',title:''};
  const document={defaultView:{AbortSignal},querySelector: selector =>
    selector==='#sentiment-content'?target:selector==='#sentiment-source'?tag:null};
  const data={schemaVersion:1,indexId:'cnn-us-fear-greed',status:'ok',source:'CNN Mirror',
    value:22.0792756539235,rating:'extreme fear',observationDate:new Date().toISOString().slice(0,10),
    asOf:new Date().toISOString().slice(0,10),asOfPrecision:'date'};
  const panel=createSentiment({document,fetch:async()=>({ok:true,json:async()=>data})});
  await panel.load();
  assert.equal(panel.data.source,'CNN Mirror');
  assert.match(tag.title,/公開鏡像（轉載 CNN）/);
  assert.match(target.innerHTML,/22\.08/);
  assert.match(target.innerHTML,/github\.com\/whit3rabbit\/fear-greed-data/);
});
