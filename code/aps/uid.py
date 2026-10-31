"""Swiss business identification numbers (UID, e.g. "CHE-116.281.710").

Every Swiss business has a UID. The commercial register vouches for it, so a seal from
the register is only meaningful if it covers a well-formed UID. The last digit is a
mod-11 check digit (eCH-0097): weights 5,4,3,2,7,6,5,4 over the first eight digits,
check = 11 - (sum mod 11), where 11 becomes 0 and 10 never occurs in a valid UID.
This catches typos and made-up numbers, not fraud: fraud is caught by the seal.
"""

import re

UID_PATTERN = re.compile(r"^CHE-(\d{3})\.(\d{3})\.(\d{3})$")
WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4)


def check_digit(first_eight: str) -> int | None:
    """The check digit for eight UID digits, or None if no valid UID has these digits."""
    remainder = sum(int(d) * w for d, w in zip(first_eight, WEIGHTS)) % 11
    digit = 11 - remainder
    if digit == 11:
        return 0
    return None if digit == 10 else digit


def is_valid_uid(uid) -> bool:
    """True if `uid` is written as CHE-ddd.ddd.ddd and its check digit is right."""
    match = UID_PATTERN.match(uid) if isinstance(uid, str) else None
    if not match:
        return False
    digits = "".join(match.groups())
    return check_digit(digits[:8]) == int(digits[8])
