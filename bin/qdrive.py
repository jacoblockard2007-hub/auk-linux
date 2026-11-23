"""Minimal expect-style driver for a QEMU guest on a serial console.

No pexpect dependency: spawns QEMU with stdio as the serial port, reads
output on a thread, and waits for regexes.
"""

import os
import re
import subprocess
import threading
import time


class VM:
    def __init__(self, argv, logpath):
        os.makedirs(os.path.dirname(logpath), exist_ok=True)
        self.logfile = open(logpath, "wb", buffering=0)
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            start_new_session=True,
        )
        self.buf = ""
        self.lock = threading.Lock()
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self.reader.start()

    def _read_loop(self):
        while True:
            chunk = self.proc.stdout.read(1)
            if not chunk:
                break
            self.logfile.write(chunk)
            with self.lock:
                self.buf += chunk.decode("utf-8", "replace")

    def tail(self, n=4000):
        with self.lock:
            return self.buf[-n:]

    def mark(self):
        """Return a buffer offset usable as wait(..., since=...)."""
        with self.lock:
            return len(self.buf)

    def wait(self, pattern, timeout=600, dump=6000, since=0):
        rx = re.compile(pattern)
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                match = rx.search(self.buf, since)
            if match:
                return match
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"QEMU exited while waiting for {pattern!r}\n{self.tail(dump)}"
                )
            time.sleep(0.25)
        raise TimeoutError(f"timeout after {timeout}s waiting for {pattern!r}\n{self.tail(dump)}")

    def send(self, text):
        self.proc.stdin.write(text.encode())
        self.proc.stdin.flush()

    def sendline(self, text):
        self.send(text + "\n")

    def run(self, command, timeout=600, echo_marker=True):
        """Run a command, return (rc, output) using a unique end marker."""
        token = "__QD_%d_%d__" % (os.getpid(), int(time.time() * 1000) % 1000000)
        self.sendline(command + f" ; echo {token}$?")
        match = self.wait(token + r"(\d+)", timeout=timeout)
        return int(match.group(1))

    def kill(self):
        if self.proc.poll() is None:
            import signal
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.proc.wait(timeout=10)
        self.logfile.flush()


def qemu_args(workdir, *, kernel, initrd, append, disks, cdrom=None, monitor=None,
              memory="6144", cpus="6", extra=()):
    argv = [
        "qemu-system-x86_64",
        "-accel", "kvm",
        "-cpu", "host",
        "-smp", str(cpus),
        "-m", str(memory),
        "-display", "none",
        "-monitor", f"unix:{monitor},server=on,wait=off" if monitor else "none",
        "-serial", "stdio",
        "-no-reboot",
    ]
    if kernel:
        argv += ["-kernel", kernel, "-initrd", initrd, "-append", append, "-boot", "d"]
    if cdrom:
        argv += ["-cdrom", cdrom]
    for path, readonly in disks:
        argv += ["-drive", f"file={path},format=raw,if=virtio" + (",readonly=on" if readonly else "")]
    argv += [
        "-netdev", "user,id=n0",
        "-device", "virtio-net-pci,netdev=n0",
    ]
    argv += list(extra)
    return argv


def hmp(monitor_path, command, timeout=5):
    import socket
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(monitor_path)
    try:
        sock.recv(4096)  # banner
        sock.sendall((command + "\n").encode())
        time.sleep(0.5)
        try:
            return sock.recv(65536).decode("utf-8", "replace")
        except socket.timeout:
            return ""
    finally:
        sock.close()
