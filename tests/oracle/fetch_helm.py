"""Download the Helm releases listed in helm-sha256.txt (linux-amd64), check each tarball against the pinned SHA-256 and unpack to DEST/v<version>/helm.

    python tests/oracle/fetch_helm.py DEST
"""
import hashlib
import os
import sys
import tarfile
import urllib.request

here = os.path.dirname(os.path.abspath(__file__))
dest = sys.argv[1]
for line in open(os.path.join(here, "helm-sha256.txt"), encoding="utf-8"):
    if not line.strip():
        continue
    version, want = line.split()
    out = os.path.join(dest, "v" + version)
    if os.path.exists(os.path.join(out, "helm")):
        continue
    data = urllib.request.urlopen(f"https://get.helm.sh/helm-v{version}-linux-amd64.tar.gz", timeout=120).read()
    got = hashlib.sha256(data).hexdigest()
    if got != want:
        sys.exit(f"helm {version}: sha256 {got} != pinned {want}")
    os.makedirs(out, exist_ok=True)
    tgz = os.path.join(dest, f"h{version}.tgz")
    with open(tgz, "wb") as fh:
        fh.write(data)
    with tarfile.open(tgz) as tf:
        member = tf.getmember("linux-amd64/helm")
        member.name = "helm"
        tf.extract(member, out)
    os.chmod(os.path.join(out, "helm"), 0o755)
    print("ok", version)
