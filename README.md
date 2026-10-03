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

## Optional snapshot ingestion

The separate Python standard-library crawler can fetch new metadata snapshots from the fixed HTTPS arXiv API. It is never run by the browser or by importing the module. Its default output directory is this checkout's `data/`, regardless of the current working directory; it no longer requires a private home-directory installation.

```sh
python src/crawler.py --help
python src/crawler.py
python src/crawler.py --category cs.RO --max-results 10 --output-dir ./new-snapshots
```

Running the crawler performs network requests. The default selects the existing four categories and up to 50 records each. Repeat `--category` to select a subset; `--max-results` accepts 1–50. The filename date is the UTC snapshot date, not a paper's publication date. Original metadata fields and 500-character saved summaries remain; new rows additionally retain the supplied Atom `id` and a validated HTTPS arXiv abstract `url`. Existing browser search still uses its four pinned July 29 files and title-search links: **new snapshots do not automatically update the browser's data or navigation**.

Responses are limited to 2 MiB and 50 entries, redirects are refused, and network operations use a 30-second timeout with no automatic retries. That socket-operation timeout is not a hard total run deadline. Invalid feeds, API error entries, missing metadata, mismatched article identity, and HTTP/read failures exit nonzero without publishing that category. Earlier successful categories remain saved if a later category fails; such a run skips indexing.

The CLI fetches sequentially and waits three seconds between categories, with no delay before the first request or after the final request or a failure. This follows the [arXiv API manual](https://github.com/arXiv/arxiv-docs/blob/develop/source/help/api/user-manual.md) and [API rate limits](https://info.arxiv.org/help/api/tou.html#rate-limits). Run only one instance: the provider's one-connection and three-second spacing requirements apply across machines under your control. This CLI's delay is per invocation; it does not coordinate overlapping processes or separate direct calls to `fetch_arxiv`.

JSON is written as UTF-8 to a temporary file, flushed, and atomically published. Same-day files are refused unless `--overwrite` is explicit; a failed fetch or failed replacement preserves the prior target. Default no-overwrite publication requires filesystem hard-link support (normal NTFS/ext4 supports it); unsupported filesystems fail rather than exposing a partial JSON file. This is per-file publication, not a transaction across all categories or a power-loss recovery guarantee.

Indexing is optional and requires an explicit executable path:

```sh
python src/crawler.py --index-with /absolute/path/to/mempalace
```

Only files successfully produced by that invocation are indexed, after all selected fetches succeed. Each `mine FILE --mode projects` invocation has a 120-second timeout and a checked exit status. An indexing failure exits nonzero and leaves saved snapshots intact; it does not roll back any earlier successful indexing. MemPalace compatibility and live arXiv availability have not been exercised in this checkpoint. No scheduling, backend, or freshness guarantee is added.

Run ingestion checks without network, private indexing, or repository data writes:

```sh
python -B -m unittest discover -s tests -p test_crawler.py -v
```

These checks use fictional Atom feeds, temporary directories, and mocked fetch/process boundaries. The four original datasets remain unchanged.

## License

MIT. Resource metadata remains attributed to its supplied arXiv authors; the application license does not relicense linked papers.
