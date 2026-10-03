"""Rule registry. Every flag/behaviour rule carries the oracle case that was run against real Helm binaries.

TESTED is the pair of Helm versions the oracle (tests/oracle/run_oracle.py) was last run against; a rule is only claimed for those.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TESTED = {"3": "3.22.0", "4": "4.3.0"}
REPO = "https://github.com/cosmichackerx/helm4-ready"
# Every Helm 4 release the oracle ran on (4.1.2 does not exist). Differences between them are in the facts below.
HELM4_TESTED = ["4.0.0", "4.0.1", "4.0.2", "4.0.4", "4.0.5", "4.1.0", "4.1.1", "4.1.3", "4.1.4", "4.2.0", "4.2.1", "4.2.2", "4.2.3", "4.2.4", "4.3.0"]

# Where Helm 4 releases disagree with each other (oracle-verified: tests/oracle/run_oracle.py --extra-helm4 ... --strict-extra). Anything not listed
# behaved the same on all of HELM4_TESTED. `helm install --atomic` and `helm template --atomic` were unknown flags until Helm 4.1.1 (helm/helm#31900).
ATOMIC_REJECTED = ("4.0.0", "4.0.1", "4.0.2", "4.0.4", "4.0.5", "4.1.0", "4.1.1")
# template --hide-notes / --render-subchart-notes: accepted without a notice before 4.2.0, deprecated since.
TEMPLATE_NOTES_SILENT = ("4.0.0", "4.0.1", "4.0.2", "4.0.4", "4.0.5", "4.1.0", "4.1.1", "4.1.3", "4.1.4")

HELM3_EOL = "2027-02-10"          # security fixes end (extended from 2026-11-11): https://helm.sh/blog/helm-v3-end-of-life
HELM3_LAST_FEATURE = "2026-09-09"  # final limited Helm 3 feature release, bug fixes end with it
EOL_SOURCE = "https://helm.sh/blog/helm-v3-end-of-life"


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    summary: str
    fix: str
    oracle: bool
    url: str = ""

    def __post_init__(self):
        object.__setattr__(self, "url", f"{REPO}#rules")


RULES = {r.id: r for r in [
    Rule("flag-removed", "error", "A Helm 3 flag that Helm 4 rejects with 'unknown flag'", "Remove the flag (see the replacement in the message).", True),
    Rule("flag-deprecated", "warning", "A Helm 3 flag that Helm 4 still accepts but reports as deprecated", "Switch to the new flag (Helm 3 does not know it) or remove the flag.", True),
    Rule("post-renderer-executable", "error", "--post-renderer with an executable path or program name: Helm 4 only takes the name of an installed post-renderer plugin", "Package the post-renderer as a Helm 4 plugin and pass its name.", True),
    Rule("registry-login-url", "error", "helm registry login with a scheme, a path or a trailing slash: Helm 4 accepts only host[:port]", "Pass only the registry host, for example registry.example.com or registry.example.com:5000.", True),
    Rule("helm3-eol", "warning", "A pinned Helm 3 version; Helm 3 security fixes end on " + HELM3_EOL, "Move the pin to Helm 4 and run the CLI rules of this tool.", False),
    Rule("helm-version-latest", "note", "azure/setup-helm without a version (or 'latest') installs Helm 4 today", "Pin the version you test with, or fix the Helm 4 findings.", False),
]}


@dataclass(frozen=True)
class FlagRule:
    """One flag on one or more commands. `oracle` maps a command to the argv (after `helm`) that the oracle runs on Helm 3 and 4."""
    rule: str                 # flag-removed | flag-deprecated
    flags: tuple              # accepted spellings, e.g. ("--atomic",)
    cmds: tuple               # command paths, e.g. (("install",), ("upgrade",))
    replacement: str
    only_value: tuple = ()    # for --dry-run: the flag only counts with these values (empty string = bare)
    oracle_extra: tuple = ()  # extra argv appended in the oracle case
    new: tuple = ()           # argv of the replacement flag, run by the oracle (empty: nothing to run)
    v3_knows_new: bool = False  # whether Helm 3.22.0 accepts the replacement (the oracle checks this)
    note: str = ""            # extra sentence for the message (version differences between Helm 4 releases)


def _c(*names):
    return tuple(tuple(n.split()) for n in names)


FLAG_RULES = [
    # removed in Helm 4 (unknown flag)
    FlagRule("flag-removed", ("--all", "-a"), _c("list"), "removed in Helm 4; select statuses explicitly with --deployed, --failed, --pending, --superseded, --uninstalled, --uninstalling"),
    FlagRule("flag-removed", ("--no-update",), _c("repo add"), "removed in Helm 4; Helm 3 already ignored it (use --force-update to replace an existing repository)", oracle_extra=("x", "https://example.invalid")),
    FlagRule("flag-removed", ("--fail-on-repo-update-fail",), _c("repo update"), "removed in Helm 4, where helm repo update always exits non-zero when a repository cannot be updated (Helm 3 only did with this flag)"),
    FlagRule("flag-removed", ("--recreate-pods",), _c("rollback"), "removed in Helm 4; restart the pods yourself (kubectl rollout restart)", oracle_extra=("r", "1")),
    FlagRule("flag-removed", ("--show-desc", "--show-resources"), _c("status"), "removed in Helm 4 with no replacement flag; helm get manifest and kubectl show the resources", oracle_extra=("r",)),
    FlagRule("flag-removed", ("--hide-notes",), _c("test"), "removed in Helm 4", oracle_extra=("r",)),
    # deprecated in Helm 4 (still accepted)
    FlagRule("flag-deprecated", ("--atomic",), _c("install", "template"), "--rollback-on-failure", new=("--rollback-on-failure",),
             note="Helm 4.0.0 to 4.1.1 reject `--atomic` on install and template as an unknown flag (helm/helm#31900); 4.1.3 and later accept it with this warning"),
    FlagRule("flag-deprecated", ("--atomic",), _c("upgrade"), "--rollback-on-failure", new=("--rollback-on-failure",)),
    FlagRule("flag-deprecated", ("--force",), _c("install", "upgrade", "rollback", "template"), "--force-replace", new=("--force-replace",)),
    FlagRule("flag-deprecated", ("--validate",), _c("template"), "--dry-run=server", new=("--dry-run=server",), v3_knows_new=True),
    FlagRule("flag-deprecated", ("--hide-notes", "--render-subchart-notes"), _c("template"), "nothing: the flag has no effect for helm template and is removed in Helm 5"),
    FlagRule("flag-deprecated", ("--dry-run",), _c("install", "upgrade", "template"), "--dry-run=client (or =server)", only_value=("", "true"), new=("--dry-run=client",), v3_knows_new=True),
]

# the registry/login rule is not a flag rule; the post-renderer rule neither (see scan.py)
POST_RENDERER_CMDS = _c("install", "upgrade", "template")
