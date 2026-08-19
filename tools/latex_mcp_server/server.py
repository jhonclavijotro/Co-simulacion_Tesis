"""
LaTeX MCP Server - Main MCP Tool & Resource Declarations.
Exposes clean, structured tools for creating, inspecting, editing, validating,
and compiling LaTeX documents over standard Model Context Protocol (MCP).
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from mcp.server import MCPServer

from .scaffolding import scaffold_latex_project
from .parser import parse_latex_file, validate_latex_document
from .compiler import compile_latex_document, render_tikz_diagram
from .bib_manager import parse_bib_file, add_bib_entry, validate_bib_file
from .table_formatter import generate_latex_table

app = MCPServer("latex-mcp-server")


@app.tool()
def latex_scaffold(
    target_dir: str,
    title: str = "Tesis de Grado",
    author: str = "Autor",
    doc_type: str = "thesis"
) -> str:
    """
    Creates a clean, modular LaTeX project structure (Thesis, Article, Report, Beamer).
    
    Args:
        target_dir: Directory where project files will be created.
        title: Document title.
        author: Author name.
        doc_type: Type of document ('thesis', 'article', 'beamer', 'report').
    """
    res = scaffold_latex_project(target_dir, title, author, doc_type)
    return json.dumps(res, indent=2, ensure_ascii=False)


@app.tool()
def latex_inspect(file_path: str) -> str:
    """
    Parses a LaTeX document and returns its structural AST (sections, environments, labels, citations, packages).
    
    Args:
        file_path: Path to the .tex file.
    """
    res = parse_latex_file(file_path)
    return json.dumps(res, indent=2, ensure_ascii=False)


@app.tool()
def latex_validate(file_path: str, bib_path: Optional[str] = None) -> str:
    """
    Performs static validation on a LaTeX document (unclosed environments, brace balance, broken citations/references).
    
    Args:
        file_path: Path to the .tex file.
        bib_path: Path to associated .bib bibliography file (optional).
    """
    res = validate_latex_document(file_path, bib_path)
    return json.dumps(res, indent=2, ensure_ascii=False)


@app.tool()
def latex_compile_doc(
    tex_path: str,
    engine: str = "latexmk",
    output_dir: Optional[str] = None,
    clean_after: bool = False
) -> str:
    """
    Compiles a LaTeX document using latexmk, pdflatex, or xelatex, returning detailed diagnostic errors and warnings.
    
    Args:
        tex_path: Path to main .tex file.
        engine: Compiler engine ('latexmk', 'pdflatex', 'xelatex').
        output_dir: Directory to save compiled PDF and logs (optional).
        clean_after: Whether to run cleanup for auxiliary files after compilation.
    """
    res = compile_latex_document(tex_path, engine, output_dir, clean_after)
    return json.dumps(res, indent=2, ensure_ascii=False)


@app.tool()
def latex_insert_snippet(
    file_path: str,
    content: str,
    target_section: Optional[str] = None,
    position: str = "append"
) -> str:
    """
    Safely inserts or appends a LaTeX code snippet (section, figure, table, equation) into a document file.
    
    Args:
        file_path: Path to .tex file to modify.
        content: TeX code snippet to insert.
        target_section: Name of section/chapter near which to insert snippet (optional).
        position: Insertion position ('append', 'prepend', 'after_section').
    """
    if not os.path.exists(file_path):
        return json.dumps({"success": False, "error": f"File not found: {file_path}"})

    with open(file_path, "r", encoding="utf-8") as f:
        file_content = f.read()

    new_content = file_content
    if position == "append":
        if r"\end{document}" in file_content:
            new_content = file_content.replace(r"\end{document}", f"\n{content}\n\n\\end{{document}}")
        else:
            new_content = file_content + f"\n\n{content}\n"

    elif position == "prepend":
        if r"\begin{document}" in file_content:
            new_content = file_content.replace(r"\begin{document}", f"\\begin{{document}}\n\n{content}\n")
        else:
            new_content = f"{content}\n\n" + file_content

    elif position == "after_section" and target_section:
        pattern = re.compile(rf'(\\(?:chapter|section|subsection)\*?\{{{re.escape(target_section)}\}})', re.IGNORECASE)
        match = pattern.search(file_content)
        if match:
            idx = match.end()
            new_content = file_content[:idx] + f"\n\n{content}\n" + file_content[idx:]
        else:
            new_content += f"\n\n{content}\n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return json.dumps({
        "success": True,
        "file_path": os.path.abspath(file_path),
        "message": f"Successfully inserted snippet into {os.path.basename(file_path)}."
    }, indent=2)


@app.tool()
def latex_manage_bibliography(
    bib_path: str,
    action: str,
    bibtex_code: Optional[str] = None,
    min_year: int = 2022
) -> str:
    """
    Manages BibTeX bibliography entries (list, validate, or add entry with publication year checks).
    
    Args:
        bib_path: Path to .bib file.
        action: Operation ('list', 'validate', 'add').
        bibtex_code: Raw BibTeX entry string (required for action='add').
        min_year: Minimum required publication year (default: 2022).
    """
    if action == "list":
        res = parse_bib_file(bib_path)
    elif action == "validate":
        res = validate_bib_file(bib_path)
    elif action == "add":
        if not bibtex_code:
            res = {"success": False, "error": "bibtex_code is required for 'add' action."}
        else:
            res = add_bib_entry(bib_path, bibtex_code, enforce_min_year=min_year)
    else:
        res = {"error": f"Unknown action: {action}"}

    return json.dumps(res, indent=2, ensure_ascii=False)


@app.tool()
def latex_render_tikz_preview(
    tikz_code: str,
    output_name: str = "diagram",
    work_dir: str = "./figures",
    fmt: str = "png"
) -> str:
    """
    Compiles a standalone TikZ diagram into an image file (PNG/SVG) for visual verification.
    
    Args:
        tikz_code: Complete TikZ code (e.g. '\\begin{tikzpicture} ... \\end{tikzpicture}').
        output_name: Base filename for output.
        work_dir: Target directory.
        fmt: Output format ('png', 'svg').
    """
    res = render_tikz_diagram(tikz_code, output_name, work_dir, fmt)
    return json.dumps(res, indent=2, ensure_ascii=False)


@app.tool()
def latex_build_table(
    data_csv_or_json: str,
    caption: str = "Tabla de Resultados",
    label: str = "tab:resultados",
    headers_csv: Optional[str] = None,
    alignments: Optional[str] = None
) -> str:
    """
    Converts CSV or JSON tabular data into publication-ready booktabs LaTeX table code.
    
    Args:
        data_csv_or_json: Tabular data as JSON string or CSV lines.
        caption: Table caption.
        label: Table cross-reference label.
        headers_csv: Comma-separated list of column headers (optional).
        alignments: LaTeX column alignments e.g. 'lcr' (optional).
    """
    headers = [h.strip() for h in headers_csv.split(",")] if headers_csv else None
    latex_code = generate_latex_table(
        data=data_csv_or_json,
        caption=caption,
        label=label,
        headers=headers,
        alignments=alignments
    )
    return json.dumps({"latex_table_code": latex_code}, indent=2, ensure_ascii=False)


def run_server():
    app.run()
