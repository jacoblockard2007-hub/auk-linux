#!/bin/sh
# Install the vendored fastfetch, Auk logo and system config into an image root.
set -eu

ROOT="${1:?usage: install-fastfetch.sh /path/to/root}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SRC="$HERE/fastfetch"

install -D -m 0755 "$SRC/fastfetch" "$ROOT/usr/local/bin/fastfetch"
install -D -m 0755 "$SRC/auk"      "$ROOT/usr/local/bin/auk"
install -D -m 0644 "$SRC/auk.txt"  "$ROOT/usr/share/auk/auk.txt"
install -D -m 0644 "$SRC/config.jsonc" "$ROOT/etc/fastfetch/config.jsonc"
install -D -m 0644 "$SRC/LICENSE"  "$ROOT/usr/share/licenses/fastfetch/LICENSE"

echo "installed fastfetch + Auk logo into $ROOT"
