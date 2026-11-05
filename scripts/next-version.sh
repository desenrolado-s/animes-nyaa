#!/usr/bin/env bash
# Increment the latest vMAJOR.MINOR.PATCH tag for automated main releases.
set -euo pipefail
cd "$(dirname "$0")/.."

latest=$(git tag --list 'v*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n 1 || true)
if [[ -z "$latest" ]]; then
  printf '0.0.1\n'
  exit 0
fi

IFS=. read -r major minor patch <<< "${latest#v}"
patch=$((patch + 1))
if (( patch > 9 )); then
  patch=0
  minor=$((minor + 1))
fi
if (( minor > 9 )); then
  minor=0
  major=$((major + 1))
fi
printf '%s.%s.%s\n' "$major" "$minor" "$patch"
