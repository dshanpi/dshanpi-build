from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import http.server
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from public_repository_download import fetch  # noqa: E402


class RangeHandler(http.server.BaseHTTPRequestHandler):
    payload = (b"dshanpi-range-fixture-" * 500000)[: 9 * 1024 * 1024]
    plain_status = 206
    range_total_offset = 0
    head_status = 200
    truncate_ranges = False

    def log_message(self, _format, *args):
        pass

    def do_HEAD(self):
        if self.head_status != 200:
            self.head_requests.append(self.path)
            self.send_error(self.head_status)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.payload)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()

    def do_GET(self):
        value = self.headers.get("Range")
        if not value:
            # Reproduce a CDN/proxy that returns only an initial slice for a
            # large object. The shared downloader must not take this path.
            body = self.payload[: 5 * 1024 * 1024]
            self.send_response(self.plain_status)
            self.send_header("Content-Range", f"bytes 0-{len(body) - 1}/{len(self.payload)}")
        else:
            prefix = "bytes="
            self.assert_range(value.startswith(prefix))
            start_text, end_text = value[len(prefix):].split("-", 1)
            start, end = int(start_text), int(end_text)
            body = self.payload[start:end + 1]
            if self.truncate_ranges:
                self.ranges.append((start, end))
                if start in self.initial_starts:
                    body = body[:1024 * 1024]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(self.payload) + self.range_total_offset}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Invalid headers are rejected before the client reads the body.
            pass

    def assert_range(self, condition):
        if not condition:
            self.send_error(400)
            raise AssertionError("invalid test range")


class PublicRepositoryDownloadTests(unittest.TestCase):
    def test_rejects_repository_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "payload.bin"
            for relative in ["../payload.bin", "/payload.bin", "", ".", "pool/../payload.bin", "pool//payload.bin"]:
                with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "unsafe repository path"):
                    fetch("https://apt.invalid", relative, target)
            self.assertFalse(target.exists())

    @contextmanager
    def fixture(self, handler):
        with tempfile.TemporaryDirectory() as temporary:
            server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                target = Path(temporary) / "payload.bin"
                target.write_bytes(b"existing verified file")
                url = f"http://127.0.0.1:{server.server_address[1]}"
                yield target, url
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def download_fixture(self, handler, *, failure=None):
        with self.fixture(handler) as (target, url):
            if failure:
                with patch("public_repository_download.time.sleep"), self.assertRaisesRegex(ValueError, failure):
                    fetch(url, "payload.bin", target)
                self.assertEqual(target.read_bytes(), b"existing verified file")
            else:
                fetch(url, "payload.bin", target)
                self.assertEqual(target.read_bytes(), handler.payload)
            self.assertFalse(target.with_suffix(".bin.tmp").exists())
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_large_object_uses_complete_bounded_ranges(self):
        self.download_fixture(RangeHandler)

    def test_small_object_uses_complete_stream(self):
        handler = type("SmallHandler", (RangeHandler,), {"payload": b"small payload", "plain_status": 200})
        self.download_fixture(handler)

    def test_rejects_range_with_wrong_object_size(self):
        handler = type("WrongTotalHandler", (RangeHandler,), {"range_total_offset": 1})
        self.download_fixture(handler, failure="range response mismatch")

    def test_rejects_unrequested_partial_response(self):
        handler = type("PartialHandler", (RangeHandler,), {"payload": b"small payload"})
        self.download_fixture(handler, failure="download failed with HTTP 206")

    def test_rejects_truncated_stream(self):
        handler = type("TruncatedHandler", (RangeHandler,), {
            "payload": b"x" * (6 * 1024 * 1024), "plain_status": 200,
        })
        self.download_fixture(handler, failure="download size mismatch")

    def test_ignores_stale_parts_from_another_download(self):
        with self.fixture(RangeHandler) as (target, url):
            stale = target.with_suffix(".bin.tmp.part0")
            stale.write_bytes(b"x" * ((len(RangeHandler.payload) + 1) // 2))
            fetch(url, "payload.bin", target)
            self.assertEqual(target.read_bytes(), RangeHandler.payload)

    def test_concurrent_downloads_use_independent_temporary_files(self):
        with self.fixture(RangeHandler) as (target, url):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(fetch, url, "payload.bin", target) for _ in range(2)]
                for future in futures:
                    future.result()
            self.assertEqual(target.read_bytes(), RangeHandler.payload)
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_checksum_mismatch_preserves_target_and_can_retry(self):
        handler = type("SmallHandler", (RangeHandler,), {"payload": b"small payload", "plain_status": 200})
        with self.fixture(handler) as (target, url):
            expected = hashlib.sha256(b"correct payload").hexdigest()
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                fetch(url, "payload.bin", target, expected_sha256=expected)
            self.assertEqual(target.read_bytes(), b"existing verified file")
            self.assertEqual(list(target.parent.iterdir()), [target])
            expected = hashlib.sha256(handler.payload).hexdigest()
            fetch(url, "payload.bin", target, expected_sha256=expected)
            self.assertEqual(target.read_bytes(), handler.payload)

    def test_range_retry_resumes_incomplete_parts(self):
        handler = type("ResumeHandler", (RangeHandler,), {
            "truncate_ranges": True, "ranges": [],
            "initial_starts": {0, (len(RangeHandler.payload) + 1) // 2},
        })
        with patch("public_repository_download.time.sleep"):
            self.download_fixture(handler)
        for start in handler.initial_starts:
            self.assertIn(start + 1024 * 1024, {value[0] for value in handler.ranges})

    def test_missing_object_fails_without_retries(self):
        handler = type("MissingHandler", (RangeHandler,), {"head_status": 404, "head_requests": []})
        self.download_fixture(handler, failure="object metadata failed with HTTP 404")
        self.assertEqual(len(handler.head_requests), 1)


if __name__ == "__main__":
    unittest.main()
