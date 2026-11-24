#!/usr/bin/env python3
"""Boot the finished USB image (BIOS or UEFI) and verify the desktop stack.

Usage:
    bin/verify_image.py [--uefi] [--image PATH] [--tag NAME]

Logs to logs/verify-<tag>-console.log and writes a screenshot to
work/verify-<tag>.png.
"""

import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from qdrive import VM, qemu_args, hmp  # noqa: E402
from phase2_boot import ppm_to_png  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")

OVMF_CODE = "/usr/share/OVMF/OVMF_CODE_4M.fd"
OVMF_VARS = "/usr/share/OVMF/OVMF_VARS_4M.fd"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uefi", action="store_true")
    ap.add_argument("--image", default=os.path.join(ROOT, "dist", "auk-linux-usb.img"))
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    tag = args.tag or ("uefi" if args.uefi else "bios")
    mon = os.path.join(WORK, f"verify-{tag}-mon.sock")
    shot_ppm = os.path.join(WORK, f"verify-{tag}.ppm")
    shot_png = os.path.join(WORK, f"verify-{tag}.png")

    extra = ["-vga", "virtio"]
    if args.uefi:
        if not (os.path.isfile(OVMF_CODE) and os.path.isfile(OVMF_VARS)):
            print("[!] OVMF firmware not found")
            return 2
        vars_copy = os.path.join(WORK, f"OVMF_VARS-{tag}.fd")
        shutil.copyfile(OVMF_VARS, vars_copy)
        extra += [
            "-machine", "q35",
            "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={OVMF_CODE}",
            "-drive", f"if=pflash,format=raw,unit=1,file={vars_copy}",
        ]

    argv = qemu_args(
        WORK,
        kernel=None, initrd=None, append=None,
        disks=[(args.image, False)],
        monitor=mon,
        memory="6144",
        cpus="4",
        extra=extra,
    )
    vm = VM(argv, os.path.join(LOGS, f"verify-{tag}-console.log"))
    ok = True
    try:
        print(f"[*] booting {args.image} ({tag})")
        vm.wait(r" login:", timeout=420)
        print("[*] login prompt reached")
        vm.sendline("root")
        vm.wait(r"Password:", timeout=30)
        vm.sendline("gentoo")
        vm.wait(r"root@\S+ ~ #", timeout=90)

        vm.run("systemctl is-system-running --wait || true", timeout=300)
        vm.sendline(
            "echo __STATE__; "
            "systemctl is-system-running; "
            "systemctl --failed --no-pager; "
            "systemctl is-active sddm; "
            "ls /dev/dri 2>/dev/null; "
            "cat /proc/cmdline; "
            "findmnt -no SOURCE,FSTYPE /; "
            "echo __STATE_DONE__"
        )
        vm.wait("__STATE_DONE__", timeout=120)

        print("[*] waiting for Plasma")
        vm.run("sleep 40", timeout=90)
        vm.sendline(
            "loginctl list-sessions --no-legend; "
            "ps -o comm= -u demo 2>/dev/null | sort -u | head -15; "
            "echo __PLASMA_DONE__"
        )
        vm.wait("__PLASMA_DONE__", timeout=90)

        if os.path.exists(shot_ppm):
            os.unlink(shot_ppm)
        hmp(mon, f"screendump {shot_ppm}")
        for _ in range(30):
            if os.path.exists(shot_ppm) and os.path.getsize(shot_ppm) > 0:
                break
            time.sleep(0.5)
        if os.path.exists(shot_ppm):
            w, h = ppm_to_png(shot_ppm, shot_png)
            print(f"[+] screenshot {w}x{h} -> {shot_png}")
        else:
            print("[!] no screenshot")
            ok = False

        print(vm.tail(8000))
        return 0 if ok else 1
    finally:
        try:
            vm.sendline("sync; poweroff -f")
            vm.proc.wait(timeout=30)
        except Exception:
            pass
        vm.kill()


if __name__ == "__main__":
    sys.exit(main())
