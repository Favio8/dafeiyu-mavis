"""Credential references cannot target other products; backend failures do not leak secrets."""
import pytest

from assistant.credentials import Credentials, CredentialUnavailable


def test_vault_proxy_and_reference_restriction():
    class Backend:
        values = {}
        def set_password(self, service, ref, value):
            self.values[(service, ref)] = value
        def get_password(self, service, ref):
            return self.values.get((service, ref))
        def delete_password(self, service, ref):
            del self.values[(service, ref)]
    credentials = Credentials(Backend())
    credentials.save("deepseek/default", "test-marker")
    assert credentials.read("deepseek/default") == "test-marker"
    credentials.delete("deepseek/default")
    assert credentials.read("deepseek/default") is None
    with pytest.raises(ValueError):
        credentials.delete("another-product/credential")
    with pytest.raises(ValueError):
        credentials.save("deepseek/default", "")


@pytest.mark.parametrize("operation,error", [("read", "VAULT_READ_FAILED"), ("delete", "VAULT_DELETE_FAILED")])
def test_raw_backend_errors_are_not_returned(operation, error):
    class Backend:
        def get_password(self, *args):
            raise RuntimeError("sensitive backend detail")
        def delete_password(self, *args):
            raise RuntimeError("sensitive backend detail")
    with pytest.raises(CredentialUnavailable, match="^" + error + "$"):
        getattr(Credentials(Backend()), operation)("deepseek/default")
