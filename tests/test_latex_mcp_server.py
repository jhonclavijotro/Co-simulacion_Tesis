"""
Unit and integration tests for LaTeX MCP Server tools.
"""

import os
import shutil
import pytest
import tempfile

from tools.latex_mcp_server.scaffolding import scaffold_latex_project
from tools.latex_mcp_server.parser import parse_latex_file, validate_latex_document
from tools.latex_mcp_server.compiler import compile_latex_document, render_tikz_diagram
from tools.latex_mcp_server.bib_manager import parse_bib_file, add_bib_entry, validate_bib_file
from tools.latex_mcp_server.table_formatter import generate_latex_table


@pytest.fixture
def temp_project_dir():
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_scaffold_thesis(temp_project_dir):
    res = scaffold_latex_project(temp_project_dir, title="Test Thesis", author="Test Author", doc_type="thesis")
    assert res["status"] == "success"
    assert os.path.exists(os.path.join(temp_project_dir, "main.tex"))
    assert os.path.exists(os.path.join(temp_project_dir, "references.bib"))
    assert os.path.exists(os.path.join(temp_project_dir, "chapters/01_introduccion.tex"))


def test_parser_and_validation(temp_project_dir):
    scaffold_latex_project(temp_project_dir, title="Validation Test", author="Tester", doc_type="thesis")
    main_tex = os.path.join(temp_project_dir, "main.tex")
    bib_file = os.path.join(temp_project_dir, "references.bib")

    parsed = parse_latex_file(main_tex)
    assert parsed["total_lines"] > 0

    val = validate_latex_document(main_tex, bib_path=bib_file)
    assert val["valid"] is True
    assert len(val["errors"]) == 0


def test_table_formatter():
    data = [
        {"Parámetro": "Eficiencia", "Valor": "98.5%", "Estado": "Óptimo"},
        {"Parámetro": "Pérdidas", "Valor": "1.5%", "Estado": "Bajo"},
    ]
    table_code = generate_latex_table(data, caption="Prueba de Tabla", label="tab:prueba")
    assert r"\begin{table}" in table_code
    assert r"\toprule" in table_code
    assert "Eficiencia" in table_code
    assert r"\end{table}" in table_code


def test_bib_manager(temp_project_dir):
    bib_path = os.path.join(temp_project_dir, "test.bib")
    
    # Add entry >= 2022
    valid_bib = r"""@article{gomez2023,
      author  = {Gómez, Carlos},
      title   = {Modelo Inteligente},
      journal = {Revista de Sistemas},
      year    = {2023}
    }"""
    add_res = add_bib_entry(bib_path, valid_bib, enforce_min_year=2022)
    assert add_res["success"] is True

    # Attempt to add entry prior to 2022
    old_bib = r"""@article{perez2015,
      author  = {Pérez, Juan},
      title   = {Modelo Antiguo},
      journal = {Revista Vieja},
      year    = {2015}
    }"""
    old_res = add_bib_entry(bib_path, old_bib, enforce_min_year=2022)
    assert old_res["success"] is False
    assert "minimum year" in old_res["error"]

    val = validate_bib_file(bib_path)
    assert val["valid"] is True


def test_latex_compilation(temp_project_dir):
    scaffold_latex_project(temp_project_dir, title="Compilation Test", author="Tester", doc_type="thesis")
    main_tex = os.path.join(temp_project_dir, "main.tex")
    res = compile_latex_document(main_tex, engine="latexmk", output_dir=temp_project_dir)
    assert res["success"] is True, f"Compilation failed: {res}"
    assert res["pdf_path"] is not None
    assert os.path.exists(res["pdf_path"])
