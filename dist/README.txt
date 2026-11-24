Auk - bootable USB image (prototype)
====================================

Auk is a beginner-friendly, zero-compilation Linux desktop built from Gentoo
binary packages. This image is a persistent installed system, not a read-only
live CD.

Files:
  auk-linux-usb.img      14 GiB raw image
  SHA256SUMS              checksums for the image and split parts

The release stores the image as compressed, split .xz parts. From a git clone,
fetch and verify them with:

  bin/download-image.sh

Verify before writing:

  sha256sum -c SHA256SUMS

Write to a USB stick of at least 16 GB (all data is erased):

  sudo dd if=auk-linux-usb.img of=/dev/sdX bs=4M conv=fsync status=progress
  sync

Or use any image writer (balenaEtcher, GNOME Disks, Rufus in DD mode).

Boot:
  - Select the USB device in the firmware boot menu (F12/F11/F9/Esc).
  - Both UEFI and legacy/BIOS boot work.
  - Disable Secure Boot: the bootloader is unsigned.

Login:
  demo / demo      graphical session (logs in automatically)
  root / gentoo    text console, or `su -` in the Terminal

Terminal:
  - "Terminal" icon on the desktop (Konsole); also in the application menu.
  - "Files" icon on the desktop (PCManFM-Qt); also in the application menu.
  - Run `auk` (or `fastfetch`) for the Snares penguin system summary.
  - Ctrl+Alt+F3 gives a text login on tty3; Ctrl+Alt+F1 returns to Plasma.
  - There is no sudo on this image: use `su -` with the root password gentoo.

Network:
  - NetworkManager and wpa_supplicant are enabled at boot.
  - Wireless firmware for Intel, Atheros, Broadcom, Marvell, MediaTek and
    Realtek cards is included.
  - In Terminal, run `nmtui` and pick "Activate a connection", or use
    `nmcli device wifi connect "SSID" password "PASSWORD"`.
  - If it asks for authentication, enter the root password gentoo (or run
    `su -` first and start `nmtui` as root).
  - Wired Ethernet and USB tethering work automatically.
  - A few Chromebooks need board-specific Broadcom NVRAM files; if no Wi-Fi
    device appears, check `rfkill list` and `dmesg | grep -i firmware`.

Install onto the computer's internal disk:
  - On the live desktop, double-click "Install Auk Linux".
  - Choose the target disk, computer name, and user account.
  - The install is offline: it copies this system; nothing is compiled.
  - The selected disk is completely erased. 16 GB minimum.
  - If that disk has an active swap partition, open Terminal, run `su -`
    (password gentoo), then `swapoff -a` before starting the installer.
  - The result boots with BIOS or UEFI and keeps the account you chose.

Notes:
  - This is a persistent installed system: changes survive reboot.
  - Prototype only. No disk encryption or dual-boot.
