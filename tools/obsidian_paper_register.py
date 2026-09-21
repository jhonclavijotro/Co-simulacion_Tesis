import os
import re
import glob
import datetime

# Configuration paths
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIB_FILE = os.path.join(WORKSPACE_DIR, "Thesis_LaTeX", "TuArchivo.bib")
PDF_DIR = os.path.join(WORKSPACE_DIR, "Thesis_LaTeX", "DOCUMENTOS")
VAULT_DIR = os.path.join(WORKSPACE_DIR, "obsidian_vault", "10_Papers")

# Ensure vault directory exists
os.makedirs(VAULT_DIR, exist_ok=True)

def parse_bib_file(bib_path):
    """
    Simple and robust BibTeX parser that extracts key fields.
    """
    if not os.path.exists(bib_path):
        print(f"Error: No se encontró el archivo BibTeX en {bib_path}")
        return []
    
    with open(bib_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Split by entries (starting with @)
    raw_entries = re.split(r'@', content)
    entries = []
    
    for raw in raw_entries:
        if not raw.strip():
            continue
        
        # Match type, key, and body
        match = re.match(r'^(\w+)\s*\{\s*([\w\-\:\/]+)\s*,\s*(.*)$', raw.strip(), re.DOTALL)
        if not match:
            continue
            
        entry_type = match.group(1).lower()
        bib_key = match.group(2)
        body = match.group(3)
        
        # Parse fields from the body
        # Handle balanced braces or quotes
        fields = {}
        # Simple parser for "field = {value}" or "field = "value""
        field_matches = re.finditer(r'(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|"([^"]*)"|(\d+))', body, re.DOTALL)
        
        for fm in field_matches:
            field_name = fm.group(1).lower()
            field_val = fm.group(2) or fm.group(3) or fm.group(4)
            if field_val:
                # Clean up latex formatting and braces
                field_val = re.sub(r'[\{\}]', '', field_val.strip())
                # Replace multiple spaces/newlines
                field_val = re.sub(r'\s+', ' ', field_val)
                fields[field_name] = field_val
        
        # Extract direct fields or set defaults
        title = fields.get("title", "")
        author = fields.get("author", "")
        year = fields.get("year", "")
        doi = fields.get("doi", "")
        url = fields.get("url", "")
        journal = fields.get("journal", fields.get("booktitle", ""))
        abstract = fields.get("abstract", "")
        
        if title:
            entries.append({
                "key": bib_key,
                "type": entry_type,
                "title": title,
                "author": author,
                "year": year,
                "doi": doi,
                "url": url,
                "journal": journal,
                "abstract": abstract
            })
            
    print(f"Parseados con éxito {len(entries)} registros de {bib_path}")
    return entries

def normalize_title(title):
    """
    Helper to normalize titles for matching.
    """
    title_clean = re.sub(r'[^\w\s]', '', title.lower())
    words = set(title_clean.split())
    # Remove common stop words
    stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'for', 'of', 'in', 'on', 'at', 'to', 'with', 'by', 'based', 'using'}
    return words - stop_words

def calculate_similarity(set1, set2):
    """
    Jaccard similarity between two word sets.
    """
    if not set1 or not set2:
        return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))

def match_pdf_to_bib(pdf_filename, bib_entries):
    """
    Finds the best matching BibTeX entry for a given PDF filename.
    """
    pdf_name_no_ext = os.path.splitext(pdf_filename)[0]
    pdf_words = normalize_title(pdf_name_no_ext.replace("_", " ").replace("-", " "))
    
    best_match = None
    best_score = 0.0
    
    for entry in bib_entries:
        entry_words = normalize_title(entry["title"])
        score = calculate_similarity(pdf_words, entry_words)
        
        if score > best_score:
            best_score = score
            best_match = entry
            
    # Check if the score is high enough (threshold 0.35 because of short/long titles)
    if best_score > 0.35:
        return best_match, best_score
    return None, 0.0

def extract_abstract_from_pdf(pdf_path):
    """
    Extracts abstract text from a PDF file using PyMuPDF (fitz).
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        
        # Read the first page (and second in case abstract spans)
        pages_text = doc[0].get_text("text")
        if len(doc) > 1:
            pages_text += "\n" + doc[1].get_text("text")
            
        text_lower = pages_text.lower()
        
        # Search for Abstract or Resumen
        abstract_idx = text_lower.find("abstract")
        if abstract_idx == -1:
            abstract_idx = text_lower.find("resumen")
            
        if abstract_idx != -1:
            # We found "Abstract" or "Resumen". Let's get the text right after it.
            # Skip the word itself
            start_pos = abstract_idx + len("abstract")
            
            # Find the beginning of the next common section (like Introduction)
            intro_idx = text_lower.find("introduction", start_pos)
            if intro_idx == -1:
                intro_idx = text_lower.find("introducción", start_pos)
            if intro_idx == -1:
                # Look for IEEE section marker "i. " or "1. " or "introduction"
                intro_idx = text_lower.find("i. ", start_pos)
                
            if intro_idx != -1 and intro_idx > start_pos:
                abstract_text = pages_text[start_pos:intro_idx].strip()
            else:
                # Fallback: take next 1200 characters
                abstract_text = pages_text[start_pos:start_pos + 1200].strip()
                
            # Clean up hyphenation and spacing
            abstract_text = re.sub(r'\s+', ' ', abstract_text)
            # Remove line breaks and hyphens
            abstract_text = re.sub(r'-\s+', '', abstract_text)
            return abstract_text
            
    except Exception as e:
        print(f"Aviso: No se pudo extraer abstract del PDF {os.path.basename(pdf_path)}: {e}")
        
    return ""

def clean_authors(author_str):
    """
    Cleans author list for displaying.
    """
    if not author_str:
        return "Desconocido"
    # Replace LaTeX commands and split multiple authors
    clean = re.sub(r'[\{\}\\]', '', author_str)
    # Split by ' and '
    authors = [a.strip() for a in clean.split(" and ")]
    if len(authors) > 1:
        return ", ".join(authors[:-1]) + " & " + authors[-1]
    return authors[0]

def make_obsidian_filename(author_str, year, title):
    """
    Generates standard file name: Paper_FirstAuthorLastname_Year_Keywords.md
    """
    if not author_str:
        first_author = "Unknown"
    else:
        # Get first author last name
        first_author = author_str.split(" and ")[0].strip()
        if "," in first_author:
            first_author = first_author.split(",")[0].strip()
        else:
            # Take last word of first author name
            first_author = first_author.split()[-1].strip()
    
    # Remove accents/special characters
    first_author = re.sub(r'[^\w]', '', first_author)
    
    # Get keywords from title
    title_clean = re.sub(r'[^\w\s-]', '', title)
    words = [w for w in title_clean.split() if len(w) > 3 and w.lower() not in ['with', 'from', 'that', 'this', 'based', 'using', 'under', 'for', 'the', 'and', 'a', 'an', 'over', 'control', 'systems', 'microgrid', 'microgrids', 'decentralized', 'distributed', 'cooperative']]
    keywords = "_".join(words[:4])
    
    if not keywords:
        keywords = "Paper"
        
    # Standardize name
    filename = f"Paper_{first_author}_{year or '202X'}_{keywords}.md"
    filename = re.sub(r'_+', '_', filename)
    return filename

def determine_thesis_mapping(title, abstract):
    """
    Categorizes the paper into thesis chapters based on title and abstract.
    """
    combined = (title + " " + abstract).lower()
    
    mappings = []
    
    # Check for Theory (voltage stability, complex networks, consensus mathematics, reinforcement learning theory)
    if any(k in combined for k in ['bifurcation', 'complex networks', 'percolation', 'stability analysis', 'consensus theory', 'finite-time control', 'graph algorithm', 'sliding mode observer']):
        mappings.append("TEORIA.tex")
        
    # Check for Design (protection algorithms, energy management design, consensus algorithms for microgrids, distributed controllers)
    if any(k in combined for k in ['protection based', 'event-triggered', 'blockchain', 'reinforcement learning', 'secondary control', 'sliding mode observer', 'active and reactive power', 'energy management', 'coordination of interlinking']):
        mappings.append("DISENO.tex")
        
    # Check for Background/Literature Review
    if any(k in combined for k in ['review', 'survey', 'recent advances', 'state of the art']):
        mappings.append("ANTECEDENTES.tex")
        
    # Default fallback
    if not mappings:
        mappings = ["ANTECEDENTES.tex", "TEORIA.tex"]
        
    return mappings

def write_obsidian_note(pdf_filename, entry, abstract, matched_score):
    """
    Writes a Markdown note in the Obsidian Vault.
    """
    author_str = entry["author"]
    year = entry["year"]
    title = entry["title"]
    doi = entry["doi"]
    url = entry["url"]
    bib_key = entry["key"]
    journal = entry["journal"]
    
    filename = make_obsidian_filename(author_str, year, title)
    filepath = os.path.join(VAULT_DIR, filename)
    
    # Generate tag list
    tags = ["Paper"]
    if "consensus" in title.lower(): tags.append("Consenso")
    if "microgrid" in title.lower() or "grid" in title.lower(): tags.append("Microrredes")
    if "agent" in title.lower(): tags.append("Multiagente")
    if "event" in title.lower(): tags.append("EventTriggered")
    if "protection" in title.lower() or "fault" in title.lower(): tags.append("Proteccion")
    if "ai" in title.lower() or "reinforcement" in title.lower(): tags.append("InteligenciaArtificial")
    
    cleaned_authors_list = clean_authors(author_str)
    
    # Determine chapters
    thesis_chapters = determine_thesis_mapping(title, abstract)
    chapters_str = ", ".join([f"`{c}`" for c in thesis_chapters])
    
    # Create DOI link
    doi_link = f"[{doi}](https://doi.org/{doi})" if doi else "No especificado"
    if not doi and url:
        doi_link = f"[URL Link]({url})"
        
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    # Construct content
    content = f"""---
title: "Paper: {title} ({cleaned_authors_list.split(' & ')[0].split(',')[0]} et al., {year or '202X'})"
tags: {tags}
date: {today}
---

# 📄 Ficha Bibliográfica: {cleaned_authors_list.split(' & ')[0].split(',')[0]} et al. ({year or '202X'})

**Título:** *{title}*  
**Autores:** {cleaned_authors_list}  
**Publicación:** *{journal or 'Publicación Científica'}*, {year or '202X'}.  
**DOI:** {doi_link}  
**Clave BibTeX:** `@{bib_key}`  
**Notas Enlazadas en el Vault:** [[00_Index_MOC]] | [[Control_Secundario_Microrredes]] | [[Topologia_Grafo_Consenso]]

---

## 1. Resumen Ejecutivo (Executive Summary)
{abstract or 'No se pudo extraer el resumen de forma automática. Por favor revise el PDF.'}

---

## 2. Descripción de la Investigación y Problema Abordado
Este artículo aborda la problemática de:
* El control y coordinación en microrredes o sistemas eléctricos avanzados.
* Aspectos de comunicación, estabilidad y optimización distribuida.

*(Nota: Referirse al archivo PDF local `{pdf_filename}` para profundizar en el planteamiento original.)*

---

## 3. Metodología y Aporte Técnico
El aporte principal reside en:
* Modelamiento matemático u optimización basada en agentes.
* Resultados de simulación que demuestran la viabilidad del método propuesto bajo diferentes escenarios de carga/falla.

---

## 4. Relevancia Directa para la Tesis de Grado
* **Capítulos de la Tesis Destino:** {chapters_str}
* **Aportes Clave para la Redacción:**
  - Sustento teórico y referencias del estado del arte para la sección de {chapters_str}.
  - Metodologías de consenso y modelado de red eléctrica relevantes para el diseño metodológico de la tesis.

---

## 5. Referencia APA 7ª Edición
{cleaned_authors_list}. ({year or '202X'}). {title}. *{journal or 'Journal'}.* {doi_link if doi else (url or '')}
"""
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Creado: {filename} (Score match: {matched_score:.2f})")
    return filepath

def run_registration():
    print("Iniciando registro de literatura en el Obsidian Vault...")
    bib_entries = parse_bib_file(BIB_FILE)
    
    if not bib_entries:
        print("Error: No hay registros BibTeX válidos para procesar.")
        return
        
    # Get all PDF files in DOCUMENTOS
    pdf_pattern = os.path.join(PDF_DIR, "*.pdf")
    pdf_files = glob.glob(pdf_pattern)
    
    print(f"Encontrados {len(pdf_files)} archivos PDF en {PDF_DIR}")
    
    matched_count = 0
    created_count = 0
    
    for pdf_path in pdf_files:
        pdf_filename = os.path.basename(pdf_path)
        
        # Match PDF to BibTeX entry
        match_res = match_pdf_to_bib(pdf_filename, bib_entries)
        if match_res[0]:
            entry, score = match_res
            matched_count += 1
            
            # Check if abstract is in BibTeX, otherwise extract from PDF
            abstract = entry.get("abstract", "")
            if not abstract or len(abstract.strip()) < 50:
                # Try to extract it from the PDF file
                extracted = extract_abstract_from_pdf(pdf_path)
                if extracted:
                    abstract = extracted
            
            # Write note
            write_obsidian_note(pdf_filename, entry, abstract, score)
            created_count += 1
        else:
            print(f"No se encontró coincidencia directa para: {pdf_filename}")
            
    print(f"\n--- Resumen del Proceso ---")
    print(f"PDFs procesados: {len(pdf_files)}")
    print(f"Coincidencias BibTeX exitosas: {matched_count}")
    print(f"Fichas bibliográficas creadas en Obsidian: {created_count}")

if __name__ == "__main__":
    run_registration()
