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

    def log_message(self, _format, *args):
        pass

    def do_HEAD(self):
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

    def download_fixture(self, handler, *, failure=None):
        with tempfile.TemporaryDirectory() as temporary:
            server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                target = Path(temporary) / "payload.bin"
                target.write_bytes(b"existing verified file")
                url = f"http://127.0.0.1:{server.server_address[1]}"
                if failure:
                    with patch("public_repository_download.time.sleep"), self.assertRaisesRegex(ValueError, failure):
                        fetch(url, "payload.bin", target)
                    self.assertEqual(target.read_bytes(), b"existing verified file")
                else:
                    fetch(url, "payload.bin", target)
                    self.assertEqual(target.read_bytes(), handler.payload)
                self.assertFalse(target.with_suffix(".bin.tmp").exists())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

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


if __name__ == "__main__":
    unittest.main()
