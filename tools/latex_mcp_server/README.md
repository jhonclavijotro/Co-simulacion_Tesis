# Servidor MCP para LaTeX (`latex-mcp-server`)

Este servidor implementa el protocolo **Model Context Protocol (MCP)** estándar de Anthropic/Linux Foundation para la **construcción, manipulación, análisis, validación y compilación estructurada de documentos LaTeX** en proyectos académicos y de tesis de grado.

---

## 🚀 Características Principales

1. **Construcción y Andamiaje de Proyectos (`latex_scaffold`)**:
   - Genera plantillas modulares estructuradas en carpetas (`main.tex`, `packages.tex`, `references.bib`, `chapters/`, `figures/`).
   - Soporta plantillas para **Tesis de Grado**, **Artículos Científicos**, **Informes Técnicos** y **Presentaciones Beamer**.

2. **Inspección de Estructura y AST (`latex_inspect`)**:
   - Parsea archivos LaTeX extrayendo árbol de secciones (`\chapter`, `\section`, `\subsection`), entornos (`table`, `figure`, `equation`, `align`), etiquetas (`\label`), citas (`\cite`) y archivos incluidos (`\input`).

3. **Inserción Limpia de Snippets (`latex_insert_snippet`)**:
   - Inserta secciones, figuras, tablas, ecuaciones y listas sin romper la sintaxis ni dejar etiquetas sueltas.

4. **Validación Estática de Sintaxis (`latex_validate`)**:
   - Detecta entornos no cerrados o desbalanceados (`\begin{...}` sin `\end{...}`), llaves incompletas `{...}`, citas no encontradas en `.bib`, referencias rotas a etiquetas y caracteres TeX sin escapar (`%`, `_`, `&`).

5. **Compilación y Diagnóstico Estructurado (`latex_compile_doc`)**:
   - Ejecuta `latexmk` / `pdflatex` / `xelatex` con resolución automática de referencias cruzadas y bibliografía en múltiples pasadas.
   - Parsea el archivo `.log` para retornar errores y advertencias estructurados con número de línea exacto y contexto.

6. **Gestión de Bibliografía BibTeX (`latex_manage_bibliography`)**:
   - Permite listar, validar e insertar registros BibTeX verificando formato APA y **regla de año de publicación ($\ge 2022$)**.

7. **Renderizado Directo de Diagramas TikZ (`latex_render_tikz_preview`)**:
   - Compila diagramas TikZ independientes a archivos de imagen (`PNG` o `SVG`) mediante `pdftoppm` / `dvisvgm` para verificación visual inmediata.

8. **Generador de Tablas Académicas (`latex_build_table`)**:
   - Convierte datos tabulares en formato CSV o JSON a código LaTeX con formato profesional `booktabs` (`\toprule`, `\midrule`, `\bottomrule`).

---

## 🛠️ Configuración de Integración MCP

### Archivo de Configuración (`.mcp/latex_mcp_config.json`)

```json
{
  "mcpServers": {
    "latex-mcp-server": {
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": [
        "-m",
        "tools.latex_mcp_server.cli"
      ],
      "cwd": "${workspaceFolder}",
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

---

## 📋 Lista de Herramientas MCP Expuestas

| Nombre de Herramienta | Descripción | Parámetros Principales |
| :--- | :--- | :--- |
| `latex_scaffold` | Inicializa estructura modular de proyecto LaTeX | `target_dir`, `title`, `author`, `doc_type` |
| `latex_inspect` | Parsea y extrae árbol de estructura AST | `file_path` |
| `latex_validate` | Realiza análisis estático de sintaxis | `file_path`, `bib_path` |
| `latex_compile_doc` | Compila a PDF y extrae errores del `.log` | `tex_path`, `engine`, `output_dir`, `clean_after` |
| `latex_insert_snippet` | Inserta código LaTeX en ubicación específica | `file_path`, `content`, `target_section`, `position` |
| `latex_manage_bibliography` | Gestiona y valida entradas BibTeX ($\ge 2022$) | `bib_path`, `action`, `bibtex_code`, `min_year` |
| `latex_render_tikz_preview` | Compila gráficos TikZ a PNG/SVG | `tikz_code`, `output_name`, `work_dir`, `fmt` |
| `latex_build_table` | Convierte datos CSV/JSON a tablas `booktabs` | `data_csv_or_json`, `caption`, `label`, `headers_csv` |

---

## 🧪 Verificación y Pruebas

Para ejecutar la suite completa de pruebas unitarias e integración:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_latex_mcp_server.py
```
