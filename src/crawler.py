"""Fetch bounded arXiv metadata snapshots; indexing is an explicit optional step."""
import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

CATEGORIES = ("cs.AI", "cs.LG", "cs.RO", "q-bio")
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
API_URL = "https://export.arxiv.org/api/query"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 30
INDEX_TIMEOUT_SECONDS = 120
REQUEST_DELAY_SECONDS = 3
ATOM = "{http://www.w3.org/2005/Atom}"
PAPER_PATH = re.compile(r"/abs/(?:[0-9]{4}\.[0-9]{4,5}|[a-z][a-z.-]*/[0-9]{7})(?:v[1-9][0-9]*)?\Z")


class CrawlError(Exception):
    """An actionable ingestion failure, without remote response bodies."""


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_options(category, max_results):
    if category not in CATEGORIES:
        raise CrawlError("Choose one of the four supported categories.")
    if type(max_results) is not int or not 1 <= max_results <= 50:
        raise CrawlError("max_results must be an integer from 1 to 50.")


def paper_url(value):
    """Validate a supplied arXiv abstract URL and normalize HTTP to HTTPS."""
    try:
        if not isinstance(value, str) or any(char.isspace() for char in value):
            raise ValueError()
        url = urllib.parse.urlsplit(value)
        if (url.scheme not in ("http", "https") or url.netloc != "arxiv.org"
                or url.query or url.fragment or not PAPER_PATH.fullmatch(url.path)):
            raise ValueError()
    except (TypeError, ValueError):
        raise CrawlError("An entry has an invalid arXiv paper URL.") from None
    return "https://arxiv.org" + url.path


def parse_feed(data, category, max_results=50):
    validate_options(category, max_results)
    if len(data) > MAX_RESPONSE_BYTES:
        raise CrawlError("arXiv response exceeds the 2 MiB limit.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise CrawlError("arXiv returned invalid XML.") from None
    if root.tag != ATOM + "feed":
        raise CrawlError("arXiv did not return an Atom feed.")
    entries = root.findall(ATOM + "entry")
    if len(entries) > max_results:
        raise CrawlError("arXiv returned more entries than requested.")
    papers = []
    for entry in entries:
        atom_id = (entry.findtext(ATOM + "id") or "").strip()
        if atom_id.startswith(("http://arxiv.org/api/errors", "https://arxiv.org/api/errors")):
            raise CrawlError("arXiv returned an API error entry.")
        url = paper_url(atom_id)
        for link in entry.findall(ATOM + "link"):
            if link.get("rel") == "alternate" and link.get("type", "text/html") == "text/html":
                if paper_url(link.get("href", "")) != url:
                    raise CrawlError("An entry's article link does not match its paper ID.")
        title = " ".join((entry.findtext(ATOM + "title") or "").split())
        summary = (entry.findtext(ATOM + "summary") or "")[:500].strip()
        authors = [(author.findtext(ATOM + "name") or "").strip()
                   for author in entry.findall(ATOM + "author")]
        if not title or not summary or not authors or not all(authors):
            raise CrawlError("An entry is missing required title, summary, or author metadata.")
        papers.append({"title": title, "summary": summary, "authors": authors,
                       "source": "arxiv", "category": category,
                       "id": atom_id, "url": url})
    return papers


def fetch_arxiv(category, max_results=50):
    validate_options(category, max_results)
    query = urllib.parse.urlencode({"search_query": "cat:" + category, "start": 0,
                                  "max_results": max_results, "sortBy": "submittedDate",
                                  "sortOrder": "descending"})
    request = urllib.request.Request(API_URL + "?" + query,
                                     headers={"User-Agent": "KnowledgeEngine/1.0",
                                              "Accept": "application/atom+xml"})
    # Refuse redirects; a feed must come from the fixed HTTPS endpoint.
    opener = urllib.request.build_opener(NoRedirects())
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            if response.status != 200 or response.geturl() != request.full_url:
                raise CrawlError("Unexpected arXiv response status or endpoint.")
            data = bytearray()
            while True:
                chunk = response.read(min(65536, MAX_RESPONSE_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise CrawlError("arXiv response exceeds the 2 MiB limit.")
    except urllib.error.HTTPError as error:
        error.close()
        raise CrawlError(f"arXiv returned HTTP {error.code}; no snapshot was written.") from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise CrawlError("arXiv could not be read; no snapshot was written.") from None
    return parse_feed(bytes(data), category, max_results)


def publish_snapshot(path, papers, overwrite=False):
    """Publish complete UTF-8 JSON; never expose a partially written target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix="." + path.name + ".",
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(papers, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic no-clobber publication, including a competing creator.
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def crawl_arxiv(category="cs.AI", max_results=50, *, output_dir=DATA_DIR, overwrite=False):
    validate_options(category, max_results)
    snapshot_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = Path(output_dir) / f"arxiv_{category}_{snapshot_date}.json"
    if not overwrite and path.exists():
        raise CrawlError(f"Snapshot already exists: {path}. Use --overwrite explicitly.")
    papers = fetch_arxiv(category, max_results)
    publish_snapshot(path, papers, overwrite)
    print(f"Saved {len(papers)} arXiv/{category} records to {path}")
    return path


def index_to_mempalace(paths, executable):
    """Index only this invocation's successful files, using a supplied executable."""
    for path in paths:
        try:
            subprocess.run([str(executable), "mine", str(path), "--mode", "projects"],
                           check=True, timeout=INDEX_TIMEOUT_SECONDS,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as error:
            raise CrawlError(f"Indexing failed for {path.name} (exit {error.returncode}); snapshots remain saved.") from None
        except (subprocess.TimeoutExpired, OSError):
            raise CrawlError(f"Indexing could not finish for {path.name}; snapshots remain saved.") from None
        print(f"Indexed {path.name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", action="append", choices=CATEGORIES,
                        help="Repeat to select categories; default: all four.")
    parser.add_argument("--max-results", type=int, default=50, help="Records per category, 1-50 (default: 50).")
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR,
                        help="Default: this checkout's data directory; relative overrides use the working directory.")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace same-day snapshots after a successful fetch.")
    parser.add_argument("--index-with", type=Path, metavar="EXECUTABLE",
                        help="Optionally index new snapshots using this explicit MemPalace executable path.")
    args = parser.parse_args(argv)
    categories = list(dict.fromkeys(args.category or CATEGORIES))
    try:
        validate_options(categories[0], args.max_results)
        executable = args.index_with.resolve() if args.index_with else None
        if executable is not None and not executable.is_file():
            raise CrawlError("--index-with must name an existing executable file.")
        paths = []
        for category in categories:
            if paths:
                time.sleep(REQUEST_DELAY_SECONDS)
            paths.append(crawl_arxiv(category, args.max_results, output_dir=args.output_dir,
                                     overwrite=args.overwrite))
        if executable is not None:
            index_to_mempalace(paths, executable)
    except (CrawlError, OSError) as error:
        print(f"Ingestion failed: {error}", file=sys.stderr)
        print("Earlier successful snapshots, if any, remain saved. No automatic retries were made.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
