"""Weekly drift check for helm4-ready.

Compares what the rules were tested on (src/helm4_ready/rules.py) with the world:
  1. the newest stable Helm 3.x and 4.x releases of helm/helm (a newer release means the oracle has not been run on it);
  2. the Helm 3 end-of-life dates on https://helm.sh/blog/helm-v3-end-of-life.

Exit code 0: nothing to do. 3: drift found (the JSON written with --out has a title and Markdown body for an issue). Anything else: the check itself failed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from helm4_ready.rules import EOL_SOURCE, HELM3_EOL, HELM3_LAST_FEATURE, TESTED  # noqa: E402

RELEASES = "https://api.github.com/repos/helm/helm/releases?per_page=60"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def fetch(url: str, token: str | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "helm4-ready-watch", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def newest(tags, major: str):
    best = None
    for t in tags:
        m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", t)
        if m and m.group(1) == major:
            v = tuple(int(x) for x in m.groups())
            best = max(best, v) if best else v
    return ".".join(map(str, best)) if best else None


def ordinal_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    n = d.day
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{MONTHS[d.month - 1]} {n}{suf}, {d.year}"


def compare(releases_json: str, page_html: str):
    tags = [r["tag_name"] for r in json.loads(releases_json) if not r.get("prerelease") and not r.get("draft")]
    problems = []
    for major in ("3", "4"):
        latest = newest(tags, major)
        if latest is None:
            problems.append(f"no stable Helm {major}.x release found in the newest 60 releases (check the watcher)")
        elif tuple(map(int, latest.split("."))) > tuple(map(int, TESTED[major].split("."))):
            problems.append(f"Helm {latest} is out; the oracle last ran on {TESTED[major]}. Re-run `tests/oracle/run_oracle.py` with it and update `TESTED`, the README validation table and the rules that changed.")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page_html))
    for what, iso in (("last Helm 3 feature release", HELM3_LAST_FEATURE), ("end of Helm 3 security fixes", HELM3_EOL)):
        needle = ordinal_date(iso)
        if needle not in text:
            problems.append(f"the {what} date ({iso}, `{needle}` on the page) is no longer on {EOL_SOURCE}; the dated deadline in the helm3-eol rule may have changed.")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write the issue (title, body) here as JSON when there is drift")
    ap.add_argument("--releases-file", help="test hook: read the releases JSON from a file")
    ap.add_argument("--page-file", help="test hook: read the EOL page from a file")
    a = ap.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    releases = open(a.releases_file, encoding="utf-8").read() if a.releases_file else fetch(RELEASES, token)
    page = open(a.page_file, encoding="utf-8").read() if a.page_file else fetch(EOL_SOURCE)
    problems = compare(releases, page)
    if not problems:
        print(f"no drift: Helm {TESTED['3']} and {TESTED['4']} are the newest releases and the Helm 3 end-of-life dates match the blog post")
        return 0
    key = "-".join(sorted(re.findall(r"Helm (\d+\.\d+\.\d+) is out", " ".join(problems)))) or "dates"
    body = "The weekly watcher found drift between helm4-ready and Helm:\n\n" + "\n".join(f"* {p}" for p in problems) + "\n\nOpened by `scripts/watch/watch_helm.py`; one issue per distinct finding."
    print(body)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump({"title": f"Helm watch: drift [{key}]", "body": body}, fh)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
