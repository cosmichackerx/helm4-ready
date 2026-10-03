"""Draw the random sample of findings that gets labelled by hand (fixed seed) and print each with its surrounding lines.

    python study/sample.py SCAN.json FILES_DIR OUT.md [--seed 20261003]
"""
import json
import os
import random
import sys

scan, files, out = sys.argv[1:4]
seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 20261003
SIZES = {"flag-removed": 40, "flag-deprecated": 40, "post-renderer-executable": 25, "registry-login-url": 25, "helm3-eol": 30, "helm-version-latest": 20}
data = json.load(open(scan))
rng = random.Random(seed)
lines_out = []
chosen = []
for rule, n in SIZES.items():
    pool = sorted((f for f in data["findings"] if f["rule"] == rule), key=lambda f: (f["repo"], f["file"], f["line"]))
    pick = rng.sample(pool, min(n, len(pool)))
    for f in pick:
        chosen.append({**f, "id": f"{rule}-{len(chosen)}"})
for f in chosen:
    path = os.path.join(files, f["repo"].replace("/", "__"), f["file"])
    try:
        src = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        src = []
    a, b = max(0, f["line"] - 4), min(len(src), f["line"] + 2)
    lines_out.append(f"### {f['id']}  {f['rule']} ({f['severity']})  {f['repo']}  {f['file']}:{f['line']}")
    lines_out.append("```")
    for i in range(a, b):
        lines_out.append(("=> " if i + 1 == f["line"] else "   ") + f"{i + 1}: {src[i][:170]}")
    lines_out.append("```")
    lines_out.append(f"msg: {f['message'][:150]}\n")
open(out, "w").write("\n".join(lines_out))
json.dump(chosen, open(out.replace(".md", ".json"), "w"), indent=1)
print({r: sum(1 for c in chosen if c["rule"] == r) for r in SIZES})
