"""Crossref DOI verification for the corpus of `consenso-distribuido-voltaje-ac`.

Every DOI used in the review must resolve here. Output:
  notes/cdva_dois.json  (exact metadata)
  compact stdout table  (year | venue vol(iss):pages | title | doi)

Re-runnable: python notes/cdva_verify.py
"""
import json
import time

import requests

MAILTO = "feynman.research@example.org"

DOIS = [
    # anchors
    "10.1109/TIE.2015.2436879", "10.1109/TPEL.2019.2951694", "10.1109/TPWRS.2020.3012026",
    "10.1109/TSG.2018.2834951", "10.1109/TPWRS.2019.2950629", "10.1109/TCYB.2020.3003690",
    # time-guaranteed family
    "10.1109/TPWRS.2022.3209981", "10.1109/TIA.2025.3585857", "10.1109/TII.2026.3693673",
    "10.35833/MPCE.2025.000738", "10.1063/5.0310143", "10.1109/JIOT.2026.3682341",
    "10.1016/j.epsr.2026.112848", "10.1049/rpg2.70055", "10.1109/TIE.2026.3651283",
    # critical bus / network aware
    "10.1109/TII.2023.3331303", "10.1109/TIE.2025.3610725", "10.1016/j.automatica.2026.113022",
    "10.3390/en18205382", "10.1016/j.epsr.2023.110015", "10.1016/j.apenergy.2024.122846",
    "10.1109/TSG.2025.3540416", "10.1109/TSG.2023.3292939",
    # voltage / reactive-power trade-off
    "10.1016/j.epsr.2023.109729", "10.1109/TII.2025.3593883", "10.1016/j.epsr.2024.110342",
    "10.1016/j.egyr.2022.12.039",
    # communication
    "10.1109/TPWRS.2021.3110263", "10.1109/TCYB.2024.3364820", "10.1109/TSG.2022.3212193",
    "10.3389/fenrg.2024.1468496", "10.3389/fenrg.2023.1277198", "10.3390/en18071755",
    # resilience
    "10.1109/TCYB.2022.3218026", "10.1109/TCSI.2024.3449896", "10.17775/CSEEJPES.2020.07140",
    "10.1109/TSG.2025.3646998", "10.1109/TNSE.2025.3595571",
    # hardware / validation
    "10.1038/s41598-026-64236-x", "10.1016/j.epsr.2026.113933", "10.1109/TASE.2025.3650604",
    "10.1109/TIE.2025.3645452",
]


def fetch(doi):
    url = f"https://api.crossref.org/works/{doi}"
    for _ in range(3):
        try:
            r = requests.get(url, timeout=40,
                             headers={"User-Agent": f"litreview (mailto:{MAILTO})"})
            if r.status_code == 200:
                return {"doi": doi, "status": "OK", "msg": r.json()["message"]}
            if r.status_code in (404, 400):
                return {"doi": doi, "status": f"HTTP {r.status_code}"}
        except Exception as exc:  # noqa: BLE001
            last = repr(exc)
        time.sleep(2)
    return {"doi": doi, "status": "ERROR"}


def main():
    rows, out = [], []
    for doi in DOIS:
        rec = fetch(doi)
        out.append(rec)
        if rec["status"] != "OK":
            rows.append(f"FAIL {doi} -> {rec['status']}")
            continue
        m = rec["msg"]
        title = (m.get("title") or ["?"])[0].replace("\n", " ")
        venue = (m.get("container-title") or ["?"])[0]
        issued = m.get("issued", {}).get("date-parts", [[None]])[0]
        yr = issued[0] if issued else None
        rows.append(
            f"{yr} | {venue[:44]:44} {m.get('volume')}({m.get('issue')}):{m.get('page')} "
            f"| {title[:88]} | {m.get('DOI')}"
        )
        time.sleep(0.4)
    with open("notes/cdva_dois.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("\n".join(rows))
    ok = sum(1 for r in out if r["status"] == "OK")
    print(f"\nRESOLVED {ok}/{len(DOIS)}")


if __name__ == "__main__":
    main()
