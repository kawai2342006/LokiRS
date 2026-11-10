#!/usr/bin/env python3
"""Compare an independent LokiRS snapshot with the public default LazyRS table.

This diagnostic reads the public page's existing serialized free-table props.
It never requests member/history endpoints or feeds reference rows into LokiRS.
"""
import argparse
import csv
import json
import math
import statistics
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_URL = 'https://lazyrs.trade/?tab=stocks'


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.current = [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.current = []

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.current is not None:
            self.scripts.append(''.join(self.current))
            self.current = None


def read_public_reference(html):
    parser = Scripts()
    parser.feed(html.decode('utf-8') if isinstance(html, bytes) else html)
    chunks = []
    for script in parser.scripts:
        if script.startswith('self.__next_f.push('):
            block = json.loads(script[script.index('(')+1:script.rindex(')')])
            if isinstance(block, list) and len(block) > 1 and block[0] == 1:
                chunks.append(block[1])
    for line in ''.join(chunks).splitlines():
        try:
            value = json.loads(line.split(':', 1)[1])
        except (ValueError, IndexError):
            continue
        props = value[3] if isinstance(value, list) and len(value) > 3 else None
        if isinstance(props, dict) and props.get('tab') == 'stocks' and isinstance(props.get('rows'), list):
            if props.get('premium') is not False or props.get('volMode') is not False:
                raise ValueError('Expected the public table with volatility adjustment off')
            if not props['rows']:
                raise ValueError('Public ranking is empty')
            if not all(a['score'] >= b['score'] for a, b in zip(props['rows'], props['rows'][1:])):
                raise ValueError('Reference is not the default displayed score order')
            return props
    raise ValueError('Public ranking payload missing; page format may have changed')


def symbol(raw):
    return raw.removeprefix('LB:').removesuffix('.US').replace('.', '-')


def compare(snapshot, reference, allow_date_mismatch=False):
    source = reference['rows']
    dates = {r.get('rollingExcess', {}).get('w1', {}).get('to') for r in source}
    if len(dates) != 1 or not all(isinstance(day, str) for day in dates):
        raise ValueError('Reference has mixed or missing observation dates')
    reference_date = next(iter(dates))
    same_date = dates == {snapshot['asOf']}
    if not same_date and not allow_date_mismatch:
        raise ValueError(f'Different observation dates: reference {dates}, LokiRS {snapshot["asOf"]}; comparison stopped')
    target = {symbol(r['symbol']): r for r in source}
    if len(target) != len(source):
        raise ValueError('Reference contains duplicate normalized symbols')
    actual = {r['symbol']: r for r in snapshot['rows'] if r.get('rank') is not None and isinstance(r.get('score'), (int, float)) and math.isfinite(r['score'])}
    common = set(target) & set(actual)
    if len(common) < 2:
        raise ValueError('Too few common ranked symbols')
    # Actual displayed order is the source array. Its separate dailyRank field
    # belongs to historical bookkeeping and can differ from the visible score sort.
    target_order = [symbol(r['symbol']) for r in source if symbol(r['symbol']) in common]
    actual_order = [r['symbol'] for r in sorted(actual.values(), key=lambda r:r['rank']) if r['symbol'] in common]
    rank_a, rank_b = {s:i+1 for i,s in enumerate(target_order)}, {s:i+1 for i,s in enumerate(actual_order)}
    rows = [{'symbol':s,'referenceRankCommon':rank_a[s],'lokiRankCommon':rank_b[s],
             'referenceDisplayRank':next(i+1 for i,r in enumerate(source) if symbol(r['symbol']) == s),
             'lokiDisplayRank':actual[s]['rank'],'rankDifference':rank_b[s]-rank_a[s],
             'referenceScore':target[s]['score'],'lokiScore':actual[s]['score']} for s in target_order]
    for row in rows:
        s = row['symbol']
        row['scoreDifference'] = row['lokiScore'] - row['referenceScore']
        row['referencePrice'] = target[s].get('price')
        row['lokiPrice'] = actual[s].get('price')
        reference_parts = {**(target[s].get('intra') or {}),
                           **{key: target[s].get('excess', {}).get(name) for key, name in [('1','d1'),('5','d5'),('20','d20')]}}
        row['inputDifferences'] = {key: actual[s].get('scoreInputs', {}).get(key) - value
                                  for key, value in reference_parts.items()
                                  if isinstance(value, (int,float)) and isinstance(actual[s].get('scoreInputs', {}).get(key), (int,float))}
    differences = [abs(r['rankDifference']) for r in rows]
    n = len(rows)
    score_errors = [abs(r['scoreDifference']) for r in rows]
    input_summary = {}
    for key in ['h1','h4','1','5','20']:
        values = [r['inputDifferences'][key] for r in rows if key in r['inputDifferences']]
        if values:
            input_summary[key] = {'n':len(values), 'maePP':statistics.mean(map(abs,values)), 'biasPP':statistics.mean(values)}
    return {'asOf':snapshot['asOf'],'referenceAsOf':reference_date,'lokiAsOf':snapshot['asOf'],
            'comparisonType':'same-session-independent-prices' if same_date else 'cross-date-published-snapshots',
            'formulaAccuracyComparable':same_date,
            'referenceUrl':REFERENCE_URL,'referenceUniverse':len(source),'lokiUniverse':len(snapshot['rows']),
            'commonRanked':n,'referenceOnly':sorted(set(target)-common),'lokiOnly':sorted(set(actual)-common),
            'method':'Re-rank both visible default orders within the same common-symbol cohort; no unmatched symbols shift ranks.',
            'meanAbsoluteRankDifference':statistics.mean(differences),'medianAbsoluteRankDifference':statistics.median(differences),
            'maxAbsoluteRankDifference':max(differences),'spearman':1-6*sum(r['rankDifference']**2 for r in rows)/(n*(n*n-1)),
            'topOverlap':{str(k):len(set(target_order[:k]) & set(actual_order[:k])) for k in [10,20,50,100] if n >= k},
            'scoreMeanAbsoluteError':statistics.mean(score_errors),'scoreMedianAbsoluteError':statistics.median(score_errors),
            'scoreMaxAbsoluteError':max(score_errors),'scoreP95AbsoluteError':sorted(score_errors)[math.ceil(.95*n)-1],
            'scoreWithin005':sum(e<=.05 for e in score_errors),'scoreWithin010':sum(e<=.1 for e in score_errors),
            'inputDifferences':input_summary,
            'rows':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=ROOT/'data/latest.json')
    parser.add_argument('--reference-html', type=Path, help='Use a locally saved public page instead of downloading it')
    parser.add_argument('--output', type=Path, help='Optional JSON report path')
    parser.add_argument('--csv', type=Path, help='Optional per-stock CSV report')
    parser.add_argument('--allow-date-mismatch', action='store_true', help='Describe stale published snapshots; explicitly not a formula accuracy test')
    args = parser.parse_args()
    if args.reference_html:
        raw = args.reference_html.read_bytes()
    else:
        with urlopen(Request(REFERENCE_URL, headers={'User-Agent':'LokiRS/1.3.0 (public ranking comparison)'}), timeout=30) as response:
            raw = response.read()
    report = compare(json.loads(args.snapshot.read_text()), read_public_reference(raw),args.allow_date_mismatch)
    report['checkedAt'] = datetime.now(timezone.utc).isoformat()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        fields=['symbol','referenceAsOf','lokiAsOf','comparisonType','referenceRankCommon','lokiRankCommon','referenceDisplayRank','lokiDisplayRank','rankDifference','referenceScore','lokiScore','scoreDifference','referencePrice','lokiPrice','h1DifferencePP','h4DifferencePP','d1DifferencePP','d5DifferencePP','d20DifferencePP']
        with args.csv.open('w',encoding='utf-8-sig',newline='') as output:
            writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore');writer.writeheader()
            for row in report['rows']:
                writer.writerow({**row,**{key:report[key] for key in ['referenceAsOf','lokiAsOf','comparisonType']},
                                 **{f'{label}DifferencePP':row['inputDifferences'].get(key) for key,label in [('h1','h1'),('h4','h4'),('1','d1'),('5','d5'),('20','d20')]}})
    print(json.dumps({k:v for k,v in report.items() if k != 'rows'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
