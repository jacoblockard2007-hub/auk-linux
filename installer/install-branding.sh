#!/bin/sh
# Apply the Auk Linux identity to a root filesystem.
#
# Usage:
#   install-branding.sh /path/to/root [--hostname NAME] [--grub-cfg PATH]
#
# The script is intentionally root-relative and idempotent so the same file can
# brand a mounted image, a chroot, or a freshly installed system.
#
#   --hostname NAME   also set a static hostname (live USB image use case)
#   --grub-cfg PATH   rewrite an already generated GRUB menu to Auk labels
set -eu

ROOT="${1:?usage: install-branding.sh /path/to/root [--hostname NAME] [--grub-cfg PATH]}"
shift

NEW_HOSTNAME=""
GRUB_CFG=""
while [ $# -gt 0 ]; do
    case "$1" in
        --hostname) NEW_HOSTNAME="${2:?--hostname needs a value}"; shift 2 ;;
        --grub-cfg) GRUB_CFG="${2:?--grub-cfg needs a value}"; shift 2 ;;
        -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -d "$ROOT/etc" ] || { echo "$ROOT: not a root filesystem" >&2; exit 1; }
ROOT=${ROOT%/}
[ -n "$ROOT" ] || ROOT=/

echo "applying Auk Linux identity to $ROOT"

# --- os-release -----------------------------------------------------------
# Gentoo ships /etc/os-release as a symlink to ../usr/lib/os-release, so write
# the target and leave the symlink in place.
mkdir -p "$ROOT/usr/lib"
cat > "$ROOT/usr/lib/os-release" <<'EOF'
NAME="Auk Linux"
ID=auk
ID_LIKE=gentoo
PRETTY_NAME="Auk Linux"
VERSION="0.1 (prototype)"
VERSION_ID="0.1"
HOME_URL="https://github.com/jacoblockard2007-hub/auk-linux"
SUPPORT_URL="https://github.com/jacoblockard2007-hub/auk-linux/issues"
BUG_REPORT_URL="https://github.com/jacoblockard2007-hub/auk-linux/issues"
ANSI_COLOR="1;33"
EOF
if [ ! -L "$ROOT/etc/os-release" ]; then
    cp "$ROOT/usr/lib/os-release" "$ROOT/etc/os-release"
fi

# --- console banner -------------------------------------------------------
printf '%s\n\n' 'Auk Linux \n \l' > "$ROOT/etc/issue"

# --- hostname (live image only) ------------------------------------------
if [ -n "$NEW_HOSTNAME" ]; then
    printf '%s\n' "$NEW_HOSTNAME" > "$ROOT/etc/hostname"
    touch "$ROOT/etc/hosts"
    sed -i '/^127\.0\.1\.1[[:space:]]/d' "$ROOT/etc/hosts"
    printf '127.0.1.1\t%s\n' "$NEW_HOSTNAME" >> "$ROOT/etc/hosts"
    echo "hostname: $NEW_HOSTNAME"
fi

# --- GRUB distributor -----------------------------------------------------
GRUB_DEFAULT="$ROOT/etc/default/grub"
if [ -f "$GRUB_DEFAULT" ]; then
    if grep -q '^GRUB_DISTRIBUTOR=' "$GRUB_DEFAULT"; then
        sed -i 's|^GRUB_DISTRIBUTOR=.*|GRUB_DISTRIBUTOR="Auk Linux"|' \
            "$GRUB_DEFAULT"
    else
        printf 'GRUB_DISTRIBUTOR="Auk Linux"\n' >> "$GRUB_DEFAULT"
    fi
    echo "GRUB_DISTRIBUTOR: Auk Linux"
fi

# grub-mkconfig appends " GNU/Linux" to GRUB_DISTRIBUTOR. Rewrite an already
# generated menu so it reads "Auk Linux" exactly. Also rename legacy Gentoo
# labels when branding an image built before this script existed.
if [ -n "$GRUB_CFG" ] && [ -f "$GRUB_CFG" ]; then
    sed -i \
        -e 's/Auk Linux GNU\/Linux/Auk Linux/g' \
        -e 's/Gentoo GNU\/Linux/Auk Linux/g' \
        -e 's/--class gentoo/--class auk/g' \
        "$GRUB_CFG"
    echo "GRUB menu labels: Auk Linux"
fi

echo "Auk Linux identity applied"
