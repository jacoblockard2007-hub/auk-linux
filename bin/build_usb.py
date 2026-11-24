#!/usr/bin/env python3
"""Build a bootable, persistent BIOS+UEFI USB image from the installed system.

Usage:
    bin/build_usb.py [--force] [--size 14G]

Creates dist/auk-linux-usb.img by booting the live environment, partitioning a
fresh GPT disk (BIOS boot + ESP + root), copying the installed root read-only,
and installing GRUB for both firmware types.
"""

import fcntl
import os
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(__file__))
from qdrive import VM, qemu_args  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")
DIST = os.path.join(ROOT, "dist")
IMAGE = os.path.join(DIST, "auk-linux-usb.img")

FLAGS = [a for a in sys.argv[1:] if a.startswith("--")]
FORCE = "--force" in FLAGS
SIZE = "14G"
for a in FLAGS:
    if a.startswith("--size="):
        SIZE = a.split("=", 1)[1]

SCRIPTS = ("live-stage1.sh", "chroot-stage2.sh", "build-usb-image.sh",
           "finalize-usb.sh", "install-to-disk.sh", "finalize-install.sh",
           "gui-installer.py", "gentoo-installer.desktop",
           "gentoo-files.desktop", "gentoo-installer.svg",
           "49-gentoo-installer.rules", "install-fastfetch.sh",
           "install-branding.sh", "install-grub-theme.sh",
           "grub-theme/theme.txt", "grub-theme/auk-logo.png",
           "fastfetch/fastfetch", "fastfetch/auk", "fastfetch/auk.txt",
           "fastfetch/config.jsonc", "fastfetch/LICENSE")


def build_installer_tar():
    path = os.path.join(WORK, "installer.tar")
    with tarfile.open(path, "w") as tar:
        for name in SCRIPTS:
            tar.add(os.path.join(ROOT, "installer", name), arcname=name)
    return path


def main():
    lock = open(os.path.join(WORK, ".build.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[!] another image build is already active; refusing to start")
        return 2

    if os.path.exists(IMAGE) and not FORCE:
        print(f"[!] {IMAGE} exists; pass --force to replace it")
        return 2

    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(IMAGE):
        os.unlink(IMAGE)
    subprocess.run(
        ["qemu-img", "create", "-f", "raw", IMAGE, SIZE],
        check=True, stdout=subprocess.DEVNULL,
    )
    print(f"[*] created sparse {SIZE} image: {IMAGE}")

    installer_tar = build_installer_tar()
    argv = qemu_args(
        WORK,
        kernel=os.path.join(WORK, "gentoo-kernel"),
        initrd=os.path.join(WORK, "gentoo.igz"),
        append=(
            "root=live:CDLABEL=Gentoo-amd64-20261115 rd.live.dir=/ "
            "rd.live.squashimg=image.squashfs cdroot console=ttyS0,115200"
        ),
        cdrom=os.path.join(ROOT, "gentoo-minimal.iso"),
        disks=[
            (os.path.join(WORK, "gentoo.img"), False),  # vda: source (replayed)
            (IMAGE, False),                             # vdb: target
            (installer_tar, True),                      # vdc: scripts
        ],
        monitor=os.path.join(WORK, "build-mon.sock"),
        memory="6144",
        cpus="6",
    )
    vm = VM(argv, os.path.join(LOGS, "build-usb-console.log"))
    try:
        vm.wait(r"root@livecd ~ #", timeout=300)
        print("[*] live console ready; partitioning and copying")
        rc = vm.run(
            "mkdir -p /tmp/inst && tar -xf /dev/vdc -C /tmp/inst && "
            "bash /tmp/inst/build-usb-image.sh",
            timeout=5400,
        )
        print(f"[*] build script exited rc={rc}")
        tail = vm.tail(500000)
        if rc != 0 or "USB_BUILD_OK" not in tail:
            print(tail[-12000:])
            return 1
        print("[+] USB_BUILD_OK")
        print("\n".join(tail.splitlines()[-25:]))
        return 0
    finally:
        try:
            vm.sendline("sync; poweroff -f")
            vm.proc.wait(timeout=30)
        except Exception:
            pass
        vm.kill()


if __name__ == "__main__":
    sys.exit(main())
