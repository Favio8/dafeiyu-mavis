"""Windows Credential Manager only. No config, database, log or plaintext fallback."""
from __future__ import annotations

import re


class CredentialUnavailable(RuntimeError):
    """Credential persistence failed; caller may offer explicit memory-only use."""


class Credentials:
    """Store named secrets only through Windows' native vault backend."""
    SERVICE = "DaFeiYuMavis"

    def __init__(self, backend=None):
        if backend is None:
            try:
                from keyring.backends.Windows import WinVaultKeyring
                backend = WinVaultKeyring()
            except (ImportError, RuntimeError) as exc:
                raise CredentialUnavailable("WINDOWS_VAULT_UNAVAILABLE") from exc
        self.backend = backend

    @staticmethod
    def _ref(ref: str) -> None:
        if not re.fullmatch(r"(?:deepseek/default|probe/[0-9a-f]{32})", ref):
            raise ValueError("unknown credential reference")

    def save(self, ref: str, secret: str) -> None:
        """Persist a secret or fail explicitly. Never serialize an exception's raw message."""
        self._ref(ref)
        if not isinstance(secret, str) or not 1 <= len(secret) <= 1024:
            raise ValueError("invalid secret length")
        try:
            self.backend.set_password(self.SERVICE, ref, secret)
        except Exception:
            # Backend exceptions may contain credentials, so only a fixed code escapes.
            raise CredentialUnavailable("VAULT_WRITE_FAILED") from None

    def read(self, ref: str) -> str | None:
        """Read into caller memory; return None for an absent credential."""
        self._ref(ref)
        try:
            return self.backend.get_password(self.SERVICE, ref)
        except Exception:
            raise CredentialUnavailable("VAULT_READ_FAILED") from None

    def delete(self, ref: str) -> None:
        """Delete exactly one user-selected reference or this probe's own random reference."""
        self._ref(ref)
        try:
            self.backend.delete_password(self.SERVICE, ref)
        except Exception:
            raise CredentialUnavailable("VAULT_DELETE_FAILED") from None
