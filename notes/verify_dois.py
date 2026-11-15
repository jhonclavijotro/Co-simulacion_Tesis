import json, urllib.request, sys, time

DOIS = [
 "10.1109/TSG.2018.2834951",
 "10.1109/TPWRS.2018.2870058",
 "10.1109/TEC.2018.2878690",
 "10.1109/TSG.2019.2916727",
 "10.1109/TPWRS.2019.2950629",
 "10.1109/TPEL.2019.2951694",
 "10.1109/TCYB.2020.3003690",
 "10.1109/TPWRS.2020.3012026",
 "10.1109/ACCESS.2020.3004340",
 "10.1109/TPWRS.2021.3059158",
 "10.1109/TPWRS.2021.3110263",
 "10.1109/OAJPE.2021.3056507",
 "10.1016/j.ijepes.2021.107251",
 "10.1109/TSG.2022.3212193",
 "10.1109/TSG.2023.3263107",
 "10.1109/JSYST.2023.3284403",
 "10.17775/CSEEJPES.2020.07140",
 "10.1109/JAS.2023.123891",
 "10.1109/TIA.2025.3585857",
 "10.1109/TCSII.2025.3627624",
 "10.1109/TCYB.2023.3276800",
 "10.1016/j.ijepes.2022.108636",
 "10.1007/s00202-021-01251-3",
 "10.1109/TPEL.2020.3031539",
]

out = []
for d in DOIS:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(d)
    rec = {"doi_input": d}
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"feynman-litreview/1.0 (mailto:research@example.org)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            m = json.load(r)["message"]
        def dp(k):
            v = m.get(k, {}).get("date-parts", [[None]])[0]
            return "-".join(str(x) for x in v if x)
        rec.update({
            "status": "OK",
            "doi": m.get("DOI"),
            "title": (m.get("title") or [""])[0],
            "container": (m.get("container-title") or [""])[0],
            "type": m.get("type"),
            "issued": dp("issued"),
            "print": dp("published-print"),
            "online": dp("published-online"),
            "volume": m.get("volume"),
            "issue": m.get("issue"),
            "page": m.get("page"),
            "authors": [ (a.get("given","")+" "+a.get("family","")).strip() for a in m.get("author",[]) ],
            "url": m.get("URL"),
        })
    except Exception as e:
        rec.update({"status": "ERROR", "error": str(e)})
    out.append(rec)
    print(json.dumps(rec, ensure_ascii=False))
    time.sleep(0.4)

with open("D:/Antigravity/Projects/Tesis_Grado/notes/doi_verification.json","w",encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
