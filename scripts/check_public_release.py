"""Check the tracked release tree and optionally reachable Git blobs.

This is a narrow publishing check, not a security certification. Findings never
print matched credential values. Review all intended files before publishing.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "github_token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b",
    "api_secret": rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b",
    "aws_access_key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "private_key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
}
PATTERNS = {name: re.compile(pattern) for name, pattern in SECRET_PATTERNS.items()}
GENERATED_DIRS = {".venv", "node_modules", "__pycache__", ".pytest_cache", "dist",
                  "uploads", "backups", ".playwright-cli", "playwright-report", "test-results"}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def forbidden(path: str) -> bool:
    p = PurePosixPath(path)
    return (any(part in GENERATED_DIRS for part in p.parts)
            or path.startswith(("data/", "backend/data/", "logs/", "output/playwright/"))
            or (p.name.startswith(".env") and p.name != ".env.example")
            or ".timestamp-" in p.name
            or p.suffix in {".db", ".sqlite", ".sqlite3", ".pyc", ".log", ".tsbuildinfo",
                            ".docx", ".zip", ".pem", ".key", ".pfx", ".p12"}
            or (p.suffix == ".pdf" and not path.startswith("frontend/e2e/fixtures/")))


def secret_findings(content: bytes, path: str) -> list[dict]:
    return [{"path": path, "kind": name} for name, regex in PATTERNS.items() if regex.search(content)]


def check(history: bool = False) -> dict:
    paths = [p.decode("utf-8") for p in git("ls-files", "-z").split(b"\0") if p]
    findings = []
    for path in paths:
        if forbidden(path):
            findings.append({"path": path, "kind": "excluded_release_file"})
        content = (ROOT / path).read_bytes()
        if len(content) > 10 * 1024 * 1024:
            findings.append({"path": path, "kind": "file_over_10_mib"})
        findings.extend(secret_findings(content, path))
    for required in ("README.md", "README.en.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md",
                     ".github/workflows/ci.yml", "backend/.dockerignore", "frontend/.dockerignore"):
        if required not in paths:
            findings.append({"path": required, "kind": "required_file_not_tracked"})
    report = {"tracked_files": len(paths), "findings": findings,
              "scope": "tracked working files; credential signatures and excluded file paths"}
    if history:
        objects = {}
        for line in git("rev-list", "--objects", "--all").decode("utf-8").splitlines():
            sha, _, path = line.partition(" ")
            objects.setdefault(sha, path)
        raw = subprocess.check_output(["git", "cat-file", "--batch"], cwd=ROOT,
                                      input="\n".join(objects).encode() + b"\n")
        stream = io.BytesIO(raw)
        blobs = runtime_pdfs = 0
        for sha, path in objects.items():
            _, kind, size = stream.readline().decode("ascii").split()
            content = stream.read(int(size))
            stream.read(1)
            if kind != "blob":
                continue
            blobs += 1
            runtime_pdfs += path.startswith("data/") and path.endswith(".pdf")
            findings.extend(secret_findings(content, f"{path}@{sha[:12]}"))
        report.update(history_blobs=blobs, historical_runtime_pdf_blobs=runtime_pdfs)
    report["ok"] = not findings
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="scan all locally reachable Git blobs too")
    args = parser.parse_args()
    result = check(args.history)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
