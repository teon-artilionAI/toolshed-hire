"""A breach checker that answers what a test tells it to, without a network.

The real adapter asks Have I Been Pwned. A unit test is about the use case that
acts on the answer, so this stands in for the adapter and records how many
passwords it was asked about. It never sees a password from the process without
being handed one deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeBreachedPasswordChecker:
    """Answers every password with the same verdict."""

    breached: bool = False
    checked: list[str] = field(default_factory=list)

    def is_breached(self, plain_password: str) -> bool:
        """Record the password and answer with the verdict the test chose."""
        self.checked.append(plain_password)
        return self.breached
