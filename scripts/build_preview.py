#!/usr/bin/env python3
"""Build one offline HTML preview from the current source and dated snapshots."""
import base64
import argparse
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build(output='LokiRS_Rankings_Dashboard_Preview.html', stocks=False):
    html=(ROOT/'index.html').read_text()
    css=[]
    for name in ['assets/fonts/fonts.css','assets/styles.css','assets/home.css']:
        path=ROOT/name
        text=path.read_text()
        def font(match):
            asset=path.parent/match.group(1)
            data=base64.b64encode(asset.read_bytes()).decode()
            return f'url("data:font/woff2;base64,{data}")'
        if 'fonts' in name:
            text=re.sub(r'url\([\'"]?([^\)\'\"]+\.woff2)[\'"]?\)',font,text)
        css.append(text)
    html=re.sub(r'<link[^>]+(?:rel="(?:stylesheet|preload)")[^>]*>','',html)
    html=html.replace('</head>','<style>'+''.join(css)+'</style></head>')
    favicon=base64.b64encode((ROOT/'assets/favicon.svg').read_bytes()).decode()
    html=html.replace('./assets/favicon.svg','data:image/svg+xml;base64,'+favicon)
    modules={}
    def module(path):
        path=path.resolve()
        if path in modules:return modules[path]
        text=path.read_text()
        def dependency(match):
            return match.group(1)+module(path.parent/match.group(2).split('?')[0])+match.group(3)
        text=re.sub(r"(from\s+['\"])(\./[^'\"]+)(['\"])",dependency,text)
        modules[path]='data:text/javascript;base64,'+base64.b64encode(text.encode()).decode()
        return modules[path]
    data={name:json.loads((ROOT/'data'/name).read_text()) for name in ['latest.json','home.json','sentiment.json']}
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    bootstrap='<script>const previewSnapshots='+payload+''';
const originalPreviewFetch=window.fetch.bind(window);
window.fetch=(input,options)=>{const url=new URL(typeof input==='string'?input:input.url,location.href);const name=url.pathname.split('/').pop();return previewSnapshots[name]?Promise.resolve(new Response(JSON.stringify(previewSnapshots[name]),{status:200,headers:{'Content-Type':'application/json'}})):originalPreviewFetch(input,options);};
</script>'''
    if stocks:
        bootstrap += '<script>if(!new URLSearchParams(location.search).has("tab"))location.hash="rankings";</script>'
    html=re.sub(r'<script type="module" src="\./assets/app\.js[^\"]*"></script>',lambda _:bootstrap+'<script type="module" src="'+module(ROOT/'assets/app.js')+'"></script>',html)
    html=html.replace('<main>','<main><p class="notice-copy">離線預覽 · 內嵌快照固定於美股 '+data['latest.json']['asOf']+'；更新行情請使用正式網站及更新流程。</p>')
    html=html.replace('<title>','<title>離線預覽 / ',1)
    destination=ROOT/'preview'/output
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(html)
    print(f'Built {destination.name}: {data["latest.json"]["asOf"]}; {len(modules)} embedded JS modules')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='LokiRS_Rankings_Dashboard_Preview.html')
    parser.add_argument('--stocks', action='store_true', help='Open directly in the stock rankings')
    args=parser.parse_args()
    build(args.output, args.stocks)
