import { DATASETS, buildIndex, searchResources, summaryExcerpt, titleSearchUrl } from './search.mjs';

export function renderResults(document, container, matches, query) {
  const fragment = document.createDocumentFragment();
  for (const { record } of matches) {
    const card = document.createElement('article');
    card.className = 'result';
    const title = document.createElement('h2');
    title.textContent = record.title;
    const summary = document.createElement('p');
    summary.textContent = summaryExcerpt(record.summary, query);
    const meta = document.createElement('p');
    meta.className = 'meta';
    meta.textContent = `arXiv · ${record.categories.join(', ')} · Authors: ${record.authors.join(', ') || 'Not supplied'} · Summary excerpt from the saved metadata`;
    const link = document.createElement('a');
    link.href = titleSearchUrl(record.title);
    link.textContent = 'Search this title on arXiv';
    card.append(title, summary, meta, link);
    fragment.append(card);
  }
  container.replaceChildren(fragment);
}

export function startSearch(document, fetchResource = globalThis.fetch) {
  const form = document.getElementById('search-form');
  const input = document.getElementById('query');
  const results = document.getElementById('results');
  const status = document.getElementById('status');
  const retry = document.getElementById('retry');
  let index;
  let loading;
  let request = 0;

  function loadIndex() {
    if (index) return Promise.resolve(index);
    if (!loading) {
      loading = (async () => {
        // One deadline covers the complete load, including body reads.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 10000);
        try {
          const datasets = await Promise.all(DATASETS.map(async file => {
            const response = await fetchResource(new URL(`../data/${file}`, import.meta.url), { signal: controller.signal });
            if (!response.ok) throw new Error('Dataset unavailable');
            return response.json();
          }));
          index = buildIndex(datasets);
          return index;
        } finally {
          clearTimeout(timer);
          controller.abort();
          loading = undefined;
        }
      })();
    }
    return loading;
  }

  async function search() {
    const current = ++request;
    const query = input.value.trim();
    retry.hidden = true;
    results.replaceChildren();
    results.setAttribute('aria-busy', 'false');
    if (!query) {
      status.textContent = 'Enter a topic, author, or category to search the saved resources.';
      return;
    }
    status.textContent = 'Loading the saved arXiv resources…';
    results.setAttribute('aria-busy', 'true');
    try {
      const resources = await loadIndex();
      if (current !== request) return;
      const matches = searchResources(resources, query);
      renderResults(document, results, matches, query);
      status.textContent = matches.length
        ? `${matches.length} ${matches.length === 1 ? 'result' : 'results'} for “${query}” in ${resources.length} unique saved titles.`
        : `No saved resources match “${query}”. Try fewer words or another topic; this snapshot is not a complete catalogue.`;
    } catch {
      if (current !== request) return;
      status.textContent = 'Could not load all four resource files. Serve the repository over HTTP and try again.';
      retry.hidden = false;
    } finally {
      if (current === request) results.setAttribute('aria-busy', 'false');
    }
  }

  form.addEventListener('submit', event => { event.preventDefault(); void search(); });
  retry.addEventListener('click', () => { void search(); });
  for (const example of document.querySelectorAll('.example')) {
    example.addEventListener('click', () => { input.value = example.textContent; void search(); });
  }
}

if (typeof document !== 'undefined') startSearch(document);
