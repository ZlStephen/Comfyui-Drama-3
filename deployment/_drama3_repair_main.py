"""Locate and repair the chunks written by the concurrent legacy downloader.

The legacy downloader (drama3_chunked.py) ran at the same time as the verified
one and wrote into the SAME output file and the SAME .parts bitmap. Its worker
split was stride = len(chunks) // workers, so worker w owned indices
w, w+stride, w+2*stride, ...  With 4599 chunks and 8 workers the stride is 574,
and the indices it touched are exactly those where (index % 574) < 8.

This re-fetches only those candidate chunks, compares them byte for byte with
what is on disk, rewrites the ones that differ, and reports the damage.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _dl_fast import Fetcher, REPO  # noqa: E402

TARGET = r"J:\ComfyUI-Shared\models\diffusion_models\drama3-t8-fp8.safetensors"
SIZE = 38578460824
CHUNK = 8 * 1024 * 1024
LEGACY_STRIDE = 574
LEGACY_WORKERS = 8
WORKERS = 48

NCHUNKS = (SIZE + CHUNK - 1) // CHUNK
PARTS = TARGET + ".parts"


def candidates() -> list[int]:
    return [i for i in range(NCHUNKS) if (i % LEGACY_STRIDE) < LEGACY_WORKERS]


def main() -> int:
    log_path = r"H:\Object\Comfyui mcp\_drama3_repair.log"

    def log(m):
        line = f"[{time.strftime('%H:%M:%S')}] {m}"
        print(line, flush=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    cand = candidates()
    log(f"candidate chunks (index % {LEGACY_STRIDE} < {LEGACY_WORKERS}): {len(cand)}")

    done = bytearray(NCHUNKS)
    if os.path.exists(PARTS):
        b = open(PARTS, "rb").read()
        if len(b) == NCHUNKS:
            done = bytearray(b)
    # force the candidates to be re-checked
    for i in cand:
        done[i] = 0

    fetcher = Fetcher(REPO, "drama3-t8-fp8.safetensors", False)
    fh = open(TARGET, "r+b")
    lock = threading.Lock()
    todo = list(cand)
    stats = {"checked": 0, "mismatch": 0, "fetch_failed": 0}
    t0 = time.time()

    def worker():
        while True:
            with lock:
                if not todo:
                    return
                i = todo.pop(0)
            start = i * CHUNK
            end = min(start + CHUNK, SIZE) - 1
            n = fetcher.pull(start, end)
            if not n:
                with lock:
                    stats["fetch_failed"] += 1
                log(f"  chunk {i}: fetch failed, leaving it marked done")
                continue
            with lock:
                fh.seek(start)
                disk = fh.read(len(n))
                fh.seek(start)
                if disk != n:
                    fh.write(n)
                    fh.flush()
                    stats["mismatch"] += 1
                    log(f"  chunk {i}: MISMATCH -> repaired")
                stats["checked"] += 1
                done[i] = 1
                with open(PARTS, "wb") as pf:
                    pf.write(bytes(done))
                if stats["checked"] % 10 == 0:
                    el = time.time() - t0
                    log(f"  checked {stats['checked']}/{len(cand)}  "
                        f"mismatches={stats['mismatch']}  "
                        f"{el:.0f}s")

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fh.close()
    log(f"repair pass done: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
