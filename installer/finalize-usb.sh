#!/bin/bash
# Finalize a copied Gentoo+KDE root as a portable BIOS+UEFI USB system.
# Runs chrooted into the new root. TARGET_DISK/ROOT_UUID/ESP_UUID come from
# build-usb-image.sh.
set -Eeuo pipefail
trap 'rc=$?; echo "FINALIZE_FAILED rc=$rc line=$LINENO"' ERR
export TERM=linux

TARGET_DISK="${TARGET_DISK:-/dev/vdb}"
ROOT_UUID="${ROOT_UUID:?ROOT_UUID is required}"
ESP_UUID="${ESP_UUID:?ESP_UUID is required}"

echo "===== FINALIZE START $(date -u) disk=$TARGET_DISK ====="

echo "--- fstab by UUID ---"
cat > /etc/fstab <<EOF
UUID=$ROOT_UUID  /          ext4  defaults,noatime  0 1
UUID=$ESP_UUID   /boot/efi  vfat  umask=0077        0 2
EOF
cat /etc/fstab

echo "--- kernel command line and GRUB defaults ---"
CMDLINE='GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200"'
sed -i '/^GRUB_CMDLINE_LINUX=/d' /etc/default/grub
printf '%s\n' "$CMDLINE" >> /etc/default/grub
sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT=3/' /etc/default/grub
grep -q '^GRUB_TIMEOUT=' /etc/default/grub || echo 'GRUB_TIMEOUT=3' >> /etc/default/grub
# root= by UUID is stable across USB ports and disk ordering.
sed -i 's/^GRUB_DISABLE_LINUX_UUID=.*/GRUB_DISABLE_LINUX_UUID=false/' /etc/default/grub
grep -q '^GRUB_DISABLE_LINUX_UUID=' /etc/default/grub || \
    echo 'GRUB_DISABLE_LINUX_UUID=false' >> /etc/default/grub
grep -E '^GRUB_(CMDLINE_LINUX|TIMEOUT|DISABLE_LINUX_UUID)=' /etc/default/grub

echo "--- generic initramfs (must boot on real hardware, not just this VM) ---"
KV=$(ls -1 /lib/modules | sort -V | tail -1)
echo "kernel: $KV"
# The install-time initramfs was host-only (virtio). A USB image needs drivers
# for AHCI/NVMe/USB storage found on arbitrary machines, so build a generic one.
dracut --force --no-hostonly "/boot/initramfs-${KV}.img" "$KV"
ls -lh /boot

echo "--- GRUB: BIOS (i386-pc) ---"
grub-install --target=i386-pc --recheck --no-floppy "$TARGET_DISK"

echo "--- GRUB: UEFI removable fallback (EFI/BOOT/BOOTX64.EFI) ---"
# --removable writes the architecture-default path, which firmware boots even
# with no NVRAM entry. --no-nvram avoids touching the build machine's NVRAM.
grub-install --target=x86_64-efi --efi-directory=/boot/efi \
    --removable --no-nvram --recheck

echo "--- generate the real menu ---"
grub-mkconfig -o /boot/grub/grub.cfg

# UEFI GRUB starts with prefix /EFI/BOOT on the ESP. Point it at the menu that
# lives on the ext4 root, selected by filesystem UUID.
cat > /boot/efi/EFI/BOOT/grub.cfg <<EOF
search --no-floppy --fs-uuid --set=root $ROOT_UUID
configfile (\$root)/boot/grub/grub.cfg
EOF
cat /boot/efi/EFI/BOOT/grub.cfg

echo "--- verify boot artifacts ---"
test -s /boot/efi/EFI/BOOT/BOOTX64.EFI
test -s /boot/grub/grub.cfg
grep -q "$ROOT_UUID" /boot/grub/grub.cfg
echo "efi fallback: $(stat -c %s /boot/efi/EFI/BOOT/BOOTX64.EFI) bytes"
echo "grub menu entries:"
grep -E '^\s*(linux|initrd)' /boot/grub/grub.cfg | head -10

echo "FINALIZE_OK kernel=$KV"
