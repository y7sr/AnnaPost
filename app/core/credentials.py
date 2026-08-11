"""Resolve secret references without storing or logging secret values."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping


class CredentialResolutionError(ValueError):
    """Raised when a configured credential reference cannot be resolved."""


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def resolve_access_token(
    reference: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve an access-token reference from the process environment.

    Account rows store references such as ``env:INSTAGRAM_ACCESS_TOKEN``;
    plaintext tokens are deliberately not accepted as account configuration.
    ``environ`` is injectable so unit tests never need to modify process-wide
    environment state.
    """
    value = reference.strip()
    if not value.startswith("env:"):
        raise CredentialResolutionError(
            "Access token must be an environment reference such as "
            "env:INSTAGRAM_ACCESS_TOKEN"
        )

    name = value.removeprefix("env:").strip()
    if not _ENV_NAME.fullmatch(name):
        raise CredentialResolutionError("Access token environment reference is invalid")

    token = (os.environ if environ is None else environ).get(name)
    if not token:
        raise CredentialResolutionError(
            f"Access token environment variable {name!r} is missing or empty"
        )
    return token
