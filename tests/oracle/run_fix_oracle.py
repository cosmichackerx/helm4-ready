"""Oracle for `helm4-ready --fix --target 4`: apply the fixer to a synthetic command, then run the result on real Helm binaries.

    python tests/oracle/run_fix_oracle.py --helm3 H3 --helm4 H4 [--extra-helm4 H4b ...]

For every command of run_oracle.cases() that the fixer edits:
  * the fixed command must be accepted (no 'unknown flag', no deprecation notice) by every Helm 4 binary;
  * if every edit is marked as accepted on Helm 3, the fixed command must be accepted by Helm 3 too.
The command before the fix is printed for comparison. No cluster is needed (see run_oracle.py).
"""
from __future__ import annotations

import argparse
import os
import shlex
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from run_oracle import Helm, argv_for, cases, classify  # noqa: E402

from helm4_ready.fix import apply, plan  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--helm3", required=True)
    ap.add_argument("--helm4", required=True)
    ap.add_argument("--extra-helm4", action="append", default=[])
    ap.add_argument("--count", action="store_true", help="print how many cases the fixer edits (needs no binary)")
    a = ap.parse_args()
    todo = []
    for name, argv, _e3, _e4 in cases("CHART"):
        text = "helm " + shlex.join(argv)
        edits, skips = plan(text + "\n", "ci.sh", "2026-10-03")
        if edits:
            todo.append((name, text, apply(text + "\n", edits).strip(), all(e.helm3_ok for e in edits)))
    if a.count:
        print(len(todo))
        return 0
    bad = 0
    with tempfile.TemporaryDirectory(prefix="h4fix-") as tmp:
        h3 = Helm(a.helm3, tmp, "h3")
        h4s = [Helm(a.helm4, tmp, "m")] + [Helm(p, tmp, f"x{i}") for i, p in enumerate(a.extra_helm4)]
        for h in [h3] + h4s:
            rc, o = h.run(["create", h.chart])
            if rc != 0:
                print("helm create failed:", o)
                return 2
        print(f"Helm 3: {h3.version()}; Helm 4: " + ", ".join(h.version().split('+')[0] for h in h4s))
        for name, before, after, h3ok in todo:
            b = classify(h4s[0].run(argv_for(shlex.split(before)[1:], "CHART", h4s[0].chart))[1])
            res4 = [classify(h.run(argv_for(shlex.split(after)[1:], "CHART", h.chart))[1]) for h in h4s]
            r3 = classify(h3.run(argv_for(shlex.split(after)[1:], "CHART", h3.chart))[1])
            ok = all(r == "accepted" for r in res4) and (r3 == "accepted" or not h3ok)
            bad += 0 if ok else 1
            tag = "ok  " if ok else "FAIL"
            print(f"{tag} {name:<50} Helm 4 before: {b:<10} after (all {len(h4s)} Helm 4): {','.join(sorted(set(res4)))}; Helm 3 after: {r3}{'' if h3ok else ' (not claimed: Helm-3-incompatible spelling)'}\n     {before}\n  -> {after}")
    print(f"{len(todo)} fixed command(s), {bad} failure(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
