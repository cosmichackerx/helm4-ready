

from helm4_ready.cli import main
from helm4_ready.fix import apply, fix_path, plan
from helm4_ready.scan import scan_text

TODAY = "2026-10-03"


def fixed(text, name="ci.sh"):
    e, s = plan(text, name, TODAY)
    return apply(text, e), e, s


def test_renames_and_dry_run_values():
    out, e, s = fixed("helm upgrade --install r ./c --atomic --force --dry-run -n x\nhelm install r ./c --atomic=false --dry-run=true\n")
    assert out == "helm upgrade --install r ./c --rollback-on-failure --force-replace --dry-run=client -n x\nhelm install r ./c --rollback-on-failure=false --dry-run=client\n"
    assert not s and len(e) == 5


def test_template_validate_becomes_server_dry_run_unless_dry_run_present():
    assert fixed("helm template r ./c --validate\n")[0] == "helm template r ./c --dry-run=server\n"
    out, e, s = fixed("helm template r ./c --validate --dry-run=client\n")
    assert out == "helm template r ./c --validate --dry-run=client\n" and "already has --dry-run" in s[0].reason


def test_registry_login_keeps_only_the_host():
    out = fixed('helm registry login https://ghcr.io/owner -u u\nhelm registry login "oci://reg.example.com:5000/a/b/" -u u\nhelm registry login $REGISTRY/team -u u\n')[0]
    assert out == 'helm registry login ghcr.io -u u\nhelm registry login "reg.example.com:5000" -u u\nhelm registry login $REGISTRY -u u\n'


def test_repo_add_no_update_is_deleted_with_one_space():
    assert fixed("helm repo add a https://x --no-update --force-update\n")[0] == "helm repo add a https://x --force-update\n"
    out, e, s = fixed("helm repo add a https://x \\\n  --no-update\n")
    assert not e and "alone on its line" in s[0].reason


def test_not_fixable_flags_are_left_alone():
    t = "helm list --all\nhelm rollback r 1 --recreate-pods\nhelm template r c --hide-notes\nhelm upgrade r c --post-renderer ./x.sh\n"
    out, e, s = fixed(t)
    assert out == t and not e and not s


def test_helm3_in_the_same_file_refuses_the_helm3_breaking_edits_only():
    t = "- uses: azure/setup-helm@v4\n  with:\n    version: v3.14.0\n- run: helm upgrade r c --atomic --dry-run\n"
    out, e, s = fixed(t, "ci.yml")
    assert out.endswith("helm upgrade r c --atomic --dry-run=client\n")
    assert [x.text for x in s] == ["--atomic"] and "also runs Helm 3" in s[0].reason
    out, e, s = fixed("helm3 version\nhelm install r c --force\n")
    assert out == "helm3 version\nhelm install r c --force\n" and s


def test_idempotent_and_clears_the_findings():
    t = "helm upgrade r c --atomic --force --dry-run\nhelm template r c --validate\nhelm registry login https://r.io/x\nhelm repo add a u --no-update\n"
    once, e, s = fixed(t)
    assert not plan(once, "ci.sh", TODAY)[0]
    rules = {f.rule for f in scan_text(once, "ci.sh", "shell", TODAY, eol=False)[0]}
    assert not rules & {"flag-deprecated", "registry-login-url"} and "flag-removed" not in rules


def test_crlf_indentation_and_continuations_survive():
    t = "steps:\r\n  - run: |\r\n      helm upgrade --install r c \\\r\n        --atomic \\\r\n        --dry-run\r\n"
    out = fixed(t, "ci.yml")[0]
    assert out == t.replace("--atomic", "--rollback-on-failure").replace("--dry-run", "--dry-run=client")


def test_comments_and_ignore_markers():
    t = "# helm upgrade --atomic\nhelm upgrade r c --atomic  # helm4-ready: ignore flag-deprecated\n"
    assert fixed(t)[0] == t


def test_flags_inside_a_quoted_shell_string_are_fixed():
    assert fixed("sh -c 'helm upgrade r c --atomic'\n")[0] == "sh -c 'helm upgrade r c --rollback-on-failure'\n"


def test_cli_requires_target_and_diff_writes_nothing(tmp_path, capsys):
    f = tmp_path / "ci.sh"
    f.write_text("helm upgrade r c --atomic\n")
    assert main(["--fix", str(tmp_path)]) == 2
    assert main(["--diff", "--target", "4", str(tmp_path)]) == 1
    assert "+helm upgrade r c --rollback-on-failure" in capsys.readouterr().out
    assert f.read_text() == "helm upgrade r c --atomic\n"
    assert main(["--fix", "--target", "4", str(tmp_path)]) == 0
    assert f.read_text() == "helm upgrade r c --rollback-on-failure\n"
    assert main(["--diff", "--target", "4", str(tmp_path)]) == 0


def test_fix_path_respects_ignore_and_disable(tmp_path):
    (tmp_path / "a.sh").write_text("helm upgrade r c --atomic\n")
    (tmp_path / "b.sh").write_text("helm upgrade r c --atomic\n")
    e, s, d, n = fix_path(str(tmp_path), ignore=["b.sh"], write=False)
    assert n == 1 and e[0].file == "a.sh"
    assert fix_path(str(tmp_path), disable=["flag-deprecated"])[3] == 0


def test_registry_login_with_github_expression_in_the_path():
    t = ("- run: echo $T | helm registry login ghcr.io/${{ github.repository_owner }} -u ${{ github.actor }} --password-stdin\n"
         "- run: helm registry login \"ghcr.io/${{ github.repository_owner }}/charts\" -u u\n")
    out = fixed(t, "ci.yml")[0]
    assert out == ("- run: echo $T | helm registry login ghcr.io -u ${{ github.actor }} --password-stdin\n"
                   "- run: helm registry login \"ghcr.io\" -u u\n")
