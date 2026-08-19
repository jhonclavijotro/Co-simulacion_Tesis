"""
LaTeX Compilation Engine & Log Parser for LaTeX MCP Server.
Runs latexmk/pdflatex/xelatex, parses execution logs for precise diagnostics,
and provides standalone TikZ rendering.
"""

import os
import re
import subprocess
import shutil
import time
from typing import Dict, List, Any, Optional


def parse_latex_log(log_path: str) -> Dict[str, Any]:
    """
    Parses a LaTeX compiler log file and extracts structured errors and warnings.
    """
    if not os.path.exists(log_path):
        return {"errors": ["Log file not found."], "warnings": []}

    errors = []
    warnings = []

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    lines = content.splitlines()

    i = 0
    while i < len(lines):
        line = lines[i]

        # LaTeX Error line pattern
        if line.startswith("!"):
            err_msg = line.strip()
            line_num = None
            # Collect context lines
            context_lines = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith("!") and not lines[j].startswith("LaTeX Warning:"):
                context_lines.append(lines[j])
                match = re.search(r'l\.(\d+)', lines[j])
                if match:
                    line_num = int(match.group(1))
                if len(context_lines) > 5:
                    break
                j += 1
            
            errors.append({
                "message": err_msg,
                "line": line_num,
                "context": "\n".join(context_lines).strip()
            })

        # LaTeX Warning line pattern
        elif "LaTeX Warning:" in line or "Package " in line and "Warning:" in line:
            warn_msg = line.strip()
            line_num = None
            match = re.search(r'line (\d+)', line)
            if match:
                line_num = int(match.group(1))
            
            warnings.append({
                "message": warn_msg,
                "line": line_num
            })

        i += 1

    return {
        "errors": errors,
        "warnings": warnings,
        "total_errors": len(errors),
        "total_warnings": len(warnings)
    }


def compile_latex_document(
    tex_path: str,
    engine: str = "latexmk",
    output_dir: Optional[str] = None,
    clean_after: bool = False
) -> Dict[str, Any]:
    """
    Compiles a LaTeX file into a PDF document using latexmk/pdflatex/xelatex.
    """
    if not os.path.exists(tex_path):
        return {"success": False, "error": f"File not found: {tex_path}"}

    tex_dir = os.path.dirname(os.path.abspath(tex_path))
    tex_file = os.path.basename(tex_path)
    base_name = os.path.splitext(tex_file)[0]

    out_dir = os.path.abspath(output_dir) if output_dir else tex_dir
    os.makedirs(out_dir, exist_ok=True)

    start_time = time.time()

    if engine == "latexmk":
        cmd = [
            "latexmk",
            "-pdf",
            "-interaction=nonstopmode",
            "-synctex=1",
            f"-output-directory={out_dir}",
            tex_file
        ]
    elif engine == "xelatex":
        cmd = [
            "xelatex",
            "-interaction=nonstopmode",
            f"-output-directory={out_dir}",
            tex_file
        ]
    elif engine == "pdflatex":
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            f"-output-directory={out_dir}",
            tex_file
        ]
    else:
        return {"success": False, "error": f"Unsupported engine: {engine}"}

    try:
        process = subprocess.run(
            cmd,
            cwd=tex_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120
        )
        elapsed_time = round(time.time() - start_time, 2)

        pdf_path = os.path.join(out_dir, f"{base_name}.pdf")
        log_path = os.path.join(out_dir, f"{base_name}.log")

        log_diagnostics = parse_latex_log(log_path) if os.path.exists(log_path) else {"errors": [], "warnings": []}

        pdf_exists = os.path.exists(pdf_path)
        success = process.returncode == 0 and pdf_exists

        if clean_after and engine == "latexmk":
            subprocess.run(["latexmk", "-c", f"-output-directory={out_dir}", tex_file], cwd=tex_dir)

        return {
            "success": success,
            "return_code": process.returncode,
            "elapsed_seconds": elapsed_time,
            "pdf_path": pdf_path if pdf_exists else None,
            "log_path": log_path if os.path.exists(log_path) else None,
            "diagnostics": log_diagnostics,
            "raw_output_tail": process.stdout[-1500:] if process.stdout else ""
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Compilation timed out after 120 seconds."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def render_tikz_diagram(
    tikz_code: str,
    output_name: str = "diagram",
    work_dir: str = "./figures",
    fmt: str = "png"
) -> Dict[str, Any]:
    """
    Compiles a TikZ code snippet into a standalone image (PNG or SVG).
    """
    os.makedirs(work_dir, exist_ok=True)
    tex_path = os.path.join(work_dir, f"{output_name}_temp.tex")

    standalone_doc = rf"""\documentclass[tikz,border=10pt]{{standalone}}
\usepackage[utf8]{{utf8}}
\usepackage{{amsmath,amssymb}}
\usepackage{{tikz}}
\usetikzlibrary{{arrows.meta,positioning,shapes,shadows,calc}}

\begin{{document}}
{tikz_code}
\end{{document}}
"""

    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(standalone_doc)

    compile_res = compile_latex_document(tex_path, engine="pdflatex", output_dir=work_dir)
    if not compile_res["success"]:
        return {"success": False, "error": "Failed to compile TikZ code.", "diagnostics": compile_res.get("diagnostics")}

    pdf_path = compile_res["pdf_path"]
    out_file = os.path.join(work_dir, f"{output_name}.{fmt}")

    try:
        if fmt.lower() == "png":
            # Use pdftoppm to convert PDF page 1 to PNG
            cmd = ["pdftoppm", "-png", "-r", "300", "-singlefile", pdf_path, os.path.join(work_dir, output_name)]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        elif fmt.lower() == "svg":
            # Use dvisvgm or pdftocairo
            cmd = ["dvisvgm", "--pdf", f"--output={out_file}", pdf_path]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        return {
            "success": os.path.exists(out_file),
            "rendered_file": os.path.abspath(out_file),
            "fmt": fmt
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Image conversion failed: {str(e)}",
            "pdf_path": os.path.abspath(pdf_path)
        }
