import os
import json

VAULT_PATH = "./obsidian_vault"

DIRS = [
    "00_Inbox",
    "10_Papers",
    "20_Concepts",
    "30_Thesis_Chapters",
    "40_Architecture"
]

def init_vault():
    for d in DIRS:
        path = os.path.join(VAULT_PATH, d)
        os.makedirs(path, exist_ok=True)
    print(f"Bóveda de Obsidian inicializada en: {VAULT_PATH}")

def create_concept_note(title, content, tags=None, linked_notes=None):
    init_vault()
    filename = f"{title.replace(' ', '_')}.md"
    filepath = os.path.join(VAULT_PATH, "20_Concepts", filename)
    
    tags_str = " ".join([f"#{t}" for t in (tags or ["concepto", "tesis"])])
    links_str = "\n".join([f"- [[{l}]]" for l in (linked_notes or [])])
    
    note_content = f"""---
title: "{title}"
tags: [{", ".join(tags or ["concepto"])}]
date: 2026-07-30
---

# {title}

{tags_str}

## Descripción
{content}

## Notas Enlazadas
{links_str}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(note_content)
    print(f"Nota de concepto creada: {filepath}")

if __name__ == "__main__":
    init_vault()
    create_concept_note(
        "Consenso_Lider_Seguidor_Tiempo_Finito",
        "Estrategia de control distribuido secundario en microrredes para estabilizar tensión y potencia en tiempo finito.",
        tags=["control_distribuido", "consenso", "microrredes"],
        linked_notes=["Control_Secundario_Microrredes", "Topologia_Grafo_Consenso"]
    )
