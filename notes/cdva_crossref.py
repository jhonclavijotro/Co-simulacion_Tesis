"""Crossref bibliographic sweep (compact output) for `consenso-distribuido-voltaje-ac`.

Re-runnable:  python notes/cdva_crossref.py
Writes: notes/cdva_crossref_raw.json  (full items)  and prints one line/record.
"""
import json
import time

import requests

MAILTO = "feynman.research@example.org"
URL = "https://api.crossref.org/works"

QUERIES = [
    ("Q3a_sens_mg", "distributed consensus voltage control microgrid voltage sensitivity matrix"),
    ("Q3b_critical_bus", "critical bus voltage control microgrid distributed consensus"),
    ("Q3c_adn_sens", "sensitivity-based distributed voltage control active distribution network"),
    ("Q1_predef", "predefined-time distributed secondary voltage control microgrid"),
    ("Q1_fixed", "fixed-time consensus secondary voltage control microgrid"),
    ("Q2_tradeoff", "reactive power sharing voltage restoration trade-off microgrid consensus"),
    ("Q4_event", "event-triggered distributed secondary voltage control microgrid"),
    ("Q4_delay", "distributed secondary voltage control microgrid communication delay"),
    ("Q5_resilient", "resilient distributed secondary voltage control microgrid cyber attack"),
    ("Q6_network_aware", "network-aware distributed voltage control microgrid line impedance"),
]


def q(label, text, rows=12, from_year=2023):
    params = {
        "query.bibliographic": text,
        "rows": rows,
        "filter": f"from-pub-date:{from_year}-01-01,type:journal-article",
        "select": "DOI,title,container-title,issued,volume,issue,page,author,is-referenced-by-count",
        "mailto": MAILTO,
    }
    for attempt in range(3):
        try:
            r = requests.get(URL, params=params, timeout=45,
                             headers={"User-Agent": f"litreview (mailto:{MAILTO})"})
            if r.status_code == 200:
                return r.json()["message"]["items"]
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3)
    return []


def main():
    out, lines = {}, []
    for label, text in QUERIES:
        items = q(label, text)
        out[label] = {"query": text, "items": items}
        lines.append(f"\n### {label}  ::  {text}")
        for it in items:
            t = (it.get("title") or ["?"])[0]
            j = (it.get("container-title") or ["?"])[0]
            d = it.get("issued", {}).get("date-parts", [[None]])[0]
            yr = d[0] if d else None
            vol, iss = it.get("volume"), it.get("issue")
            pg = it.get("page")
            cites = it.get("is-referenced-by-count")
            doi = it.get("DOI")
            lines.append(f"  {yr} | {cites:>4} | {t[:105]} | {j[:38]} {vol}({iss}):{pg} | {doi}")
        time.sleep(1)
    with open("notes/cdva_crossref_raw.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
