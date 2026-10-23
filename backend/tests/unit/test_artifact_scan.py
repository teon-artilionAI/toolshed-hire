"""The pipeline artifact scan, with planted examples (NFR-17, B14.3).

The scanner is loaded from its file because it is an operations script and not
part of the backend package. The tests plant one example of each kind the scan
refuses and one of each the seed is allowed to carry, so a rule that stops
working fails here rather than in a public artifact.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPOSITORY_ROOT / "infra" / "scripts" / "scan_artifacts.py"


def load_scanner() -> ModuleType:
    """Return the scanner module from its file path."""
    spec = importlib.util.spec_from_file_location("scan_artifacts", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scanner = load_scanner()


def kinds(text: str) -> set[str]:
    """Return the kinds the scanner finds in one piece of text."""
    return {finding.kind for finding in scanner.scan_text(text, "sample.txt")}


def test_a_private_email_is_found() -> None:
    """An address outside the seed domains is a finding."""
    assert "email" in kinds("Write to jane.doe@private-domain.co.za about it.")


def test_the_seed_domains_are_allowed() -> None:
    """The addresses the seed and the tests use are not findings."""
    assert kinds("thandi.mokoena@example.co.za and person1@toolshedhire.co.za") == set()


def test_a_valid_south_african_id_is_found() -> None:
    """A thirteen digit number with a real date and a good check digit is a finding."""
    assert "sa-id" in kinds("Identity 8001015009087 was typed in.")


def test_an_invalid_south_african_id_is_not_a_finding() -> None:
    """A number that fails the checksum is not treated as an identity number."""
    assert "sa-id" not in kinds("Reference 8001015009088 is a booking number.")


def test_a_seed_phone_number_is_allowed_and_another_is_not() -> None:
    """The documented seed numbers are allowed and a different number is a finding."""
    assert kinds("Call 0824417719.") == set()
    assert "phone" in kinds("Call 072 999 8877.")


def test_a_private_key_and_a_github_token_are_findings() -> None:
    """The credential patterns refuse a private key and a token."""
    assert {"private-key", "github-token"} <= kinds(
        "-----BEGIN " + "PRIVATE KEY-----\n" + "ghp_" + "a" * 36
    )


def test_a_directory_is_scanned_and_binary_files_are_skipped(tmp_path: Path) -> None:
    """A text file is read and a binary one is left alone."""
    (tmp_path / "report.html").write_text("mail jane@private-domain.co.za", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\nnot text")
    found = scanner.scan_path(tmp_path)
    assert [finding.kind for finding in found] == ["email"]


def test_the_planted_example_self_test_passes() -> None:
    """The CLI's own planted-example check passes."""
    assert scanner.main(["--self-test"]) == 0
