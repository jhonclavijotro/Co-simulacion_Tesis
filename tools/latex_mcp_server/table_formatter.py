"""
Table Formatter for LaTeX MCP Server.
Converts JSON/CSV tabular data into professional, publication-ready LaTeX tables using booktabs.
"""

import json
import csv
import io
from typing import List, Dict, Any, Union, Optional


def generate_latex_table(
    data: Union[List[List[Any]], List[Dict[str, Any]], str],
    caption: str = "Tabla de Resultados",
    label: str = "tab:resultados",
    headers: Optional[List[str]] = None,
    alignments: Optional[str] = None,
    use_booktabs: bool = True,
    centering: bool = True,
    font_size: Optional[str] = None
) -> str:
    """
    Generates a clean LaTeX table code string from tabular data.
    """
    rows = []
    
    # Parse string input if CSV/JSON
    if isinstance(data, str):
        data_str = data.strip()
        if data_str.startswith("[") or data_str.startswith("{"):
            parsed = json.loads(data_str)
            if isinstance(parsed, list):
                data = parsed
        else:
            # Assume CSV
            f = io.StringIO(data_str)
            reader = csv.reader(f)
            data = list(reader)

    # Standardize data to rows list
    if isinstance(data, list) and len(data) > 0:
        if isinstance(data[0], dict):
            if not headers:
                headers = list(data[0].keys())
            for item in data:
                rows.append([str(item.get(h, "")) for h in headers])
        elif isinstance(data[0], list):
            if not headers:
                headers = [str(x) for x in data[0]]
                rows = [[str(cell) for cell in row] for row in data[1:]]
            else:
                rows = [[str(cell) for cell in row] for row in data]
    else:
        return "% Empty data provided for table generation."

    num_cols = len(headers) if headers else (len(rows[0]) if rows else 1)
    
    if not alignments:
        # Default: left align 1st column, center rest
        alignments = "l" + "c" * (num_cols - 1)

    lines = []
    lines.append(r"\begin{table}[htbp]")
    if centering:
        lines.append(r"\centering")
    if font_size:
        lines.append(rf"\{font_size}")
    lines.append(rf"\caption{{{caption}}}")
    lines.append(rf"\label{{{label}}}")
    lines.append(rf"\begin{{tabular}}{{{alignments}}}")

    if use_booktabs:
        lines.append(r"\toprule")
        if headers:
            header_str = " & ".join([rf"\textbf{{{h}}}" for h in headers]) + r" \\"
            lines.append(header_str)
            lines.append(r"\midrule")
        for row in rows:
            lines.append(" & ".join(row) + r" \\")
        lines.append(r"\bottomrule")
    else:
        lines.append(r"\hline")
        if headers:
            header_str = " & ".join([rf"\textbf{{{h}}}" for h in headers]) + r" \\ \hline"
            lines.append(header_str)
        for row in rows:
            lines.append(" & ".join(row) + r" \\")
        lines.append(r"\hline")

    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")

    return "\n".join(lines)
