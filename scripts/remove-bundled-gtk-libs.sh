#!/usr/bin/env bash
set -euo pipefail

bundle=${1:?Usage: remove-bundled-gtk-libs.sh BUNDLE_DIRECTORY}
if [[ ! -d "$bundle" ]]; then
  echo "Bundle directory does not exist: $bundle" >&2
  exit 1
fi

# GTK 4 and Libadwaita must come from the target system so the app uses its
# installed theme and stays compatible with the host's GTK runtime.
find "$bundle" \( \
  -name 'libadwaita-1.so*' -o \
  -name 'libgtk-4.so*' -o \
  -name 'libgtk-3.so*' -o \
  -name 'libgdk-3.so*' \
\) -delete
