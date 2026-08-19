"""
Scaffolding generator for LaTeX MCP Server.
Provides templates for Thesis, Article, Report, and Beamer documents.
"""

import os
from typing import Dict, Any

THESIS_MAIN_TEMPLATE = r"""\documentclass[12pt,oneside,a4paper]{book}

% Cargar paquetes principales
\input{packages}

\title{%(title)s}
\author{%(author)s}
\date{\today}

\begin{document}

\frontmatter
\maketitle

\chapter*{Resumen}
\addcontentsline{toc}{chapter}{Resumen}
Escriba aquí el resumen de la tesis.

\tableofcontents
\listoftables
\listoffigures

\mainmatter

\input{chapters/01_introduccion}
\input{chapters/02_marco_teorico}
\input{chapters/03_metodologia}
\input{chapters/04_resultados}
\input{chapters/05_conclusiones}

\backmatter
\bibliography{references}
\bibliographystyle{apalike}

\end{document}
"""

PACKAGES_TEMPLATE = r"""% Paquetes esenciales para documentos LaTeX académicos
\usepackage[utf8]{inputenc}
\usepackage[spanish,es-tabla]{babel}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{caption}
\usepackage{subcaption}
\usepackage{hyperref}
\usepackage{geometry}
\usepackage{cite}
\usepackage{microtype}
\usepackage{tikz}

\geometry{
  top=3cm,
  bottom=2.5cm,
  left=3cm,
  right=2.5cm
}

\hypersetup{
  colorlinks=true,
  linkcolor=blue,
  citecolor=blue,
  urlcolor=blue
}
"""

CHAPTER_01_TEMPLATE = r"""\chapter{Introducción}
\label{chap:introduccion}

\section{Contexto y Justificación}
Describa el contexto general de la investigación y la justificación del problema.

\section{Planteamiento del Problema}
Especifique de forma clara la problemática a abordar.

\section{Objetivos}
\subsection{Objetivo General}
Establezca el objetivo general de la tesis.

\subsection{Objetivos Específicos}
\begin{itemize}
    \item Objetivo específico 1.
    \item Objetivo específico 2.
    \item Objetivo específico 3.
\end{itemize}
"""

CHAPTER_02_TEMPLATE = r"""\chapter{Marco Teórico y Estado del Arte}
\label{chap:marco_teorico}

\section{Fundamentos Teóricos}
Desarrollo de los conceptos fundamentales.

\section{Revisión de la Literatura}
Síntesis del estado del arte reciente \cite{ejemplo2023}.
"""

CHAPTER_03_TEMPLATE = r"""\chapter{Metodología}
\label{chap:metodologia}

\section{Diseño Experimental}
Detalle el enfoque metodológico utilizado.

\section{Formulación Matemática}
\begin{equation}
\label{eq:ejemplo}
E = m \cdot c^2
\end{equation}
"""

CHAPTER_04_TEMPLATE = r"""\chapter{Resultados y Discusión}
\label{chap:resultados}

\section{Resultados Obtención y Análisis}
Presentación de resultados en tablas y figuras.

\begin{table}[htbp]
\centering
\caption{Resultados Comparativos}
\label{tab:resultados}
\begin{tabular}{lcc}
\toprule
\textbf{Métrica} & \textbf{Método A} & \textbf{Método B} \\
\midrule
Precisión & 94.2\% & 98.5\% \\
Tiempo (s) & 12.4 & 8.1 \\
\bottomrule
\end{tabular}
\end{table}
"""

CHAPTER_05_TEMPLATE = r"""\chapter{Conclusiones y Trabajo Futuro}
\label{chap:conclusiones}

\section{Conclusiones}
Síntesis de los aportes principales.

\section{Trabajo Futuro}
Líneas de investigación abiertas.
"""

BIB_TEMPLATE = r"""@article{ejemplo2023,
  author    = {Pérez, Juan and Gómez, María},
  title     = {Avances Recientes en Investigación Aplicada},
  journal   = {Revista de Ciencia y Tecnología},
  year      = {2023},
  volume    = {45},
  number    = {2},
  pages     = {101--115},
  doi       = {10.1000/example.2023.01}
}
"""

ARTICLE_TEMPLATE = r"""\documentclass[11pt,a4paper,twocolumn]{article}

\usepackage[utf8]{inputenc}
\usepackage[spanish]{babel}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{cite}

\title{%(title)s}
\author{%(author)s}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
Resumen ejecutivo del artículo científico.
\end{abstract}

\section{Introducción}
Texto introductorio del artículo.

\section{Metodología}
Descripción de la metodología.

\section{Resultados}
Presentación de hallazgos.

\section{Conclusiones}
Conclusiones generales.

\bibliography{references}
\bibliographystyle{ieeetr}

\end{document}
"""

BEAMER_TEMPLATE = r"""\documentclass[10pt]{beamer}

\usetheme{Madrid}
\usecolortheme{default}

\title{%(title)s}
\subtitle{Presentación de Avance / Tesis}
\author{%(author)s}
\date{\today}

\begin{document}

\begin{frame}
  \titlepage
\end{frame}

\begin{frame}{Contenido}
  \tableofcontents
\end{frame}

\section{Introducción}
\begin{frame}{Introducción y Contexto}
  \begin{itemize}
    \item Punto clave 1
    \item Punto clave 2
  \end{itemize}
\end{frame}

\section{Resultados}
\begin{frame}{Resultados Principales}
  \begin{block}{Conclusión Principal}
    Los resultados demuestran la validez del modelo propuesto.
  \end{block}
\end{frame}

\end{document}
"""


def scaffold_latex_project(target_dir: str, title: str = "Tesis de Grado", author: str = "Autor", doc_type: str = "thesis") -> Dict[str, Any]:
    """
    Creates a clean, modular LaTeX project structure at target_dir.
    """
    os.makedirs(target_dir, exist_ok=True)
    created_files = []

    def apply_sub(tmpl: str) -> str:
        return tmpl.replace("%(title)s", title).replace("%(author)s", author)

    if doc_type == "thesis":
        chapters_dir = os.path.join(target_dir, "chapters")
        figures_dir = os.path.join(target_dir, "figures")
        os.makedirs(chapters_dir, exist_ok=True)
        os.makedirs(figures_dir, exist_ok=True)

        files = {
            "main.tex": apply_sub(THESIS_MAIN_TEMPLATE),
            "packages.tex": PACKAGES_TEMPLATE,
            "references.bib": BIB_TEMPLATE,
            "chapters/01_introduccion.tex": CHAPTER_01_TEMPLATE,
            "chapters/02_marco_teorico.tex": CHAPTER_02_TEMPLATE,
            "chapters/03_metodologia.tex": CHAPTER_03_TEMPLATE,
            "chapters/04_resultados.tex": CHAPTER_04_TEMPLATE,
            "chapters/05_conclusiones.tex": CHAPTER_05_TEMPLATE,
        }

    elif doc_type == "article":
        figures_dir = os.path.join(target_dir, "figures")
        os.makedirs(figures_dir, exist_ok=True)
        files = {
            "main.tex": apply_sub(ARTICLE_TEMPLATE),
            "references.bib": BIB_TEMPLATE,
        }

    elif doc_type == "beamer":
        files = {
            "main.tex": apply_sub(BEAMER_TEMPLATE),
        }
    else:
        # Default report
        files = {
            "main.tex": apply_sub(ARTICLE_TEMPLATE),
            "references.bib": BIB_TEMPLATE,
        }

    for rel_path, content in files.items():
        full_path = os.path.join(target_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        created_files.append(rel_path)

    return {
        "status": "success",
        "doc_type": doc_type,
        "target_dir": os.path.abspath(target_dir),
        "created_files": created_files
    }
