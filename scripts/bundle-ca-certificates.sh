#!/usr/bin/env bash
set -euo pipefail

destination=${1:?Usage: bundle-ca-certificates.sh DESTINATION_DIRECTORY}
if [ -s "$destination/ca-certificates.crt" ]; then
  exit 0
fi
for certificate_file in \
  /etc/ssl/certs/ca-certificates.crt \
  /etc/pki/tls/certs/ca-bundle.crt \
  /etc/ssl/ca-bundle.pem \
  "${MINGW_PREFIX:-/ucrt64}/etc/ssl/certs/ca-bundle.crt" \
  /usr/ssl/certs/ca-bundle.crt; do
  if [ -r "$certificate_file" ]; then
    mkdir -p "$destination"
    cp -L "$certificate_file" "$destination/ca-certificates.crt"
    test -s "$destination/ca-certificates.crt"
    exit 0
  fi
done

echo 'Could not find a system CA certificate bundle.' >&2
exit 1
