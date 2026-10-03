"""Collect candidate files for the precision study with the GitHub code search API (read only; opens nothing on those repositories).

    python study/collect.py OUT.json

Every query returns at most 1000 results and the order is GitHub's relevance order, not random: the sample is therefore a convenience sample.
"""
import json
import subprocess
import sys
import time

QUERIES = [
    "helm upgrade --install path:.github/workflows",
    "helm install path:.github/workflows",
    "helm template path:.github/workflows",
    "helm repo add path:.github/workflows",
    "helm rollback path:.github/workflows",
    "helm registry login",
    "helm repo update",
    "helm list --all",
    "helm upgrade --atomic",
    "helm upgrade --install filename:Makefile",
    "helm install filename:Makefile",
    "helm upgrade --install extension:sh",
    "helm install extension:sh",
    "helm --post-renderer",
    "HELM_VERSION path:.github/workflows",
    "azure/setup-helm",
    "helm upgrade --install filename:.gitlab-ci.yml",
    "helm upgrade --install filename:Jenkinsfile",
    "helm upgrade --install filename:Dockerfile",
]
PAGES = 5


def api(path):
    for attempt in range(6):
        p = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if p.returncode == 0:
            return json.loads(p.stdout)
        if "rate limit" in (p.stderr + p.stdout).lower() or "403" in p.stderr:
            time.sleep(30 * (attempt + 1))
            continue
        if "422" in p.stderr:
            return None
        time.sleep(5)
    return None


def main(out):
    seen = {}
    for q in QUERIES:
        for page in range(1, PAGES + 1):
            d = api("search/code?per_page=100&page=%d&q=%s" % (page, q.replace(" ", "+")))
            time.sleep(7)
            if not d or not d.get("items"):
                break
            for it in d["items"]:
                repo = it["repository"]["full_name"]
                if repo.startswith("cosmichackerx/"):
                    continue
                url = it["html_url"]  # https://github.com/o/r/blob/<sha>/<path>
                seen.setdefault(repo + "|" + it["path"], {"repo": repo, "path": it["path"], "html_url": url, "fork": it["repository"].get("fork", False), "query": q})
            print(q, page, len(seen), flush=True)
            if len(d["items"]) < 100:
                break
        json.dump(list(seen.values()), open(out, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
