"""Run helm4-ready on every downloaded repository directory and write all findings (and per-repo counts) as JSON.

    python study/run_scan.py DEST OUT.json [--today 2026-10-03]
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helm4_ready.scan import scan  # noqa: E402

dest, out = sys.argv[1], sys.argv[2]
today = sys.argv[sys.argv.index("--today") + 1] if "--today" in sys.argv else None
repos, findings = [], []
for d in sorted(os.listdir(dest)):
    p = os.path.join(dest, d)
    if not os.path.isdir(p):
        continue
    r = scan(p, today=today)
    repos.append({"repo": d.replace("__", "/", 1), "files": r.files_scanned, "helm_commands": r.invocations, "findings": len(r.findings)})
    for f in r.findings:
        findings.append({"repo": d.replace("__", "/", 1), "rule": f.rule, "severity": f.severity, "file": f.file, "line": f.line, "message": f.message, "snippet": f.snippet})
json.dump({"repos": repos, "findings": findings}, open(out, "w"), indent=1)
print(len(repos), "repositories,", sum(r["helm_commands"] for r in repos), "helm commands,", len(findings), "findings")
