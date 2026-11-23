#!/usr/bin/env python3
"""Boot the USB image, launch the GTK installer in the live Plasma session,
capture each page, and exercise the pkexec backend path with --dry-run."""

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from qdrive import VM, qemu_args, hmp  # noqa: E402
from phase2_boot import ppm_to_png  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")
GUI = "/usr/local/bin/gentoo-installer"
DEMO_ENV = (
    "HOME=/home/demo USER=demo LOGNAME=demo "
    "XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 "
    "XDG_SESSION_TYPE=wayland GDK_BACKEND=wayland "
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"
)


def shot(mon, tag):
    ppm = os.path.join(WORK, f"gui-{tag}.ppm")
    png = os.path.join(WORK, f"gui-{tag}.png")
    if os.path.exists(ppm):
        os.unlink(ppm)
    hmp(mon, f"screendump {ppm}")
    for _ in range(30):
        if os.path.exists(ppm) and os.path.getsize(ppm) > 0:
            break
        time.sleep(0.5)
    if os.path.exists(ppm):
        w, h = ppm_to_png(ppm, png)
        print(f"[+] {tag}: {w}x{h} -> {png}")
    else:
        print(f"[!] {tag}: no screenshot")


def login_root(vm, tries=4):
    """Log in on the serial console, tolerating repeated getty banners."""
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
        vm.wait(r"root@gentoo-proto ~ #", timeout=60, since=mark)
        return
    raise RuntimeError("could not log in on ttyS0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usb", default=os.path.join(ROOT, "dist", "gentoo-kde-usb.img"))
    ap.add_argument("--target", default=os.path.join(WORK, "gui-target.img"))
    ap.add_argument("--keep-target", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.target):
        subprocess.run(["qemu-img", "create", "-f", "raw", args.target, "20G"],
                       check=True, stdout=subprocess.DEVNULL)
        print(f"[*] created {args.target}")

    mon = os.path.join(WORK, "gui-smoke-mon.sock")
    argv = qemu_args(
        WORK, kernel=None, initrd=None, append=None,
        disks=[(args.usb, False), (args.target, False)],
        monitor=mon, memory="6144", cpus="4",
        extra=["-vga", "virtio"],
    )
    vm = VM(argv, os.path.join(LOGS, "gui-smoke.log"))
    try:
        print("[*] booting USB image")
        login_root(vm)
        vm.run("systemctl is-system-running --wait || true; "
               "loginctl list-sessions --no-legend; "
               "ls /run/user/1000/wayland-* 2>/dev/null", timeout=240)
        print("[*] waiting for Plasma")
        vm.run("sleep 35", timeout=90)

        for page in (0, 1, 2, 3):
            vm.run("pkill -f /usr/local/bin/gentoo-installer 2>/dev/null; sleep 1; "
                   f"( runuser -u demo -- env {DEMO_ENV} {GUI} --page {page} "
                   f">/tmp/gui-{page}.log 2>&1 & )", timeout=30)
            rc = vm.run(
                f"for i in $(seq 1 40); do "
                f"pgrep -f 'gentoo-installer --page {page}' >/dev/null && break; "
                f"sleep 0.5; done; sleep 5; "
                f"pgrep -f 'gentoo-installer --page {page}' >/dev/null",
                timeout=60)
            print(f"[*] page {page}: {'alive' if rc == 0 else 'DEAD'}")
            shot(mon, f"page{page}")
            vm.run(f"cat /tmp/gui-{page}.log 2>/dev/null", timeout=30)

        print("[*] dry-run through pkexec")
        vm.run("rm -f /var/log/gentoo-install.log; "
               "pkill -f /usr/local/bin/gentoo-installer 2>/dev/null; sleep 1; "
               f"( runuser -u demo -- env {DEMO_ENV} {GUI} "
               f"--test-fill --dry-run --autostart >/tmp/gui-dry.log 2>&1 & )",
               timeout=30)
        vm.run("for i in $(seq 1 120); do "
               "grep -qE 'DRY_RUN_OK|INSTALL_FAILED|ERROR:' "
               "/var/log/gentoo-install.log 2>/dev/null && break; sleep 1; done; "
               "true", timeout=150)
        time.sleep(3)
        shot(mon, "dryrun")
        vm.run("pkill -f /usr/local/bin/gentoo-installer 2>/dev/null; "
               "cat /tmp/gui-dry.log 2>/dev/null; "
               "cat /var/log/gentoo-install.log 2>/dev/null", timeout=30)
        print(vm.tail(6000))
        return 0
    finally:
        try:
            vm.sendline("sync; systemctl poweroff")
            vm.proc.wait(timeout=90)
        except Exception:
            pass
        vm.kill()


if __name__ == "__main__":
    sys.exit(main())
