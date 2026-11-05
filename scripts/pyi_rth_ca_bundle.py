"""Point Python TLS clients at the CA certificates shipped with the bundle."""
import os
import sys

bundle = os.path.join(sys._MEIPASS, 'certs', 'ca-certificates.crt')
if os.path.isfile(bundle):
    os.environ.setdefault('SSL_CERT_FILE', bundle)
