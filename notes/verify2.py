import json, urllib.request, urllib.parse, time

def get(url, hdr=True):
    req = urllib.request.Request(url, headers={"User-Agent":"feynman-litreview/1.0 (mailto:research@example.org)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)

new = [
 "10.1109/TCYB.2022.3218026",
 "10.1016/j.epsr.2025.111646",
 "10.1016/j.apenergy.2024.124722",
 "10.1109/TCSI.2024.3449896",
 "10.1109/TCYB.2024.3364820",
 "10.1016/j.segan.2025.102068",
 "10.1049/rpg2.70055",
 "10.3390/en18071755",
 "10.1109/JSYST.2024.3469932",
 "10.1016/j.amc.2024.129184",
]
recs=[]
for d in new:
    rec={"doi":d}
    try:
        m = get("https://api.crossref.org/works/"+urllib.parse.quote(d))["message"]
        rec.update({"status":"OK","title":(m.get("title") or [""])[0],
                    "container":(m.get("container-title") or [""])[0],
                    "issued":"-".join(str(x) for x in m.get("issued",{}).get("date-parts",[[None]])[0] if x),
                    "volume":m.get("volume"),"issue":m.get("issue"),"page":m.get("page"),
                    "authors":[ (a.get("given","")+" "+a.get("family","")).strip() for a in m.get("author",[]) ]})
    except Exception as e:
        rec.update({"status":"ERROR","error":str(e)})
    print(json.dumps(rec, ensure_ascii=False))
    recs.append(rec); time.sleep(0.5)

print("\n--- abstracts ---")
for r in recs:
    if r["status"]!="OK": continue
    try:
        a = get("https://api.semanticscholar.org/graph/v1/paper/DOI:"+urllib.parse.quote(r["doi"])+"?fields=abstract,citationCount")
        r["abstract"]=a.get("abstract"); r["citations"]=a.get("citationCount")
    except Exception as e:
        r["abstract"]=None
    print("\n>>", r["doi"], "|", r["issued"], "|", r["container"][:50], "| cit:", r.get("citations"))
    print((r.get("abstract") or "NO ABSTRACT")[:900])
    time.sleep(1.5)
json.dump(recs, open("D:/Antigravity/Projects/Tesis_Grado/notes/doi_verification_2024_2025.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)

print("\n--- counts by year ---")
for q in ['"secondary voltage control" AND consensus', '"distributed secondary control"']:
    for y in range(2018, 2026):
        url=("https://api.openalex.org/works?filter=title_and_abstract.search:"+urllib.parse.quote(q)+f",publication_year:{y}&per-page=1&mailto=research@example.org")
        try:
            c=get(url)["meta"]["count"]
        except Exception as e:
            c="ERR"
        print(f"{q} | {y} | {c}")
