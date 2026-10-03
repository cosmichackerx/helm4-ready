import json
import textwrap

import pytest

from helm4_ready.rules import FLAG_RULES, RULES, TESTED
from helm4_ready.scan import eol_severity, kind_of, scan_text
from helm4_ready.cli import main

TODAY = "2026-10-03"


def run(text, name="ci.sh", today=TODAY, disabled=(), only=()):
    kind = kind_of(name.rsplit("/", 1)[-1], name)
    if kind is None:
        return []
    found, _ = scan_text(textwrap.dedent(text), name, kind, today)
    return [f for f in found if f.rule not in disabled and (not only or f.rule in only)]


def ids(findings):
    return sorted(f.rule for f in findings)


# ---------------------------------------------------------------- removed flags
@pytest.mark.parametrize("line", [
    "helm list --all", "helm list -a -n prod", "helm repo add bitnami https://x.example --no-update",
    "helm repo update --fail-on-repo-update-fail", "helm rollback app 1 --recreate-pods",
    "helm status app --show-desc", "helm status app --show-resources", "helm test app --hide-notes",
])
def test_removed_flags(line):
    assert ids(run(line)) == ["flag-removed"]


def test_removed_flag_message_names_both_versions():
    (f,) = run("helm list -a")
    assert TESTED["4"] in f.message and TESTED["3"] in f.message and f.severity == "error"


@pytest.mark.parametrize("line", [
    "helm upgrade --install app ./c --atomic", "helm install app ./c --atomic=true", "helm rollback app 1 --force",
    "helm template app ./c --validate", "helm template app ./c --hide-notes", "helm template app ./c --render-subchart-notes",
    "helm install app ./c --dry-run", "helm template app ./c --dry-run=true", "helm upgrade app ./c --force",
])
def test_deprecated_flags(line):
    (f,) = run(line)
    assert f.rule == "flag-deprecated" and f.severity == "warning"


@pytest.mark.parametrize("line", [
    "helm install app ./c --dry-run=false", "helm install app ./c --dry-run=client", "helm install app ./c --dry-run=server",
    "helm install app ./c --rollback-on-failure", "helm install app ./c --force-replace", "helm list --deployed --failed",
    "helm list", "helm template app ./c", "helm upgrade --install app ./c --wait --timeout 5m",
])
def test_new_spellings_and_plain_commands_are_clean(line):
    assert run(line) == []


def test_atomic_false_still_warns_because_helm_warns_when_the_flag_is_set():
    # oracle: Helm 4.3.0 prints the deprecation notice for --atomic=false too
    assert ids(run("helm install app ./c --atomic=false")) == ["flag-deprecated"]


def test_flag_must_belong_to_that_subcommand():
    # `helm list --force` and `helm lint --all` are not rules; --all is only removed for `list`
    assert run("helm lint ./c --all") == []
    assert run("helm list --force") == []
    assert run("helm get values app --all") == []   # `helm get values --all` still exists
    assert run("helm history app --all") == []


def test_dry_run_message_mentions_replacement():
    (f,) = run("helm install app ./c --dry-run")
    assert "--dry-run=client" in f.message


# ---------------------------------------------------------------- shapes of commands
def test_workflow_run_block_with_continuations_and_position():
    src = """\
    jobs:
      d:
        steps:
          - run: |
              helm upgrade --install app ./chart \\
                --namespace prod --atomic --wait
    """
    (f,) = run(src, "deploy.yml")
    assert f.rule == "flag-deprecated" and f.line == 6 and f.file == "deploy.yml"


def test_makefile_variable_and_path_forms():
    src = "HELM ?= helm\ndeploy:\n\t$(HELM) list -a\n\t${HELM} status app --show-desc\n\t/usr/local/bin/helm rollback a 1 --recreate-pods\n\t$HELM test a --hide-notes\n"
    fs = run(src, "Makefile")
    assert ids(fs) == ["flag-removed"] * 4
    assert sorted(f.line for f in fs) == [3, 4, 5, 6]


def test_dockerfile_run():
    fs = run("FROM alpine\nRUN helm list -a && helm install a ./c --atomic\n", "Dockerfile")
    assert ids(fs) == ["flag-deprecated", "flag-removed"]


def test_chained_commands_and_pipes():
    fs = run("helm repo update --fail-on-repo-update-fail && helm list -a | grep deployed; helm install a ./c --atomic")
    assert ids(fs) == ["flag-deprecated", "flag-removed", "flag-removed"]


def test_flag_before_subcommand_and_global_flags():
    assert ids(run("helm --kube-context prod -n ns list -a")) == ["flag-removed"]
    assert ids(run("helm -n ns upgrade a ./c --atomic")) == ["flag-deprecated"]


def test_comments_prose_and_strings_are_not_commands():
    assert run("# helm list -a is removed in Helm 4\n") == []
    assert run("echo 'run helm list -a later'  # nothing to see\n") == []
    assert run("Use the helm chart for list --all\n", "notes.sh") == []
    assert run("helm_list -a\n") == []
    assert run("kubectl get pods -a\n") == []


@pytest.mark.parametrize("line", [
    'sh "helm rollback app 1 --recreate-pods"', "sh 'helm rollback app 1 --recreate-pods'", 'bash -c "helm rollback app 1 --recreate-pods"',
    'command: ["sh", "-c", "helm rollback app 1 --recreate-pods"]', 'sh(script: "helm rollback app 1 --recreate-pods")',
    'eval "$HELM rollback app 1 --recreate-pods"', 'command: ["helm", "rollback", "app", "1", "--recreate-pods"]',
])
def test_commands_inside_shell_strings_and_inline_lists(line):
    (f,) = run(line + "\n", "Jenkinsfile")
    assert f.rule == "flag-removed"


def test_quoted_prose_that_starts_with_helm_is_not_a_command():
    assert run('echo "helm list -a is removed in Helm 4"\n') == []
    assert run('log "helm rollback --recreate-pods"\n') == []


def test_trailing_comment_is_cut():
    assert run("helm list # -a is gone\n") == []


def test_quoted_arguments_keep_their_text_together():
    assert run('helm template a ./c --set "x=--atomic"\n') == []


def test_suppression_comment():
    assert run("helm list -a  # helm4-ready: ignore\n") == []
    assert run("helm list -a  # helm4-ready: ignore flag-removed\n") == []
    assert ids(run("helm list -a  # helm4-ready: ignore flag-deprecated\n")) == ["flag-removed"]
    assert run("# helm4-ready: ignore\nhelm list -a\n") == []


def test_scan_ignores_unrelated_file_kinds():
    assert run("helm list -a", "notes.txt") == []
    assert run("helm list -a", "README.md") == []


# ---------------------------------------------------------------- post-renderer
@pytest.mark.parametrize("v", ["./kustomize.sh", "/usr/bin/cat", "kustomize.sh", "bin/pr", "$PWD/pr"])
def test_post_renderer_executable_is_error(v):
    (f,) = run(f"helm template a ./c --post-renderer {v}\n")
    assert f.rule == "post-renderer-executable" and f.severity == "error"


def test_post_renderer_equals_form_and_bare_name():
    (a,) = run("helm install a ./c --post-renderer=./x.sh\n")
    assert a.severity == "error"
    (b,) = run("helm install a ./c --post-renderer kustomize\n")
    assert b.rule == "post-renderer-executable" and b.severity == "warning"


def test_post_renderer_args_alone_is_not_flagged():
    # Helm 4.3.0 still has the flag (oracle: accepted); it is the --post-renderer value that breaks
    assert run("helm template a ./c --post-renderer-args x\n") == []


# ---------------------------------------------------------------- registry login
@pytest.mark.parametrize("host", ["https://ghcr.io", "ghcr.io/acme", "oci://ghcr.io", "https://ghcr.io/"])
def test_registry_login_with_url_or_path(host):
    (f,) = run(f"echo $T | helm registry login {host} -u me --password-stdin\n")
    assert f.rule == "registry-login-url" and f.severity == "error"


@pytest.mark.parametrize("host", ["ghcr.io", "registry.example.com:5000", "$REGISTRY", '"$REGISTRY"', "localhost:5000"])
def test_registry_login_with_host_only(host):
    assert run(f"helm registry login {host} -u me -p x\n") == []


def test_registry_login_flags_before_host():
    (f,) = run("helm registry login -u me --password-stdin https://ghcr.io\n")
    assert f.rule == "registry-login-url"
    assert run("helm registry login -u me --password-stdin ghcr.io\n") == []


def test_registry_logout_untouched_and_variable_with_scheme():
    assert run("helm registry logout https://ghcr.io\n") == []
    assert ids(run("helm registry login https://$REG -u a -p b\n")) == ["registry-login-url"]


# ---------------------------------------------------------------- EOL
def test_eol_severity_ramp():
    sev = lambda d: eol_severity(d)[0]  # noqa: E731
    assert sev("2026-10-03") == "note"
    assert sev("2026-11-11") == "note"      # 91 days before 2027-02-10
    assert sev("2026-11-12") == "warning"   # 90 days
    assert sev("2027-02-10") == "warning"   # the last day of Helm 3 security fixes
    assert sev("2027-02-11") == "error"


@pytest.mark.parametrize("line", [
    "HELM_VERSION=v3.16.2", "HELM_VERSION: v3.19.0", 'export HELM_VERSION="3.14.4"',
    "curl -fsSL https://get.helm.sh/helm-v3.18.0-linux-amd64.tar.gz | tar xz",
    "curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash",
    "FROM alpine/helm:3.15.0", "image: dtzar/helm-kubectl:3.12",
])
def test_helm3_pins(line):
    fs = run(line + "\n", "ci.sh" if not line.startswith(("FROM", "image")) else ("Dockerfile" if line.startswith("FROM") else "k.yaml"))
    assert ids(fs) == ["helm3-eol"], line


def test_eol_severity_follows_today():
    assert run("HELM_VERSION=v3.19.0\n", today="2026-10-03")[0].severity == "note"
    assert run("HELM_VERSION=v3.19.0\n", today="2026-12-20")[0].severity == "warning"
    assert run("HELM_VERSION=v3.19.0\n", today="2027-03-01")[0].severity == "error"
    assert "2027-02-10" in run("HELM_VERSION=v3.19.0\n")[0].message


@pytest.mark.parametrize("line", ["HELM_VERSION=v4.3.0", "HELM_VERSION: v4.0.0", "FROM alpine/helm:4.1.0", "curl https://get.helm.sh/helm-v4.3.0-linux-amd64.tar.gz"])
def test_helm4_pins_are_clean(line):
    assert run(line + "\n", "Dockerfile") == []


def test_setup_helm_versions():
    wf = """\
    steps:
      - uses: azure/setup-helm@v5
        with:
          version: v3.16.0
      - uses: azure/setup-helm@v5
        with:
          version: v4.3.0
      - uses: azure/setup-helm@v5
      - uses: azure/setup-helm@v5
        with:
          version: latest
    """
    fs = run(wf, "ci.yml")
    assert [(f.rule, f.line) for f in fs] == [("helm3-eol", 4), ("helm-version-latest", 8), ("helm-version-latest", 9)]


def test_setup_helm_expression_is_not_flagged():
    wf = "steps:\n  - uses: azure/setup-helm@v5\n    with:\n      version: ${{ env.HELM_VERSION }}\n"
    assert run(wf, "ci.yml") == []


# ---------------------------------------------------------------- engine options
def test_disable_and_only():
    src = "helm list -a\nhelm install a ./c --atomic\n"
    assert ids(run(src, disabled=["flag-removed"])) == ["flag-deprecated"]
    assert ids(run(src, only=["flag-removed"])) == ["flag-removed"]


def test_rule_table_is_consistent():
    for fr in FLAG_RULES:
        assert fr.rule in RULES and fr.flags and fr.cmds
    for r in RULES.values():
        assert r.severity in ("error", "warning", "note") and r.summary and r.fix
    assert TESTED == {"3": "3.22.0", "4": "4.3.0"}


# ---------------------------------------------------------------- CLI and outputs
def make_repo(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "d.yml").write_text("jobs:\n  a:\n    steps:\n      - run: helm list -a\n")
    (tmp_path / "Makefile").write_text("deploy:\n\thelm upgrade --install a ./c --atomic\n")
    return tmp_path


def test_cli_exit_codes(tmp_path, capsys):
    make_repo(tmp_path)
    assert main([str(tmp_path), "--today", TODAY]) == 1
    assert main([str(tmp_path), "--today", TODAY, "--fail-on", "never"]) == 0
    assert main([str(tmp_path), "--today", TODAY, "--disable", "flag-removed"]) == 0
    assert main([str(tmp_path), "--today", TODAY, "--disable", "flag-removed", "--fail-on", "warning"]) == 1
    assert main([str(tmp_path), "--disable", "nope"]) == 2


def test_cli_json_and_sarif(tmp_path, capsys):
    make_repo(tmp_path)
    main([str(tmp_path), "--today", TODAY, "-f", "json"])
    d = json.loads(capsys.readouterr().out)
    assert d["summary"]["error"] == 1 and d["summary"]["warning"] == 1 and d["testedAgainst"] == TESTED
    out = tmp_path / "r.sarif"
    main([str(tmp_path), "--today", TODAY, "-f", "sarif", "-o", str(out)])
    s = json.loads(out.read_text())
    assert s["version"] == "2.1.0"
    run0 = s["runs"][0]
    assert run0["tool"]["driver"]["name"] == "helm4-ready" and len(run0["results"]) == 2
    rid = {r["id"] for r in run0["tool"]["driver"]["rules"]}
    assert {r["ruleId"] for r in run0["results"]} <= rid
    loc = run0["results"][0]["locations"][0]["physicalLocation"]
    assert loc["region"]["startLine"] >= 1 and "\\" not in loc["artifactLocation"]["uri"]


def test_cli_github_format_and_markdown(tmp_path, capsys):
    make_repo(tmp_path)
    main([str(tmp_path), "--today", TODAY, "-f", "github", "--fail-on", "never"])
    out = capsys.readouterr().out
    assert out.count("::error file=") == 1 and out.count("::warning file=") == 1
    main([str(tmp_path), "--today", TODAY, "-f", "markdown", "--fail-on", "never"])
    assert "| error | `flag-removed` |" in capsys.readouterr().out


def test_ignore_glob_and_single_file(tmp_path, capsys):
    make_repo(tmp_path)
    assert main([str(tmp_path), "--today", TODAY, "--ignore", ".github/**", "--ignore", "Makefile"]) == 0
    assert main([str(tmp_path / "Makefile"), "--today", TODAY, "--fail-on", "warning"]) == 1


def test_list_rules_and_version(capsys):
    assert main(["--list-rules"]) == 0
    out = capsys.readouterr().out
    assert "flag-removed" in out and "helm3-eol" in out
    with pytest.raises(SystemExit):
        main(["--version"])
    assert TESTED["4"] in capsys.readouterr().out


def test_skips_vendor_and_git_dirs(tmp_path):
    for d in (".git", "node_modules", "vendor"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "x.sh").write_text("helm list -a\n")
    assert main([str(tmp_path)]) == 0
