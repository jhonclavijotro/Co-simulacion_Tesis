"""Fetch abstracts (Semantic Scholar batch API, with backoff) for the verified corpus."""
import json, time, requests

MAILTO = "feynman.research@example.org"
raw = json.load(open("notes/cdva_dois.json", encoding="utf-8"))
dois = [r["doi"] for r in raw if r["status"] == "OK"]
url = "https://api.semanticscholar.org/graph/v1/paper/batch"
params = {"fields": "title,abstract,venue,year,externalIds,citationCount,openAccessPdf"}
out = {}
for i in range(0, len(dois), 20):
    chunk = dois[i:i+20]
    for attempt in range(5):
        r = requests.post(url, params=params, json={"ids": [f"DOI:{d}" for d in chunk]}, timeout=60,
                          headers={"User-Agent": f"litreview (mailto:{MAILTO})"})
        if r.status_code == 200:
            for d, item in zip(chunk, r.json()):
                out[d] = item
            break
        print(f"  batch {i} -> HTTP {r.status_code}; sleeping {8*(attempt+1)}s")
        time.sleep(8 * (attempt + 1))
    time.sleep(4)
json.dump(out, open("notes/cdva_abstracts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
got = sum(1 for v in out.values() if v and v.get("abstract"))
print(f"abstracts obtained: {got}/{len(dois)}")
for d, v in out.items():
    if not v or not v.get("abstract"):
        print("MISSING", d)
