import fitz  # PyMuPDF
import sys
import json
import os

def extract_pdf_content(pdf_path):
    if not os.path.exists(pdf_path):
        return {"error": f"Archivo no encontrado: {pdf_path}"}
    
    doc = fitz.open(pdf_path)
    metadata = doc.metadata
    pages_data = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        pages_data.append({
            "page_number": page_num + 1,
            "text_snippet": text[:500],
            "full_text": text
        })

    return {
        "file_name": os.path.basename(pdf_path),
        "total_pages": len(doc),
        "metadata": metadata,
        "pages": pages_data
    }

if __name__ == "__main__":
    if len(sys.argv) > 1:
        res = extract_pdf_content(sys.argv[1])
        print(f"Extraídas {res.get('total_pages', 0)} páginas de {res.get('file_name')}")
    else:
        print("Uso: python pdf_extractor.py <ruta_al_pdf>")
