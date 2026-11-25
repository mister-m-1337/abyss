"""TLS nativo no código-fonte; certificados incluídos no executável distribuído."""
import ssl
import sys


def tls_context():
    if getattr(sys, "frozen", False):
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()
