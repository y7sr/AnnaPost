"""Credential-reference tests."""

from __future__ import annotations

import pytest

from app.core.credentials import CredentialResolutionError, resolve_access_token


def test_resolves_environment_reference_without_exposing_secret_in_configuration() -> None:
    assert (
        resolve_access_token(
            "env:INSTAGRAM_ACCESS_TOKEN",
            environ={"INSTAGRAM_ACCESS_TOKEN": "real-test-token"},
        )
        == "real-test-token"
    )


@pytest.mark.parametrize(
    "reference",
    ["", "real-token", "env:", "env:NOT-A-VARIABLE"],
)
def test_rejects_plaintext_and_invalid_environment_references(reference: str) -> None:
    with pytest.raises(CredentialResolutionError):
        resolve_access_token(reference, environ={})


def test_rejects_missing_environment_value() -> None:
    with pytest.raises(CredentialResolutionError, match="missing or empty"):
        resolve_access_token("env:INSTAGRAM_ACCESS_TOKEN", environ={})
