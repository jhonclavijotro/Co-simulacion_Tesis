import os
import sys
import re
import json
import glob
import fitz  # PyMuPDF

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VAULT_DIR = os.path.join(WORKSPACE_DIR, "obsidian_vault", "10_Papers")
PDF_DIR = os.path.join(WORKSPACE_DIR, "Thesis_LaTeX", "DOCUMENTOS")

SCRATCH_DIR = r"C:\Users\Jhonathan\.gemini\antigravity-ide\brain\b9033bb8-ef4e-4b90-9670-7eb7642520ef\scratch"
os.makedirs(SCRATCH_DIR, exist_ok=True)

PENDING_JSON = os.path.join(SCRATCH_DIR, "pending_papers.json")
ENRICHED_JSON = os.path.join(SCRATCH_DIR, "enriched_papers.json")

# English stop words list for basic language detection
ENGLISH_INDICATORS = {"the", "and", "of", "with", "based", "abstract", "microgrid", "triggering", "results", "proposed"}

def is_english(text):
    if not text:
        return False
    words = set(re.sub(r"[^\w\s]", "", text.lower()).split())
    eng_count = len(words.intersection(ENGLISH_INDICATORS))
    return eng_count >= 3

def get_pdf_name_from_markdown(content):
    match = re.search(r"Referirse al archivo PDF local [`']([^`']+\.pdf)[`']", content)
    if match:
        return match.group(1)
    return None

def extract_conclusions_from_pdf(pdf_path):
    """
    Tries to locate the conclusions section at the end of the PDF and returns it.
    """
    try:
        doc = fitz.open(pdf_path)
        num_pages = len(doc)
        
        # Scan from the end of the document (last 3 pages)
        conclusions_text = ""
        found_conclusions = False
        
        pages_to_check = range(max(0, num_pages - 3), num_pages)
        for p_idx in reversed(pages_to_check):
            page_text = doc[p_idx].get_text("text")
            text_lower = page_text.lower()
            
            # Find index of "conclusion" or "conclusions" or "concluding remarks"
            for term in ["concluding remarks", "conclusions and future", "conclusion and future", "conclusions", "conclusion"]:
                idx = text_lower.find(term)
                if idx != -1:
                    start_pos = idx
                    ref_idx = text_lower.find("references", start_pos)
                    if ref_idx != -1 and ref_idx > start_pos:
                        conclusions_text = page_text[start_pos:ref_idx].strip()
                    else:
                        conclusions_text = page_text[start_pos:].strip()
                    found_conclusions = True
                    break
            if found_conclusions:
                break
                
        if not conclusions_text and num_pages > 0:
            # Fallback: Extract the last page or last two pages
            start_page = max(0, num_pages - 2)
            fallback_parts = []
            for p_idx in range(start_page, num_pages):
                fallback_parts.append(doc[p_idx].get_text("text"))
            conclusions_text = "\n".join(fallback_parts).strip()
            # Clean and truncate if needed
            
        if conclusions_text:
            conclusions_text = re.sub(r'\s+', ' ', conclusions_text)
            conclusions_text = re.sub(r'-\s+', '', conclusions_text)
            return conclusions_text[:2000]
            
    except Exception as e:
        print(f"Error al extraer conclusiones del PDF {pdf_path}: {e}")
    return ""

def extract_abstract_from_pdf(pdf_path):
    """
    Extracts abstract from the first couple of pages of the PDF.
    """
    try:
        doc = fitz.open(pdf_path)
        pages_text = doc[0].get_text("text")
        if len(doc) > 1:
            pages_text += "\n" + doc[1].get_text("text")
            
        text_lower = pages_text.lower()
        abstract_idx = text_lower.find("abstract")
        if abstract_idx == -1:
            abstract_idx = text_lower.find("resumen")
            
        abstract_text = ""
        if abstract_idx != -1:
            start_pos = abstract_idx + len("abstract")
            intro_idx = text_lower.find("introduction", start_pos)
            if intro_idx == -1:
                intro_idx = text_lower.find("introducción", start_pos)
            if intro_idx == -1:
                intro_idx = text_lower.find("i. ", start_pos)
                
            if intro_idx != -1 and intro_idx > start_pos:
                abstract_text = pages_text[start_pos:intro_idx].strip()
            else:
                abstract_text = pages_text[start_pos:start_pos + 1500].strip()
        else:
            # Fallback: take the first 3000 characters of the document
            abstract_text = pages_text[:3000].strip()
                
        abstract_text = re.sub(r'\s+', ' ', abstract_text)
        abstract_text = re.sub(r'-\s+', '', abstract_text)
        return abstract_text
    except Exception as e:
        print(f"Error al extraer abstract del PDF {pdf_path}: {e}")
    return ""

def do_extraction():
    print("Iniciando escaneo de notas de Obsidian y extracción de PDFs...")
    files = glob.glob(os.path.join(VAULT_DIR, "*.md"))
    
    pending_papers = []
    
    for filepath in files:
        filename = os.path.basename(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Extract existing abstract
        abstract_content = ""
        match = re.search(r"## 1\. Resumen Ejecutivo \(Executive Summary\)\s*\n(.*?)\n\s*---", content, re.DOTALL)
        if match:
            abstract_content = match.group(1).strip()
            
        needs_enrichment = False
        reason = ""
        
        # Determine if needs enrichment
        if "No se pudo extraer" in abstract_content or not abstract_content or len(abstract_content) < 50:
            needs_enrichment = True
            reason = "Abstract faltante o placeholder"
        elif is_english(abstract_content):
            needs_enrichment = True
            reason = "Abstract en inglés"
            
        if needs_enrichment:
            pdf_name = get_pdf_name_from_markdown(content)
            if not pdf_name:
                print(f"Aviso: No se pudo obtener el nombre del PDF para {filename}")
                continue
                
            pdf_path = os.path.join(PDF_DIR, pdf_name)
            if not os.path.exists(pdf_path):
                print(f"Aviso: PDF no encontrado en {pdf_path}")
                continue
                
            print(f"Procesando {filename} (Razón: {reason}) -> PDF: {pdf_name}")
            
            # Extract clean abstract and conclusions
            pdf_abstract = extract_abstract_from_pdf(pdf_path)
            pdf_conclusions = extract_conclusions_from_pdf(pdf_path)
            
            # If pdf_abstract failed to extract, fallback to whatever we had
            final_raw_abstract = pdf_abstract if pdf_abstract else abstract_content
            
            pending_papers.append({
                "markdown_file": filename,
                "pdf_file": pdf_name,
                "reason": reason,
                "raw_abstract": final_raw_abstract,
                "raw_conclusions": pdf_conclusions
            })
            
    with open(PENDING_JSON, "w", encoding="utf-8") as f:
        json.dump(pending_papers, f, ensure_ascii=False, indent=2)
        
    print(f"\nExtracción completada. Guardadas {len(pending_papers)} entradas en {PENDING_JSON}")

def do_writing():
    if not os.path.exists(ENRICHED_JSON):
        print(f"Error: No se encontró el archivo de resultados enriquecidos en {ENRICHED_JSON}")
        return
        
    with open(ENRICHED_JSON, "r", encoding="utf-8") as f:
        enriched_data = json.load(f)
        
    print(f"Leídas {len(enriched_data)} entradas de {ENRICHED_JSON}")
    
    updated_count = 0
    
    for entry in enriched_data:
        filename = entry.get("markdown_file")
        filepath = os.path.join(VAULT_DIR, filename)
        
        if not os.path.exists(filepath):
            print(f"Aviso: El archivo markdown {filename} no existe en {VAULT_DIR}")
            continue
            
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Reemplazar secciones usando expresiones regulares
        
        # 1. Resumen Ejecutivo
        new_summary = entry.get("resumen_ejecutivo", "")
        # Reemplaza todo entre ## 1. Resumen Ejecutivo (Executive Summary)\n y \n\n---
        content_mod = re.sub(
            r"(## 1\. Resumen Ejecutivo \(Executive Summary\)\s*\n).*?(\n\s*---)",
            rf"\1{new_summary}\2",
            content,
            flags=re.DOTALL
        )
        
        # 2. Descripción de la Investigación y Problema Abordado
        new_problem = entry.get("descripcion_problema", "")
        content_mod = re.sub(
            r"(## 2\. Descripción de la Investigación y Problema Abordado\s*\n).*?(\n\s*---)",
            rf"\1{new_problem}\2",
            content_mod,
            flags=re.DOTALL
        )
        
        # 3. Metodología y Aporte Técnico
        new_methodology = entry.get("metodologia_aporte", "")
        content_mod = re.sub(
            r"(## 3\. Metodología y Aporte Técnico\s*\n).*?(\n\s*---)",
            rf"\1{new_methodology}\2",
            content_mod,
            flags=re.DOTALL
        )
        
        # 4. Relevancia Directa para la Tesis de Grado
        new_relevance = entry.get("relevancia_tesis", "")
        content_mod = re.sub(
            r"(## 4\. Relevancia Directa para la Tesis de Grado\s*\n).*?(\n\s*---)",
            rf"\1{new_relevance}\2",
            content_mod,
            flags=re.DOTALL
        )
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content_mod)
            
        print(f"Actualizado: {filename}")
        updated_count += 1
        
    print(f"\nProceso de escritura completado. Actualizados {updated_count} archivos markdown.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "--extract":
            do_extraction()
        elif mode == "--write":
            do_writing()
        else:
            print("Argumento inválido. Use --extract o --write.")
    else:
        print("Uso: python obsidian_paper_enricher.py --extract | --write")
