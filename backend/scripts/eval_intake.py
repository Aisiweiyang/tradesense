"""Run an intake pipeline over the golden set and score field-level accuracy.

Usage: python scripts/eval_intake.py [--pipeline rules|ai]
  rules  — the deterministic slot extractor (baseline; no API key needed)
  ai     — services.ai.intake.propose_slots (needs a configured provider;
           without one this prints a skip note and exits 0)

A field counts as hit when any proposed update for it matches the expected
normalized value (case-insensitive). Report goes to stdout; --out writes JSON.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.slot_extractor import extract_slots  # noqa: E402


def run_rules(text: str) -> dict[str, str]:
    return {u.field: u.normalized for u in extract_slots(text).updates}


def run_ai(text: str) -> dict[str, str] | None:
    from app.services.ai.intake import propose_slots
    updates = propose_slots(text)
    if updates is None:
        return None
    return {u.field: u.normalized for u in updates}


def score(golden: list[dict], got_by_name: dict[str, dict | None],
          pipeline: str) -> dict:
    per_field: dict[str, dict] = {}
    misses = []
    total = hit = 0
    for g in golden:
        got = got_by_name.get(g["name"])
        got = got or {}
        for fld, expected in g["expect"].items():
            total += 1
            bucket = per_field.setdefault(fld, {"hit": 0, "total": 0})
            bucket["total"] += 1
            actual = str(got.get(fld, "")).strip().lower()
            if actual == str(expected).strip().lower():
                hit += 1
                bucket["hit"] += 1
            else:
                misses.append({"name": g["name"], "field": fld,
                               "expected": expected, "got": got.get(fld, "")})
    return {
        "pipeline": pipeline, "samples": len(golden), "fields": total,
        "hit": hit, "accuracy": round(hit / total, 4) if total else None,
        "per_field": {k: round(v["hit"] / v["total"], 2) for k, v in sorted(per_field.items())},
        "misses": misses,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline", choices=["rules", "ai"], default="rules")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    golden = json.loads((Path(__file__).resolve().parent.parent / "eval/golden/intake_golden.json")
                        .read_text(encoding="utf-8"))
    runner = run_rules if args.pipeline == "rules" else run_ai

    got_by_name: dict[str, dict | None] = {}
    for g in golden:
        try:
            got_by_name[g["name"]] = runner(g["text"])
        except Exception as exc:  # noqa: BLE001 — one bad sample must not kill the run
            print(f"[warn] {g['name']}: {exc}", file=sys.stderr)
            got_by_name[g["name"]] = {}

    if args.pipeline == "ai" and all(v is None for v in got_by_name.values()):
        print("AI 不可用（未配置 provider），评估跳过。规则基线请用 --pipeline rules。")
        return 0

    report = score(golden, got_by_name, args.pipeline)
    print(f"pipeline={report['pipeline']}  samples={report['samples']}  "
          f"fields={report['fields']}  hit={report['hit']}  accuracy={report['accuracy']}")
    print("per-field:", json.dumps(report["per_field"], ensure_ascii=False))
    for m in report["misses"][:20]:
        print(f"  miss {m['name']}.{m['field']}: expected {m['expected']!r}, got {m['got']!r}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
