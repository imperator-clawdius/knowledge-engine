"""
Knowledge Engine — Crawl Layer
Discovers and indexes free educational resources from open sources.
Runs as a cron job. Outputs to MemPalace.
"""
import json, subprocess, sys, time
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

MP = Path.home() / "mempalace/.venv/bin/mempalace"
DATA_DIR = Path.home() / "knowledge-engine/data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def crawl_arxiv(category="cs.AI", max_results=50):
    """Scrape arXiv for recent papers in a category."""
    import urllib.request
    url = f"http://export.arxiv.org/api/query?search_query=cat:{category}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    req = urllib.request.Request(url, headers={"User-Agent": "KnowledgeEngine/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    
    papers = []
    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
        summary = (entry.find("atom:summary", ns).text or "")[:500].strip()
        authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)]
        papers.append({
            "title": title,
            "summary": summary,
            "authors": authors,
            "source": "arxiv",
            "category": category
        })
    
    path = DATA_DIR / f"arxiv_{category}_{datetime.now().strftime('%Y%m%d')}.json"
    with open(path, "w") as f:
        json.dump(papers, f, indent=2)
    print(f"  arXiv/{category}: {len(papers)} papers → {path}")
    return path

def index_to_mempalace():
    """Feed crawled data into MemPalace for searchable memory."""
    for path in sorted(DATA_DIR.glob("*.json"), reverse=True)[:5]:
        print(f"  Indexing: {path.name}")
        subprocess.run(
            [str(MP), "mine", str(path), "--mode", "projects"],
            capture_output=True, timeout=120
        )

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Knowledge Engine Crawler")
    crawl_arxiv("cs.AI")
    crawl_arxiv("cs.LG")  # Machine Learning
    crawl_arxiv("cs.RO")  # Robotics
    crawl_arxiv("q-bio")  # Quantitative Biology (cancer research, etc.)
    index_to_mempalace()
