"""F1.3 measurement: generate once per (base|adapter), cache, re-score under candidate gate rules.

Run in the app image from the repo root (see TODO F1.3). Outputs cached in .scratch/f13_outputs.json.
"""
import asyncio
import json
import re
import shutil
from pathlib import Path

from adapta.core import adapter_conversion
from adapta.core.model_catalog import resolve
from adapta.services import eval_gate as eg

BASE = "qwen2.5-0.5b-instruct"
FIX = Path("tests/fixtures/adapters")
CACHE = Path(".scratch/f13_outputs_{}.json")
ROWS_CLS = [json.loads(x) for x in (FIX / "classify-pass/dataset_eval.jsonl").read_text().splitlines() if x.strip()]
TEAM = {"billing": "billing", "technical": "technical support", "account": "account management"}
# Freeform-shaped variant of the SAME 30 tickets: sentence references, sentence-style system prompt.
ROWS_FREE = [
    {
        "system": "Reply in one sentence saying which team should handle this support message: billing, technical support or account management.",
        "prompt": r["prompt"],
        "response": f"This message should be handled by the {TEAM[r['response']]} team.",
    }
    for r in ROWS_CLS
]
SETS = {"classify-shaped": ROWS_CLS, "freeform-shaped": ROWS_FREE}


async def generate(name, rows) -> dict:
    out = {}
    out["base"] = (await eg.score(BASE, None, rows, "classify")).predictions
    out["classify-pass"] = (await eg.score(BASE, str(FIX / "classify-pass/adapter.gguf"), rows, "classify")).predictions
    work = Path(".scratch/garbage-control")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(FIX / "garbage-control", work)
    gguf = await adapter_conversion.convert_peft_to_gguf(work, base_config_dir=resolve(BASE).hf_config_dir())
    out["garbage-control"] = (await eg.score(BASE, str(gguf), rows, "classify")).predictions
    Path(str(CACHE).format(name)).write_text(json.dumps(out, indent=1))
    return out


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def metrics(rows, preds):
    refs = [r["response"] for r in rows]
    f1 = eg.aggregate("freeform", preds, refs)[0]
    em = sum(norm(p) == norm(r) for p, r in zip(preds, refs)) / len(refs)
    # classify reference: accuracy of the team label ("is the reference's label word in the output")
    return f1, em


def main():
    for name, rows in SETS.items():
        path = Path(str(CACHE).format(name))
        out = json.loads(path.read_text()) if path.exists() else asyncio.run(generate(name, rows))
        print(f"== eval set: {name} ({len(rows)} rows)")
        m = {k: metrics(rows, v) for k, v in out.items()}
        for k, (f1, em) in m.items():
            acc = eg.aggregate("classify", out[k], [r["response"] for r in ROWS_CLS if True])[0] if name == "classify-shaped" else float("nan")
            print(f"  {k:16s} F1={f1:.3f} EM={em:.3f} classify={acc:.3f}")
        for k in ("classify-pass", "garbage-control"):
            for mn, idx in (("F1", 0), ("EM", 1)):
                d = eg.passes(m[k][idx], m["base"][idx])
                print(f"    {k} {mn}: delta={d.delta:+.3f} current-rule passed={d.passed} ({d.rule})")
        for k in out:
            print("  ", k, [x[:70] for x in out[k][:3]])


main()
