import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { DATASETS, buildIndex, searchResources, summaryExcerpt, titleSearchUrl } from '../web/search.mjs';

const row = (title, summary = 'A saved research summary.', extra = {}) => ({
  title, summary, authors: ['Fictional Researcher'], source: 'arxiv', category: 'cs.AI', ...extra,
});
const titles = results => results.map(({ record }) => record.title);

test('actual snapshot searches distinct topics and deduplicates 200 rows into 180 titles', async () => {
  const datasets = await Promise.all(DATASETS.map(file => readFile(new URL(`../data/${file}`, import.meta.url), 'utf8').then(JSON.parse)));
  const before = JSON.stringify(datasets);
  const index = buildIndex(datasets);
  assert.equal(datasets.flat().length, 200);
  assert.equal(index.length, 180);
  assert.equal(JSON.stringify(datasets), before);
  const robotics = searchResources(index, 'robotics');
  assert.ok(robotics.length > 0);
  const biology = searchResources(index, 'synchronization');
  assert.ok(titles(biology).includes('Synchronization of active mechanical oscillators by an inertial load'));
  assert.notDeepEqual(titles(robotics), titles(biology));
  assert.ok(searchResources(index, 'cs.RO').every(({ record }) => record.categories.includes('cs.RO')));
  assert.deepEqual(searchResources(index, 'fictionalunmatchedtopic'), []);
});

test('normalized duplicate titles merge provenance without changing the first summary', () => {
  const index = buildIndex([[row('  Robot   Learning ', 'First supplied excerpt.')], [row('robot learning', 'Other excerpt.', { category: 'cs.RO', authors: ['Another Author'] })]]);
  assert.equal(index.length, 1);
  assert.equal(index[0].summary, 'First supplied excerpt.');
  assert.deepEqual(index[0].categories, ['cs.AI', 'cs.RO']);
  assert.deepEqual(index[0].authors, ['Fictional Researcher', 'Another Author']);
  assert.equal(searchResources(index, 'another')[0].record, index[0]);
});

test('title matches outrank summary and author matches, with deterministic title ties', () => {
  const rows = [row('Zeta Robotics'), row('Beta', 'Robotics findings.'), row('Alpha Robotics'), row('Gamma', 'Research.', { authors: ['Robotics'] })];
  const expected = ['Alpha Robotics', 'Zeta Robotics', 'Beta', 'Gamma'];
  assert.deepEqual(titles(searchResources(buildIndex([rows]), 'robotics')), expected);
  assert.deepEqual(titles(searchResources(buildIndex([[...rows].reverse()]), 'ROBOTICS')), expected);
});

test('all distinct words are required; punctuation/case/Unicode normalize without substring matches', () => {
  const index = buildIndex([[row('Robot learning'), row('Robotics control'), row('CAFÉ 学習', 'Unicode research.')]]);
  assert.deepEqual(titles(searchResources(index, 'ROBOT, learning learning')), ['Robot learning']);
  assert.deepEqual(searchResources(index, 'robot control'), []);
  assert.deepEqual(titles(searchResources(index, 'cafe\u0301 学習')), ['CAFÉ 学習']);
  assert.deepEqual(searchResources(index, '   ... '), []);
});

test('empty datasets are usable; broken metadata fails the complete index', () => {
  assert.deepEqual(buildIndex([[], []]), []);
  for (const bad of [null, {}, [row('')], [row('Valid', 'Summary', { authors: 'not an array' })], [row('Valid', 'Summary', { source: 'unknown' })]]) {
    assert.throws(() => buildIndex([[row('Good')], bad]), /Invalid resource/);
  }
});

test('long summary excerpt includes a late matching passage and labels truncation', () => {
  const summary = 'Earlier unrelated context. '.repeat(15) + 'robotics coordinates movement. ' + 'More supplied context. '.repeat(10);
  const excerpt = summaryExcerpt(summary, 'robotics');
  assert.ok(excerpt.includes('robotics coordinates movement'));
  assert.ok(excerpt.startsWith('…') && excerpt.endsWith('…'));
  assert.ok(excerpt.length <= 282);
  assert.equal(summaryExcerpt('Short summary.', 'robotics'), 'Short summary.');
});

test('external navigation is a fixed-origin, encoded title search, never a supplied URL', () => {
  const title = 'javascript:alert(1) & <fictional> # title';
  const url = new URL(titleSearchUrl(title));
  assert.equal(url.origin, 'https://arxiv.org');
  assert.equal(url.pathname, '/search/');
  assert.equal(url.searchParams.get('query'), title);
  assert.equal(url.searchParams.get('searchtype'), 'title');
  assert.equal(url.hash, '');
});
