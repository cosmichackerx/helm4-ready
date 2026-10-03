# Changelog

## 0.1.0 - 2026-10-03

First release.

* Six rules, each tied to the Helm versions it was tested on (Helm 3.22.0 and 4.3.0, linux-amd64): `flag-removed`, `flag-deprecated`, `post-renderer-executable`, `registry-login-url`, `helm3-eol`, `helm-version-latest`.
* Finds `helm` commands in GitHub Actions workflows, shell scripts, Makefiles (`$(HELM)`), Dockerfiles, Jenkinsfiles and GitLab CI files; joins `\` continuations; ignores comments.
* Dated Helm 3 deadline (security fixes end 2027-02-10) as a severity ramp: note, then warning within 90 days, then error after the date.
* `tests/oracle/run_oracle.py` runs every claim against real Helm binaries (no cluster); CI runs it on Helm 3.22.0 and 4.3.0.
* Text, Markdown, JSON, GitHub annotation and SARIF 2.1.0 output; PR mode (`--base`); sticky pull request comment; composite GitHub Action; pre-commit hook; weekly watcher for new Helm releases and changed end-of-life dates.
