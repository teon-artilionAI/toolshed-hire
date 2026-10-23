#!/usr/bin/env python3
"""Scan a pipeline artifact for personal information and credentials (NFR-17).

The coverage report, the Playwright report and the staging failure screenshots
are uploaded from CI. Before each upload, this script reads the directory or
file and refuses a hit on an email address outside the seed domains, a South
African identity number that passes the checksum, a phone number that is not
one of the documented seed numbers, or a credential shaped like a key, token
or private key.

The scan is deliberately blunt. A false positive stops one artifact upload and
shows the line, which is cheaper than publishing a customer's details in a
public workflow artifact. Test values that are plainly fake are allowed by the
domain and phone allowlists, so the seed's own data does not trip it.

Run the planted-example check with:

    python infra/scripts/scan_artifacts.py --self-test
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable

ALLOWED_EMAIL_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "toolshedhire.co.za",
        "example.com",
        "example.co.za",
        "example.org",
    }
)
# The numbers the seed and the browser tests use. They are plainly made up and
# are the only numbers an artifact may carry.
ALLOWED_PHONE_DIGITS: Final[frozenset[str]] = frozenset(
    {
        "0824417719",
        "0215550199",
        "0835550199",
        "0215550100",
        "27824417719",
        "27215550199",
    }
)
MAXIMUM_FILE_BYTES: Final[int] = 5 * 1024 * 1024
TEXT_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".html",
        ".htm",
        ".json",
        ".jsonl",
        ".md",
        ".txt",
        ".log",
        ".xml",
        ".csv",
        ".yaml",
        ".yml",
        ".js",
        ".mjs",
        ".cjs",
        ".css",
        ".svg",
        ".ts",
        ".tsx",
        ".py",
        ".trace",
        ".har",
    }
)
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
PHONE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)(?:\+27|0)[6-8]\d(?:[\s-]?\d){7}(?!\d)"
)
SA_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\d{13}(?!\d)")
SECRET_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("resend-key", re.compile(r"\bre_[A-Za-z0-9]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One reason an artifact may not be uploaded."""

    path: str
    line: int
    kind: str
    preview: str


def sa_id_is_valid(value: str) -> bool:
    """Return True when a thirteen digit string has a real date and the Luhn check digit."""
    if len(value) != 13 or not value.isdigit():
        return False
    month = int(value[2:4])
    day = int(value[4:6])
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return False
    total = 0
    for index, character in enumerate(value[:-1]):
        digit = int(character)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    check = (10 - (total % 10)) % 10
    return check == int(value[-1])


def scan_text(text: str, path: str) -> list[Finding]:
    """Return every finding in one piece of text."""
    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        findings.extend(_email_findings(line, path, line_number))
        findings.extend(_phone_findings(line, path, line_number))
        findings.extend(_identity_findings(line, path, line_number))
        findings.extend(_secret_findings(line, path, line_number))
    return findings


def _email_findings(line: str, path: str, line_number: int) -> list[Finding]:
    found: list[Finding] = []
    for match in EMAIL_PATTERN.finditer(line):
        domain = match.group(0).rsplit("@", 1)[-1].lower()
        if domain not in ALLOWED_EMAIL_DOMAINS:
            found.append(Finding(path, line_number, "email", _preview(match.group(0))))
    return found


def _phone_findings(line: str, path: str, line_number: int) -> list[Finding]:
    found: list[Finding] = []
    for match in PHONE_PATTERN.finditer(line):
        digits = re.sub(r"\D", "", match.group(0))
        if digits not in ALLOWED_PHONE_DIGITS:
            found.append(Finding(path, line_number, "phone", _preview(match.group(0))))
    return found


def _identity_findings(line: str, path: str, line_number: int) -> list[Finding]:
    return [
        Finding(path, line_number, "sa-id", _preview(match.group(0)))
        for match in SA_ID_PATTERN.finditer(line)
        if sa_id_is_valid(match.group(0))
    ]


def _secret_findings(line: str, path: str, line_number: int) -> list[Finding]:
    return [
        Finding(path, line_number, kind, _preview(match.group(0)))
        for kind, pattern in SECRET_PATTERNS
        for match in pattern.finditer(line)
    ]


def _preview(value: str) -> str:
    """Return enough of a hit to find it without copying the whole value."""
    return value if len(value) <= 24 else f"{value[:12]}..."


def scan_path(root: Path) -> list[Finding]:
    """Return every finding under a file or directory."""
    targets: Iterable[Path] = [root] if root.is_file() else sorted(root.rglob("*"))
    findings: list[Finding] = []
    for path in targets:
        if not path.is_file():
            continue
        if any(part in {".git", "node_modules"} for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.stat().st_size > MAXIMUM_FILE_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(scan_text(text, str(path)))
    return findings


def _self_test() -> int:
    """Prove a planted example is found and the seed's own values are not."""
    planted = [
        "Contact jane.doe@private-domain.co.za about this.",
        "Identity 8001015009087 is in the file.",
        "Phone 072 999 8877 was typed.",
        "-----BEGIN PRIVATE KEY-----",
    ]
    found = [finding for text in planted for finding in scan_text(text, "planted.txt")]
    kinds = {finding.kind for finding in found}
    required = {"email", "sa-id", "phone", "private-key"}
    if not required <= kinds:
        print(f"Self-test failed. Expected {sorted(required)} and found {sorted(kinds)}.", file=sys.stderr)
        return 1

    clean = scan_text(
        "Thandi Mokoena, thandi.mokoena@example.co.za, 0824417719, "
        "booking TSH-R-26-000124, amount R 280.00.",
        "clean.txt",
    )
    if clean:
        print(f"Self-test failed. The seed example produced {clean}.", file=sys.stderr)
        return 1
    print("Self-test passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the scanner over the paths given, or the self-test."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip a path that does not exist, for an artifact an earlier step may not write.",
    )
    arguments = parser.parse_args(argv)
    if arguments.self_test:
        return _self_test()
    if not arguments.paths:
        parser.error("Give at least one file or directory to scan.")
    findings: list[Finding] = []
    for path in arguments.paths:
        if not path.exists():
            if arguments.allow_missing:
                print(f"Nothing to scan at {path}.")
                continue
            print(f"Artifact path does not exist: {path}", file=sys.stderr)
            return 2
        findings.extend(scan_path(path))
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.kind}: {finding.preview}")
        print(f"Refusing the upload because {len(findings)} finding(s) were in the artifact.")
        return 1
    print(f"Scanned {len(arguments.paths)} artifact path(s), no findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
