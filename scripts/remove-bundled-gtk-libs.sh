#!/usr/bin/env bash
set -euo pipefail

bundle=${1:?Usage: remove-bundled-gtk-libs.sh BUNDLE_DIRECTORY}
if [[ ! -d "$bundle" ]]; then
  echo "Bundle directory does not exist: $bundle" >&2
  exit 1
fi

# GTK 4, Libadwaita, and their dependency stack must come from the target
# system. Keeping only the GTK libraries out still mixes host HarfBuzz/Pango
# with copies from the build distro and can prevent GTK from loading.
python3 - "$bundle" <<'PY'
import os
from pathlib import Path
import subprocess
import sys

bundle = Path(sys.argv[1]).resolve()
patterns = (
    'libadwaita-1.so*',
    'libgtk-4.so*',
    'libgtk-3.so*',
    'libgdk-3.so*',
)
roots = {path for pattern in patterns for path in bundle.rglob(pattern)}
if not roots:
    print('No bundled GTK libraries found; nothing to remove.')
    raise SystemExit(0)

env = os.environ.copy()
existing_library_path = env.get('LD_LIBRARY_PATH')
library_dirs = sorted(
    {str(path.parent) for path in bundle.rglob('*.so*') if path.is_file() or path.is_symlink()}
)
env['LD_LIBRARY_PATH'] = os.pathsep.join(
    library_dirs + ([existing_library_path] if existing_library_path else [])
)
remove_targets = {path.resolve() for path in roots}

for root in roots:
    result = subprocess.run(
        ['ldd', str(root)], capture_output=True, text=True, env=env, check=False
    )
    if result.returncode or 'not found' in result.stdout:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(f'Could not inspect bundled GTK dependencies: {root}')
    for line in result.stdout.splitlines():
        fields = line.strip().split()
        if '=>' in fields:
            index = fields.index('=>') + 1
            dependency = fields[index] if index < len(fields) else ''
        else:
            dependency = fields[0] if fields and fields[0].startswith('/') else ''
        if dependency:
            resolved = Path(dependency).resolve()
            if resolved.is_relative_to(bundle):
                remove_targets.add(resolved)

# Remove the aliases too. PyInstaller often creates several SONAME symlinks
# for one bundled library, and leaving any alias behind would create a broken
# dependency that the dynamic loader still tries to open.
remove = set()
for path in bundle.rglob('*'):
    if path.is_file() or path.is_symlink():
        try:
            if path.resolve() in remove_targets:
                remove.add(path)
        except OSError:
            continue

for path in sorted(remove, key=lambda item: len(item.parts), reverse=True):
    path.unlink(missing_ok=True)

print(f'Removed {len(remove)} bundled GTK runtime libraries and dependencies.')
PY
