#!/usr/bin/env python3
"""Boot the installed disk and collect facts needed to build a USB image."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from qdrive import VM, qemu_args  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")

COMMANDS = [
    ("df -h / /boot; echo __A__", "du -xhd1 / 2>/dev/null; echo __B__"),
    ("du -xhd1 /var /usr /boot /root 2>/dev/null; echo __C__",),
    ("ls -la /boot; echo __D__", "ls -la /usr/lib/systemd/boot/efi/ 2>/dev/null; echo __E__"),
    ("ls /usr/lib/grub/ 2>/dev/null; echo __F__", "cat /etc/fstab; echo __G__"),
    ("cat /etc/default/grub; echo __H__", "command -v sgdisk parted sfdisk rsync mkfs.fat mkfs.vfat grub-install dracut; echo __I__"),
    ("findmnt -no SOURCE /; blkid; echo __J__",),
]


def main():
    argv = qemu_args(
        WORK,
        kernel=None, initrd=None, append=None,
        disks=[(os.path.join(WORK, "gentoo.img"), False)],
        monitor=None,
        memory="4096",
        cpus="4",
    )
    vm = VM(argv, os.path.join(LOGS, "probe-console.log"))
    try:
        vm.wait(r" login:", timeout=300)
        vm.sendline("root")
        vm.wait(r"Password:", timeout=30)
        vm.sendline("gentoo")
        vm.wait(r"root@\S+ ~ #", timeout=60)
        vm.sendline("systemctl is-system-running --wait || true; echo __READY__")
        vm.wait("__READY__", timeout=240)
        for group in COMMANDS:
            for cmd in group:
                vm.sendline(cmd)
        vm.wait("__J__", timeout=120)
        print(vm.tail(30000))
        vm.sendline("sync; poweroff -f")
        vm.proc.wait(timeout=30)
        return 0
    finally:
        vm.kill()


if __name__ == "__main__":
    sys.exit(main())
