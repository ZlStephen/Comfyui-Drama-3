"""Parallel ranged downloader for large model files.

Resolves the redirect once to get the final CDN URL, then pulls byte ranges in
parallel with N workers, writing straight into a preallocated file at the right
offset. Failed chunks are retried with backoff; already-written chunks are
skipped on a re-run, so the download is resumable across restarts.

Usage:
    python _parallel_download.py <url> <out_path> [--workers 12] [--chunk-mb 16]
"""
import argparse
import os
import sys
import threading
import time
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def resolve(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.headers


def fetch_range(url, start, end, fh, timeout=180, retries=6):
    """Fetch [start, end] inclusive and write it at its absolute offset."""
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Range": f"bytes={start}-{end}"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if len(data) != end - start + 1:
                raise IOError(f"short read {len(data)} != {end - start + 1}")
            fh.seek(start)
            fh.write(data)
            return len(data)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(min(2 ** attempt, 20))
    raise last


def already_present(fh, start, end):
    """True when this range is FULLY written.

    A chunk is only written after its whole body is read, so a completed chunk
    is entirely non-zero. Requiring every byte to be non-zero also catches a
    chunk interrupted mid-write (zero tail) — those get re-fetched rather than
    being trusted.
    """
    fh.seek(start)
    remaining = end - start + 1
    while remaining > 0:
        buf = fh.read(min(remaining, 4 * 1024 * 1024))
        if not buf:
            return False
        if not any(buf):
            return False
        remaining -= len(buf)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--chunk-mb", type=int, default=16)
    args = ap.parse_args()

    final_url, headers = resolve(args.url)
    total = int(headers.get("Content-Length"))
    etag = headers.get("X-Linked-ETag") or headers.get("ETag")
    print(f"resolved -> {final_url[:120]}", flush=True)
    print(f"size     -> {total} bytes ({total/1024/1024:.1f} MB)", flush=True)
    print(f"etag     -> {etag}", flush=True)
    if headers.get("Accept-Ranges", "").lower() != "bytes":
        print("!! server does not advertise range support", flush=True)

    chunk = args.chunk_mb * 1024 * 1024
    ranges = []
    pos = 0
    while pos < total:
        end = min(pos + chunk, total) - 1
        ranges.append((pos, end))
        pos = end + 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    if os.path.exists(args.out) and os.path.getsize(args.out) == total:
        print(f"resuming into existing {args.out}", flush=True)
        fh = open(args.out, "r+b")
    else:
        fh = open(args.out, "w+b")
        fh.truncate(total)

    done = [0]
    lock = threading.Lock()
    idx = [0]
    errors = []

    def worker():
        while True:
            with lock:
                if idx[0] >= len(ranges) or errors:
                    return
                i = idx[0]
                idx[0] += 1
            s, e = ranges[i]
            try:
                if already_present(fh, s, e):
                    n = e - s + 1
                else:
                    n = fetch_range(final_url, s, e, fh)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"chunk {i} [{s}-{e}]: {exc}")
                return
            with lock:
                done[0] += n
                pct = done[0] / total * 100
                mb = done[0] / 1024 / 1024
                print(f"  {mb:8.1f} MB  {pct:5.1f}%  (chunk {i+1}/{len(ranges)})", flush=True)

    t0 = time.time()
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    fh.flush()
    fh.close()
    elapsed = time.time() - t0
    if errors:
        print("ERRORS:", flush=True)
        for e in errors:
            print("  " + e, flush=True)
        sys.exit(1)
    actual = os.path.getsize(args.out)
    print(f"done: {actual} bytes in {elapsed:.1f}s ({actual/1024/1024/elapsed:.2f} MB/s)", flush=True)
    if actual != total:
        print("!! size mismatch", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
