#!/bin/bash
# Configure a freshly cloned root as a standalone installed system.
# Runs chrooted from install-to-disk.sh.
set -Eeuo pipefail
trap 'rc=$?; echo "FINALIZE_INSTALL_FAILED rc=$rc line=$LINENO"' ERR
export TERM=linux

TARGET_DISK="${TARGET_DISK:?}"
ROOT_UUID="${ROOT_UUID:?}"
ESP_UUID="${ESP_UUID:?}"
INSTALL_USER="${INSTALL_USER:?}"
INSTALL_PASS="${INSTALL_PASS:?}"
INSTALL_HOST="${INSTALL_HOST:?}"
INSTALL_FULL="${INSTALL_FULL:-}"

echo "===== FINALIZE INSTALL $(date -u) host=$INSTALL_HOST user=$INSTALL_USER ====="

echo "--- identity ---"
cat > /etc/fstab <<EOF
UUID=$ROOT_UUID  /          ext4  defaults,noatime  0 1
UUID=$ESP_UUID   /boot/efi  vfat  umask=0077        0 2
EOF
cat /etc/fstab

echo "$INSTALL_HOST" > /etc/hostname
sed -i '/^127\.0\.1\.1[[:space:]]/d' /etc/hosts
echo "127.0.1.1 $INSTALL_HOST" >> /etc/hosts

# New machine identity and fresh SSH host keys for every installation.
rm -f /etc/machine-id
systemd-machine-id-setup >/dev/null 2>&1 || true
rm -f /etc/ssh/ssh_host_*

echo "--- users ---"
if id "$INSTALL_USER" >/dev/null 2>&1; then
    usermod -aG wheel,audio,video,usb,plugdev,portage "$INSTALL_USER"
else
    useradd -m -G wheel,audio,video,usb,plugdev,portage -s /bin/bash "$INSTALL_USER"
fi
echo "$INSTALL_USER:$INSTALL_PASS" | chpasswd
# Prototype: root uses the same password so recovery via serial/su works.
# A product build should lock root and provide a graphical admin prompt.
echo "root:$INSTALL_PASS" | chpasswd
[ -n "$INSTALL_FULL" ] && usermod -c "$INSTALL_FULL" "$INSTALL_USER" || true

if [ "$INSTALL_USER" != "demo" ]; then
    userdel -r demo >/dev/null 2>&1 || true
    rm -rf /home/demo
fi

echo "--- desktop autologin ---"
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/10-autologin.conf <<EOF
[Autologin]
User=$INSTALL_USER
Session=plasma
Relogin=false
EOF

systemctl enable serial-getty@ttyS0.service >/dev/null 2>&1 || true
systemctl enable sddm.service >/dev/null 2>&1 || true
systemctl enable NetworkManager.service >/dev/null 2>&1 || true
systemctl set-default graphical.target >/dev/null 2>&1 || true

echo "--- remove live-installer assets from the installed system ---"
rm -f /usr/local/sbin/gentoo-install-to-disk \
      /usr/local/bin/gentoo-installer \
      /usr/share/applications/gentoo-installer.desktop \
      /etc/polkit-1/rules.d/49-gentoo-installer.rules \
      /usr/share/icons/hicolor/scalable/apps/gentoo-installer.svg \
      /root/finalize-install.sh \
      /root/install-branding.sh \
      /var/log/gentoo-install.log
rm -rf /usr/local/lib/gentoo-installer
rm -rf /home/*/Desktop/gentoo-installer.desktop /etc/xdg/autostart/gentoo-installer.desktop
rm -rf /var/log/journal/* /tmp/* /var/tmp/*
rm -f /home/*/.bash_history /root/.bash_history
rm -rf /home/*/.cache
rm -f /var/lib/systemd/random-seed

echo "--- kernel/initramfs ---"
KV=$(ls -1 /lib/modules | sort -V | tail -n1)
echo "kernel: $KV"
if ! ls /boot/initramfs-*.img >/dev/null 2>&1; then
    echo "no initramfs, generating a generic one"
    dracut --force --no-hostonly "/boot/initramfs-${KV}.img" "$KV"
fi

echo "--- GRUB: BIOS + UEFI ---"
grub-install --target=i386-pc --recheck --no-floppy "$TARGET_DISK"
grub-install --target=x86_64-efi --efi-directory=/boot/efi \
    --removable --no-nvram --recheck

# On a real UEFI machine, also create an NVRAM entry so the installed system
# appears in the firmware boot menu. The removable fallback above always exists.
if [ -d /sys/firmware/efi/efivars ] && command -v efibootmgr >/dev/null 2>&1; then
    echo "UEFI variables present; adding a boot entry"
    grub-install --target=x86_64-efi --efi-directory=/boot/efi \
        --bootloader-id=Auk --no-nvram --recheck || true
    efibootmgr -c -d "$TARGET_DISK" -p 2 -L "Auk Linux" \
        -l '\EFI\Auk\grubx64.efi' || true
fi

grub-mkconfig -o /boot/grub/grub.cfg
# Normalize "Auk Linux GNU/Linux" (grub-mkconfig's suffix) to "Auk Linux".
if [ -f /root/install-branding.sh ]; then
    sh /root/install-branding.sh / --grub-cfg /boot/grub/grub.cfg
fi
cat > /boot/efi/EFI/BOOT/grub.cfg <<EOF
search --no-floppy --fs-uuid --set=root $ROOT_UUID
configfile (\$root)/boot/grub/grub.cfg
EOF

echo "--- verify ---"
test -s /boot/efi/EFI/BOOT/BOOTX64.EFI
test -s /boot/grub/grub.cfg
grep -q "$ROOT_UUID" /boot/grub/grub.cfg
grep -E '^\s*(linux|initrd)' /boot/grub/grub.cfg | head -4

sync
echo "FINALIZE_INSTALL_OK host=$INSTALL_HOST user=$INSTALL_USER"
