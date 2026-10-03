"""The rule a password has to meet when it is chosen (BR-45).

A password is at least twelve characters. That is the whole of the policy the
design document sets, and it applies at the two moments a password is chosen,
which are registration and the completion of a reset. It does not apply when a
password is presented at sign in, because refusing a short one there would say
something about the value that was typed.

The upper bound is not policy. bcrypt reads 72 bytes and ignores the rest, so
a longer password is refused instead of being quietly shortened.

The sentences are shown beside the input, so they say what to do. Neither of
them repeats the password, and nothing here logs it.
"""

from __future__ import annotations

from typing import Final

from app.domain.errors import ValidationFailure

PASSWORD_RULE: Final[str] = "BR-45"
MINIMUM_PASSWORD_LENGTH: Final[int] = 12
MAXIMUM_PASSWORD_BYTES: Final[int] = 72
PASSWORD_ENCODING: Final[str] = "utf-8"

PASSWORD_TOO_SHORT_MESSAGE: Final[str] = (
    f"Choose a password of at least {MINIMUM_PASSWORD_LENGTH} characters."
)
PASSWORD_TOO_LONG_MESSAGE: Final[str] = (
    f"Choose a shorter password. It may take up at most {MAXIMUM_PASSWORD_BYTES} bytes."
)


def ensure_password_may_be_chosen(plain_password: str) -> None:
    """Refuse a password that is too short to choose, or too long to hash whole.

    Args:
        plain_password: The password as it was typed. It is measured and
            never kept.

    Raises:
        ValidationFailure: If the password is under twelve characters, or
            over the 72 bytes bcrypt reads.

    """
    if len(plain_password) < MINIMUM_PASSWORD_LENGTH:
        raise ValidationFailure(
            PASSWORD_TOO_SHORT_MESSAGE,
            {"minimum_length": MINIMUM_PASSWORD_LENGTH},
            rule=PASSWORD_RULE,
        )
    if len(plain_password.encode(PASSWORD_ENCODING)) > MAXIMUM_PASSWORD_BYTES:
        raise ValidationFailure(
            PASSWORD_TOO_LONG_MESSAGE,
            {"maximum_bytes": MAXIMUM_PASSWORD_BYTES},
            rule=PASSWORD_RULE,
        )
