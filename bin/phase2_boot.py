#!/usr/bin/env python3
"""Phase 2: boot the installed system, verify the desktop came up, screenshot it."""

import os
import struct
import sys
import time
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from qdrive import VM, qemu_args, hmp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "work")
LOGS = os.path.join(ROOT, "logs")
MON = os.path.join(WORK, "mon2.sock")
SHOT_PPM = os.path.join(WORK, "plasma.ppm")
SHOT_PNG = os.path.join(WORK, "plasma.png")


def ppm_to_png(src, dst):
    with open(src, "rb") as f:
        data = f.read()
    # P6\n<w> <h>\n<max>\n
    parts, idx = [], 0
    while len(parts) < 4:
        while data[idx:idx + 1].isspace():
            idx += 1
        if data[idx:idx + 1] == b"#":
            while data[idx:idx + 1] != b"\n":
                idx += 1
            continue
        start = idx
        while not data[idx:idx + 1].isspace():
            idx += 1
        parts.append(data[start:idx])
    idx += 1
    magic, w, h, _maxval = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
    assert magic == b"P6", magic
    pixels = data[idx:idx + w * h * 3]

    raw = b"".join(b"\x00" + pixels[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload +
                struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    with open(dst, "wb") as f:
        f.write(png)
    return w, h


def main():
    argv = qemu_args(
        WORK,
        kernel=None, initrd=None, append=None,
        disks=[(os.path.join(WORK, "gentoo.img"), False)],
        monitor=MON,
        memory="8192",
        cpus="6",
        extra=["-vga", "virtio", "-vnc", "127.0.0.1:5"],
    )
    vm = VM(argv, os.path.join(LOGS, "phase2-console.log"))
    ok = True
    try:
        print("[*] booting installed system from disk")
        vm.wait(r" login:", timeout=300)
        print("[*] getty up, logging in")
        vm.sendline("root")
        vm.wait(r"Password:", timeout=30)
        vm.sendline("gentoo")
        # login(1) flushes pending tty input when it execs the shell, so a
        # command sent immediately after the password is silently discarded.
        # Wait for the prompt before sending anything.
        vm.wait(r"root@\S+ ~ #", timeout=60)
        print("[*] root shell up")

        rc = vm.run("systemctl is-system-running --wait || true", timeout=240)
        vm.sendline("systemctl is-system-running; systemctl --failed --no-pager; "
                    "systemctl is-active sddm; ls /dev/dri 2>/dev/null; "
                    "cat /root/proto-report.txt; echo __INFO_DONE__")
        vm.wait("__INFO_DONE__", timeout=120)

        print("[*] waiting for Plasma to finish starting")
        vm.run("sleep 45", timeout=120)
        vm.sendline("cat /root/proto-report.txt > /dev/ttyS0; systemctl is-active sddm; "
                    "loginctl list-sessions --no-legend; "
                    "ps -o comm= -u demo 2>/dev/null | sort -u | head -20; "
                    "echo __STATE_DONE__")
        vm.wait("__STATE_DONE__", timeout=60)

        print("[*] screendump")
        hmp(MON, f"screendump {SHOT_PPM}")
        # the monitor answers before QEMU has necessarily written the file
        for _ in range(20):
            if os.path.exists(SHOT_PPM):
                break
            time.sleep(0.5)
        if os.path.exists(SHOT_PPM):
            w, h = ppm_to_png(SHOT_PPM, SHOT_PNG)
            print(f"[+] screenshot {w}x{h} -> {SHOT_PNG}")
        else:
            print("[!] screendump produced no file")
            ok = False

        vm.sendline("systemctl status sddm --no-pager | tail -15; "
                    "journalctl -b -u sddm --no-pager | tail -25; echo __LOG_DONE__")
        vm.wait("__LOG_DONE__", timeout=60)
        print(vm.tail(3000))
        return 0 if ok else 1
    finally:
        vm.kill()


if __name__ == "__main__":
    sys.exit(main())
