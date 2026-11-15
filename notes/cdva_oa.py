"""OpenAlex sweep for the review `consenso-distribuido-voltaje-ac`.

Writes raw JSON to notes/cdva_oa_raw.json and a compact human-readable
summary to notes/cdva_oa_summary.txt.

Re-runnable:  python notes/cdva_oa.py
"""
import json
import time
import urllib.parse

import requests

MAILTO = "feynman.research@example.org"
BASE = "https://api.openalex.org/works"

# ---------------------------------------------------------------- queries
# (label, filter expression, sort, per-page)
QUERIES = [
    # A. census (title+abstract search, counts by year)
    ("census_dsc", 'title_and_abstract.search:"distributed secondary control"', None, 1),
    ("census_svc", 'title_and_abstract.search:"secondary voltage control"', None, 1),
    ("census_vrest", 'title_and_abstract.search:"voltage restoration",title_and_abstract.search:microgrid', None, 1),
    ("census_sens", 'title_and_abstract.search:"voltage sensitivity"', None, 1),

    # B. recent frontier retrieval
    ("recent_predef", 'title_and_abstract.search:"predefined-time",title_and_abstract.search:microgrid', "cited_by_count:desc", 25),
    ("recent_fixed", 'title_and_abstract.search:"fixed-time",title_and_abstract.search:"secondary control"', "cited_by_count:desc", 25),
    ("recent_etc", 'title_and_abstract.search:"event-triggered",title_and_abstract.search:"secondary voltage"', "cited_by_count:desc", 25),
    ("recent_resilient", 'title_and_abstract.search:resilient,title_and_abstract.search:"secondary voltage"', "cited_by_count:desc", 25),

    # C. decisive novelty check: network-aware / sensitivity / critical bus
    ("q3_sens_mg", 'title_and_abstract.search:"voltage sensitivity",title_and_abstract.search:microgrid', "cited_by_count:desc", 25),
    ("q3_sens_consensus", 'title_and_abstract.search:"sensitivity",title_and_abstract.search:"distributed voltage control"', "cited_by_count:desc", 25),
    ("q3_criticalbus", 'title_and_abstract.search:"critical bus",title_and_abstract.search:microgrid', "cited_by_count:desc", 25),
    ("q3_pilotbus", 'title_and_abstract.search:"pilot bus"', "cited_by_count:desc", 25),
    ("q3_networkaware", 'title_and_abstract.search:"network-aware",title_and_abstract.search:voltage', "cited_by_count:desc", 25),
    ("q3_adn_sens", 'title_and_abstract.search:"voltage sensitivity",title_and_abstract.search:"distribution network"', "cited_by_count:desc", 25),

    # D. the structural trade-off
    ("tradeoff", 'title_and_abstract.search:"reactive power sharing",title_and_abstract.search:"voltage restoration"', "cited_by_count:desc", 25),
]


def get(params, tries=3):
    last = None
    for _ in range(tries):
        try:
            r = requests.get(BASE, params=params, timeout=45,
                             headers={"User-Agent": f"review-bot (mailto:{MAILTO})"})
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(2)
    raise RuntimeError(f"OpenAlex failed: {last}")


def short(w):
    src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
    return {
        "id": w.get("id", "").rsplit("/", 1)[-1],
        "doi": w.get("doi"),
        "year": w.get("publication_year"),
        "title": w.get("title"),
        "venue": src,
        "cites": w.get("cited_by_count"),
        "type": w.get("type"),
        "oa": (w.get("open_access") or {}).get("oa_url"),
        "abstract": (w.get("abstract_inverted_index") is not None),
    }


def main():
    raw, lines = {}, []
    for label, filt, sort, per in QUERIES:
        params = {"filter": filt, "per-page": 1, "mailto": MAILTO}
        meta = get(params)
        total = meta["meta"]["count"]
        by_year = {}
        if label.startswith("census"):
            for y in range(2012, 2027):
                p = {"filter": f"{filt},publication_year:{y}", "per-page": 1, "mailto": MAILTO}
                by_year[y] = get(p)["meta"]["count"]
        params = {"filter": filt, "per-page": per, "mailto": MAILTO}
        if sort:
            params["sort"] = sort
            params["filter"] = filt + ",publication_year:>2022"
        res = get(params)
        recs = [short(w) for w in res["results"]]
        raw[label] = {"filter": filt, "total": total, "by_year": by_year, "records": recs}
        lines.append(f"\n### {label}  (total={total})  filter: {filt}")
        if by_year:
            lines.append("year counts: " + ", ".join(f"{y}:{c}" for y, c in by_year.items()))
        for r in recs:
            lines.append(f"  {r['year']} | {r['cites']:>5} | {str(r['title'])[:120]} | {r['venue']} | {r['doi']}")
        time.sleep(0.6)

    with open("notes/cdva_oa_raw.json", "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=1)
    with open("notes/cdva_oa_summary.txt", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
