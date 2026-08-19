"""
BibTeX Bibliography Manager for LaTeX MCP Server.
Parses, updates, validates, and queries BibTeX references with APA and publication year rules.
"""

import os
import re
from typing import Dict, List, Any, Optional

BIB_ENTRY_REGEX = re.compile(
    r'@(\w+)\s*\{\s*([^,\s]+)\s*,\s*(.*?)\n\}',
    re.DOTALL
)

FIELD_REGEX = re.compile(r'(\w+)\s*=\s*[\{"]?(.*?)[\}"]?\s*(?:,|\n|$)')


def parse_bib_file(bib_path: str) -> Dict[str, Any]:
    """
    Parses a .bib file and returns all entries as structured dictionaries.
    """
    if not os.path.exists(bib_path):
        return {"entries": [], "count": 0, "error": f"File not found: {bib_path}"}

    with open(bib_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    entries = []
    # Find all entry blocks @type{key, ...}
    blocks = re.findall(r'(@\w+\s*\{\s*[^,]+,[\s\S]*?\n\s*\})', content)

    for block in blocks:
        header_match = re.match(r'@(\w+)\s*\{\s*([^,\s]+)\s*,', block)
        if not header_match:
            continue

        entry_type = header_match.group(1).lower()
        cite_key = header_match.group(2).strip()

        fields = {}
        for line in block.splitlines():
            field_match = re.search(r'(\w+)\s*=\s*[\{"]?([^}"\n]+)[\}"]?\s*,?', line)
            if field_match:
                fname = field_match.group(1).lower()
                fval = field_match.group(2).strip().rstrip(',')
                fields[fname] = fval

        entries.append({
            "type": entry_type,
            "key": cite_key,
            "fields": fields,
            "raw": block.strip()
        })

    return {
        "file_path": os.path.abspath(bib_path),
        "count": len(entries),
        "entries": entries
    }


def add_bib_entry(
    bib_path: str,
    bibtex_code: str,
    enforce_min_year: int = 2022
) -> Dict[str, Any]:
    """
    Validates and appends a BibTeX entry to a .bib file.
    Enforces minimum publication year rule (e.g. >= 2022).
    """
    # Extract entry type and key
    header_match = re.search(r'@(\w+)\s*\{\s*([^,\s]+)\s*,', bibtex_code)
    if not header_match:
        return {"success": False, "error": "Invalid BibTeX syntax: Could not parse header @type{key,"}

    cite_key = header_match.group(2).strip()

    # Extract year field if present
    year_match = re.search(r'year\s*=\s*[\{"]?(\d{4})[\}"]?', bibtex_code, re.IGNORECASE)
    year = int(year_match.group(1)) if year_match else None

    if year and year < enforce_min_year:
        return {
            "success": False,
            "error": f"Publication year {year} is prior to required minimum year {enforce_min_year}."
        }

    # Check for existing key
    existing = parse_bib_file(bib_path)
    if any(e["key"] == cite_key for e in existing.get("entries", [])):
        return {
            "success": False,
            "error": f"Citation key '{cite_key}' already exists in bibliography."
        }

    os.makedirs(os.path.dirname(os.path.abspath(bib_path)), exist_ok=True)
    with open(bib_path, "a", encoding="utf-8") as f:
        f.write("\n" + bibtex_code.strip() + "\n")

    return {
        "success": True,
        "key": cite_key,
        "year": year,
        "message": f"Successfully added '{cite_key}' to {os.path.basename(bib_path)}."
    }


def validate_bib_file(bib_path: str) -> Dict[str, Any]:
    """
    Validates all entries in a .bib file for required fields and formatting.
    """
    parsed = parse_bib_file(bib_path)
    if "error" in parsed:
        return {"valid": False, "errors": [parsed["error"]], "warnings": []}

    errors = []
    warnings = []
    seen_keys = set()

    required_fields_map = {
        "article": ["author", "title", "journal", "year"],
        "book": ["author", "title", "publisher", "year"],
        "inproceedings": ["author", "title", "booktitle", "year"],
        "techreport": ["author", "title", "institution", "year"],
    }

    for entry in parsed["entries"]:
        key = entry["key"]
        etype = entry["type"]
        fields = entry["fields"]

        # Duplicate key check
        if key in seen_keys:
            errors.append(f"Duplicate citation key found: '{key}'")
        seen_keys.add(key)

        # Required fields check
        reqs = required_fields_map.get(etype, ["author", "title", "year"])
        for req in reqs:
            if req not in fields:
                warnings.append(f"Entry '{key}' (@{etype}) missing recommended field '{req}'.")

        # DOI check recommendation
        if "doi" not in fields and etype == "article":
            warnings.append(f"Article '{key}' missing DOI reference.")

    return {
        "file_path": os.path.abspath(bib_path),
        "total_entries": len(parsed["entries"]),
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }
