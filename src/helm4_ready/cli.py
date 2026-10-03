"""Command line interface."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .diffmode import GitError, scan_against_base
from .report import RENDERERS, meets_threshold
from .rules import RULES, TESTED
from .scan import scan


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="helm4-ready", description="Find Helm 3 CLI usage that Helm 4 rejects or deprecates in CI workflows, scripts, Makefiles and Dockerfiles, plus the Helm 3 end-of-life date.")
    p.add_argument("path", nargs="?", default=".", help="directory (default: .) or one file")
    p.add_argument("-f", "--format", choices=sorted(RENDERERS), default="text")
    p.add_argument("-o", "--output", help="write the report to a file instead of stdout")
    p.add_argument("--fail-on", choices=["error", "warning", "never"], default="error", help="lowest severity that gives exit code 1 (default: error)")
    p.add_argument("--ignore", action="append", default=[], metavar="GLOB", help="path glob to skip (repeatable)")
    p.add_argument("--disable", action="append", default=[], metavar="RULE", help="turn a rule off (repeatable)")
    p.add_argument("--only", action="append", default=[], metavar="RULE", help="run only this rule (repeatable)")
    p.add_argument("--base", metavar="REF", help="PR mode: report only findings that are new compared to this git revision (merge base with HEAD)")
    p.add_argument("--today", metavar="YYYY-MM-DD", help="date used for the Helm 3 end-of-life ramp (for tests)")
    p.add_argument("--fix", action="store_true", help="rewrite the mechanical Helm 3 spellings in place (needs --target 4); see the README for exactly which")
    p.add_argument("--diff", action="store_true", help="show what --fix would change as a unified diff and write nothing (exit 1 if anything would change)")
    p.add_argument("--target", choices=["4"], help="Helm major the files should be ready for; required with --fix and --diff")
    p.add_argument("--list-rules", action="store_true")
    p.add_argument("--version", action="version", version=f"helm4-ready {__version__} (rules tested on Helm {TESTED['3']} and {TESTED['4']})")
    a = p.parse_args(argv)
    if a.list_rules:
        for r in RULES.values():
            print(f"{r.id:<26} {r.severity:<8} {'oracle (Helm ' + TESTED['3'] + ' / ' + TESTED['4'] + ')' if r.oracle else 'docs':<26} {r.summary}")
        return 0
    for rid in a.disable + a.only:
        if rid not in RULES:
            print(f"unknown rule: {rid} (see --list-rules)", file=sys.stderr)
            return 2
    if a.fix or a.diff:
        if a.target != "4":
            print("helm4-ready: --fix and --diff need --target 4", file=sys.stderr)
            return 2
        if a.base or a.fix and a.diff:
            print("helm4-ready: --base cannot be combined with --fix or --diff, and --fix and --diff exclude each other", file=sys.stderr)
            return 2
        from .fix import fix_path
        edits, skips, diffs, changed = fix_path(a.path, a.ignore, a.disable, a.only, a.today, write=a.fix)
        if a.diff:
            sys.stdout.write("".join(diffs))
        for e in edits:
            print(f"{'fixed' if a.fix else 'would fix'} {e.file}:{e.line}: {e.old} -> {e.new or '(removed)'}  [{e.rule}]", file=sys.stderr)
        for s in skips:
            print(f"skipped {s.file}:{s.line}: {s.text}: {s.reason}  [{s.rule}]", file=sys.stderr)
        left = scan(a.path, a.ignore, a.disable, a.only, a.today)
        left.findings = [f for f in left.findings if f.rule not in ("helm3-eol", "helm-version-latest")]
        print(f"helm4-ready: {len(edits)} edit(s) in {changed} file(s){'' if a.fix else ' (nothing written)'}, {len(skips)} skipped, {len(left.findings)} CLI finding(s) "
              f"{'remain' if a.fix else 'before the fixes'} that need a human (run without --fix for the list)", file=sys.stderr)
        return 1 if a.diff and edits else 0
    if a.base:
        try:
            r = scan_against_base(a.path, a.base, a.ignore, a.disable, a.only, a.today)
        except GitError as e:
            print(f"helm4-ready: {e}", file=sys.stderr)
            return 2
    else:
        r = scan(a.path, a.ignore, a.disable, a.only, a.today)
    text = RENDERERS[a.format](r)
    if a.output:
        with open(a.output, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 1 if meets_threshold(r, a.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
