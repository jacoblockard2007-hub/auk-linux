#!/bin/bash
# Install the running Auk Linux system onto another disk.
#
# Runs as root on the live USB system. Clones the running root filesystem,
# regenerates machine identity/users/fstab, and installs GRUB for BIOS+UEFI.
#
# Usage:
#   gentoo-install-to-disk --disk /dev/sdX --username alice \
#       --password secret --hostname alice-pc [--fullname "Alice"] --yes
#
#   gentoo-install-to-disk --config FILE --yes
#       FILE: disk<TAB>username<TAB>password<TAB>hostname<TAB>fullname
#
# The running system's disk is always refused as a target.
set -Eeuo pipefail

LOG=/var/log/gentoo-install.log
mkdir -p /var/log
exec > >(tee -a "$LOG") 2>&1

cleanup() {
    set +e
    sync
    umount -R /mnt/target 2>/dev/null && return 0
    # A chroot can leave /dev/pts busy; detach the nested trees lazily.
    for m in dev/pts dev/shm dev sys proc; do
        umount -R -l "/mnt/target/$m" 2>/dev/null
    done
    umount -R -l /mnt/target 2>/dev/null
    return 0
}
trap 'rc=$?; echo "INSTALL_FAILED rc=$rc line=$LINENO"; cleanup; exit $rc' ERR

DISK=""
INSTALL_USER=""
INSTALL_PASS=""
INSTALL_HOST=""
INSTALL_FULL=""
CONFIG_STDIN=0
CONFIG_FILE=""
DRY_RUN=0
ASSUME_YES=0

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

die() { echo "ERROR: $*"; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --disk) DISK=${2:?}; shift 2 ;;
        --username) INSTALL_USER=${2:?}; shift 2 ;;
        --password) INSTALL_PASS=${2:?}; shift 2 ;;
        --hostname) INSTALL_HOST=${2:?}; shift 2 ;;
        --fullname) INSTALL_FULL=${2:-}; shift 2 ;;
        --config) CONFIG_FILE=${2:?}; shift 2 ;;
        --config-stdin) CONFIG_STDIN=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --yes) ASSUME_YES=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown option: $1" ;;
    esac
done

if [ -n "$CONFIG_FILE" ]; then
    [ -r "$CONFIG_FILE" ] || die "cannot read config file"
    IFS=$'\t' read -r DISK INSTALL_USER INSTALL_PASS INSTALL_HOST INSTALL_FULL < "$CONFIG_FILE" || true
    rm -f "$CONFIG_FILE"
fi
if [ "$CONFIG_STDIN" = 1 ]; then
    # Tab-separated, one record. Empty trailing fullname is allowed.
    IFS=$'\t' read -r DISK INSTALL_USER INSTALL_PASS INSTALL_HOST INSTALL_FULL || true
fi

echo "===== AUK LINUX INSTALL $(date -u) ====="

[ "$(id -u)" = 0 ] || die "must run as root"
[ -n "$DISK" ] && [ -b "$DISK" ] || die "target disk missing or not a block device"
[ "$(lsblk -dno TYPE "$DISK")" = "disk" ] || die "$DISK is not a whole disk"
case "$(basename "$DISK")" in
    fd*|sr*|loop*|ram*|zram*|nbd*) die "$DISK is not an installable disk" ;;
esac
[ "$(blockdev --getsize64 "$DISK" 2>/dev/null || echo 0)" -gt 0 ] || \
    die "cannot read the size of $DISK"
[[ "$INSTALL_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "invalid username"
[ "$INSTALL_USER" != root ] || die "username 'root' is not allowed"
[[ "$INSTALL_HOST" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]] || die "invalid hostname"
[ -n "$INSTALL_PASS" ] || die "password must not be empty"
case "$INSTALL_PASS" in *$'\t'*|*$'\n'*) die "password contains an unsupported character" ;; esac

for tool in sgdisk partprobe mkfs.vfat mkfs.ext4 rsync blkid chroot grub-install; do
    command -v "$tool" >/dev/null || die "required tool missing: $tool"
done

# Refuse the disk we are running from.
LIVE_SRC=$(findmnt -no SOURCE /)
LIVE_DISK=$(lsblk -no PKNAME "$LIVE_SRC" 2>/dev/null | head -n1 || true)
[ -n "$LIVE_DISK" ] || LIVE_DISK=$(basename "$LIVE_SRC")
LIVE_DISK="/dev/$LIVE_DISK"
if [ "$(readlink -f "$DISK")" = "$(readlink -f "$LIVE_DISK")" ]; then
    die "refusing to install onto the running system's disk ($LIVE_DISK)"
fi
if lsblk -no MOUNTPOINTS "$DISK" | grep -q .; then
    die "$DISK has mounted partitions; unmount them first"
fi
# Refuse only swap the kernel is actually using. A leftover swap signature is
# harmless because the installer repartitions the whole disk, and lsblk keeps
# reporting it from cache even after swapoff.
ACTIVE_SWAP=$(
    awk 'NR > 1 { print $1 }' /proc/swaps |
        while read -r dev; do readlink -f "$dev"; done
)
for part in $(lsblk -nlo PATH "$DISK"); do
    if printf '%s\n' "$ACTIVE_SWAP" | grep -qxF "$(readlink -f "$part")"; then
        die "$part is in use as swap; run 'swapoff $part' first"
    fi
done

# Partition naming works for /dev/sda, /dev/vda, /dev/nvme0n1, /dev/mmcblk0.
case "$DISK" in
    *[0-9]) PART_PREFIX="${DISK}p" ;;
    *)      PART_PREFIX="$DISK" ;;
esac
ESP_PART="${PART_PREFIX}2"
ROOT_PART="${PART_PREFIX}3"

DISK_BYTES=$(blockdev --getsize64 "$DISK")
USED_KB=$(df --output=used -k / | tail -n1 | tr -d ' ')
NEED_BYTES=$(( USED_KB * 1024 + 2 * 1024 * 1024 * 1024 ))

echo "target:      $DISK ($(lsblk -dno SIZE,MODEL "$DISK" | xargs))"
echo "live disk:   $LIVE_DISK (excluded)"
echo "source used: $(( USED_KB / 1024 )) MiB"
echo "minimum:     $(( NEED_BYTES / 1024 / 1024 )) MiB"
echo "layout:      p1 BIOS boot 1 MiB, p2 ESP 512 MiB, p3 root rest"

[ "$DISK_BYTES" -ge "$NEED_BYTES" ] || \
    die "target is too small: need at least $(( NEED_BYTES / 1024 / 1024 )) MiB"

if [ "$DRY_RUN" = 1 ]; then
    echo "DRY_RUN_OK target=$DISK root_part=$ROOT_PART esp_part=$ESP_PART"
    exit 0
fi

if [ "$ASSUME_YES" != 1 ]; then
    echo "ALL DATA ON $DISK WILL BE ERASED."
    read -r -p "Type ERASE to continue: " answer
    [ "$answer" = "ERASE" ] || die "aborted"
fi

echo "==> partitioning $DISK"
sgdisk --zap-all "$DISK"
sgdisk --clear \
    --new=1:2048:+1M --typecode=1:ef02 --change-name=1:"BIOS boot" \
    --new=2:0:+512M  --typecode=2:ef00 --change-name=2:"EFI System" \
    --new=3:0:0      --typecode=3:8300 --change-name=3:"Auk root" \
    "$DISK"
partprobe "$DISK" || true
udevadm settle || true
sleep 1

echo "==> formatting"
mkfs.vfat -F32 -n AUKEFI "$ESP_PART"
mkfs.ext4 -F -m 1 -L auk-root "$ROOT_PART"

echo "==> mounting target"
mkdir -p /mnt/target
mount "$ROOT_PART" /mnt/target
mkdir -p /mnt/target/boot/efi
mount "$ESP_PART" /mnt/target/boot/efi

echo "==> copying the running system (offline)"
rsync -aHAX --numeric-ids --stats \
    --exclude=/proc --exclude=/sys --exclude=/dev --exclude=/run \
    --exclude=/tmp --exclude=/mnt --exclude=/media --exclude=/lost+found \
    --exclude=/boot/efi --exclude=/etc/machine-id \
    --exclude=/var/log/journal --exclude=/var/cache/binhost \
    --exclude=/root/.bash_history --exclude='/home/*/.bash_history' \
    --exclude='/home/*/.cache' \
    / /mnt/target/

# rsync skipped these; recreate the mountpoints and permissions.
install -d -m 1777 /mnt/target/tmp
install -d -m 0755 /mnt/target/mnt /mnt/target/media /mnt/target/proc \
    /mnt/target/sys /mnt/target/run /mnt/target/dev

rm -f /mnt/target/etc/resolv.conf
printf 'nameserver 1.1.1.1\nnameserver 9.9.9.9\n' > /mnt/target/etc/resolv.conf

ROOT_UUID=$(blkid -s UUID -o value "$ROOT_PART")
ESP_UUID=$(blkid -s UUID -o value "$ESP_PART")
[ -n "$ROOT_UUID" ] && [ -n "$ESP_UUID" ] || die "could not read filesystem UUIDs"

echo "==> configuring the installed system"
FINALIZE=${GENTOO_FINALIZE:-/usr/local/lib/gentoo-installer/finalize-install.sh}
[ -f "$FINALIZE" ] || die "finalizer not found: $FINALIZE"
cp "$FINALIZE" /mnt/target/root/finalize-install.sh
chmod 0755 /mnt/target/root/finalize-install.sh
BRANDING=/usr/local/lib/gentoo-installer/install-branding.sh
if [ -f "$BRANDING" ]; then
    cp "$BRANDING" /mnt/target/root/install-branding.sh
    chmod 0755 /mnt/target/root/install-branding.sh
fi
mount --rbind /proc /mnt/target/proc
mount --rbind /sys  /mnt/target/sys
mount --rbind /dev  /mnt/target/dev
chroot /mnt/target /usr/bin/env -i HOME=/root TERM=linux \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    TARGET_DISK="$DISK" ROOT_UUID="$ROOT_UUID" ESP_UUID="$ESP_UUID" \
    INSTALL_USER="$INSTALL_USER" INSTALL_PASS="$INSTALL_PASS" \
    INSTALL_HOST="$INSTALL_HOST" INSTALL_FULL="$INSTALL_FULL" \
    /bin/bash /root/finalize-install.sh

echo "==> flushing"
cleanup
trap - ERR

echo "INSTALL_OK disk=$DISK root_uuid=$ROOT_UUID esp_uuid=$ESP_UUID user=$INSTALL_USER"
