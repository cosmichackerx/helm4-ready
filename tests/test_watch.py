import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location("watch_helm", os.path.join(os.path.dirname(__file__), "..", "scripts", "watch", "watch_helm.py"))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

PAGE = "<p>September 9th, 2026 ... Security fixes end <b>February 10th, 2027</b></p>"


def rel(*tags, pre=()):
    return json.dumps([{"tag_name": t} for t in tags] + [{"tag_name": t, "prerelease": True} for t in pre])


def test_no_drift():
    assert w.compare(rel("v4.3.0", "v3.22.0", "v4.2.9", "v3.21.1"), PAGE) == []


def test_newer_release_is_drift_but_prereleases_are_not():
    p = w.compare(rel("v4.4.0", "v3.22.0"), PAGE)
    assert len(p) == 1 and "Helm 4.4.0 is out" in p[0]
    assert w.compare(rel("v4.3.0", "v3.22.0", pre=("v4.4.0-rc.1",)), PAGE) == []


def test_changed_dates_are_drift():
    p = w.compare(rel("v4.3.0", "v3.22.0"), "<p>September 9th, 2026, security fixes end March 3rd, 2027</p>")
    assert len(p) == 1 and "2027-02-10" in p[0]


def test_ordinals():
    assert w.ordinal_date("2027-02-10") == "February 10th, 2027"
    assert w.ordinal_date("2026-09-09") == "September 9th, 2026"
    assert w.ordinal_date("2026-09-01") == "September 1st, 2026"
    assert w.ordinal_date("2026-09-22") == "September 22nd, 2026"
    assert w.ordinal_date("2026-09-23") == "September 23rd, 2026"
