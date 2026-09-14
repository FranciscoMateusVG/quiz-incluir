"""Strict CPF normalization and checksum parity with Programa Incluir."""

from __future__ import annotations

import re


_RAW_CPF = re.compile(r"^[0-9]{11}$", flags=re.ASCII)
_MASKED_CPF = re.compile(
    r"^([0-9]{3})\.([0-9]{3})\.([0-9]{3})-([0-9]{2})$",
    flags=re.ASCII,
)


def is_valid_cpf(cpf: str) -> bool:
    """Validate an already-normalized 11-ASCII-digit CPF."""

    if _RAW_CPF.fullmatch(cpf) is None:
        return False
    if len(set(cpf)) == 1:
        return False

    digits = [int(digit) for digit in cpf]
    first_sum = sum(digits[index] * (10 - index) for index in range(9))
    first_check = (first_sum * 10) % 11
    if first_check == 10:
        first_check = 0
    if first_check != digits[9]:
        return False

    second_sum = sum(digits[index] * (11 - index) for index in range(10))
    second_check = (second_sum * 10) % 11
    if second_check == 10:
        second_check = 0
    return second_check == digits[10]


def normalize_cpf(value: str) -> str | None:
    """Normalize only the two approved CPF wire/display shapes."""

    candidate = value.strip()
    if _RAW_CPF.fullmatch(candidate) is not None:
        normalized = candidate
    else:
        masked = _MASKED_CPF.fullmatch(candidate)
        if masked is None:
            return None
        normalized = "".join(masked.groups())
    return normalized if is_valid_cpf(normalized) else None
