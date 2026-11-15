"""Crossref publication counts per year for three queries (OpenAlex was rate-limited)."""
import json, time, requests
M="feynman.research@example.org"; U="https://api.crossref.org/works"
Q={"q1":"distributed secondary voltage control microgrid",
   "q2":"consensus secondary control microgrid voltage",
   "q3":"voltage sensitivity distributed voltage control distribution network"}
res={}
for k,q in Q.items():
    res[k]={"query":q,"by_year":{}}
    for y in range(2018,2027):
        p={"query.bibliographic":q,"rows":0,"filter":f"from-pub-date:{y}-01-01,until-pub-date:{y}-12-31,type:journal-article","mailto":M}
        for _ in range(3):
            r=requests.get(U,params=p,timeout=40,headers={"User-Agent":f"litreview (mailto:{M})"})
            if r.status_code==200:
                res[k]["by_year"][y]=r.json()["message"]["total-results"]; break
            time.sleep(2)
        time.sleep(0.5)
json.dump(res,open("notes/cdva_counts.json","w",encoding="utf-8"),indent=1)
for k,v in res.items():
    print(k, v["query"])
    print("   "+", ".join(f"{y}:{c}" for y,c in v["by_year"].items()))
