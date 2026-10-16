"""Bounded, resumable downloads from the public DShanPI repository."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def _fail(message: str) -> None:
    raise ValueError(message)


def _fetch_stream(
    request: str | Request,
    temporary: Path,
    relative: str,
    expected_status: int,
    expected_size: int,
) -> None:
    for attempt in range(5):
        try:
            with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                if response.status != expected_status:
                    _fail(f"download failed with HTTP {response.status}: {relative}")
                shutil.copyfileobj(response, output, 1024 * 1024)
            if expected_size and temporary.stat().st_size != expected_size:
                _fail(f"download size mismatch: {relative}")
            return
        except HTTPError as error:
            temporary.unlink(missing_ok=True)
            if error.code in {400, 401, 403, 404}:
                _fail(f"download failed with HTTP {error.code}: {relative}")
            if attempt == 4:
                raise
        except (OSError, http.client.IncompleteRead, ValueError):
            temporary.unlink(missing_ok=True)
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)


def _fetch_range(url: str, part: Path, relative: str, start: int, end: int, total: int) -> None:
    expected_size = end - start + 1
    for attempt in range(5):
        current = part.stat().st_size if part.exists() else 0
        if current == expected_size:
            return
        if current > expected_size:
            _fail(f"range download exceeds expected size: {relative}")
        request = Request(url, headers={
            "Range": f"bytes={start + current}-{end}", "Cache-Control": "no-cache",
        })
        try:
            with urlopen(request, timeout=120) as response, part.open("ab") as output:
                if response.status != 206:
                    _fail(f"range download failed with HTTP {response.status}: {relative}")
                content_range = response.headers.get("Content-Range", "")
                expected_range = f"bytes {start + current}-{end}/{total}"
                if content_range != expected_range:
                    _fail(f"range response mismatch: {relative}")
                shutil.copyfileobj(response, output, 1024 * 1024)
            if part.stat().st_size == expected_size:
                return
        except HTTPError as error:
            if error.code in {400, 401, 403, 404, 416}:
                _fail(f"range download failed with HTTP {error.code}: {relative}")
            if attempt == 4:
                raise
        except (OSError, http.client.IncompleteRead):
            if attempt == 4:
                raise
        time.sleep(2 ** attempt)
    _fail(f"range download remained incomplete: {relative}")


def _fetch_parts(url: str, relative: str, temporary: Path, size: int) -> None:
    workers = min(8, max(2, (size + 16 * 1024 * 1024 - 1) // (16 * 1024 * 1024)))
    chunk = (size + workers - 1) // workers
    parts = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = []
        for index in range(workers):
            start = index * chunk
            end = min(size, start + chunk) - 1
            part = temporary.parent / f"part{index}"
            parts.append(part)
            futures.append(executor.submit(_fetch_range, url, part, relative, start, end, size))
        for future in futures:
            future.result()
    with temporary.open("wb") as output:
        for part in parts:
            with part.open("rb") as stream:
                shutil.copyfileobj(stream, output, 1024 * 1024)
    if temporary.stat().st_size != size:
        _fail(f"download size mismatch: {relative}")


def fetch(
    base_url: str,
    relative: str,
    destination: Path,
    *,
    expected_sha256: str | None = None,
) -> None:
    """Download atomically; when given a signed hash, verify it before replacement."""
    relative_path = PurePosixPath(relative)
    if relative_path.is_absolute() or relative in {"", "."} or str(relative_path) != relative or ".." in relative_path.parts:
        _fail(f"unsafe repository path: {relative}")
    if expected_sha256 is not None and (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        _fail("invalid expected SHA-256")
    url = base_url.rstrip("/") + "/" + quote(relative, safe="/")
    size = 0
    accepts_ranges = False
    for attempt in range(5):
        try:
            request = Request(url, method="HEAD", headers={"Cache-Control": "no-cache"})
            with urlopen(request, timeout=30) as response:
                if response.status != 200:
                    _fail(f"object metadata failed with HTTP {response.status}: {relative}")
                size = int(response.headers.get("Content-Length", "0"))
                if size <= 0:
                    _fail(f"object metadata has no positive size: {relative}")
                accepts_ranges = response.headers.get("Accept-Ranges", "").lower() == "bytes"
            break
        except HTTPError as error:
            if error.code in {400, 401, 403, 404}:
                _fail(f"object metadata failed with HTTP {error.code}: {relative}")
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)
        except (OSError, ValueError):
            if attempt == 4:
                _fail(f"cannot determine public object size: {relative}")
            time.sleep(2 ** attempt)
    # Use the destination filesystem for atomic replacement, with private files
    # per invocation. A failed or concurrent fetch cannot reuse another URL's parts.
    with tempfile.TemporaryDirectory(prefix=".dshanpi-download-", dir=destination.parent) as work:
        temporary = Path(work) / "download"
        if size >= 8 * 1024 * 1024 and accepts_ranges:
            _fetch_parts(url, relative, temporary, size)
        else:
            request = Request(url, headers={"Cache-Control": "no-cache"})
            _fetch_stream(request, temporary, relative, 200, size)
        if expected_sha256 is not None:
            with temporary.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected_sha256:
                _fail(f"downloaded package checksum mismatch: {relative}")
        temporary.replace(destination)
