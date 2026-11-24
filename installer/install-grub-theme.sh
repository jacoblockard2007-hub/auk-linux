#!/bin/sh
# Install the Auk GRUB theme artwork into a root filesystem.
#
# Usage: install-grub-theme.sh /path/to/root
#
# The image ships the packaged Gentoo glass theme (background, selection
# pixmaps and font). This replaces its logo and theme file with the Auk ones
# and points GRUB_THEME at the result. Safe to re-run.
set -eu

ROOT="${1:?usage: install-grub-theme.sh /path/to/root}"
HERE=$(cd "$(dirname "$0")" && pwd)
SRC="$HERE/grub-theme"

die() { echo "error: $*" >&2; exit 1; }

[ -d "$ROOT/etc" ] || die "$ROOT: not a root filesystem"
[ -f "$SRC/theme.txt" ] || die "missing $SRC/theme.txt"
[ -f "$SRC/auk-logo.png" ] || die "missing $SRC/auk-logo.png"

ROOT=${ROOT%/}
[ -n "$ROOT" ] || ROOT=/
GRUB_DEFAULT="$ROOT/etc/default/grub"

# Keep whatever theme directory GRUB is already configured for; the packaged
# glass theme is the fallback.
THEME=""
if [ -f "$GRUB_DEFAULT" ]; then
    THEME=$(sed -n 's/^GRUB_THEME="\(.*\)"$/\1/p' "$GRUB_DEFAULT" | head -n 1)
fi
if [ -z "$THEME" ]; then
    THEME="/boot/grub/themes/gentoo_glass/theme.txt"
fi
THEME_NAME=${THEME%/theme.txt}
THEME_NAME=${THEME_NAME##*/}
THEME_DIR="$ROOT${THEME%/*}"

if [ ! -d "$THEME_DIR" ]; then
    echo "no GRUB theme directory for $THEME; leaving the theme alone"
    exit 0
fi

# Brand the active copy and the packaged copy it was installed from.
for dir in "$THEME_DIR" "$ROOT/usr/share/grub/themes/$THEME_NAME"; do
    [ -d "$dir" ] || continue
    install -m 0644 "$SRC/theme.txt" "$dir/theme.txt"
    install -m 0644 "$SRC/auk-logo.png" "$dir/auk-logo.png"
    rm -f "$dir/logo_glass.png"
done

if [ -f "$GRUB_DEFAULT" ]; then
    if grep -q '^GRUB_THEME=' "$GRUB_DEFAULT"; then
        sed -i "s|^GRUB_THEME=.*|GRUB_THEME=\"$THEME\"|" "$GRUB_DEFAULT"
    else
        printf 'GRUB_THEME="%s"\n' "$THEME" >> "$GRUB_DEFAULT"
    fi
fi

echo "GRUB theme: Auk ($THEME)"
