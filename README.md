# 🎓 Knowledge Engine

**Free resource search over a saved arXiv research snapshot. Built by Cerberus.**

## What works

The static web page searches the four checked-in JSON datasets dated **2026-07-29**: artificial intelligence (`cs.AI`), machine learning (`cs.LG`), robotics (`cs.RO`), and quantitative biology (`q-bio`). These contain 200 metadata rows and 180 unique normalized titles. They are research resources, not a beginner curriculum or a complete, current arXiv catalogue.

Search by topic, author, or category. Search is local to your browser after loading the four files: every query word must appear in a title, saved summary, author, or category. Title matches rank above summary matches, then metadata matches; ties sort by title. There is no semantic search or AI generation. No account, paid provider, or backend is needed.

Duplicate normalized titles are merged across categories, keeping the first supplied summary and combining authors/categories. Without retained paper IDs this is title-based deduplication, not verified paper identity. The saved summaries are already truncated; results display excerpts, not full abstracts. Each result attributes its supplied authors and categories. Links labelled **“Search this title on arXiv”** open a title search because the data does not retain article IDs or URLs; they are not direct paper links.

## Run locally

From the repository root:

```sh
python -m http.server 8000 --bind 127.0.0.1
```

Open `http://127.0.0.1:8000/web/`. Keep `web/` and `data/` together when serving the static site. Opening the HTML as a `file://` URL does not support the dataset fetches. A failed or invalid dataset produces an error with retry rather than partial results; the browser load has a ten-second deadline.

Examples: `robotics`, `machine learning`, `synchronization`, or `cs.RO`. A topic absent from this small snapshot may have no results. Queries and resource text are rendered as text, not HTML.

## Checks

With Node.js 22 or later:

```sh
node --test tests/search.test.mjs
```

The optional real-browser checks use an existing Playwright installation and its Chromium browser; no package installation is needed by the application. Set `PLAYWRIGHT_MODULE_PATH` to that installation's absolute module directory, then run:

```sh
node --test tests/browser.test.mjs
```

Those checks serve only this repository on loopback and deny external browser requests. They cover actual corpus results, safe text rendering, loading, stale-query handling, and failed-load retry.

## Not implemented

Personalized roadmaps, prerequisite sequencing, projects, scholarships, AI-generated curricula, and the broader textbook/course sources described in the original concept remain future work. The UI does not promise these features.

`src/crawler.py` is a separate experimental arXiv ingestion script. It is not used by the browser and is unchanged by this search checkpoint. It writes to home-directory paths and invokes a private local MemPalace executable; it has not been qualified as a portable ingestion pipeline. Serving/searching the saved resources does not run it, schedule crawling, or establish data freshness.

## License

MIT. Resource metadata remains attributed to its supplied arXiv authors; the application license does not relicense linked papers.
