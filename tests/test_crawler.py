"""Fictional feeds and temporary output only; network/process boundaries fail closed."""
import contextlib
import io
import json
from pathlib import Path
import socket
import tempfile
import types
import unittest
from unittest import mock
import urllib.error
import urllib.parse
from xml.sax.saxutils import escape

SOURCE = Path(__file__).resolve().parents[1] / "src/crawler.py"


def load_module():
    module = types.ModuleType("knowledge_crawler_test")
    module.__file__ = str(SOURCE)
    exec(compile(SOURCE.read_bytes(), str(SOURCE), "exec"), module.__dict__)
    return module


crawler = load_module()


def feed(entries=1, atom_id="http://arxiv.org/abs/2601.12345v2", link=None,
         title=" Fictional\n robotics ", summary="A fictional résumé summary.", author="Zoë Researcher"):
    link = link if link is not None else atom_id
    entry = (f"<entry><id>{escape(atom_id)}</id><title>{escape(title)}</title>"
             f"<summary>{escape(summary)}</summary><author><name>{escape(author)}</name></author>"
             f'<link rel="alternate" type="text/html" href="{escape(link)}"/></entry>')
    return ('<feed xmlns="http://www.w3.org/2005/Atom">' + entry * entries + '</feed>').encode()


class Response:
    def __init__(self, data, status=200):
        self.data, self.status, self.offset, self.read_sizes = data, status, 0, []
        self.closed = False

    def read(self, size):
        self.read_sizes.append(size)
        chunk = self.data[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True


class CrawlerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="knowledge-crawler-fictional-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.network = mock.patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.opener = mock.patch.object(crawler.urllib.request, "build_opener", side_effect=AssertionError("Unmocked fetch forbidden"))
        self.opener.start()
        self.addCleanup(self.opener.stop)
        self.process = mock.patch.object(crawler.subprocess, "run", side_effect=AssertionError("Process execution forbidden"))
        self.process.start()
        self.addCleanup(self.process.stop)
        self.delay = mock.patch("time.sleep")
        self.delay.start()
        self.addCleanup(self.delay.stop)

    def fake_fetch(self, response):
        def open_request(request, timeout):
            self.assertEqual(timeout, 30)
            self.assertEqual(urllib.parse.urlsplit(request.full_url).scheme, "https")
            self.assertEqual(urllib.parse.urlsplit(request.full_url).netloc, "export.arxiv.org")
            response.url = request.full_url
            return response
        opener = mock.Mock()
        opener.open.side_effect = open_request
        return mock.patch.object(crawler.urllib.request, "build_opener", return_value=opener), opener

    def run_main(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = crawler.main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_import_has_no_directory_network_or_process_side_effects(self):
        with mock.patch.object(Path, "mkdir") as mkdir:
            module = load_module()
        mkdir.assert_not_called()
        self.assertEqual(module.DATA_DIR, SOURCE.parent.parent / "data")

    def test_fetch_preserves_identity_and_unicode_from_fixed_https_endpoint(self):
        response = Response(feed())
        patched, opener = self.fake_fetch(response)
        with patched:
            papers = crawler.fetch_arxiv("cs.RO", 1)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(opener.open.call_args.args[0].full_url).query)
        self.assertEqual(query["search_query"], ["cat:cs.RO"])
        self.assertEqual(query["max_results"], ["1"])
        self.assertTrue(response.closed)
        self.assertEqual(papers[0], {"title": "Fictional robotics", "summary": "A fictional résumé summary.",
                                   "authors": ["Zoë Researcher"], "source": "arxiv", "category": "cs.RO",
                                   "id": "http://arxiv.org/abs/2601.12345v2", "url": "https://arxiv.org/abs/2601.12345v2"})

    def test_legacy_identity_and_empty_feed_remain_supported(self):
        self.assertEqual(crawler.parse_feed(feed(atom_id="http://arxiv.org/abs/hep-th/9901001v1"), "cs.AI")[0]["url"],
                         "https://arxiv.org/abs/hep-th/9901001v1")
        self.assertEqual(crawler.parse_feed(feed(entries=0), "q-bio"), [])
        self.assertEqual(len(crawler.parse_feed(feed(summary="x" * 600), "cs.AI")[0]["summary"]), 500)

    def test_response_byte_limit_stops_before_draining_and_closes_response(self):
        response = Response(b"x" * (crawler.MAX_RESPONSE_BYTES + 100000))
        patched, _ = self.fake_fetch(response)
        with patched, self.assertRaisesRegex(crawler.CrawlError, "2 MiB"):
            crawler.fetch_arxiv("cs.AI")
        self.assertEqual(response.offset, crawler.MAX_RESPONSE_BYTES + 1)
        self.assertLess(response.offset, len(response.data))
        self.assertTrue(response.closed)
        self.assertTrue(all(0 < size <= 65536 for size in response.read_sizes))

    def test_invalid_options_fail_before_fetch(self):
        for category, limit in [("other", 50), ("cs.AI", 0), ("cs.AI", 51), ("cs.AI", True)]:
            with self.subTest(category=category, limit=limit), self.assertRaises(crawler.CrawlError):
                crawler.fetch_arxiv(category, limit)

    def test_bad_feed_or_identity_cannot_become_saved_resources(self):
        cases = [b"not xml", b"<wrong/>", feed(entries=2), feed(author=""), feed(title=""),
                 feed(atom_id="http://arxiv.org/api/errors#incorrect_id_format"),
                 feed(link="https://example.invalid/abs/2601.12345v2"),
                 feed(link="https://arxiv.org/abs/2601.99999v2"),
                 feed(atom_id="https://arxiv.org/abs/2601.12345v2?redirect=other"),
                 feed(atom_id="https://arxiv.org/abs/2601.12\n345v2")]
        for data in cases:
            with self.subTest(data=data[:50]), self.assertRaises(crawler.CrawlError):
                crawler.parse_feed(data, "cs.AI", 1)

    def test_http_and_timeout_errors_are_explicit_without_response_body(self):
        for error in [urllib.error.HTTPError(crawler.API_URL, 503, "PRIVATE RESPONSE", {}, None), TimeoutError("PRIVATE RESPONSE")]:
            opener = mock.Mock()
            opener.open.side_effect = error
            with mock.patch.object(crawler.urllib.request, "build_opener", return_value=opener):
                code, _, message = self.run_main("--output-dir", str(self.directory / "new"), "--category", "cs.AI")
            self.assertEqual(code, 1)
            self.assertNotIn("PRIVATE RESPONSE", message)
            self.assertIn("no snapshot was written", message)
            self.assertFalse((self.directory / "new").exists())

    def test_redirect_handler_never_follows_an_alternate_endpoint(self):
        self.assertIsNone(crawler.NoRedirects().redirect_request(None, None, 302, None, None, "https://example.invalid/"))

    def test_interrupted_body_read_is_an_explicit_failure_and_closes_response(self):
        response = Response(feed())
        patched, _ = self.fake_fetch(response)
        with patched, mock.patch.object(response, "read", side_effect=crawler.http.client.IncompleteRead(b"partial", 30)):
            with self.assertRaisesRegex(crawler.CrawlError, "could not be read"):
                crawler.fetch_arxiv("cs.AI")
        self.assertTrue(response.closed)

    def test_publication_utf8_no_clobber_atomic_replacement_and_cleanup(self):
        path = self.directory / "new" / "snapshot.json"
        papers = crawler.parse_feed(feed(), "cs.AI")
        crawler.publish_snapshot(path, papers)
        saved = path.read_bytes()
        self.assertIn("Zoë".encode(), saved)
        self.assertEqual(json.loads(saved), papers)
        with self.assertRaises(FileExistsError):
            crawler.publish_snapshot(path, [], overwrite=False)
        self.assertEqual(path.read_bytes(), saved)
        with mock.patch.object(crawler.os, "replace", side_effect=OSError("fictional write failure")), self.assertRaises(OSError):
            crawler.publish_snapshot(path, [], overwrite=True)
        self.assertEqual(path.read_bytes(), saved)
        crawler.publish_snapshot(path, [], overwrite=True)
        self.assertEqual(json.loads(path.read_bytes()), [])
        self.assertEqual(list(path.parent.glob(".*.tmp")), [])

    def test_failed_fetch_does_not_replace_existing_snapshot(self):
        with mock.patch.object(crawler, "fetch_arxiv", return_value=[]), contextlib.redirect_stdout(io.StringIO()):
            path = crawler.crawl_arxiv(output_dir=self.directory)
        before = path.read_bytes()
        with mock.patch.object(crawler, "fetch_arxiv", side_effect=crawler.CrawlError("fictional failure")) as fetch:
            with self.assertRaisesRegex(crawler.CrawlError, "already exists"):
                crawler.crawl_arxiv(output_dir=self.directory)
            fetch.assert_not_called()
            with self.assertRaisesRegex(crawler.CrawlError, "fictional failure"):
                crawler.crawl_arxiv(output_dir=self.directory, overwrite=True)
        self.assertEqual(path.read_bytes(), before)

    def test_default_four_category_run_does_not_index(self):
        with mock.patch.object(crawler, "fetch_arxiv", return_value=[]) as fetch:
            code, _, errors = self.run_main("--output-dir", str(self.directory))
        self.assertEqual((code, errors), (0, ""))
        self.assertEqual(fetch.call_args_list, [mock.call(category, 50) for category in crawler.CATEGORIES])
        self.assertEqual(len(list(self.directory.glob("*.json"))), 4)

    def test_partial_category_failure_keeps_successful_file_and_skips_index(self):
        executable = self.directory / "fictional-indexer"
        executable.write_text("This file is never executed.")
        with mock.patch.object(crawler, "fetch_arxiv", side_effect=[[], crawler.CrawlError("second category failed")]):
            code, output, errors = self.run_main("--output-dir", str(self.directory), "--index-with", str(executable))
        self.assertEqual(code, 1)
        self.assertIn("Saved 0 arXiv/cs.AI", output)
        self.assertIn("Earlier successful snapshots", errors)
        self.assertEqual(len(list(self.directory.glob("*.json"))), 1)

    def test_sequential_request_spacing_has_no_leading_trailing_or_after_failure_delay(self):
        for fail_at in [None, "cs.AI", "cs.LG"]:
            with self.subTest(fail_at=fail_at):
                events = []
                def fetch(category, _limit):
                    events.append(("fetch", category))
                    if category == fail_at:
                        raise crawler.CrawlError("fictional fetch failure")
                    return []
                directory = self.directory / (fail_at or "success")
                with mock.patch.object(crawler, "fetch_arxiv", side_effect=fetch), mock.patch("time.sleep", side_effect=lambda seconds: events.append(("delay", seconds))):
                    code, _, _ = self.run_main("--output-dir", str(directory))
                expected = [("fetch", "cs.AI")]
                if fail_at != "cs.AI":
                    expected += [("delay", 3), ("fetch", "cs.LG")]
                if fail_at is None:
                    expected += [("delay", 3), ("fetch", "cs.RO"), ("delay", 3), ("fetch", "q-bio")]
                self.assertEqual(events, expected)
                self.assertEqual(code, 0 if fail_at is None else 1)

    def test_explicit_indexing_uses_only_current_files_and_propagates_failure(self):
        executable = self.directory / "fictional-indexer"
        executable.write_text("This file is never executed.")
        old = self.directory / "old.json"
        old.write_text("[]")
        with mock.patch.object(crawler, "fetch_arxiv", return_value=[]), mock.patch.object(crawler.subprocess, "run") as run:
            code, _, _ = self.run_main("--category", "cs.RO", "--category", "cs.RO", "--output-dir", str(self.directory), "--index-with", str(executable))
        self.assertEqual(code, 0)
        self.assertEqual(run.call_count, 1)
        args, options = run.call_args
        self.assertEqual(args[0][0:2], [str(executable.resolve()), "mine"])
        self.assertNotEqual(args[0][2], str(old))
        self.assertEqual(options["timeout"], 120)
        self.assertTrue(options["check"])
        for error in [crawler.subprocess.CalledProcessError(7, ["fictional"]), crawler.subprocess.TimeoutExpired(["fictional"], 120)]:
            with mock.patch.object(crawler.subprocess, "run", side_effect=error), self.assertRaises(crawler.CrawlError):
                crawler.index_to_mempalace([old], executable)

    def test_missing_explicit_indexer_fails_before_fetch(self):
        with mock.patch.object(crawler, "fetch_arxiv") as fetch:
            code, _, error = self.run_main("--index-with", str(self.directory / "missing"))
        self.assertEqual(code, 1)
        self.assertIn("existing executable", error)
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
