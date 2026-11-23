#!/usr/bin/env python3
"""End-to-end test of the graphical installer backend.

Phase A: boot the USB image, attach a blank target disk, run the installer
         backend as root over the serial console.
Phase B: boot the installed target alone under BIOS and verify the account.
Phase C: boot the installed target alone under UEFI/OVMF and screenshot it.

Usage:
    bin/test_installer.py [--usb IMAGE] [--target IMAGE] [--size 20G]
                          [--skip-install] [--skip-uefi] [--force]
"""

import argparse
import fcntl
import os
import shutil
import subprocess
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

USER = "testuser"
PASS = "testpass"
HOST = "testbox"


def poweroff(vm):
    try:
        vm.sendline("sync; systemctl poweroff")
        vm.proc.wait(timeout=90)
    except Exception:
        pass
    vm.kill()


def login(vm, user=USER, password=PASS, timeout=420, tries=4):
    for _ in range(tries):
        mark = vm.mark()
        try:
            vm.wait(rf"{HOST} login:", timeout=timeout, since=mark)
        except TimeoutError:
            continue
        time.sleep(1)
        vm.sendline(user)
        mark = vm.mark()
        try:
            vm.wait(r"Password:", timeout=15, since=mark)
        except TimeoutError:
            continue
        vm.sendline(password)
        mark = vm.mark()
        try:
            vm.wait(rf"{user}@{HOST} ~ \$", timeout=60, since=mark)
            return
        except TimeoutError:
            continue
    raise RuntimeError(f"could not log in as {user} on {HOST}")


def login_live(vm, tries=4):
    for _ in range(tries):
        mark = vm.mark()
        try:
            vm.wait(r"gentoo-proto login:", timeout=180, since=mark)
        except TimeoutError:
            continue
        time.sleep(1)
        vm.sendline("root")
        mark = vm.mark()
        try:
            vm.wait(r"Password:", timeout=15, since=mark)
        except TimeoutError:
            continue
        vm.sendline("gentoo")
        mark = vm.mark()
        try:
            vm.wait(r"root@gentoo-proto ~ #", timeout=60, since=mark)
            return
        except TimeoutError:
            continue
    raise RuntimeError("could not log in on the live image")


def check_system(vm, tag):
    vm.sendline(
        "echo __STATE__; "
        "systemctl is-system-running; "
        "systemctl --failed --no-pager; "
        "systemctl is-active sddm; "
        "hostname; "
        "findmnt -no SOURCE,FSTYPE /; "
        "findmnt -no SOURCE,FSTYPE /boot/efi 2>/dev/null; "
        "loginctl list-sessions --no-legend | head -3; "
        "ls /dev/dri 2>/dev/null; "
        "if ! test -e /usr/local/sbin/gentoo-install-to-disk && "
        "! test -e /etc/polkit-1/rules.d/49-gentoo-installer.rules; "
        "then echo INSTALLER_ASSETS_REMOVED; else echo INSTALLER_ASSETS_PRESENT; fi; "
        "echo __STATE_DONE__"
    )
    vm.wait("__STATE_DONE__", timeout=120)
    print(f"----- {tag} state -----")
    print(vm.tail(2500))


def screenshot(vm, mon, tag):
    ppm = os.path.join(WORK, f"installer-{tag}.ppm")
    png = os.path.join(WORK, f"installer-{tag}.png")
    if os.path.exists(ppm):
        os.unlink(ppm)
    hmp(mon, f"screendump {ppm}")
    for _ in range(30):
        if os.path.exists(ppm) and os.path.getsize(ppm) > 0:
            break
        time.sleep(0.5)
    if os.path.exists(ppm):
        w, h = ppm_to_png(ppm, png)
        print(f"[+] screenshot {w}x{h} -> {png}")
    return os.path.exists(png)


def phase_install(usb, target):
    mon = os.path.join(WORK, "test-installer-mon.sock")
    argv = qemu_args(
        WORK, kernel=None, initrd=None, append=None,
        disks=[(usb, False), (target, False)],
        monitor=mon, memory="6144", cpus="6",
    )
    vm = VM(argv, os.path.join(LOGS, "test-installer-install.log"))
    try:
        print("[*] booting USB image with blank target disk")
        login_live(vm)
        rc = vm.run(
            "test -x /usr/local/sbin/gentoo-install-to-disk && "
            "test -f /usr/local/lib/gentoo-installer/finalize-install.sh && "
            "test -x /usr/local/bin/gentoo-installer && "
            "command -v mkfs.vfat && echo ASSETS_OK",
            timeout=60,
        )
        if rc != 0:
            print("[!] installer assets missing on the image")
            print(vm.tail(3000))
            return 1
        print("[*] assets present; running backend install (10-20 min)")
        rc = vm.run(
            "/usr/local/sbin/gentoo-install-to-disk "
            f"--disk /dev/vdb --username {USER} --password {PASS} "
            f"--hostname {HOST} --fullname 'Test User' --yes",
            timeout=3600,
        )
        tail = vm.tail(600000)
        if rc != 0 or "INSTALL_OK" not in tail:
            print(f"[!] install failed rc={rc}")
            print(tail[-8000:])
            return 1
        print("[+] INSTALL_OK")
        print("\n".join(tail.splitlines()[-30:]))
        return 0
    finally:
        poweroff(vm)


def phase_boot(target, uefi=False):
    tag = "uefi" if uefi else "bios"
    mon = os.path.join(WORK, f"test-installer-{tag}-mon.sock")
    extra = ["-vga", "virtio"]
    if uefi:
        if not (os.path.isfile(OVMF_CODE) and os.path.isfile(OVMF_VARS)):
            print("[!] OVMF firmware not found")
            return 1
        vars_copy = os.path.join(WORK, f"OVMF_VARS-installer-{tag}.fd")
        shutil.copyfile(OVMF_VARS, vars_copy)
        extra += [
            "-machine", "q35",
            "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={OVMF_CODE}",
            "-drive", f"if=pflash,format=raw,unit=1,file={vars_copy}",
        ]
    argv = qemu_args(
        WORK, kernel=None, initrd=None, append=None,
        disks=[(target, False)], monitor=mon,
        memory="6144", cpus="4", extra=extra,
    )
    vm = VM(argv, os.path.join(LOGS, f"test-installer-{tag}.log"))
    try:
        print(f"[*] booting installed target ({tag})")
        login(vm)
        vm.run("systemctl is-system-running --wait || true", timeout=300)
        check_system(vm, tag)
        vm.sendline("sleep 35; echo __SLEEP_DONE__")
        vm.wait("__SLEEP_DONE__", timeout=60)
        screenshot(vm, mon, tag)
        return 0
    except Exception as exc:
        print(f"[!] {tag} boot failed: {exc}")
        print(vm.tail(6000))
        return 1
    finally:
        poweroff(vm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usb", default=os.path.join(ROOT, "dist", "gentoo-kde-usb.img"))
    ap.add_argument("--target", default=os.path.join(WORK, "test-install-target.img"))
    ap.add_argument("--size", default="20G")
    ap.add_argument("--skip-install", action="store_true")
    ap.add_argument("--skip-uefi", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    lock = open(os.path.join(WORK, ".test-installer.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("[!] another installer test is running")
        return 2

    if not args.skip_install:
        if os.path.exists(args.target):
            if not args.force:
                print(f"[!] {args.target} exists; pass --force to recreate")
                return 2
            os.unlink(args.target)
        subprocess.run(["qemu-img", "create", "-f", "raw", args.target, args.size],
                       check=True, stdout=subprocess.DEVNULL)
        print(f"[*] created {args.size} target: {args.target}")
        if phase_install(args.usb, args.target) != 0:
            return 1

    rc = 0
    if phase_boot(args.target, uefi=False) != 0:
        rc = 1
    if not args.skip_uefi and phase_boot(args.target, uefi=True) != 0:
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
