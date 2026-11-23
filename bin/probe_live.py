#!/usr/bin/env python3
"""Probe the live ISO for the tools needed to build the USB image."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from qdrive import VM, qemu_args  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")


def main():
    argv = qemu_args(
        WORK,
        kernel=os.path.join(WORK, "gentoo-kernel"),
        initrd=os.path.join(WORK, "gentoo.igz"),
        append=(
            "root=live:CDLABEL=Gentoo-amd64-20261115 rd.live.dir=/ "
            "rd.live.squashimg=image.squashfs cdroot console=ttyS0,115200"
        ),
        cdrom=os.path.join(ROOT, "gentoo-minimal.iso"),
        disks=[],
        monitor=None,
        memory="2048",
        cpus="2",
    )
    vm = VM(argv, os.path.join(LOGS, "liveprobe-console.log"))
    try:
        vm.wait(r"root@livecd ~ #", timeout=300)
        vm.sendline(
            "for t in sgdisk parted sfdisk rsync mkfs.ext4 mkfs.vfat mkfs.fat "
            "mkdosfs partprobe blkid grub-install chroot tar xz; do "
            "printf '%-12s %s\\n' $t \"$(command -v $t || echo MISSING)\"; done; "
            "echo __TOOLS__; ls /usr/lib/grub 2>/dev/null; echo __GRUB__"
        )
        vm.wait("__GRUB__", timeout=60)
        print(vm.tail(6000))
        return 0
    finally:
        vm.kill()


if __name__ == "__main__":
    sys.exit(main())
