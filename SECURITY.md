# Security

helm4-ready only reads files under the directory you give it and writes a report to stdout or the file you name. It has no runtime dependencies, never runs `helm`, a shell or any project code, and makes no network request, except the optional sticky pull request comment of the GitHub Action (GitHub API, only when you turn `comment` on).

The oracle in `tests/oracle/` and the weekly watcher download Helm binaries and web pages in CI; the binaries are checked against a pinned SHA-256.

Found a vulnerability (for example a path traversal through a crafted file name)? Please use GitHub's private vulnerability reporting for this repository ("Security" tab, "Report a vulnerability") instead of a public issue.
