import json, urllib.request, urllib.parse, time

dois = [r["doi_input"] for r in json.load(open("D:/Antigravity/Projects/Tesis_Grado/notes/doi_verification.json", encoding="utf-8"))]
out=[]
for d in dois:
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{urllib.parse.quote(d)}?fields=title,abstract,year,venue,citationCount,publicationTypes,externalIds"
    rec={"doi":d}
    try:
        req=urllib.request.Request(url, headers={"User-Agent":"feynman-litreview/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            m=json.load(r)
        rec.update({"status":"OK","title":m.get("title"),"year":m.get("year"),"venue":m.get("venue"),
                    "citations":m.get("citationCount"),"abstract":m.get("abstract"),"ids":m.get("externalIds")})
    except Exception as e:
        rec.update({"status":"ERROR","error":str(e)})
    out.append(rec); print(d, rec["status"], (rec.get("abstract") or "")[:80].replace("\n"," "))
    time.sleep(1.2)
json.dump(out, open("D:/Antigravity/Projects/Tesis_Grado/notes/abstracts.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
