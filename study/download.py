"""Download the files named by collect.py at the commit code search returned (raw.githubusercontent.com, no API quota, read only).

    python study/download.py FILES.json DEST [--max-per-repo 6]
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor


def main():
    files = json.load(open(sys.argv[1]))
    dest = sys.argv[2]
    cap = 6
    if "--max-per-repo" in sys.argv:
        cap = int(sys.argv[sys.argv.index("--max-per-repo") + 1])
    per = {}
    jobs = []
    for f in files:
        m = re.match(r"https://github.com/([^/]+/[^/]+)/blob/([0-9a-f]{40})/(.+)$", f["html_url"])
        if not m:
            continue
        repo, sha, path = m.groups()
        if per.get(repo, 0) >= cap:
            continue
        per[repo] = per.get(repo, 0) + 1
        jobs.append((repo, sha, path, f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"))

    def get(j):
        repo, sha, path, url = j
        out = os.path.join(dest, repo.replace("/", "__"), path)
        if os.path.exists(out):
            return 0
        os.makedirs(os.path.dirname(out), exist_ok=True)
        r = subprocess.run(["curl", "-fsSL", "--max-time", "30", "--max-filesize", "1000000", "-o", out, url], capture_output=True)
        if r.returncode != 0 and os.path.exists(out):
            os.remove(out)
        return 1 if r.returncode != 0 else 0

    with ThreadPoolExecutor(4) as ex:
        failed = sum(ex.map(get, jobs))
    json.dump([{"repo": r, "sha": s, "path": p} for r, s, p, _ in jobs], open(os.path.join(dest, "_manifest.json"), "w"), indent=1)
    print(f"{len(per)} repositories, {len(jobs)} files, {failed} downloads failed")


main()
