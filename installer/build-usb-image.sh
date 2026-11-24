#!/bin/bash
# Build a bootable USB image from an installed Gentoo+KDE disk.
#
# Runs as root in the Gentoo live environment. Disks attached by the harness:
#   /dev/vda  existing installed system (mounted read-only, never modified)
#   /dev/vdb  blank target image (GPT: BIOS boot + ESP + root)
#   /dev/vdc  tar archive containing the installer scripts
#
# The result boots on both BIOS and UEFI machines and is persistent (it is a
# normal installed system, not a squashfs live image).
set -Eeuo pipefail
trap 'rc=$?; echo "USB_BUILD_FAILED rc=$rc line=$LINENO"' ERR
export TERM=linux

OLD_DISK="${OLD_DISK:-/dev/vda}"
OLD_PART="${OLD_DISK}1"
NEW_DISK="${NEW_DISK:-/dev/vdb}"
NEW_ESP="${NEW_DISK}2"
NEW_ROOT="${NEW_DISK}3"

echo "===== USB IMAGE BUILD START $(date -u) ====="
lsblk -o NAME,SIZE,TYPE,FSTYPE,MODEL

[ -b "$OLD_PART" ] || { echo "missing $OLD_PART"; exit 1; }
[ -b "$NEW_DISK" ] || { echo "missing $NEW_DISK"; exit 1; }

cleanup() {
    set +e
    umount -R /mnt/new 2>/dev/null
    umount -R /mnt/old 2>/dev/null
}
trap cleanup EXIT

echo "--- partition $NEW_DISK (GPT, hybrid BIOS+UEFI) ---"
sgdisk --zap-all "$NEW_DISK"
sgdisk --clear \
    --new=1:2048:+1M --typecode=1:ef02 --change-name=1:"BIOS boot" \
    --new=2:0:+512M  --typecode=2:ef00 --change-name=2:"EFI System" \
    --new=3:0:0      --typecode=3:8300 --change-name=3:"Auk root" \
    "$NEW_DISK"
sgdisk --verify "$NEW_DISK"
partprobe "$NEW_DISK" || true
udevadm settle || true
sleep 1

echo "--- filesystems ---"
mkfs.vfat -F32 -n AUKEFI "$NEW_ESP"
# -m 1 keeps the ext4 reserved-block overhead low, appropriate for a USB stick.
mkfs.ext4 -F -m 1 -L auk-root "$NEW_ROOT"

echo "--- mount source and target ---"
mkdir -p /mnt/old /mnt/new
# The previous VM shutdown can leave the ext4 journal dirty; a read-only mount
# refuses to replay it. Mount rw once to recover, then remount read-only so the
# copy cannot modify the source system.
mount "$OLD_PART" /mnt/old
mount -o remount,ro /mnt/old
mount "$NEW_ROOT" /mnt/new
mkdir -p /mnt/new/boot/efi
mount "$NEW_ESP" /mnt/new/boot/efi

echo "--- copy root filesystem (pseudo-filesystems excluded) ---"
rsync -aHAX --numeric-ids --stats \
    --exclude=/proc --exclude=/sys --exclude=/dev --exclude=/run \
    --exclude=/tmp --exclude=/mnt --exclude=/media --exclude=/lost+found \
    /mnt/old/ /mnt/new/

# rsync excluded these; recreate the empty mountpoints the system expects.
install -d -m 1777 /mnt/new/tmp
install -d -m 0755 /mnt/new/mnt /mnt/new/media /mnt/new/proc /mnt/new/sys \
    /mnt/new/run /mnt/new/dev

echo "--- install the graphical installer into the image ---"
install -D -m 0755 /tmp/inst/install-to-disk.sh \
    /mnt/new/usr/local/sbin/gentoo-install-to-disk
install -D -m 0755 /tmp/inst/finalize-install.sh \
    /mnt/new/usr/local/lib/gentoo-installer/finalize-install.sh
install -D -m 0755 /tmp/inst/gui-installer.py \
    /mnt/new/usr/local/bin/gentoo-installer
install -D -m 0644 /tmp/inst/gentoo-installer.desktop \
    /mnt/new/usr/share/applications/gentoo-installer.desktop
install -D -m 0644 /tmp/inst/49-gentoo-installer.rules \
    /mnt/new/etc/polkit-1/rules.d/49-gentoo-installer.rules
install -D -m 0644 /tmp/inst/gentoo-installer.svg \
    /mnt/new/usr/share/icons/hicolor/scalable/apps/gentoo-installer.svg
install -D -m 0755 /tmp/inst/install-branding.sh \
    /mnt/new/usr/local/lib/gentoo-installer/install-branding.sh

# Vendored fastfetch + Snares penguin logo and the system-wide config.
sh /tmp/inst/install-fastfetch.sh /mnt/new

# Brand the copied system as Auk Linux: os-release, console banner, hostname,
# GRUB distributor. Runs before finalize-usb.sh regenerates the GRUB menu.
sh /tmp/inst/install-branding.sh /mnt/new --hostname auk

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /mnt/new/usr/share/icons/hicolor || true
fi
install -d -m 0755 -o 1000 -g 1000 /mnt/new/home/demo/Desktop
install -m 0755 -o 1000 -g 1000 /tmp/inst/gentoo-installer.desktop \
    /mnt/new/home/demo/Desktop/gentoo-installer.desktop
install -m 0755 -o 1000 -g 1000 /tmp/inst/gentoo-files.desktop \
    /mnt/new/home/demo/Desktop/gentoo-files.desktop
install -D -m 0755 /tmp/inst/gentoo-files.desktop \
    /mnt/new/etc/skel/Desktop/gentoo-files.desktop

ROOT_UUID=$(blkid -s UUID -o value "$NEW_ROOT")
ESP_UUID=$(blkid -s UUID -o value "$NEW_ESP")
[ -n "$ROOT_UUID" ] && [ -n "$ESP_UUID" ] || { echo "no UUIDs"; exit 1; }
echo "root uuid: $ROOT_UUID"
echo "esp  uuid: $ESP_UUID"

# Replace the inherited resolv.conf (possibly a dangling symlink) with a
# plain file so DNS works before NetworkManager starts.
rm -f /mnt/new/etc/resolv.conf
cp -L /etc/resolv.conf /mnt/new/etc/resolv.conf

echo "--- chroot: initramfs, fstab, GRUB (BIOS + UEFI) ---"
mount --rbind /proc /mnt/new/proc
mount --rbind /sys  /mnt/new/sys
mount --rbind /dev  /mnt/new/dev
install -m 0755 /tmp/inst/finalize-usb.sh /mnt/new/root/finalize-usb.sh
install -m 0755 /tmp/inst/install-branding.sh /mnt/new/root/install-branding.sh
chroot /mnt/new /usr/bin/env -i HOME=/root TERM=linux \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    TARGET_DISK="$NEW_DISK" ROOT_UUID="$ROOT_UUID" ESP_UUID="$ESP_UUID" \
    /bin/bash /root/finalize-usb.sh
rm -f /mnt/new/root/finalize-usb.sh /mnt/new/root/install-branding.sh

echo "--- flush and unmount ---"
sync
umount -R /mnt/new
umount -R /mnt/old
trap - EXIT

echo "--- final layout ---"
sgdisk --print "$NEW_DISK"
echo "USB_BUILD_OK root_uuid=$ROOT_UUID esp_uuid=$ESP_UUID"
