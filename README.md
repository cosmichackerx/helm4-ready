# helm4-ready

**Find the Helm 3 CLI usage that Helm 4 rejects or deprecates in your CI, scripts and Makefiles, before the Helm 3 end of life.** A zero-dependency static
scanner (Python 3.9+) for GitHub Actions workflows, shell scripts, Makefiles (`$(HELM)`), Dockerfiles, Jenkinsfiles and GitLab CI files. It reads the `helm`
commands in them and reports removed flags (`helm list --all`, `helm repo update --fail-on-repo-update-fail`, `helm rollback --recreate-pods` ...),
deprecated flags (`--atomic`, `--force`, bare `--dry-run`, `template --validate`), a **`--post-renderer` that is an executable** instead of a plugin name,
**`helm registry login` with a URL or path**, and **Helm 3 version pins** against the dated Helm 3 end of life (**security fixes end 2027-02-10**).
Every rule was run against **real Helm 3.22.0 and Helm 4.3.0 binaries** (the [oracle](#validation--results)); no cluster is needed. It emits **SARIF** and
GitHub annotations and ships as a **GitHub Action** and a **pre-commit** hook.

[![CI](https://github.com/cosmichackerx/helm4-ready/actions/workflows/ci.yml/badge.svg)](https://github.com/cosmichackerx/helm4-ready/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cosmichackerx/helm4-ready?sort=semver)](https://github.com/cosmichackerx/helm4-ready/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Why a static scanner? A pipeline that runs `helm` only fails when it reaches the broken line, and many pipelines (release, rollback, repo update) run rarely.
An unpinned [`azure/setup-helm`](https://github.com/Azure/setup-helm) already installs Helm 4 (its `latest` resolves through `get.helm.sh/helm-latest-version`,
which returned `v4.3.0` on 2026-10-03), so a workflow can break without anyone touching it. This lists every affected line at once. It does **not** look at
charts (templates, `Chart.yaml`) and it does **not** replace [`helm template`](https://helm.sh/docs/helm/helm_template/) or [`helm lint`](https://helm.sh/docs/helm/helm_lint/);
for Kubernetes API deprecations inside rendered manifests use [pluto](https://github.com/FairwindsOps/pluto) or [kubeconform](https://github.com/yannh/kubeconform).

## At a glance

|  | Lite (try it in a minute) | Full (keep it in CI) |
|---|---|---|
| How | `pipx install git+https://github.com/cosmichackerx/helm4-ready` then `helm4-ready .` (read-only, no network) | the [GitHub Action](#github-action) (SARIF, job summary, PR comment), the [pre-commit](#pre-commit) hook, `--base origin/main` [PR mode](#pr-mode), and the weekly [Helm watch](#helm-watch-keeps-the-tested-versions-and-dates-honest) |

## Validation / results

Every number below is from this repository's own tests or scripts. "Not proven" is as important as "Result".

| What is claimed | Checked against | Size | Result | Not proven |
|---|---|---|---|---|
| Each flag, post-renderer and registry-login rule is true on the real binaries | Real **Helm 3.22.0** (2026-09-10) and **Helm 4.3.0** (2026-09-09), linux-amd64, SHA-256 checked, run by [`tests/oracle/run_oracle.py`](tests/oracle/run_oracle.py) on every push | 49 cases (flags x commands, replacements, controls, 5 post-renderer, 5 registry-login, 1 exit-code) | 0 disagreements required for CI to pass; main is green. The scanner's claims and the binaries agree | One OS (linux-amd64). The two main binaries are 3.22.0 and 4.3.0, and all 15 Helm 4 releases (4.0.0 to 4.3.0) also ran: only 5 of 49 cases differ, see [oracle-matrix.md](docs/oracle-matrix.md). Behaviour changed between Helm 4 releases before ([helm/helm#31900](https://github.com/helm/helm/issues/31900) reported `install --atomic` as broken; on 4.3.0 it only warns), so a rule is true **for the tested versions**, nothing else. `install`/`template --atomic` is **rejected** by Helm 4.0.0 to 4.1.1 and only warns from 4.1.3, which the `--atomic` message now says |
| The Helm 3 end of life dates | The [Helm 3 end-of-life post](https://helm.sh/blog/helm-v3-end-of-life) fetched on 2026-10-03; re-checked weekly by the [watcher](#helm-watch-keeps-the-tested-versions-and-dates-honest) | 2 dates | Last feature release 2026-09-09, security fixes end 2027-02-10 (extended from 2026-11-11) | Documentation only; there is no oracle for a date. The post could change again, the watcher then opens an issue |
| An unpinned `azure/setup-helm` installs Helm 4 | `src/run.ts` of azure/setup-helm v5.0.1 and `https://get.helm.sh/helm-latest-version` (returned `v4.3.0`) | 1 | Read from source and from the live file | The action itself was **not** run |
| Detection accuracy on real repositories | [Precision study](docs/precision-study.md): 3,287 public repositories found by code search (1,576 with helm commands, 6,999 commands), findings hand-labelled by one person | 116 findings checked: `flag-removed` 13/13, `flag-deprecated` 40/40 (1 context caveat), `post-renderer-executable` 3/3, `registry-login-url` 10/10, `helm3-eol` 30/30, `helm-version-latest` 19/20 | 1 false positive (fixed in 0.2.0) and 9 missed lines in one Makefile (fixed). A loose-regex cross-check flagged 55 of 67 single-line commands before the fixes, 64 of 67 after (the other 3 are `echo` text) | **Not a random sample** (GitHub relevance order), one labeller, small `n` for the rare rules (95% lower bounds 44% to 91%), and the cross-check is **not a recall measurement**. Detection is text matching (100+ unit tests), not a shell parser: expect misses on variables, `eval`, Helmfile, `xargs` and wrappers |

Oracle cases (condensed; the full 49-row table is printed in the CI job summary):

| Case | Helm 3.22.0 | Helm 4.3.0 |
|---|---|---|
| `list --all` / `-a`, `repo add --no-update`, `repo update --fail-on-repo-update-fail`, `rollback --recreate-pods`, `status --show-desc` / `--show-resources`, `test --hide-notes` | accepted | **rejected** (`unknown flag`) |
| `install`/`upgrade`/`template --atomic`, `--force` (also `rollback --force`), `template --validate`, `template --hide-notes`, `--render-subchart-notes`, bare `--dry-run` or `--dry-run=true`, `--atomic=false` | accepted | accepted with a **deprecation warning** |
| `--rollback-on-failure`, `--force-replace` | rejected | accepted |
| `--dry-run=client`, `--dry-run=server`, `--dry-run=false` | accepted | accepted |
| `--post-renderer /bin/cat`, `./x.sh` (an existing executable), `cat` | accepted | **rejected** (`plugin ... not found`) |
| `--post-renderer-args x` alone | accepted | accepted (the flag still exists) |
| `registry login` with `https://host`, `host/path`, `oci://host`, `https://host/` | accepted | **rejected** (`invalid reference`; a warning says only a hostname is supported) |
| `registry login host:5000` | accepted | accepted |
| `repo update` with an unreachable repository | exit 0, exit 1 with `--fail-on-repo-update-fail` | exit 1 |

**Releases:** v0.1.0 was the first release and v0.2.0 the precision-study release (both 2026-10-03). Every release is in [CHANGELOG.md](CHANGELOG.md) and on the [Releases page](https://github.com/cosmichackerx/helm4-ready/releases); the weekly watcher opens an issue when something drifts, it does not release anything.

## Install and run

```
pipx install git+https://github.com/cosmichackerx/helm4-ready      # or: pip install git+https://github.com/cosmichackerx/helm4-ready
helm4-ready .                          # scan the current repository
helm4-ready . --base origin/main       # PR mode: only what this branch introduces
helm4-ready . -f sarif -o helm4.sarif --fail-on never
helm4-ready --list-rules
```

From a checkout without installing: `PYTHONPATH=src python -m helm4_ready .`

Exit code: 0 clean, 1 findings at or above `--fail-on` (default `error`), 2 usage error. Output formats: `text`, `markdown`, `json`, `github` (annotations), `sarif`.
Options: `--ignore GLOB`, `--disable RULE`, `--only RULE`, `--today YYYY-MM-DD` (date for the end-of-life ramp). Suppress one finding with a comment on the same or the previous line:
`# helm4-ready: ignore flag-removed` (any comment syntax; no rule id means all rules).

## Example output

```
.github/workflows/deploy.yml
      4:3    note    helm3-eol                  `HELM_VERSION: v3.19` pins Helm 3: Helm 3 security fixes end on 2027-02-10 (130 days); the last Helm 3 feature release was 2026-09-09. See https://helm.sh/blog/helm-v3-end-of-life
     10:7    note    helm-version-latest        azure/setup-helm without a version installs the latest Helm; get.helm.sh/helm-latest-version said v4.3.0 on 2026-10-03, so this job already runs Helm 4. The CLI rules of helm4-ready apply to it
     12:50   error   registry-login-url         helm registry login https://ghcr.io/acme: Helm 4.3.0 fails with "invalid reference" for anything but host[:port]; Helm 3.22.0 accepts it. Use only the host
     16:30   warning flag-deprecated            helm upgrade --atomic: deprecated in Helm 4.3.0, which still accepts it; use --rollback-on-failure (Helm 3.22.0 does not know the new spelling)
     17:13   error   post-renderer-executable   helm upgrade --post-renderer ./kustomize.sh: Helm 4.3.0 rejects an executable path ("plugin ... not found"); Helm 4 takes the name of an installed post-renderer plugin
     18:21   error   flag-removed               helm list -a: Helm 4.3.0 rejects it (unknown flag; Helm 3.22.0 accepts it) - removed in Helm 4; select statuses explicitly with --deployed, --failed, --pending, --superseded, --uninstalled, --uninstalling
     19:40   warning flag-deprecated            helm template --dry-run: deprecated in Helm 4.3.0, which still accepts it; use --dry-run=client (or =server) (Helm 3.22.0 also accepts the new spelling)
     19:50   warning flag-deprecated            helm template --validate: deprecated in Helm 4.3.0, which still accepts it; use --dry-run=server (Helm 3.22.0 also accepts the new spelling)

Makefile
      4:40   warning flag-deprecated            helm upgrade --atomic: deprecated in Helm 4.3.0, which still accepts it; use --rollback-on-failure (Helm 3.22.0 does not know the new spelling)
      4:49   warning flag-deprecated            helm upgrade --force: deprecated in Helm 4.3.0, which still accepts it; use --force-replace (Helm 3.22.0 does not know the new spelling)
      5:21   error   flag-removed               helm status --show-resources: Helm 4.3.0 rejects it (unknown flag; Helm 3.22.0 accepts it) - removed in Helm 4 with no replacement flag; helm get manifest and kubectl show the resources
      6:22   error   flag-removed               helm repo update --fail-on-repo-update-fail: Helm 4.3.0 rejects it (unknown flag; Helm 3.22.0 accepts it) - removed in Helm 4, where helm repo update always exits non-zero when a repository cannot be updated (Helm 3 only did with this flag)

release.sh
      3:20   note    helm3-eol                  `get.helm.sh/helm-v3.16.2` pins Helm 3: Helm 3 security fixes end on 2027-02-10 (130 days); the last Helm 3 feature release was 2026-09-09. See https://helm.sh/blog/helm-v3-end-of-life
      4:21   error   registry-login-url         helm registry login oci://ghcr.io/acme: Helm 4.3.0 fails with "invalid reference" for anything but host[:port]; Helm 3.22.0 accepts it. Use only the host
      5:21   error   flag-removed               helm rollback --recreate-pods: Helm 4.3.0 rejects it (unknown flag; Helm 3.22.0 accepts it) - removed in Helm 4; restart the pods yourself (kubectl rollout restart)

3 file(s) scanned, 9 helm command(s) read, checked against Helm 3.22.0 and 4.3.0. 7 error, 5 warning, 3 note.
```

(That is `tests/fixtures/legacy-ci`, run with `--today 2026-10-03`.)

## Rules (6)

| Rule | Default severity | What it finds | Tested on |
|---|---|---|---|
| `flag-removed` | error | `list --all/-a`, `repo add --no-update`, `repo update --fail-on-repo-update-fail`, `rollback --recreate-pods`, `status --show-desc/--show-resources`, `test --hide-notes` | oracle: Helm 3.22.0 accepts, 4.3.0 rejects |
| `flag-deprecated` | warning | `--atomic` (use `--rollback-on-failure`), `--force` (use `--force-replace`), `template --validate` (use `--dry-run=server`), bare `--dry-run` (use `--dry-run=client`), `template --hide-notes/--render-subchart-notes` | oracle: 4.3.0 prints a deprecation notice. The new spellings of the first two are **unknown to Helm 3.22.0**, so a repo that must still run on Helm 3 cannot switch yet; the message says so |
| `post-renderer-executable` | error (warning for a bare name) | `install`/`upgrade`/`template --post-renderer ./script.sh` or a path; Helm 4 takes the name of an installed post-renderer plugin | oracle: 4.3.0 rejects a path and a bare name that is not an installed plugin. A bare name can be valid when the plugin is installed, which is why it is only a warning; the installed-plugin case was **not** run |
| `registry-login-url` | error | `helm registry login https://host`, `host/path`, `oci://host` | oracle: 4.3.0 rejects, 3.22.0 accepts. `registry logout` is unchanged |
| `helm3-eol` | note, then warning, then error | a Helm 3 pin: `HELM_VERSION=v3.x`, a `get.helm.sh/helm-v3...` download, `get-helm-3`, `alpine/helm:3...`, `dtzar/helm-kubectl:3...`, `azure/setup-helm` with a `version: v3...` | docs only (see below) |
| `helm-version-latest` | note | `azure/setup-helm` without a version or with `latest` | source and live file, not run |

## Dated deadline

Source: [Helm 3 End of Life](https://helm.sh/blog/helm-v3-end-of-life) (fetched 2026-10-03).

* **2026-09-09**: the last, limited Helm 3 feature release; bug fixes end with it. (Helm 3.22.0 was published 2026-09-10.)
* **2027-02-10**: Helm 3 security fixes end (extended from November 2026). After that, no Helm 3 release of any kind.
* Helm 4.0.0 was released 2025-11-12.

The `helm3-eol` severity follows the calendar so a green build today does not hide a red one later: a **note** while more than 90 days remain, a **warning** from 90 days before
2027-02-10 until that day, an **error** after it. Use `--today` to see the future (`--today 2027-02-11`). The dates are constants in `src/helm4_ready/rules.py` and checked by the weekly watcher.

## GitHub Action

```yaml
- uses: actions/checkout@v7
  with:
    fetch-depth: 0          # only needed for pr-mode
- uses: cosmichackerx/helm4-ready@v0.2.0
  with:
    path: .
    fail-on: error          # error | warning | never
    pr-mode: true           # on pull requests report only what the PR introduces
    comment: true           # one sticky comment, updated in place (needs pull-requests: write; skipped for forks)
    sarif-file: helm4.sarif
```

Inputs: `path`, `fail-on`, `disable`, `ignore`, `summary` (job summary), `pr-mode`, `base`, `comment`, `github-token`, `sarif-file`. Upload the SARIF with
`github/codeql-action/upload-sarif`. The action runs the scanner from its own checkout with the runner's Python; it does not install anything and makes no network calls except the sticky comment.

## pre-commit

```yaml
repos:
  - repo: https://github.com/cosmichackerx/helm4-ready
    rev: v0.2.0
    hooks:
      - id: helm4-ready        # report; fails the commit on errors
```

The hook scans the whole repository (`pass_filenames: false`) and runs when a YAML file, shell script, Makefile, Dockerfile or Jenkinsfile changed. CI checks it with `pre-commit try-repo`.

## PR mode

`helm4-ready . --base origin/main` scans the merge base and the working tree and reports only findings that are new (matched by rule, file and the text of the line, so moving a line does not make it new).
In the Action, `pr-mode: true` does this on pull requests. Needs git history (`fetch-depth: 0`).

## How it is verified

* **Unit tests** (`pytest`, 100+ cases): positives and negatives per rule, `\` continuations, `$(HELM)`, comments and prose, suppression, the end-of-life ramp, setup-helm, outputs, PR mode.
  CI runs them on Ubuntu, Windows and macOS with Python 3.9, 3.11 and 3.13.
* **Oracle** (`tests/oracle/run_oracle.py`): runs each claim on a real Helm 3 and Helm 4 binary and fails on any disagreement. While building this, it caught two wrong claims of mine
  (that `--post-renderer ./x.sh` is a Helm 4-only failure, it also fails on Helm 3 when the file does not exist; and that `--post-renderer-args` alone is rejected, it is still accepted), which were fixed before release.
  Run it yourself: `python tests/oracle/run_oracle.py --helm3 /path/to/helm3 --helm4 /path/to/helm4`.
* **Action, packaging, pre-commit** self-tests in CI, plus a check of the Marketplace limits for `action.yml` (name, description of at most 125 characters, branding).
* CI also runs [dependabot-gaps](https://github.com/cosmichackerx/dependabot-gaps) and [node24-ready](https://github.com/cosmichackerx/node24-ready) on this repository.

## Helm watch (keeps the tested versions and dates honest)

A weekly workflow ([`helm-watch.yml`](.github/workflows/helm-watch.yml), [`scripts/watch/watch_helm.py`](scripts/watch/watch_helm.py)) compares the newest stable Helm 3.x and 4.x releases with the versions the oracle ran on
and checks that the two end-of-life dates are still on the Helm blog post. It opens at most one issue per distinct finding.

## Limitations (read these)

* Text matching on logical lines, not a shell parser: `helm` inside `eval`, a variable-built command line, `xargs`, a wrapper script or Helmfile is not seen. Commands in a quoted string given to `sh`/`bash -c`/`eval`/Jenkins `sh` are read, and so is an inline list that contains `helm` (`command: ["helm", "list", "-a"]`); an `args:` list for an image whose entrypoint is already `helm` (such as `alpine/helm`), and YAML block lists, are not.
* Rules hold for Helm 3.22.0 and 4.3.0 only. Other versions may differ. Flag lists are not exhaustive: only the changes that were reproduced on the binaries are rules.
* It does not read charts, `Chart.yaml`, values or plugin metadata, and does not check what a Helm 4 plugin does.
* No precision/recall study on real repositories has been run.

## Related tools

**Helm 4 migration**

* [kentomk/helm4-plugin-preflight](https://github.com/kentomk/helm4-plugin-preflight): a Go tool (JSON and SARIF output) for the **plugin slice** of the Helm 4 migration, as described in its README: plugin installation and signature-verification behaviour, legacy plugin metadata, and post-renderer hazards.
  **This tool covers the other slice:** the CLI flags in your CI, scripts and Makefiles, `registry login` paths, and the dated Helm 3 end-of-life pins. The post-renderer is the one overlap: helm4-ready looks at the `--post-renderer` value on the command line, helm4-ready does not inspect plugins.
  Run both. (I read their README to write this paragraph; I have not run their tool or compared results.)
* [pluto](https://github.com/FairwindsOps/pluto) and [kubeconform](https://github.com/yannh/kubeconform): Kubernetes API deprecations and schema checks of rendered manifests; a different job from this one.

**Gradle and Android migrations**

* [gradle-version-catalog-lint](https://github.com/cosmichackerx/gradle-version-catalog-lint): Lints `libs.versions.toml`: unused libraries, plugins and versions, dynamic or SNAPSHOT versions, hard-coded dependencies.
* [gradle10-ready](https://github.com/cosmichackerx/gradle10-ready): Static scan of Gradle build scripts for what Gradle 10 removes (space assignment, multi-string dependencies, Kotlin DSL delegates). `--fix`, PR mode.
* [agp9-ready](https://github.com/cosmichackerx/agp9-ready): Static scan of Gradle files for what Android Gradle Plugin 9 and 10 break (built-in Kotlin, legacy variant API, opt-outs), including `buildSrc`. `--fix`, PR mode.
* [kotlin24-ready](https://github.com/cosmichackerx/kotlin24-ready): Finds what Kotlin 2.4 removes in the Kotlin Gradle plugin from Gradle build files, without running Gradle.
* [android-target-ready](https://github.com/cosmichackerx/android-target-ready): Static scanner for the targetSdk 36 / 37 migration in app code and manifests (edge-to-edge, predictive back, large screens).
* [android-target-lint](https://github.com/cosmichackerx/android-target-lint): The same targetSdk migration checks as real Android Lint rules (a lint jar with type resolution).

**CI and repository hygiene**

* [node24-ready](https://github.com/cosmichackerx/node24-ready): Finds GitHub Actions still on the removed Node 20 runtime, also inside composite actions and reusable workflows, and the smallest node24 upgrade.
* [dependabot-gaps](https://github.com/cosmichackerx/dependabot-gaps): Finds manifests your `dependabot.yml` does not cover, and dead or overlapping entries.
* [sha256-ready](https://github.com/cosmichackerx/sha256-ready): Finds code that assumes 40-character Git hashes before Git 3.0 makes SHA-256 repositories the default.
* [agent-context-diff](https://github.com/cosmichackerx/agent-context-diff): Diffs `AGENTS.md`, `CLAUDE.md`, Cursor rules and MCP configs between git refs (new servers, widened permissions, hidden Unicode).

## Roadmap

See the [open issues](https://github.com/cosmichackerx/helm4-ready/issues).

## License

MIT, see [LICENSE](LICENSE).
