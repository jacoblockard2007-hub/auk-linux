# Auk Linux 0.1 (prototype)

A bootable, persistent KDE Plasma USB system built entirely from Gentoo binary
packages. Nothing is compiled on the user's machine, and the live desktop
includes a graphical installer that copies the running system onto an internal
disk.

## Download

The image is not stored in git. From a clone of
[`jacoblockard2007-hub/auk-linux`](https://github.com/jacoblockard2007-hub/auk-linux):

```sh
bin/download-image.sh
```

The script downloads the split `.xz` parts below, verifies every SHA-256, joins
them and decompresses `dist/auk-linux-usb.img` (14 GiB). Then write a USB stick
of at least 16 GB:

```sh
sudo bin/write-usb.sh /dev/sdX dist/auk-linux-usb.img
```

## Assets

| Asset | Purpose |
|---|---|
| `SHA256SUMS` | Checksums for the raw image, the `.xz`, and every part |
| `auk-linux-usb.img.xz.part00` … | Split compressed image, each part under 2 GiB |
| `README.txt` | What is on the image, credentials and recovery notes |

## Identity

- OS: **Auk Linux** 0.1, based on Gentoo Linux
- Hostname on the live image: `auk` (`demo@auk` in fastfetch)
- Installer: **Install Auk Linux**
- GRUB menu: **Auk Linux**
- Fastfetch logo: the Auk Snares penguin, available with the `auk` command

## Credentials

| Account | Password | Notes |
|---|---|---|
| `demo` | `demo` | Plasma autologin; no sudo, use `su -` |
| `root` | `gentoo` | Text console / recovery |

The credentials are public and the root password is weak. This is a prototype;
do not put personal data on it or expose it to an untrusted network.

## Verified

- BIOS and UEFI boot from the same image
- KDE Plasma 6.7.6 on Wayland, Konsole, PCManFM-Qt
- GTK 4 installer and pkexec dry-run
- Debian non-free Wi-Fi firmware for common Intel/Atheros/Broadcom/Marvell/
  MediaTek/Realtek cards
- `fastfetch` via `auk` with the Snares penguin

## Limits

- Whole-disk install only; no dual-boot and no disk encryption
- Secure Boot must be disabled (the bootloader is unsigned)
- x86-64 only
- Prototype, not a supported distribution

Auk is an independent project based on Gentoo Linux and is not affiliated with
or endorsed by the Gentoo Foundation. Auk is MIT-licensed; third-party
components keep their own licenses. See `LICENSE` and `THIRD_PARTY.md`.
