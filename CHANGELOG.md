# Changelog

## 0.3.0 - 2026-10-03

* **`--fix --target 4`** (and `--diff`): rewrites `--atomic` to `--rollback-on-failure`, `--force` to `--force-replace`, bare `--dry-run` to `--dry-run=client`, `template --validate` to `--dry-run=server`, `registry login` URLs to the host, and deletes `repo add --no-update`. Refuses the rewrites Helm 3 would reject when the same file also runs Helm 3. Does not touch removed flags whose removal changes behaviour (`list --all` etc.). `tests/oracle/run_fix_oracle.py` runs 20 fixed commands on Helm 3.22.0 and all 15 Helm 4 releases in CI. Tests: 118 (was 106). Closes the `--fix` roadmap issue.

* CI: README numbers are checked by [claims-check](https://github.com/cosmichackerx/claims-check) (`.claims.json`: oracle case count, Helm 4 release count, unit-test count, version pins). `run_oracle.py --count` needs no binary.

## 0.2.0 - 2026-10-03

Precision study ([docs/precision-study.md](docs/precision-study.md)) and the oracle on every Helm 4 release.

* **Fixed** `azure/setup-helm` with a flow-map `with: { version: ... }` was reported as "without a version" (7 of 323 `helm-version-latest` findings in the study corpus; three were really Helm 3 pins and are now `helm3-eol`).
* **Fixed** Makefile variables `$(NAME)` ended the command at the parenthesis, so flags after it were lost.
* **Changed** the `helm-version-latest` message claims "already runs Helm 4" only for `azure/setup-helm` v3, v4 and v5 (read from the action's source, not run); other majors say the Helm major is unknown.
* **Changed** the `--atomic` message on `install` and `template` says Helm 4.0.0 to 4.1.1 reject the flag as unknown (helm/helm#31900) and 4.1.3 and later only warn. `upgrade --atomic` is deprecated on every Helm 4 release.
* **Added** the oracle runs on all 15 Helm 4 releases (4.0.0 to 4.3.0; `--extra-helm4`, `--matrix`, `--strict-extra`), downloads are SHA-256 checked (`tests/oracle/helm-sha256.txt`), and a difference between releases that `rules.py` does not document fails CI. Matrix: [docs/oracle-matrix.md](docs/oracle-matrix.md).
* **Added** `study/` scripts (collect, download, scan, sample, cross-check).
* Tests: 106 (was 103).

## 0.1.0 - 2026-10-03

First release.

* Six rules, each tied to the Helm versions it was tested on (Helm 3.22.0 and 4.3.0, linux-amd64): `flag-removed`, `flag-deprecated`, `post-renderer-executable`, `registry-login-url`, `helm3-eol`, `helm-version-latest`.
* Finds `helm` commands in GitHub Actions workflows, shell scripts, Makefiles (`$(HELM)`), Dockerfiles, Jenkinsfiles and GitLab CI files; joins `\` continuations; ignores comments.
* Dated Helm 3 deadline (security fixes end 2027-02-10) as a severity ramp: note, then warning within 90 days, then error after the date.
* `tests/oracle/run_oracle.py` runs every claim against real Helm binaries (no cluster); CI runs it on Helm 3.22.0 and 4.3.0.
* Text, Markdown, JSON, GitHub annotation and SARIF 2.1.0 output; PR mode (`--base`); sticky pull request comment; composite GitHub Action; pre-commit hook; weekly watcher for new Helm releases and changed end-of-life dates.
