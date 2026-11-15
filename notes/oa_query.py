import json, urllib.request, urllib.parse, sys, time

def oa(q, y1=2023, y2=2025, n=20, extra=""):
    url = ("https://api.openalex.org/works?search=" + urllib.parse.quote(q)
           + f"&filter=publication_year:{y1}-{y2}" + extra
           + f"&per-page={n}&sort=cited_by_count:desc&mailto=research@example.org")
    req = urllib.request.Request(url, headers={"User-Agent":"feynman-litreview/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        d = json.load(r)
    print(f"\n### {q}  [total={d['meta']['count']}]")
    for w in d["results"]:
        print(f"- {w.get('publication_year')} | {(w.get('title') or '')[:105]} | {((w.get('primary_location') or {}).get('source') or {}).get('display_name','')[:45]} | doi:{w.get('doi')} | cit:{w.get('cited_by_count')}")
    return d

qs = [
 "predefined-time secondary control microgrid consensus",
 "resilient distributed secondary voltage control AC microgrid cyber attack",
 "distributed secondary voltage control communication delay microgrid consensus",
]
for q in qs:
    try: oa(q)
    except Exception as e: print("ERR", q, e)
    time.sleep(1)
