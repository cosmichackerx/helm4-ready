"""Find Helm command lines in CI/YAML/shell/Makefile/Dockerfile text and apply the rules.

Text matching, not a shell parser: a logical line (backslash continuations joined) is tokenised, every `helm` word that is followed by a
known sub-command starts an invocation that ends at the next `; & | ( ) \\``. Nothing is executed.
"""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from datetime import date

from .rules import EOL_SOURCE, FLAG_RULES, HELM3_EOL, HELM3_LAST_FEATURE, POST_RENDERER_CMDS, RULES, TESTED

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "target", ".venv", "venv", "__pycache__", ".tox"}
YAML_EXT = (".yml", ".yaml")
SHELL_EXT = (".sh", ".bash", ".zsh", ".ksh", ".envrc")
MAX_BYTES = 1_000_000

TOP = {"install", "upgrade", "template", "rollback", "status", "list", "ls", "test", "repo", "registry", "plugin", "pull", "push", "lint",
       "package", "dependency", "dep", "get", "show", "history", "uninstall", "delete", "un", "create", "search", "verify", "env", "version",
       "completion", "help"}
TWO = {"repo": {"add", "update", "remove", "list", "index"}, "registry": {"login", "logout"}, "plugin": {"install", "list", "uninstall", "update", "package", "verify"},
       "dependency": {"build", "list", "update"}, "dep": {"build", "list", "update"}, "get": {"all", "hooks", "manifest", "metadata", "notes", "values"},
       "show": {"all", "chart", "crds", "readme", "values"}, "search": {"hub", "repo"}}
ALIAS = {"ls": "list", "dep": "dependency", "delete": "uninstall", "un": "uninstall"}
VALUE_FLAGS = {"-u", "-p", "-f", "-o", "-n", "-l", "--username", "--password", "--ca-file", "--cert-file", "--key-file", "--keyring", "--post-renderer", "--post-renderer-args",
               "--set", "--set-string", "--set-file", "--set-json", "--set-literal", "--values", "--version", "--repo", "--timeout", "--output", "--namespace", "--description",
               "--kube-context", "--kubeconfig", "--name-template", "--api-versions", "--kube-version", "--output-dir", "--show-only", "--destination", "--registry-config",
               "--repository-cache", "--repository-config", "--filter", "--selector", "--max", "--offset", "--chart-version"}
GLOBAL_VALUE = {"-n", "--namespace", "--kube-context", "--kubeconfig", "--kube-as-user", "--kube-as-group", "--kube-apiserver", "--kube-token",
                "--kube-ca-file", "--kube-tls-server-name", "--burst-limit", "--qps", "--registry-config", "--repository-cache", "--repository-config", "--color", "--colour", "--content-cache"}


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    col: int
    message: str
    snippet: str = ""

    @property
    def url(self) -> str:
        return RULES[self.rule].url


@dataclass
class Result:
    findings: list = field(default_factory=list)
    files_scanned: int = 0
    invocations: int = 0
    pr: dict | None = None


def kind_of(name: str, path: str = "") -> str | None:
    low = name.lower()
    if low.endswith(YAML_EXT):
        return "yaml"
    if low.endswith(SHELL_EXT):
        return "shell"
    if low in ("makefile", "gnumakefile") or low.endswith(".mk"):
        return "makefile"
    if low == "dockerfile" or low.startswith("dockerfile.") or low.endswith(".dockerfile") or low.startswith("containerfile"):
        return "dockerfile"
    if low in ("jenkinsfile", "justfile", "taskfile"):
        return "shell"
    return None


# ---------------------------------------------------------------- logical lines and tokens
def logical_lines(text: str):
    """Yield (joined_text, [(start_index_in_joined, lineno, col0)]) with backslash continuations joined."""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        parts, segs, pos = [], [], 0
        j = i
        while j < len(lines):
            raw = lines[j]
            body = raw.rstrip()
            cont = body.endswith("\\") and not body.lstrip().startswith("#")
            if cont:
                body = body[:-1]
            lead = len(body) - len(body.lstrip()) if j > i else 0
            piece = body[lead:] if j > i else body
            segs.append((pos, j + 1, lead))
            parts.append(piece)
            pos += len(piece) + 1
            j += 1
            if not cont:
                break
        yield " ".join(parts), segs
        i = j


def locate(segs, idx):
    ln, col0, start = segs[0][1], segs[0][2], segs[0][0]
    for s, l, c in segs:
        if s <= idx:
            ln, col0, start = l, c, s
    return ln, idx - start + col0 + 1


def strip_comment(s: str) -> str:
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or s[i - 1].isspace()):
            return s[:i]
    return s


TOKEN = re.compile(r"""(?:[^\s"';&|()`]+|"[^"]*"|'[^']*')+|[;&|()`]""")


def norm(tok: str) -> str:
    t = tok.strip(",[]")
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1]
    return t


def is_helm(tok: str) -> bool:
    t = norm(tok).lstrip("@")
    return bool(re.fullmatch(r"(?:.*/)?helm[34]?(?:\.exe)?|\$\{?HELM\w*\}?|\$\(HELM\w*\)", t))


# ---------------------------------------------------------------- invocations
@dataclass
class Invocation:
    cmd: tuple
    flags: list          # (flag, value|None, index_in_joined)
    args: list           # positional args after the command path: (text, index)


# a quoted command string handed to a shell: sh "helm ...", bash -c 'helm ...', ["sh", "-c", "helm ..."], eval "helm ...", script: "helm ..."
SHELL_STRING = re.compile(
    r"""((?:\b(?:sh|bash|zsh|dash|eval|script)\b["']?:?\s*\(?\s*|(?:^|\s|["'])-c["']?,?\s*))(["'])"""
    r"""(\s*(?:\$\{?HELM\w*\}?|\$\(HELM\w*\)|(?:[\w./-]*/)?helm[34]?)\s[^"']*)\2""")


def unwrap_shell_strings(s: str) -> str:
    """Blank out the quotes around a command string given to a shell, so its content is tokenized as a command (same length)."""
    def blank(m):
        return m.group(1) + " " + m.group(3) + " "
    return SHELL_STRING.sub(blank, s)


def invocations(joined: str):
    # Make variables: $(VAR) -> $VAR plus two spaces (same length, so indices stay valid); otherwise the parenthesis would end the command
    s = re.sub(r"\$\(([A-Za-z_][\w.-]*)\)", lambda m: "$" + m.group(1) + "  ", joined)
    s = unwrap_shell_strings(s)
    toks = [(m.group(0), m.start()) for m in TOKEN.finditer(s)]
    out = []
    n = len(toks)
    k = 0
    while k < n:
        text, pos = toks[k]
        if text in ";&|()`" or not is_helm(text):
            k += 1
            continue
        # collect arguments until a separator
        j = k + 1
        args = []
        while j < n and toks[j][0] not in ";&|()`":
            args.append(toks[j])
            j += 1
        a = 0
        while a < len(args):  # global flags before the sub-command
            t = norm(args[a][0])
            if t.startswith("-"):
                a += 2 if (t in GLOBAL_VALUE and "=" not in t) else 1
            else:
                break
        if a >= len(args):
            k = j
            continue
        sub = norm(args[a][0])
        if sub not in TOP:
            k = j
            continue
        cmd = [ALIAS.get(sub, sub)]
        a += 1
        if sub in TWO and a < len(args) and norm(args[a][0]) in TWO[sub]:
            cmd.append(norm(args[a][0]))
            a += 1
        flags, pos_args = [], []
        b = a
        while b < len(args):
            t = norm(args[b][0])
            if t.startswith("--") and len(t) > 2:
                name, eq, val = t.partition("=")
                flags.append((name, val if eq else None, args[b][1]))
                if not eq and name in VALUE_FLAGS and b + 1 < len(args):
                    b += 1  # the next token is this flag's value, not a positional argument
            elif t.startswith("-") and len(t) > 1 and not t[1:].isdigit():
                flags.append((t, None, args[b][1]))
                if t in VALUE_FLAGS and b + 1 < len(args):
                    b += 1
            else:
                pos_args.append((t, args[b][1]))
            b += 1
        out.append(Invocation(tuple(cmd), flags, pos_args))
        k = j
    return out


# ---------------------------------------------------------------- rule application
def flag_findings(inv: Invocation, joined: str, segs, file: str, snippet: str):
    res = []
    cmd = inv.cmd
    for fl, val, idx in inv.flags:
        ln, col = locate(segs, idx)
        # --post-renderer / --post-renderer-args
        if cmd in POST_RENDERER_CMDS and fl == "--post-renderer":
            target = val
            if target is None:
                m = re.search(re.escape(fl) + r"\s+(\S+)", joined[idx:])
                target = norm(m.group(1)) if m else ""
            if re.search(r"[/\\]|\.(sh|py|exe|bat|cmd|js|rb)$", target or ""):
                res.append(Finding("post-renderer-executable", "error", file, ln, col,
                                   f"helm {' '.join(cmd)} --post-renderer {target}: Helm {TESTED['4']} rejects an executable path (\"plugin ... not found\"); Helm 4 takes the name of an installed post-renderer plugin", snippet))
            else:
                res.append(Finding("post-renderer-executable", "warning", file, ln, col,
                                   f"helm {' '.join(cmd)} --post-renderer {target}: in Helm 4 this names a post-renderer plugin, not a program on PATH; it fails unless such a plugin is installed (checked on Helm {TESTED['4']})", snippet))
            continue
        for fr in FLAG_RULES:
            if cmd not in fr.cmds or fl not in fr.flags:
                continue
            if fr.only_value:
                v = "" if val is None else val.lower()
                if v not in fr.only_value:
                    continue
            what = f"helm {' '.join(cmd)} {fl}" + (f"={val}" if val is not None else "")
            if fr.rule == "flag-removed":
                msg = f"{what}: Helm {TESTED['4']} rejects it (unknown flag; Helm {TESTED['3']} accepts it) - {fr.replacement}"
                res.append(Finding("flag-removed", "error", file, ln, col, msg, snippet))
            else:
                new = fr.replacement
                tail = "" if new.startswith("nothing") else f" (Helm {TESTED['3']} {'also accepts' if fr.v3_knows_new else 'does not know'} the new spelling)"
                msg = f"{what}: deprecated in Helm {TESTED['4']}, which still accepts it; use {new}" + tail + (f". {fr.note}" if fr.note else "")
                res.append(Finding("flag-deprecated", "warning", file, ln, col, msg, snippet))
            break
    # registry login
    if cmd == ("registry", "login") and inv.args:
        host = inv.args[0][0]
        if re.search(r"^[a-z][a-z0-9+.-]*://", host) or "/" in host:
            idx = inv.args[0][1]
            ln, col = locate(segs, idx)
            res.append(Finding("registry-login-url", "error", file, ln, col,
                               f"helm registry login {host}: Helm {TESTED['4']} fails with \"invalid reference\" for anything but host[:port]; Helm {TESTED['3']} accepts it. Use only the host", snippet))
    return res


EOL_PATTERNS = [
    (re.compile(r"\bHELM_?VERSION\b[\"']?\s*[:=]\s*[\"']?v?(\d+)\.(\d+)", re.I), "a HELM_VERSION of {m}"),
    (re.compile(r"get\.helm\.sh/helm-v(\d+)\.(\d+)\.\d+"), "a get.helm.sh download of Helm {m}"),
    (re.compile(r"get-helm-(3)\b()"), "the get-helm-3 install script"),
    (re.compile(r"\balpine/helm:v?(\d+)(?:\.(\d+))?"), "the alpine/helm:{m} image"),
    (re.compile(r"\bdtzar/helm-kubectl:v?(\d+)(?:\.(\d+))?"), "the dtzar/helm-kubectl:{m} image"),
    (re.compile(r"\bhelm-version\b[\"']?\s*[:=]\s*[\"']?v?(\d+)\.(\d+)", re.I), "a helm-version of {m}"),
]


def eol_severity(today: str) -> tuple:
    left = (date.fromisoformat(HELM3_EOL) - date.fromisoformat(today)).days
    if left < 0:
        return "error", f"Helm 3 security fixes ended on {HELM3_EOL} ({-left} days ago) and no Helm 3 release of any kind is planned"
    if left <= 90:
        return "warning", f"Helm 3 security fixes end on {HELM3_EOL} ({left} days)"
    return "note", f"Helm 3 security fixes end on {HELM3_EOL} ({left} days); the last Helm 3 feature release was {HELM3_LAST_FEATURE}"


def eol_findings(text: str, file: str, today: str):
    out = []
    sev, tail = eol_severity(today)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        code = strip_comment(line)
        for rx, label in EOL_PATTERNS:
            m = rx.search(code)
            if not m or m.group(1) != "3":
                continue
            what = f"`{m.group(0).strip()}` pins Helm 3"
            out.append(Finding("helm3-eol", sev, file, i + 1, m.start() + 1, f"{what}: {tail}. See {EOL_SOURCE}", line.strip()[:160]))
            break
    # azure/setup-helm: with.version
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(?:-\s+)?uses:\s*[\"']?azure/setup-helm@", line)
        if not m:
            continue
        indent = len(m.group(1))
        version = None
        vline = i + 1
        for j in range(i + 1, min(len(lines), i + 25)):
            l2 = lines[j]
            if l2.strip() and (len(l2) - len(l2.lstrip())) <= indent and not l2.strip().startswith("#") and l2.strip().startswith("-"):
                break
            if l2.strip() and (len(l2) - len(l2.lstrip())) < indent:
                break
            mv = re.match(r"^\s*version:\s*[\"']?([^\s\"'#]+)", l2) or re.search(r"\bwith:\s*\{[^}]*\bversion:\s*[\"']?([^\s\"'#,}]+)", l2)
            if mv:
                version, vline = mv.group(1), j + 1
                break
        if version is None or version.lower() == "latest":
            ref = re.search(r"azure/setup-helm@([^\s\"'#]+)", line)
            ref = ref.group(1) if ref else ""
            cm = re.search(r"#\s*v?(\d+)", line)
            major = (re.match(r"v(\d+)", ref) or (cm if re.fullmatch(r"[0-9a-f]{40}", ref) else None))
            major = major.group(1) if major else None
            if major in ("3", "4", "5"):
                msg = (f"azure/setup-helm@v{major} without a version installs the latest Helm, which the action's source resolves to v4.3.0 on 2026-10-03"
                       f" ({'the helm/helm repository' + chr(39) + 's \"latest\" release' if major == '3' else 'get.helm.sh/helm-latest-version'}; read from the source, the action was not run), so this job already runs Helm 4. The CLI rules of helm4-ready apply to it")
            else:
                msg = f"azure/setup-helm@{ref[:12] or '?'} without a version installs 'latest' by that release's own lookup, which was not checked (only v3, v4 and v5 were read), so the Helm major is unknown"
            out.append(Finding("helm-version-latest", "note", file, i + 1, len(m.group(1)) + 1, msg, lines[i].strip()[:160]))
        else:
            mm = re.match(r"v?(\d+)", version)
            if mm and mm.group(1) == "3":
                out.append(Finding("helm3-eol", sev, file, vline, 1, f"azure/setup-helm version {version}: {tail}. See {EOL_SOURCE}", lines[vline - 1].strip()[:160]))
    return out


IGNORE_RE = re.compile(r"helm4-ready:\s*ignore(?:\s+([\w, -]+))?")


def suppressed(lines, line_no: int, rule: str) -> bool:
    for ln in (line_no, line_no - 1):
        if 1 <= ln <= len(lines):
            m = IGNORE_RE.search(lines[ln - 1])
            if m:
                ids = (m.group(1) or "").replace(",", " ").split()
                if not ids or rule in ids:
                    return True
    return False


def scan_text(text: str, file: str, kind: str, today: str, eol: bool = True):
    findings, n_inv = [], 0
    for joined, segs in logical_lines(text):
        code = strip_comment(joined)
        if "helm" not in code.lower() and "HELM" not in code:
            continue
        for inv in invocations(code):
            n_inv += 1
            findings += flag_findings(inv, code, segs, file, code.strip()[:160])
    if eol:
        findings += eol_findings(text, file, today)
    lines = text.splitlines()
    return [f for f in findings if not suppressed(lines, f.line, f.rule)], n_inv


def _walk(path: str, ignore):
    if os.path.isfile(path):
        yield path
        return
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            yield os.path.join(root, f)


def scan(path: str = ".", ignore=(), disabled=(), only=(), today: str | None = None) -> Result:
    today = today or date.today().isoformat()
    base = path if os.path.isdir(path) else os.path.dirname(path) or "."
    res = Result()
    for full in _walk(path, ignore):
        rel = os.path.relpath(full, base).replace(os.sep, "/")
        kind = kind_of(os.path.basename(full), rel)
        if not kind or any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(os.path.basename(rel), g) for g in ignore):
            continue
        try:
            if os.path.getsize(full) > MAX_BYTES:
                continue
            with open(full, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        res.files_scanned += 1
        found, n = scan_text(text, rel, kind, today)
        res.invocations += n
        res.findings += [f for f in found if f.rule not in disabled and (not only or f.rule in only)]
    res.findings.sort(key=lambda f: (f.file, f.line, f.col, f.rule))
    return res
