"""High-throughput range downloader for the Drama-3 weights.

The plain CAS stream dies at ~3 MiB on this host. A single long-lived
response therefore cannot finish a 38 GiB file. This instead resolves the
signed CDN URL once, then pulls many fixed-size byte ranges in parallel and
writes them into a preallocated file. A dropped connection costs one chunk,
not the whole transfer, and the signed URL is re-resolved when it expires.

Usage:
    python _dl_fast.py <manifest.json> [--workers N] [--chunk-mb M] [--proxy MODE]
    manifest.json: [{"file": "...", "out": "...", "size": N}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

import requests

REPO = "t8star/Drama-3-Comfy"
MIRROR = "https://hf-mirror.com"
PROXY = "http://127.0.0.1:10808"

# Keep the malformed inherited NO_PROXY out of the way: bare "::1" and
# bracketed "[::1]" break requests/urllib proxy-bypass parsing.
_NP = "hf-mirror.com,.hf-mirror.com,huggingface.co,.huggingface.co,.hf.co,127.0.0.1,localhost"
os.environ["NO_PROXY"] = _NP
os.environ["no_proxy"] = _NP

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class Fetcher:
    """Resolves the CDN URL and hands out parallel range pulls."""

    def __init__(self, repo: str, filename: str, use_proxy: bool):
        self.repo = repo
        self.filename = filename
        self.use_proxy = use_proxy
        self._lock = threading.Lock()
        self._cdn: str | None = None
        self._cdn_at = 0.0
        self._local = threading.local()

    def _session(self) -> requests.Session:
        """One session per thread: requests.Session is not concurrency-safe."""
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            s.trust_env = False
            if self.use_proxy:
                s.proxies = {"http": PROXY, "https": PROXY}
            else:
                s.proxies = {"http": None, "https": None}
            self._local.s = s
        return s

    def resolve(self) -> str:
        with self._lock:
            if self._cdn and (time.time() - self._cdn_at) < 900:
                return self._cdn
            url = f"{MIRROR}/{self.repo}/resolve/main/{urllib.parse.quote(self.filename)}"
            r = self._session().get(url, allow_redirects=True, timeout=60, stream=True)
            r.close()
            cdn = r.url
            if "resolve" in cdn and "cas" not in cdn and "cdn-lfs" not in cdn:
                raise RuntimeError(f"unexpected redirect target: {cdn}")
            self._cdn = cdn
            self._cdn_at = time.time()
            log(f"resolved CDN: {urllib.parse.urlparse(cdn).hostname}")
            return cdn

    def pull(self, start: int, end: int) -> bytes:
        """Return the bytes for [start, end] inclusive, b'' on failure."""
        for attempt in range(1, 9):
            try:
                cdn = self.resolve()
                headers = {"Range": f"bytes={start}-{end}", "User-Agent": "dsh/1.0"}
                with self._session().get(cdn, headers=headers, stream=True, timeout=600) as r:
                    if r.status_code in (401, 403, 404):
                        with self._lock:
                            self._cdn = None
                        time.sleep(2 + attempt)
                        continue
                    r.raise_for_status()
                    buf = bytearray()
                    for block in r.iter_content(262144):
                        if block:
                            buf.extend(block)
                    if len(buf) != end - start + 1:
                        raise IOError(f"short read {len(buf)}/{end-start+1}")
                    return bytes(buf)
            except Exception as exc:  # noqa: BLE001
                if attempt == 8:
                    log(f"    chunk {start} failed after {attempt}: {type(exc).__name__} {str(exc)[:90]}")
                    return b""
                time.sleep(min(2 * attempt, 10))
        return b""


def download_one(spec: dict, workers: int, chunk_mb: int, use_proxy: bool) -> bool:
    filename = spec["file"]
    out = spec["out"]
    size = int(spec["size"])
    parts_path = out + ".parts"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    chunk = chunk_mb * 1024 * 1024
    nchunks = (size + chunk - 1) // chunk

    done = bytearray(nchunks)
    if os.path.exists(parts_path) and os.path.exists(out):
        saved = open(parts_path, "rb").read()
        if len(saved) == nchunks:
            done = bytearray(saved)
            log(f"  resume: {sum(done)}/{nchunks} chunks already present")
    if not os.path.exists(out) or os.path.getsize(out) != size:
        with open(out, "wb") as fh:
            fh.truncate(size)

    todo = [i for i in range(nchunks) if not done[i]]
    if not todo:
        log(f"  {filename}: already complete")
        return True

    fetcher = Fetcher(REPO, filename, use_proxy)
    fh = open(out, "r+b")
    lock = threading.Lock()
    counter = {"n": 0, "bytes": 0}
    t0 = time.time()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            with lock:
                if not todo:
                    return
                i = todo.pop(0)
            start = i * chunk
            end = min(start + chunk, size) - 1
            n = fetcher.pull(start, end)
            if n:
                with lock:
                    fh.seek(start)
                    fh.write(n)
                    fh.flush()
                    done[i] = 1
                    with open(parts_path, "wb") as pf:
                        pf.write(bytes(done))
                    counter["n"] += 1
                    counter["bytes"] += len(n)
                    el = time.time() - t0
                    rate = counter["bytes"] / max(el, 0.001) / 1048576
                    pct = 100.0 * sum(done) / nchunks
                    log(f"  {filename}: {sum(done)}/{nchunks} chunks "
                        f"({pct:5.1f}%) {counter['bytes']/1073741824:6.2f} GiB "
                        f"@ {rate:6.2f} MiB/s  eta {(size-counter['bytes'])/max(counter['bytes']/max(el,0.001),1)/60:5.1f} min")
            else:
                with lock:
                    todo.append(i)
                time.sleep(3)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fh.close()

    missing = [i for i in range(nchunks) if not done[i]]
    if missing:
        log(f"  {filename}: INCOMPLETE, {len(missing)} chunks missing")
        return False
    log(f"  {filename}: COMPLETE ({size/1073741824:.2f} GiB)")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--chunk-mb", type=int, default=4)
    ap.add_argument("--proxy", choices=["direct", "proxy", "auto"], default="auto")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    specs = json.load(open(args.manifest, encoding="utf-8"))
    if args.only:
        specs = [s for s in specs if args.only in s["file"]]
    use_proxy = args.proxy == "proxy"
    if args.proxy == "auto":
        use_proxy = False  # decided by the benchmark; hf-mirror direct is the only live route

    ok = True
    for spec in specs:
        log(f"=== {spec['file']} -> {spec['out']}")
        if not download_one(spec, args.workers, args.chunk_mb, use_proxy):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
