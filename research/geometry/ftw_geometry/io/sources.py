"""Reusable source snapshots and remote identities; no study-specific choices."""

import hashlib
import json
import urllib.request
from datetime import UTC, datetime

from ftw_geometry.io.manifests import file_digest, write_json

USER_AGENT = "Mozilla/5.0 FTW-descriptor-pilot/1.0"


def now():
    return datetime.now(UTC).isoformat()


class Sources:
    """Cache byte snapshots with hashes; never trust an unverified cache file."""

    def __init__(self, root):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def fetch(self, url, name, expected=None):
        path = self.root / name
        record = path.with_name(path.name + ".source.json")
        if path.exists() and record.exists():
            meta = json.loads(record.read_text())
            if meta["url"] != url or file_digest(path) != meta["sha256"]:
                raise ValueError(f"Source cache changed: {path}")
        else:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
                meta = {
                    "url": url,
                    "resolved_url": response.url,
                    "retrieved_at": now(),
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "integrity": "complete downloaded bytes hashed locally",
                }
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
            write_json(record, meta)
        expected_sha256 = (
            expected[4:]
            if expected and len(expected) == 68 and expected.startswith("1220")
            else expected
        )
        if expected_sha256 and meta["sha256"] != expected_sha256:
            raise ValueError(f"Published checksum mismatch: {url}")
        return path, meta


def remote_identity(url):
    request = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return {
            "url": url,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "size_bytes": int(response.headers["Content-Length"]),
            "integrity": "remote identity only; whole raster checksum NOT verified",
        }
