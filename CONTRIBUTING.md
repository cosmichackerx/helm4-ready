# Contributing

    python -m venv .venv && . .venv/bin/activate
    pip install -e . pytest
    pytest -q

* A new rule needs an entry in `src/helm4_ready/rules.py` that names the Helm version(s) it was tested on, a detector in `scan.py`, and unit tests with positive and negative cases.
* Every rule that claims "Helm 4 rejects X" must be a case in `tests/oracle/run_oracle.py`, run against real Helm binaries: `python tests/oracle/run_oracle.py --helm3 /path/to/helm3 --helm4 /path/to/helm4` (no cluster needed). If a behaviour cannot be checked that way, mark the rule `oracle=False` and say so in the README.
* When a new Helm release changes a behaviour, change `TESTED` in `rules.py`, re-run the oracle and update the validation table in the README. Do not widen a claim to versions that were not run.
* Keep the project dependency-free (standard library only) and compatible with Python 3.9.
* Releasing: bump the version and the README pins in a PR, merge when green, then run **Actions > Release gate** with the new tag (for example `v1.2.3`) *before* you create the tag. The same check runs again on the tag, and a weekly job (`claims-latest.yml`) fails when the README pins an older release than the newest tag.
