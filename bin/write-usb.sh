#!/usr/bin/env bash
# Write the finished image to a USB stick, with guardrails.
#
#   sudo bin/write-usb.sh /dev/sdX
#   sudo bin/write-usb.sh /dev/sdX dist/auk-linux-usb.img.xz
#
# Refuses to write to the disk holding /, requires the target to be removable,
# and asks you to type the device name before destroying it.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEVICE=${1:-}
IMAGE=${2:-$ROOT/dist/auk-linux-usb.img}

die() { echo "error: $*" >&2; exit 1; }

[ -n "$DEVICE" ] || die "usage: $0 /dev/sdX [image.img|image.img.xz]"
[ -b "$DEVICE" ] || die "$DEVICE is not a block device"
[ -f "$IMAGE" ] || die "image not found: $IMAGE"

if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo >/dev/null; then
        exec sudo -- "$0" "$@"
    fi
    die "must run as root"
fi

DEV=$(basename "$(readlink -f "$DEVICE")")
SYS=/sys/block/$DEV
[ -d "$SYS" ] || die "cannot resolve $DEVICE to a whole disk"
[ -f "$SYS/removable" ] && [ "$(cat "$SYS/removable")" = 1 ] || \
    die "$DEV is not a removable device (refusing: could be an internal disk)"

ROOT_SRC=$(findmnt -no SOURCE /)
ROOT_DISK=$(lsblk -no PKNAME "$ROOT_SRC" 2>/dev/null || true)
[ "$DEV" != "$ROOT_DISK" ] || die "$DEV holds the running root filesystem"

MODEL=$(cat "$SYS/device/model" 2>/dev/null || echo unknown)
SIZE=$(lsblk -dno SIZE "$DEVICE")
echo "Target:  $DEVICE  ($MODEL, $SIZE)"
echo "Image:   $IMAGE"
echo
echo "ALL DATA ON $DEVICE WILL BE DESTROYED."
printf 'Type the device name (%s) to continue: ' "$DEV"
read -r answer
[ "$answer" = "$DEV" ] || die "aborted"

echo "[*] writing (this takes several minutes)"
case "$IMAGE" in
    *.xz)  xz -dc -- "$IMAGE" | dd of="$DEVICE" bs=4M conv=fsync status=progress ;;
    *.zst) zstd -dc -- "$IMAGE" | dd of="$DEVICE" bs=4M conv=fsync status=progress ;;
    *)     dd if="$IMAGE" of="$DEVICE" bs=4M conv=fsync status=progress ;;
esac
sync
blockdev --rereadpt "$DEVICE" 2>/dev/null || true
echo "[+] done. Remove the stick and boot it (BIOS or UEFI)."
echo "    If it does not boot, disable Secure Boot in the firmware settings."
