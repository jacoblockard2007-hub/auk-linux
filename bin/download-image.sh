#!/usr/bin/env bash
# Download the Auk Linux USB image from GitHub Releases.
#
# The image is 14 GiB, so it is compressed and split into parts smaller than
# GitHub's 2 GiB per-asset limit. This script downloads the parts, verifies
# every SHA-256, joins them, and decompresses the raw image into dist/.
#
#   bin/download-image.sh
#   bin/download-image.sh --tag v0.1.0
#   bin/download-image.sh --dir /some/other/dir
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIST="$ROOT/dist"
TAG="${AUK_RELEASE:-latest}"
REPO="${AUK_REPO:-jacoblockard2007-hub/auk-linux}"

die() { echo "error: $*" >&2; exit 1; }

usage() {
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --tag) TAG=${2:?--tag needs a value}; shift 2 ;;
        --dir) DIST=${2:?--dir needs a value}; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1 (try --help)" ;;
    esac
done

command -v sha256sum >/dev/null || die "sha256sum is required"
command -v xz >/dev/null || die "xz is required"

if [ "$TAG" = "latest" ]; then
    BASE="https://github.com/$REPO/releases/latest/download"
else
    BASE="https://github.com/$REPO/releases/download/$TAG"
fi

fetch() {
    local url=$1 out=$2
    echo "[*] $out"
    if command -v curl >/dev/null; then
        curl -fL --retry 3 --retry-delay 2 -o "$out" "$url"
    elif command -v wget >/dev/null; then
        wget -O "$out" "$url"
    else
        die "curl or wget is required"
    fi
}

mkdir -p "$DIST"
DIST=$(cd "$DIST" && pwd)
cd "$DIST"

echo "[*] release: $BASE"
fetch "$BASE/SHA256SUMS" SHA256SUMS.download
mv SHA256SUMS.download SHA256SUMS

XZ=$(awk '$2 ~ /\.img\.xz$/ {print $2; exit}' SHA256SUMS)
[ -n "$XZ" ] || die "SHA256SUMS has no .img.xz entry"
RAW=${XZ%.xz}

mapfile -t PARTS < <(awk '$2 ~ /\.img\.xz\.part[0-9][0-9]$/ {print $2}' SHA256SUMS | sort)
[ "${#PARTS[@]}" -gt 0 ] || die "SHA256SUMS has no split parts"

echo "[*] downloading ${#PARTS[@]} part(s) for $XZ"
for part in "${PARTS[@]}"; do
    fetch "$BASE/$part" "$part"
done

echo "[*] verifying parts"
awk '$2 ~ /\.img\.xz\.part[0-9][0-9]$/ {print}' SHA256SUMS | sha256sum -c -

echo "[*] joining parts"
cat "${PARTS[@]}" > "$XZ"

# The joined file should match the whole-image checksum.
awk -v name="$XZ" '$2 == name {print}' SHA256SUMS | sha256sum -c -

xz_bytes=$(stat -c%s "$XZ")
raw_bytes=15032385536
avail_bytes=$(df -Pk "$DIST" | awk 'NR == 2 {print $4 * 1024}')
[ "$avail_bytes" -gt $((raw_bytes + xz_bytes + 1073741824)) ] || \
    die "not enough free space in $DIST (need about 18 GiB)"

echo "[*] decompressing $XZ (this takes a few minutes)"
rm -f "$RAW.download"
xz -dc -- "$XZ" > "$RAW.download"
mv "$RAW.download" "$RAW"

echo "[*] verifying raw image"
awk -v name="$RAW" '$2 == name {print}' SHA256SUMS | sha256sum -c -

cat <<EOF

[+] image ready: $DIST/$RAW
    compressed:   $DIST/$XZ
    checksums:    $DIST/SHA256SUMS

Write it to a USB stick of at least 16 GB (all data is erased):

    sudo bin/write-usb.sh /dev/sdX "$DIST/$RAW"

You can delete the .xz and .part* files after writing if you need the space.
EOF
