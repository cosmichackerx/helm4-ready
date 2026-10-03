"""Oracle: run the same commands on real Helm 3 and Helm 4 binaries and compare with what helm4-ready claims.

No cluster is needed: the checks are about flag parsing, deprecation notices and argument validation, which Helm does before it talks to
a cluster or a registry (the .invalid TLD never resolves, so network calls fail the same way everywhere).

    python tests/oracle/run_oracle.py --helm3 /path/to/helm3 --helm4 /path/to/helm4

Classification of one run (stderr + stdout):
  rejected    "unknown flag", "unknown shorthand flag", 'invalid argument ... for ... flag', "invalid reference"
  deprecated  "has been deprecated" / "is deprecated"
  accepted    anything else (including later failures such as 'cluster unreachable')
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from helm4_ready.rules import FLAG_RULES, TESTED  # noqa: E402

REJ = re.compile(r"unknown flag|unknown shorthand flag|invalid argument .* for .* flag|invalid reference", re.I)
DEP = re.compile(r"has been deprecated|is deprecated", re.I)


def classify(out: str) -> str:
    if REJ.search(out):
        return "rejected"
    if DEP.search(out):
        return "deprecated"
    return "accepted"


class Helm:
    def __init__(self, path: str, tmp: str, tag: str):
        self.path, self.tag = path, tag
        h = os.path.join(tmp, tag)
        os.makedirs(h, exist_ok=True)
        self.env = {"PATH": "/usr/bin:/bin", "HOME": h, "HELM_CACHE_HOME": h + "/cache", "HELM_CONFIG_HOME": h + "/config", "HELM_DATA_HOME": h + "/data",
                    "KUBECONFIG": h + "/none", "HELM_REPOSITORY_CONFIG": h + "/repositories.yaml", "HELM_REPOSITORY_CACHE": h + "/rcache"}
        self.chart = os.path.join(tmp, "chart-" + tag)

    def run(self, args, stdin="pw\n"):
        p = subprocess.run([self.path, *args], capture_output=True, text=True, timeout=120, env=self.env, input=stdin, cwd=os.path.dirname(self.chart))
        return p.returncode, p.stderr + p.stdout

    def version(self) -> str:
        return self.run(["version", "--short"])[1].strip()


def positional(cmd, chart):
    if cmd[0] in ("install", "upgrade", "template"):
        return ["r", chart]
    return []


def cases(chart):
    """(name, argv, expected classification on Helm 3, on Helm 4)"""
    out = []
    for fr in FLAG_RULES:
        for cmd in fr.cmds:
            base = list(cmd) + (list(fr.oracle_extra) if fr.oracle_extra else positional(cmd, chart))
            for fl in fr.flags:
                if fr.only_value:
                    out.append((f"{' '.join(cmd)} {fl}", base + [fl], "accepted", "deprecated"))
                    out.append((f"{' '.join(cmd)} {fl}=true", base + [fl + "=true"], "accepted", "deprecated"))
                else:
                    out.append((f"{' '.join(cmd)} {fl}", base + [fl], "accepted", "rejected" if fr.rule == "flag-removed" else "deprecated"))
            if fr.new:
                out.append((f"{' '.join(cmd)} {' '.join(fr.new)} (replacement)", base + list(fr.new), "accepted" if fr.v3_knows_new else "rejected", "accepted"))
    t = ["template", "r", chart]
    out += [
        ("template --atomic=false (Helm warns whenever the flag is set)", t + ["--atomic=false"], "accepted", "deprecated"),
        ("template --dry-run=false (no notice)", t + ["--dry-run=false"], "accepted", "accepted"),
        ("template --post-renderer /bin/cat", t + ["--post-renderer", "/bin/cat"], "accepted", "rejected"),
        ("template --post-renderer ./x.sh (executable file)", t + ["--post-renderer", "./x.sh"], "accepted", "rejected"),
        ("template --post-renderer cat (bare name)", t + ["--post-renderer", "cat"], "accepted", "rejected"),
        ("upgrade --post-renderer /bin/cat", ["upgrade", "r", chart, "--post-renderer", "/bin/cat"], "accepted", "rejected"),
        ("template --post-renderer-args x alone (control: flag still exists)", t + ["--post-renderer-args", "x"], "accepted", "accepted"),
    ]
    for host in ("https://example.invalid", "example.invalid/path", "oci://example.invalid", "https://example.invalid/"):
        out.append((f"registry login {host}", ["registry", "login", host, "-u", "u", "--password-stdin"], "accepted", "rejected"))
    out.append(("registry login example.invalid:5000 (control)", ["registry", "login", "example.invalid:5000", "-u", "u", "--password-stdin"], "accepted", "accepted"))
    out.append(("template (control, no flags)", t, "accepted", "accepted"))
    return out


def repo_update_default(h3: Helm, h4: Helm) -> list:
    """Helm 3 exits 0 when a repository cannot be updated unless --fail-on-repo-update-fail is given; Helm 4 always fails."""
    res = []
    for h in (h3, h4):
        with open(h.env["HELM_REPOSITORY_CONFIG"], "w") as fh:
            fh.write('apiVersion: ""\ngenerated: "0001-01-01T00:00:00Z"\nrepositories:\n- name: bad\n  url: https://example.invalid\n')
    r3, _ = h3.run(["repo", "update"])
    r3f, _ = h3.run(["repo", "update", "--fail-on-repo-update-fail"])
    r4, _ = h4.run(["repo", "update"])
    res.append(("repo update with an unreachable repository: exit code", f"Helm 3: {r3} (with the flag: {r3f}), Helm 4: {r4}", r3 == 0 and r3f != 0 and r4 != 0))
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--helm3", required=True)
    ap.add_argument("--helm4", required=True)
    ap.add_argument("--markdown", help="also write the result table as Markdown here")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="h4oracle-") as tmp:
        h3, h4 = Helm(a.helm3, tmp, "h3"), Helm(a.helm4, tmp, "h4")
        v3, v4 = h3.version(), h4.version()
        print(f"Helm 3 under test: {v3}\nHelm 4 under test: {v4}")
        if TESTED["3"] not in v3 or TESTED["4"] not in v4:
            print(f"note: rules.py claims Helm {TESTED['3']} and {TESTED['4']}; the binaries above differ, so a pass does not confirm those claims")
        x = os.path.join(tmp, "x.sh")
        with open(x, "w") as fh:
            fh.write("#!/bin/sh\ncat\n")
        os.chmod(x, 0o755)
        for h in (h3, h4):
            rc, o = h.run(["create", h.chart])
            if rc != 0:
                print("helm create failed:", o)
                return 2
        bad = 0
        rows = []
        for name, argv, e3, e4 in cases(h3.chart):
            _, o3 = h3.run([x.replace(h3.chart, h3.chart) for x in argv])
            _, o4 = h4.run([x.replace(h3.chart, h4.chart) for x in argv])
            g3, g4 = classify(o3), classify(o4)
            ok = (g3, g4) == (e3, e4)
            bad += 0 if ok else 1
            rows.append((name, g3, g4, ok))
            print(f"{'ok  ' if ok else 'FAIL'} {name:<58} helm3={g3:<10} helm4={g4:<10}" + ("" if ok else f" expected helm3={e3} helm4={e4}\n      helm3 said: {o3.strip()[:160]!r}\n      helm4 said: {o4.strip()[:160]!r}"))
        for name, what, ok in repo_update_default(h3, h4):
            bad += 0 if ok else 1
            rows.append((name, what, "", ok))
            print(f"{'ok  ' if ok else 'FAIL'} {name}: {what}")
        print(f"{len(rows)} case(s), {bad} disagreement(s)")
        if a.markdown:
            with open(a.markdown, "w") as fh:
                fh.write(f"Helm 3 {v3}, Helm 4 {v4}\n\n| Case | Helm 3 | Helm 4 | As claimed |\n|---|---|---|---|\n")
                for n, g3, g4, ok in rows:
                    fh.write(f"| `{n}` | {g3} | {g4} | {'yes' if ok else '**NO**'} |\n")
        return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
