"""Compare embedding models on the E3.8 golden set (E3.6) — no stack, no Postgres, no Chroma.

    docker compose exec app python scripts/compare_embedders.py            # default candidates
    docker compose exec app python scripts/compare_embedders.py --models all-MiniLM-L6-v2 BAAI/bge-m3

Each candidate runs in its own subprocess (so RSS is a clean before/after-load delta),
embeds the golden docs with the production chunker and ``EmbeddingService`` (so the
per-model query/passage prefixes are the production ones), then answers the golden
questions by brute-force cosine over the chunk vectors. It prints a markdown table:

  dense recall@5 / MRR (file-level, like the golden test) · p50 query ms (embed + search)
  · embedder RAM (RSS delta after load, MB) · model download (HF cache bytes, MB)

These are DENSE-ONLY numbers, for ranking candidates and the RAM/download columns. The
hybrid (vector + FTS) recall that gates releases comes from ``make golden`` — see the
procedure in docs/reference/OPERATIONS.md "Changing the embedding model". The download
column is the model's total HF cache size (already-cached models report it too).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "fixtures" / "golden"
K = 5

# baseline, multilingual-small x2, one heavy. See TODO E3.6.
DEFAULT_MODELS = [
    "all-MiniLM-L6-v2",
    "paraphrase-multilingual-MiniLM-L12-v2",
    "intfloat/multilingual-e5-small",
    "BAAI/bge-m3",  # heavy: ~2.3 GB download, 1024d
]


def _rss_mb() -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def _hf_cache_mb(model: str) -> float:
    """Size of the model's repo in the HF hub cache (blobs are deduplicated)."""
    try:
        from huggingface_hub import constants

        hub = Path(constants.HF_HUB_CACHE)
    except Exception:
        hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    # sentence-transformers resolves bare names like "all-MiniLM-L6-v2" to "sentence-transformers/..."
    repo = model if "/" in model else f"sentence-transformers/{model}"
    blobs = hub / f"models--{repo.replace('/', '--')}" / "blobs"
    if not blobs.is_dir():
        return 0.0
    return sum(f.stat().st_size for f in blobs.iterdir() if f.is_file()) / 1e6


def _worker(model: str) -> dict:
    """Runs in a fresh process: load, embed corpus, answer questions."""
    sys.path.insert(0, str(ROOT))
    import numpy as np

    from adapta.services.documents import chunk_text
    from adapta.services.embeddings import EmbeddingService

    questions = [
        json.loads(ln)
        for ln in (GOLDEN / "questions.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    chunks = []
    for d in sorted((GOLDEN / "docs").iterdir()):
        chunks += chunk_text(d.read_text(encoding="utf-8"), source=d.name)
    texts = [c.text for c in chunks]
    sources = [c.source for c in chunks]

    rss0 = _rss_mb()
    svc = EmbeddingService(model)
    t0 = time.perf_counter()
    svc._load()
    load_s = time.perf_counter() - t0
    rss_delta = _rss_mb() - rss0

    t0 = time.perf_counter()
    mat = np.asarray(svc.embed(texts), dtype="float32")
    index_s = time.perf_counter() - t0
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    svc.embed_one("warm-up")

    rows = []
    for q in questions:
        t0 = time.perf_counter()
        v = np.asarray(svc.embed_one(q["q"]), dtype="float32")
        v /= np.linalg.norm(v)
        order = np.argsort(-(mat @ v))
        ms = (time.perf_counter() - t0) * 1000
        rank = None
        seen: list[str] = []
        for i in order:  # file-level rank over the top chunks, as in the golden test
            seen.append(sources[i])
            if len(seen) > 50:
                break
        for r, s in enumerate(seen, start=1):
            if s == q["expected_file"]:
                rank = r
                break
        rows.append({"rank": rank, "ms": ms, "lang": q["lang"], "q": q["q"]})

    def agg(rs):
        n = len(rs)
        return {
            "n": n,
            "recall": sum(1 for r in rs if r["rank"] and r["rank"] <= K) / n,
            "mrr": sum(1 / r["rank"] for r in rs if r["rank"]) / n,
        }

    return {
        "model": model,
        "dim": int(mat.shape[1]),
        "chunks": len(texts),
        "all": agg(rows),
        "by_lang": {lg: agg([r for r in rows if r["lang"] == lg]) for lg in {r["lang"] for r in rows}},
        "p50_ms": statistics.median(r["ms"] for r in rows),
        "rss_delta_mb": round(rss_delta, 0),
        "download_mb": round(_hf_cache_mb(model), 0),
        "load_s": round(load_s, 1),
        "index_s": round(index_s, 1),
        "misses": [r["q"] for r in rows if not r["rank"] or r["rank"] > K],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--json", action="store_true", help="print raw JSON instead of the table")
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.worker:
        print("RESULT " + json.dumps(_worker(a.worker)))
        return 0

    results = []
    for m in a.models:
        print(f"== {m} ...", file=sys.stderr, flush=True)
        p = subprocess.run(
            [sys.executable, __file__, "--worker", m], capture_output=True, text=True, cwd=ROOT
        )
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("RESULT ")), None)
        if p.returncode != 0 or line is None:
            print(f"   FAILED: {p.stderr[-400:]}", file=sys.stderr)
            continue
        results.append(json.loads(line[7:]))

    if a.json:
        print(json.dumps(results, indent=2))
        return 0
    langs = sorted({lg for r in results for lg in r["by_lang"]})
    head = "| model | dim | recall@5 | MRR | " + " | ".join(f"R@5 {lg}" for lg in langs)
    head += " | p50 ms | RAM MB | download MB |"
    print(head)
    print("|" + "---|" * (head.count("|") - 1))
    for r in results:
        per = " | ".join(f"{r['by_lang'][lg]['recall']:.3f}" for lg in langs)
        print(
            f"| {r['model']} | {r['dim']} | {r['all']['recall']:.3f} | {r['all']['mrr']:.3f} | {per} "
            f"| {r['p50_ms']:.1f} | {r['rss_delta_mb']:.0f} | {r['download_mb']:.0f} |"
        )
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
