#!/usr/bin/env python3
"""Install Debian's redistributable Wi-Fi firmware into a root filesystem.

The Gentoo binhost has no sys-kernel/linux-firmware build, so Auk takes the
firmware from Debian's non-free-firmware archive instead. Only files under
/usr/lib/firmware (plus each package's copyright file) are extracted; nothing
is installed through dpkg and no Debian package database is created.

Usage:
    install-wifi-firmware.py /path/to/root
    install-wifi-firmware.py /path/to/root --packages firmware-iwlwifi
"""

import argparse
import hashlib
import io
import lzma
import os
import sys
import tarfile
import tempfile
import urllib.request

DEFAULT_MIRROR = "https://deb.debian.org/debian"
DEFAULT_SUITE = "trixie"
COMPONENTS = ("non-free-firmware", "main")
PACKAGES = (
    "firmware-iwlwifi",
    "firmware-atheros",
    "firmware-brcm80211",
    "firmware-libertas",
    "firmware-realtek",
    "firmware-misc-nonfree",
    "wireless-regdb",
)


def fetch(url):
    print(f"  fetch {url}", flush=True)
    with urllib.request.urlopen(url, timeout=300) as resp:
        return resp.read()


def load_index(mirror, suite, component):
    url = f"{mirror}/dists/{suite}/{component}/binary-amd64/Packages.xz"
    raw = fetch(url)
    data = lzma.decompress(raw).decode("utf-8", "replace")
    index = {}
    for stanza in data.split("\n\n"):
        fields = {}
        for line in stanza.splitlines():
            if line.startswith((" ", "\t")):
                continue
            key, _, value = line.partition(": ")
            if key:
                fields[key] = value
        if "Package" in fields:
            index[fields["Package"]] = fields
    return index


def read_ar(path):
    """Yield (name, bytes) for each member of a .deb (ar archive)."""
    with open(path, "rb") as fh:
        if fh.read(8) != b"!<arch>\n":
            raise ValueError(f"{path}: not an ar archive")
        while True:
            header = fh.read(60)
            if len(header) < 60:
                return
            name = header[0:16].decode("ascii", "replace").strip().rstrip("/")
            size = int(header[48:58].decode("ascii").strip() or 0)
            yield name, fh.read(size)
            if size % 2:
                fh.read(1)


def extract_data(payload, root, package):
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as tar:
        members = []
        for member in tar:
            name = member.name.lstrip("./")
            keep = name.startswith("usr/lib/firmware/") or (
                name.startswith(f"usr/share/doc/{package}/")
                and member.isfile()
            )
            if keep and (member.isfile() or member.issym()):
                members.append(member)
        for member in members:
            tar.extract(member, path=root, filter="data")
    return len(members)


def install(package, meta, mirror, root, tmpdir):
    filename = meta.get("Filename")
    if not filename:
        raise SystemExit(f"{package}: no Filename in Packages index")
    deb = os.path.join(tmpdir, os.path.basename(filename))
    data = fetch(f"{mirror}/{filename}")
    expected = meta.get("SHA256")
    actual = hashlib.sha256(data).hexdigest()
    if expected and actual != expected:
        raise SystemExit(f"{package}: SHA256 mismatch ({actual})")
    with open(deb, "wb") as fh:
        fh.write(data)
    installed = 0
    for name, payload in read_ar(deb):
        if name.startswith("data.tar"):
            installed = extract_data(payload, root, package)
            break
    os.unlink(deb)
    print(f"  {package} {meta.get('Version', '?')}: {installed} files", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--mirror", default=DEFAULT_MIRROR)
    ap.add_argument("--suite", default=DEFAULT_SUITE)
    ap.add_argument("--packages", nargs="*", default=list(PACKAGES))
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, "usr")):
        raise SystemExit(f"{root}: does not look like a root filesystem")

    print(f"installing Wi-Fi firmware from Debian {args.suite} into {root}")
    index = {}
    for component in COMPONENTS:
        index.update(load_index(args.mirror, args.suite, component))

    missing = [p for p in args.packages if p not in index]
    if missing:
        raise SystemExit(f"packages not found in {args.suite}: {', '.join(missing)}")

    with tempfile.TemporaryDirectory(prefix="auk-firmware-") as tmpdir:
        for package in args.packages:
            install(package, index[package], args.mirror, root, tmpdir)
    print("Wi-Fi firmware installed")


if __name__ == "__main__":
    sys.exit(main())
