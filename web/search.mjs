// Search only the checked-in metadata snapshot. No network or model dependency.
export const DATASETS = Object.freeze([
  'arxiv_cs.AI_20260729.json',
  'arxiv_cs.LG_20260729.json',
  'arxiv_cs.RO_20260729.json',
  'arxiv_q-bio_20260729.json',
]);
const normalize = text => text.normalize('NFKC').toLowerCase().replace(/\s+/gu, ' ').trim();
const words = text => normalize(text).match(/[\p{L}\p{N}]+/gu) ?? [];
const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;

export function buildIndex(datasets) {
  const records = new Map();
  for (const rows of datasets) {
    if (!Array.isArray(rows)) throw new Error('Invalid resource dataset');
    for (const row of rows) {
      if (!row || typeof row !== 'object' ||
          !['title', 'summary', 'category'].every(key => typeof row[key] === 'string' && row[key].trim()) ||
          row.source !== 'arxiv' || !Array.isArray(row.authors) ||
          !row.authors.every(author => typeof author === 'string' && author.trim())) {
        throw new Error('Invalid resource record');
      }
      // No IDs were retained. This is title-based deduplication, not paper identity.
      const key = normalize(row.title);
      const existing = records.get(key);
      if (existing) {
        existing.categories.add(row.category.trim());
        for (const author of row.authors) existing.authors.add(author.trim());
      } else {
        records.set(key, {
          title: row.title.trim(), summary: row.summary.trim(), source: row.source,
          categories: new Set([row.category.trim()]), authors: new Set(row.authors.map(author => author.trim())),
        });
      }
    }
  }
  return [...records.entries()].sort(([a], [b]) => compare(a, b)).map(([key, row]) => {
    const categories = [...row.categories].sort(compare);
    const authors = [...row.authors];
    return Object.freeze({
      ...row, key, categories: Object.freeze(categories), authors: Object.freeze(authors),
      titleWords: new Set(words(row.title)), summaryWords: new Set(words(row.summary)),
      metadataWords: new Set(words([...categories, ...authors].join(' '))),
    });
  });
}

export function searchResources(index, query) {
  const terms = [...new Set(words(query))];
  if (!terms.length) return [];
  const phrase = normalize(query);
  return index.flatMap(record => {
    // Every query term must occur. Exact word matching avoids unrelated substrings.
    let score = normalize(record.title).includes(phrase) ? 20 : 0;
    for (const term of terms) {
      if (record.titleWords.has(term)) score += 8;
      else if (record.summaryWords.has(term)) score += 3;
      else if (record.metadataWords.has(term)) score += 1;
      else return [];
    }
    return [{ record, score }];
  }).sort((a, b) => b.score - a.score || compare(a.record.key, b.record.key));
}

export function summaryExcerpt(summary, query, maxLength = 280) {
  if (summary.length <= maxLength) return summary;
  const lower = summary.toLowerCase();
  const positions = words(query).map(term => lower.indexOf(term)).filter(position => position >= 0);
  const match = positions.length ? Math.min(...positions) : 0;
  let start = Math.max(0, match - 65);
  if (start > 0) {
    const boundary = summary.indexOf(' ', start);
    if (boundary !== -1 && boundary < match) start = boundary + 1;
  }
  start = Math.min(start, summary.length - maxLength);
  return `${start ? '…' : ''}${summary.slice(start, start + maxLength).trim()}${start + maxLength < summary.length ? '…' : ''}`;
}

export function titleSearchUrl(title) {
  const url = new URL('https://arxiv.org/search/');
  url.searchParams.set('query', title);
  url.searchParams.set('searchtype', 'title');
  return url.href;
}
