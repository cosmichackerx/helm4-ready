# Precision study of helm4-ready on public repositories

Run on 2026-10-03 against helm4-ready v0.1.0, then the three bugs it found were fixed in v0.2.0. Read-only: the study downloaded files and opened **no** issue, pull request or comment on any of those repositories, and this document names no repository whose owner did not already publish the file.

## What was done

1. **Collect** (`study/collect.py`): GitHub code search, 10 queries that returned results (for example `helm upgrade --install path:.github/workflows`, `helm registry login`, `helm list --all`, `azure/setup-helm`, `HELM_VERSION path:.github/workflows`). Another 8 queries returned nothing and were dropped (`--atomic`, `--post-renderer` and several GitLab/Jenkins/Dockerfile forms). Result: 3,627 file hits in 3,288 repositories.
2. **Download** (`study/download.py`): up to 6 hit files per repository, pinned to the commit SHA that code search reported, from raw.githubusercontent.com. 3,593 files in 3,287 repositories (28 downloads failed).
3. **Scan** (`study/run_scan.py`): helm4-ready with `--today 2026-10-03`. 2,304 repositories contained a file type the scanner reads; **1,576 contained a helm command** (6,999 commands).
4. **Sample and label** (`study/sample.py`, seed 20261003): every finding of the rare rules, a random sample of the common ones. One labeller (the author). Labels: **true positive** = the line really is what the rule says (a real `helm` command with that flag, a real pin); **false positive** = the rule's claim is wrong for that line; **context** = correct as text, but something the scanner cannot see changes the consequence.
5. **Cross-check for misses** (`study/loose.py`): a deliberately loose regex (a line mentions `helm`, a sub-command and a flag a rule knows) lists lines helm4-ready did not flag; those were read by hand.

## Findings per rule (v0.1.0 scan, before the fixes)

| Rule | Findings | Repos | Hand-checked | True positive | False positive | 95% lower bound (Wilson) |
|---|---|---|---|---|---|---|
| `flag-removed` | 13 | 10 | 13 (all) | 13 | 0 | 77% |
| `flag-deprecated` | 155 | - | 40 (random) | 40 | 0 | 91% |
| `post-renderer-executable` | 3 | 3 | 3 (all) | 3 | 0 | 44% |
| `registry-login-url` | 10 | 7 | 10 (all) | 10 | 0 | 72% |
| `helm3-eol` | 777 | - | 30 (random) | 30 | 0 | 89% |
| `helm-version-latest` | 323 | - | 20 (random) | 19 | **1** | 76% |

Rules whose sample is all of the findings have no sampling error but a small `n`, so the lower bound is low; do not read "13/13" as "always right".

What the labels mean in practice:

* **`flag-removed`**: all 13 are real `helm list --all/-a` commands (one `status --show-resources`). Helm 4.3.0 rejects them, the oracle shows it.
* **`flag-deprecated`**: mostly `upgrade --atomic`, `template --dry-run`, `install --dry-run`, `template --validate`. One of the 40 is **context**: a `helm` command run through an action that bundles Helm 3 (`WyriHaximus/github-action-helm3`), where the Helm 4 notice does not apply today. The scanner cannot see this.
* **`registry-login-url`**: 8 of 10 are `helm registry login ghcr.io/<owner>`, the most common real break.
* **`post-renderer-executable`**: one of the 3 was a variable (`"${HASH_GATE}"`, a generated script); it is reported as a warning, not an error.
* **`helm3-eol`**: all 30 are real Helm 3 pins. This is "a pin is present" precision. One repository pins 3.21.3 on purpose with the comment that Helm 4 breaks helmfile and the helm-diff plugin, so a note is right but the pin is a decision, not a mistake.
* **`helm-version-latest`**: **one false positive**, `uses: azure/setup-helm@v4` followed by `with: { version: v4.1.1 }` on one line (a YAML flow map). The parser only read block-style `version:`.

## What the study found, and what changed in v0.2.0

| Found | How | Fix |
|---|---|---|
| Flow-map `with: { version: ... }` was not read, so a pinned version was reported as "without a version" | hand-check of the `helm-version-latest` sample | Parser reads the flow map. **7 of the 323 `helm-version-latest` findings** in the corpus were this bug (three of the seven were really Helm 3 pins, now reported as `helm3-eol`) |
| Makefile variables `$(NAME)` ended the command at the parenthesis, so flags after it were lost (9 `template --dry-run` lines in one Makefile) | loose cross-check | Make variables are read as words |
| The `helm-version-latest` message claimed the job "already runs Helm 4" for every `azure/setup-helm` major | reading the action's source for v1 to v5 | Claim kept only for v3, v4, v5 (v3 asks GitHub for the repository's "latest" release, v4 and v5 read `get.helm.sh/helm-latest-version`; both gave v4.3.0 on 2026-10-03; **read from source, the action was not run**). For other majors the message says the Helm major is unknown. v2 takes the first non-rc release in the GitHub releases list, v1 a semver maximum; neither was run |

After the fixes the corpus gives 1,286 findings (v0.1.0: 1,281): `helm3-eol` 779, `helm-version-latest` 316, `flag-deprecated` 165, `flag-removed` 13, `registry-login-url` 10, `post-renderer-executable` 3.

## Cross-check for misses (a weak recall estimate)

The loose regex found **67** single-line commands with a known flag. v0.1.0 flagged **55** (82%). Of the 12 it did not flag, **9 were real misses** (all in one Makefile, the `$(NAME)` bug) and **3 were `echo "helm upgrade ..."` strings**, which are text, not commands, so not flagging them is right. v0.2.0 flags 64 of 67, and the other 3 are those echo strings.

This is **not** a recall measurement. It only covers lines where the flag sits on the same line as `helm` and the sub-command, and it was written by the same person who wrote the scanner. Commands split across lines, built from variables, run through `eval`/`xargs`/Helmfile, or kept in files that code search did not return are not covered.

## Limits

* **Not a random sample of GitHub.** Code search returns at most 1,000 hits per query in relevance order; hits are biased towards files that talk about Helm a lot, and towards repositories that GitHub ranks high. The numbers describe this convenience sample.
* One labeller, no second opinion, labels were made after seeing the rule's message.
* The rare rules were checked in full but are tiny (3 to 13 findings).
* `helm3-eol` and `helm-version-latest` are precision of "a pin / no pin is present", not a claim about which Helm actually runs.
* Files were read as text at one commit; reusable workflows, `include:` files and templates are not followed.
* Study data (the downloaded files, 142 MB) is not committed. `study/*.py` reproduce it; the search results change over time.

## Oracle across Helm 4 releases

The same release also ran the oracle on all 15 Helm 4 releases that exist on 2026-10-03; see [oracle-matrix.md](oracle-matrix.md). Only 5 of 49 cases differ between releases. Helm 4.0.0 to 4.1.1 **reject** `--atomic` on `install` and `template` as an unknown flag (helm/helm#31900), 4.1.3 and later accept it with a deprecation notice. `upgrade --atomic` is deprecated on every release. `template --hide-notes` and `--render-subchart-notes` are accepted silently before 4.2.0.
