import json, urllib.request, urllib.parse, time

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"feynman-litreview/1.0 (mailto:research@example.org)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)

def oa_tiab(q, y1, y2, n=15, sort="cited_by_count:desc"):
    url = ("https://api.openalex.org/works?filter=title_and_abstract.search:" + urllib.parse.quote(q)
           + f",publication_year:{y1}-{y2}&per-page={n}&sort={sort}&mailto=research@example.org")
    try:
        d = get(url)
    except Exception as e:
        print("ERR", q, e); return
    print(f"\n### TIAB='{q}' {y1}-{y2} total={d['meta']['count']}")
    for w in d["results"]:
        src = ((w.get('primary_location') or {}).get('source') or {}).get('display_name','')
        print(f"- {w.get('publication_year')} | {(w.get('title') or '')[:100]} | {src[:40]} | {w.get('doi')} | cit:{w.get('cited_by_count')}")
    time.sleep(0.6)

oa_tiab('"secondary voltage control" AND consensus', 2024, 2026, 15)
oa_tiab('"secondary control" AND "predefined-time"', 2023, 2026, 15)
oa_tiab('"secondary voltage" AND resilient', 2023, 2026, 12)
oa_tiab('"secondary voltage" AND "event-triggered"', 2023, 2026, 12)

# Crossref bibliographic for missing Yang paper
cq = "Event-Triggered Distributed Secondary Control With Model-Free Predictive Compensation in AC/DC Networked Microgrids"
url = "https://api.crossref.org/works?query.bibliographic=" + urllib.parse.quote(cq) + "&rows=5&select=DOI,title,container-title,issued"
print("\n### CROSSREF bibliographic:", cq)
try:
    for it in get(url)["message"]["items"]:
        print("-", it.get("DOI"), "|", (it.get("title") or [""])[0][:110], "|", (it.get("container-title") or [""])[0][:40], "|", it.get("issued",{}).get("date-parts"))
except Exception as e:
    print("ERR", e)
