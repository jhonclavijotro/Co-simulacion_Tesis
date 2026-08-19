"""
LaTeX Parser and Static Analyzer for LaTeX MCP Server.
Parses document structures (sections, environments, labels, citations)
and performs static validation (environment matching, brace balance, bib integrity).
"""

import os
import re
from typing import Dict, List, Any, Optional

SECTION_REGEX = re.compile(r'\\(chapter|section|subsection|subsubsection|paragraph)\*?\{([^}]+)\}')
ENV_BEGIN_REGEX = re.compile(r'\\begin\{([^}]+)\}')
ENV_END_REGEX = re.compile(r'\\end\{([^}]+)\}')
LABEL_REGEX = re.compile(r'\\label\{([^}]+)\}')
REF_REGEX = re.compile(r'\\(ref|eqref|pageref|autoref|cref)\{([^}]+)\}')
CITE_REGEX = re.compile(r'\\(cite|citep|citet|autocite|parencite)\{([^}]+)\}')
INPUT_REGEX = re.compile(r'\\(input|include)\{([^}]+)\}')
PACKAGE_REGEX = re.compile(r'\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}')


def parse_latex_file(file_path: str) -> Dict[str, Any]:
    """
    Parses a single LaTeX file and extracts structural information.
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    sections = []
    environments = []
    labels = []
    citations = []
    inputs = []
    packages = []

    env_stack = []

    for idx, line in enumerate(lines, 1):
        # Remove comments for regex matching
        clean_line = line.split('%')[0]

        # Packages
        for match in PACKAGE_REGEX.finditer(clean_line):
            pkgs = [p.strip() for p in match.group(1).split(',')]
            packages.extend(pkgs)

        # Sections
        for match in SECTION_REGEX.finditer(clean_line):
            sections.append({
                "type": match.group(1),
                "title": match.group(2),
                "line": idx
            })

        # Labels
        for match in LABEL_REGEX.finditer(clean_line):
            labels.append({
                "label": match.group(1),
                "line": idx
            })

        # Citations
        for match in CITE_REGEX.finditer(clean_line):
            keys = [k.strip() for k in match.group(2).split(',')]
            for k in keys:
                citations.append({
                    "key": k,
                    "line": idx
                })

        # Inputs
        for match in INPUT_REGEX.finditer(clean_line):
            inputs.append({
                "target": match.group(2),
                "line": idx
            })

        # Environments tracking
        for match in ENV_BEGIN_REGEX.finditer(clean_line):
            env_name = match.group(1)
            env_stack.append({"name": env_name, "start_line": idx})

        for match in ENV_END_REGEX.finditer(clean_line):
            env_name = match.group(1)
            if env_stack:
                start_env = env_stack.pop()
                environments.append({
                    "name": env_name,
                    "start_line": start_env["start_line"],
                    "end_line": idx,
                    "matched": start_env["name"] == env_name
                })
            else:
                environments.append({
                    "name": env_name,
                    "start_line": None,
                    "end_line": idx,
                    "matched": False
                })

    return {
        "file_path": os.path.abspath(file_path),
        "total_lines": len(lines),
        "sections": sections,
        "environments": environments,
        "labels": labels,
        "citations": citations,
        "inputs": inputs,
        "packages": list(set(packages)),
        "unclosed_environments": env_stack
    }


def validate_latex_document(file_path: str, bib_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs comprehensive static validation on a LaTeX document.
    Checks environment balance, brace matching, broken labels/citations, and common typos.
    """
    if not os.path.exists(file_path):
        return {"valid": False, "errors": [f"File not found: {file_path}"], "warnings": []}

    parsed = parse_latex_file(file_path)
    errors = []
    warnings = []

    # 1. Check unclosed environments
    if parsed.get("unclosed_environments"):
        for env in parsed["unclosed_environments"]:
            errors.append(f"Line {env['start_line']}: Environment '\\begin{{{env['name']}}}' is never closed.")

    # 2. Check unmatched end environments
    for env in parsed.get("environments", []):
        if not env.get("matched", True):
            errors.append(f"Line {env['end_line']}: '\\end{{{env['name']}}}' does not match any '\\begin{{{env['name']}}}'.")

    # 3. Check brace matching
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Strip TeX comments for brace checking
    no_comments = "\n".join([line.split('%')[0] for line in content.splitlines()])

    brace_count = 0
    bracket_count = 0
    for i, ch in enumerate(no_comments):
        if ch == '{' and (i == 0 or no_comments[i-1] != '\\'):
            brace_count += 1
        elif ch == '}' and (i == 0 or no_comments[i-1] != '\\'):
            brace_count -= 1
            if brace_count < 0:
                errors.append("Unmatched closing brace '}' found in document.")
                break

    if brace_count > 0:
        errors.append(f"Document has {brace_count} unclosed opening brace(s) '{{'.")

    # 4. Check labels and internal cross-references
    defined_labels = {l["label"] for l in parsed.get("labels", [])}
    for idx, line in enumerate(content.splitlines(), 1):
        clean_line = line.split('%')[0]
        for match in REF_REGEX.finditer(clean_line):
            ref_key = match.group(2)
            if ref_key not in defined_labels:
                warnings.append(f"Line {idx}: Reference '\\ref{{{ref_key}}}' points to undefined label '{ref_key}'.")

    # 5. Check BibTeX references if bib_path is given or exists
    bib_keys = set()
    if bib_path and os.path.exists(bib_path):
        with open(bib_path, "r", encoding="utf-8", errors="replace") as bf:
            bib_content = bf.read()
            bib_keys = set(re.findall(r'@\w+\s*\{\s*([^,\s]+)', bib_content))

    if bib_keys:
        for cite in parsed.get("citations", []):
            if cite["key"] not in bib_keys:
                warnings.append(f"Line {cite['line']}: Citation '\\cite{{{cite['key']}}}' not found in bibliography '{os.path.basename(bib_path)}'.")

    # 6. Check common syntax issues (e.g. unescaped _ or & outside tabular/math)
    for idx, line in enumerate(content.splitlines(), 1):
        clean_line = line.split('%')[0]
        # Check for unescaped % inside text (which truncates line)
        if re.search(r'(?<!\\)%', line) and idx < 10 and r'%' in line:
            pass # normal comment
        # Check for unescaped _ in non-math lines
        if '_' in clean_line and '$' not in clean_line and '\\' not in clean_line and r'\_' not in clean_line:
            if not any(env in clean_line for env in ['equation', 'align', 'label', 'cite', 'input', 'include', 'includegraphics']):
                warnings.append(f"Line {idx}: Unescaped underscore '_' found outside math mode.")

    is_valid = len(errors) == 0
    return {
        "file_path": os.path.abspath(file_path),
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "summary": f"Validation complete: {len(errors)} error(s), {len(warnings)} warning(s)."
    }
