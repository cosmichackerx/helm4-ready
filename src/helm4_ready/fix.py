"""`--fix --target 4`: rewrite the mechanical Helm 3 -> Helm 4 spellings in place.

Only edits whose result the oracle ran on real Helm are made (tests/oracle/run_fix_oracle.py). Text edits at the flag's position, nothing else in the file
changes (line endings and indentation stay). An edit that Helm 3 would reject (`--rollback-on-failure`, `--force-replace`) is refused when the same file
also runs Helm 3, because the file would break on the Helm 3 half.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .rules import FLAG_RULES
from .scan import IGNORE_RE, TOKEN, eol_findings, invocations, locate, logical_lines, strip_comment, suppressed

# Rewrites whose new spelling Helm 3.22.0 accepts but whose behaviour on Helm 3 was not compared (no cluster in the oracle): treated as Helm-4-only.
HELM3_BEHAVIOUR_UNVERIFIED = {"--validate"}


@dataclass
class Edit:
    file: str
    line: int          # 1-based physical line
    start: int         # 0-based offset in that line's content
    end: int
    old: str
    new: str
    rule: str
    helm3_ok: bool     # the result is also accepted by Helm 3.22.0 (oracle) with the same meaning
    why: str


@dataclass
class Skip:
    file: str
    line: int
    rule: str
    text: str
    reason: str


def runs_helm3(text: str, file: str, today: str) -> bool:
    """The file pins or calls Helm 3: a helm3-eol finding or a `helm3` binary."""
    if any(f.rule == "helm3-eol" for f in eol_findings(text, file, today)):
        return True
    return any(re.search(r"(?:^|[\s/\"'=])helm3(?:\.exe)?(?=\s|$|[\"'])", strip_comment(j)) for j, _ in logical_lines(text))


def _arg_span(s: str, idx: int) -> str:
    """The whole shell word starting at idx, including quoted parts and `${{ expressions with spaces }}`."""
    i, q, depth = idx, None, 0
    while i < len(s):
        c = s[i]
        if q:
            if c == q:
                q = None
        elif s.startswith("${{", i):
            depth += 1
            i += 2
        elif depth and s.startswith("}}", i):
            depth -= 1
            i += 1
        elif depth:
            pass
        elif c in "\"'":
            q = c
        elif c.isspace() or c in ";&|()`":
            break
        i += 1
    return s[idx:i]


def _host_of(body: str):
    """body without its quotes -> the host part (before the first slash that is outside `${{ }}`), or None."""
    rest = re.sub(r"^[a-z][a-z0-9+.-]*://", "", body)
    depth, i = 0, 0
    while i < len(rest):
        if rest.startswith("${{", i):
            depth += 1
            i += 3
            continue
        if depth and rest.startswith("}}", i):
            depth -= 1
            i += 2
            continue
        if rest[i] == "/" and not depth:
            return rest[:i]
        i += 1
    return rest


def _raw_token(joined: str, idx: int) -> str:
    m = TOKEN.match(joined, idx)
    return m.group(0) if m else ""


def _plan_line(joined, segs, file):
    """Yield ('edit', Edit) / ('skip', Skip) for one logical line."""
    code = strip_comment(joined)
    if "helm" not in code.lower() and "HELM" not in code:
        return
    for inv in invocations(code):
        names = {fl for fl, _, _ in inv.flags}
        for fl, val, idx in inv.flags:
            ln, col = locate(segs, idx)
            raw = _raw_token(code, idx)
            if not raw or '"' in raw or "'" in raw:
                continue
            start = col - 1
            for fr in FLAG_RULES:
                if inv.cmd not in fr.cmds or fl not in fr.flags:
                    continue
                if fr.rule == "flag-removed":
                    if fr.flags == ("--no-update",) and raw == "--no-update":
                        yield "edit", Edit(file, ln, start, start + len(raw), raw, "", "flag-removed", True,
                                           "repo add --no-update is rejected by Helm 4 and was already ignored by Helm 3")
                    break
                if not fr.new:
                    break
                new = fr.new[0]
                if fr.only_value:  # --dry-run, --validate: whole token becomes the new spelling
                    v = "" if val is None else val.lower()
                    if v not in fr.only_value:
                        break
                    if raw.lower() not in (fl, fl + "=true"):
                        break
                    repl = new
                else:
                    if not (raw == fl or raw.startswith(fl + "=")):
                        break
                    repl = new + raw[len(fl):]
                if fl == "--validate":
                    if raw != "--validate" and raw.lower() != "--validate=true":
                        break
                    if "--dry-run" in names:
                        yield "skip", Skip(file, ln, "flag-deprecated", raw, "the command already has --dry-run; choose =client or =server yourself")
                        break
                yield "edit", Edit(file, ln, start, start + len(raw), raw, repl, "flag-deprecated", fr.v3_knows_new and fl not in HELM3_BEHAVIOUR_UNVERIFIED,
                                   f"{fl} -> {new}")
                break
        if inv.cmd == ("registry", "login") and inv.args:
            host, idx = inv.args[0]
            raw = _arg_span(code, idx)
            if not raw or not (re.search(r"^[\"']?[a-z][a-z0-9+.-]*://", raw) or "/" in raw):
                continue
            q = raw[0] if raw[0] in "\"'" and raw[-1] == raw[0] and len(raw) > 1 else ""
            body = raw[1:-1] if q else raw
            if not q and ('"' in raw or "'" in raw):
                continue
            new_host = _host_of(body)
            ln, col = locate(segs, idx)
            if not new_host or "\n" in raw or new_host == body:
                yield "skip", Skip(file, ln, "registry-login-url", raw, "cannot find the host part")
                continue
            yield "edit", Edit(file, ln, col - 1, col - 1 + len(raw), raw, f"{q}{new_host}{q}", "registry-login-url", True,
                               "registry login takes only host[:port] in Helm 4; Helm 3 accepts that too")


def plan(text: str, file: str, today: str):
    """Return (edits, skips) for one file's text."""
    h3 = runs_helm3(text, file, today)
    lines = text.splitlines()
    edits, skips = [], []
    for joined, segs in logical_lines(text):
        for kind, item in _plan_line(joined, segs, file):
            if suppressed(lines, item.line, item.rule):
                continue
            if kind == "skip":
                skips.append(item)
            elif h3 and not item.helm3_ok:
                skips.append(Skip(file, item.line, item.rule, item.old, f"file also runs Helm 3; `{item.new or 'deleting it'}` would break there"))
            else:
                edits.append(item)
    # an edit that would leave an empty / backslash-only line is refused (it would change the command's line structure)
    out = []
    for e in edits:
        if e.new == "":
            ln = text.splitlines()[e.line - 1]
            rest = (ln[:e.start] + ln[e.end:]).strip()
            if rest in ("", "\\"):
                skips.append(Skip(file, e.line, e.rule, e.old, "the flag is alone on its line; remove it by hand"))
                continue
        out.append(e)
    return out, skips


def apply(text: str, edits) -> str:
    lines = text.splitlines(keepends=True)
    for e in sorted(edits, key=lambda e: (e.line, e.start), reverse=True):
        ln = lines[e.line - 1]
        body = ln.rstrip("\r\n")
        assert body[e.start:e.end] == e.old, (e, body)
        s, t = e.start, e.end
        if e.new == "":  # delete the flag together with one adjacent space
            if s > 0 and body[s - 1] in " \t":
                s -= 1
            elif t < len(body) and body[t] in " \t":
                t += 1
        lines[e.line - 1] = body[:s] + e.new + body[t:] + ln[len(body):]
    return "".join(lines)


def unified(file: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True), f"a/{file}", f"b/{file}"))


def fix_path(path: str, ignore=(), disable=(), only=(), today: str | None = None, write: bool = False):
    """Plan (and with write=True apply) the fixes under `path`. Returns (edits, skips, diffs, files_changed)."""
    import fnmatch
    import os
    from datetime import date

    from .scan import MAX_BYTES, _walk, kind_of

    today = today or date.today().isoformat()
    base = path if os.path.isdir(path) else os.path.dirname(path) or "."
    edits, skips, diffs, changed = [], [], [], 0
    for full in _walk(path, ignore):
        rel = os.path.relpath(full, base).replace(os.sep, "/")
        if not kind_of(os.path.basename(full), rel) or any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(os.path.basename(rel), g) for g in ignore):
            continue
        try:
            if os.path.getsize(full) > MAX_BYTES:
                continue
            with open(full, encoding="utf-8", newline="") as fh:  # newline="": keep CRLF
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        e, s = plan(text, rel, today)
        e = [x for x in e if x.rule not in disable and (not only or x.rule in only)]
        s = [x for x in s if x.rule not in disable and (not only or x.rule in only)]
        skips += s
        if not e:
            continue
        new = apply(text, e)
        edits += e
        diffs.append(unified(rel, text, new))
        changed += 1
        if write:
            with open(full, "w", encoding="utf-8", newline="") as fh:
                fh.write(new)
    return edits, skips, diffs, changed
