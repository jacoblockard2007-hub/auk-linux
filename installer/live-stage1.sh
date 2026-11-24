#!/bin/bash
# Prototype installer, stage 1. Runs as root in the Gentoo live environment.
#
# Disks attached by the harness:
#   /dev/vda  target disk (blank, or reusable with PROTO_REUSE=1)
#   /dev/vdb  stage3 tarball (raw)
#   /dev/vdc  tar archive containing this script and chroot-stage2.sh
#
# Environment:
#   PROTO_DRY_RUN=1  resolve only, do not install
#   PROTO_REUSE=1    keep an existing filesystem/stage3 on /dev/vda
#
# This is the piece a Calamares "Gentoo" module would eventually call.
set -Eeuo pipefail
trap 'rc=$?; echo "STAGE1_FAILED rc=$rc line=$LINENO"' ERR

export TERM=linux
DISK=/dev/vda
: "${PROTO_DRY_RUN:=0}"
: "${PROTO_REUSE:=0}"

echo "===== STAGE1 START $(date -u) dry_run=$PROTO_DRY_RUN reuse=$PROTO_REUSE ====="

echo "--- network ---"
ip -4 -o addr show | awk '{print $2, $4}'
ip route || true
for _ in 1 2 3; do
    ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 && { echo "net: reachable"; break; }
    sleep 2
done

echo "--- inventory ---"
lsblk -o NAME,SIZE,TYPE,FSTYPE
for tool in fdisk mkfs.ext4 tar xz chroot; do
    printf '%-10s %s\n' "$tool" "$(command -v "$tool" || echo MISSING)"
done

if [ "$PROTO_REUSE" = 1 ] && [ "$(blkid -o value -s TYPE "${DISK}1" 2>/dev/null)" = "ext4" ]; then
    echo "--- reusing existing filesystem on ${DISK}1 ---"
    mount "${DISK}1" /mnt/gentoo
else
    echo "--- partition + format $DISK ---"
    fdisk "$DISK" <<'FDISK'
o
n
p
1
2048

w
FDISK
    udevadm settle || true
    mkfs.ext4 -F -q "${DISK}1"
    mount "${DISK}1" /mnt/gentoo

    echo "--- extract stage3 ---"
    cp /dev/vdb /tmp/stage3.tar.xz
    tar -xJpf /tmp/stage3.tar.xz -C /mnt/gentoo
    rm -f /tmp/stage3.tar.xz
    echo "top-level: $(ls -A /mnt/gentoo | tr '\n' ' ')"
fi

echo "--- prepare chroot ---"
cp -L /etc/resolv.conf /mnt/gentoo/etc/resolv.conf
mkdir -p /tmp/inst
tar -xf /dev/vdc -C /tmp/inst
install -m 0755 /tmp/inst/chroot-stage2.sh /mnt/gentoo/root/chroot-stage2.sh
install -m 0755 /tmp/inst/install-branding.sh /mnt/gentoo/root/install-branding.sh
install -m 0755 /tmp/inst/install-wifi-firmware.py /mnt/gentoo/root/install-wifi-firmware.py
mountpoint -q /mnt/gentoo/proc || mount -t proc proc /mnt/gentoo/proc
mountpoint -q /mnt/gentoo/sys || mount --rbind /sys /mnt/gentoo/sys
mountpoint -q /mnt/gentoo/dev || mount --rbind /dev /mnt/gentoo/dev

echo "--- chroot: package install + system config ---"
chroot /mnt/gentoo /usr/bin/env -i HOME=/root TERM=linux \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    TARGET_DISK="$DISK" PROTO_DRY_RUN="$PROTO_DRY_RUN" \
    PROTO_SKIP_FIRMWARE="${PROTO_SKIP_FIRMWARE:-0}" \
    /bin/bash /root/chroot-stage2.sh

echo "--- cleanup ---"
sync
umount -R /mnt/gentoo || true
echo "STAGE1_OK $(date -u)"
