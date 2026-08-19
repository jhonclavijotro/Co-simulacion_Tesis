import arxiv
import os
import json
import sys

def search_papers(query, max_results=5, download_pdf=False, output_dir="./papers"):
    print(f"Buscando artículos científicos para: '{query}'...")
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance
    )

    client = arxiv.Client(page_size=5, delay_seconds=3, num_retries=3)
    results = []
    if download_pdf and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    try:
        for paper in client.results(search):
            item = {
                "title": paper.title,
                "authors": [a.name for a in paper.authors],
                "published": str(paper.published),
                "summary": paper.summary,
                "pdf_url": paper.pdf_url,
                "entry_id": paper.entry_id
            }
            results.append(item)
            if download_pdf:
                pdf_name = f"{paper.entry_id.split('/')[-1]}.pdf"
                paper.download_pdf(dirpath=output_dir, filename=pdf_name)
                item["local_path"] = os.path.join(output_dir, pdf_name)
    except Exception as e:
        print(f"Aviso en consulta a arXiv API: {e}")

    return results

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "microgrid consensus control leader follower finite time"
    papers = search_papers(q, max_results=3)
    print(json.dumps(papers, indent=2))
