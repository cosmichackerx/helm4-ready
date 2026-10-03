"""Independent cross-check for misses: a loose regex finds lines that mention helm, the sub-command and a flag the rules know; lines helm4-ready did not flag are listed.

    python study/loose.py FILES_DIR SCAN.json OUT.json
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from helm4_ready.rules import FLAG_RULES  # noqa: E402
from helm4_ready.scan import kind_of  # noqa: E402

files, scan, out = sys.argv[1:4]
flagged = {(f["repo"], f["file"], f["line"]) for f in json.load(open(scan))["findings"]}
rx = []
for fr in FLAG_RULES:
    for cmd in fr.cmds:
        for fl in fr.flags:
            flag = re.escape(fl) + r"(?![\w-])"
            if fr.only_value:
                flag = re.escape(fl) + r"(?:=true)?(?![\w=-])"
            rx.append((re.compile(r"\bhelm[34]?\b[^\n#]*\b" + r"\s+(?:\S+\s+)*?".join(map(re.escape, cmd)) + r"\b[^\n#]*" + flag), f"{' '.join(cmd)} {fl}"))
hits, missed = 0, []
for d in sorted(os.listdir(files)):
    root = os.path.join(files, d)
    if not os.path.isdir(root):
        continue
    for dp, _, fs in os.walk(root):
        for f in fs:
            full = os.path.join(dp, f)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if not kind_of(f, rel):
                continue
            for i, line in enumerate(open(full, encoding="utf-8", errors="replace").read().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                for r, name in rx:
                    if r.search(line):
                        hits += 1
                        if (d.replace("__", "/", 1), rel, i) not in flagged:
                            missed.append({"repo": d.replace("__", "/", 1), "file": rel, "line": i, "rule_hit": name, "text": line.strip()[:200]})
                        break
json.dump({"loose_hits": hits, "unflagged": missed}, open(out, "w"), indent=1)
print(hits, "loose hits,", len(missed), "not flagged")
