#!/usr/bin/env python3
"""Phase 1: boot the Gentoo live environment and run the prototype installer.

Usage:
    phase1_install.py [stage3.tar.xz] [--dry-run] [--reuse]

--dry-run  resolve the KDE dependency graph and report binary/compile counts
--reuse    keep the existing filesystem on the target disk (faster iterations)
"""

import fcntl
import os
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from qdrive import VM, qemu_args  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
FLAGS = [a for a in sys.argv[1:] if a.startswith("--")]
DRY_RUN = "--dry-run" in FLAGS
REUSE = "--reuse" in FLAGS
STAGE3 = args[0] if args else os.path.join(ROOT, "stage3-desktop.tar.xz")

ENV = f"PROTO_DRY_RUN={1 if DRY_RUN else 0} PROTO_REUSE={1 if REUSE else 0}"


def build_installer_tar():
    path = os.path.join(WORK, "installer.tar")
    with tarfile.open(path, "w") as tar:
        for name in ("live-stage1.sh", "chroot-stage2.sh",
                     "install-branding.sh", "install-wifi-firmware.py"):
            tar.add(os.path.join(ROOT, "installer", name), arcname=name)
    return path


def main():
    lock = open(os.path.join(WORK, ".phase1.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[!] another phase1 run is already active; refusing to start")
        return 2
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
            (os.path.join(WORK, "gentoo.img"), False),
            (STAGE3, True),
            (installer_tar, True),
        ],
        monitor=os.path.join(WORK, "mon.sock"),
        memory="8192",
        cpus="6",
    )
    logname = "phase1-dryrun.log" if DRY_RUN else "phase1-console.log"
    vm = VM(argv, os.path.join(LOGS, logname))
    marker = "DRYRUN_OK" if DRY_RUN else "STAGE1_OK"
    try:
        print(f"[*] argv={sys.argv[1:]!r} dry_run={DRY_RUN} reuse={REUSE}")
        print(f"[*] guest env: {ENV}")
        vm.wait(r"root@livecd ~ #", timeout=300)
        print("[*] live console ready")
        rc = vm.run(
            "mkdir -p /tmp/inst && tar -xf /dev/vdc -C /tmp/inst && "
            f"{ENV} bash /tmp/inst/live-stage1.sh",
            timeout=3600 if DRY_RUN else 10800,
        )
        print(f"[*] installer exited rc={rc}")
        tail = vm.tail(400000)
        if rc != 0 or marker not in tail:
            print(tail[-8000:])
            return 1
        print(f"[+] {marker}")
        print(vm.tail(4000))
        return 0
    finally:
        # flush the guest filesystem before tearing the VM down
        try:
            vm.sendline("sync; poweroff -f")
            vm.proc.wait(timeout=20)
        except Exception:
            pass
        vm.kill()


if __name__ == "__main__":
    sys.exit(main())
