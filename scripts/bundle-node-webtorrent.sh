#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
bundle_root=${1:?Usage: bundle-node-webtorrent.sh <bundle-internal-directory>}
node_version=24.22.2
node_sha256=48cc0e21e048790e54c0cf5749c2725005313d652651c40b7a21feb9697aaf75
node_archive="node-v${node_version}-linux-x64.tar.xz"
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT

curl --fail --location --retry 3 \
  "https://nodejs.org/dist/v${node_version}/${node_archive}" \
  --output "$work_dir/$node_archive"
printf '%s  %s\n' "$node_sha256" "$work_dir/$node_archive" | sha256sum --check

mkdir "$work_dir/node" "$work_dir/webtorrent-cli"
tar -xJf "$work_dir/$node_archive" -C "$work_dir/node" --strip-components=1
cp "$repo_root/packaging/node/package.json" \
  "$repo_root/packaging/node/package-lock.json" \
  "$work_dir/webtorrent-cli/"

export PATH="$work_dir/node/bin:$PATH"
npm ci --prefix "$work_dir/webtorrent-cli" --omit=dev --no-audit --no-fund \
  --strict-allow-scripts

"$work_dir/node/bin/node" --version | grep -Fx "v${node_version}"
"$work_dir/node/bin/node" \
  "$work_dir/webtorrent-cli/node_modules/webtorrent-cli/bin/cmd.js" \
  --help >/dev/null
(
  cd "$work_dir/webtorrent-cli"
  "$work_dir/node/bin/node" --input-type=module \
    -e "import('node-datachannel').then(() => console.log('node-datachannel native binding loaded'))"
)

mkdir -p "$bundle_root"
rm -rf "$bundle_root/node" "$bundle_root/webtorrent-cli"
mkdir -p "$bundle_root/node/bin" "$bundle_root/webtorrent-cli"
install -m 755 "$work_dir/node/bin/node" "$bundle_root/node/bin/node"
install -m 644 "$work_dir/node/LICENSE" "$bundle_root/node/LICENSE"
cp -a "$work_dir/webtorrent-cli/node_modules" "$bundle_root/webtorrent-cli/"

cat > "$bundle_root/NODE-WEBTORRENT.txt" <<EOF
Bundled runtime tools

Node.js ${node_version} (MIT License: node/LICENSE)
WebTorrent CLI 6.0.1 (MIT License: webtorrent-cli/node_modules/webtorrent-cli/LICENSE)

mpv, GTK 4 and Libadwaita are provided by the host system.
EOF
