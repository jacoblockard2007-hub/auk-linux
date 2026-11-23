# Third-party components

Auk itself is MIT-licensed (see [LICENSE](LICENSE)). It builds on other
projects; this file records what is vendored, what is downloaded at build time,
and where the licenses live.

## Vendored in this repository

### fastfetch 2.71.0

- Location: `installer/fastfetch/fastfetch`
- License: MIT (`installer/fastfetch/LICENSE`)
- Upstream: https://github.com/fastfetch-cli/fastfetch
- Source asset: `fastfetch-linux-amd64.tar.gz` from the 2.71.0 release
- SHA-256: `a26789e98c21c14e16e9e47e22ed6bd6be8dbe618098ee3d3c1db9a9641ce9b8`

The Auk logo (`installer/fastfetch/auk.txt`), wrapper and config are original
to this project and covered by the MIT license.

## Downloaded at build time, not stored in git

### Gentoo binary packages

Installed from Gentoo's official binhost
(`https://distfiles.gentoo.org/releases/amd64/binpackages/23.0/x86-64/`) into
built images. Each package keeps its own license, installed under
`/usr/share/licenses/<package>` inside the image. No Gentoo packages are
redistributed in this repository.

### Debian Wi-Fi firmware

`installer/install-wifi-firmware.py` downloads these Debian `trixie` packages
and extracts `/usr/lib/firmware` (plus each package's copyright file) into the
image:

- `firmware-iwlwifi`
- `firmware-atheros`
- `firmware-brcm80211`
- `firmware-libertas`
- `firmware-realtek`
- `firmware-misc-nonfree`
- `wireless-regdb`

The blobs are redistributable under the terms in each package; the copyright
files are installed at `/usr/share/doc/<package>/copyright` in the built image.
They are not committed here.

## External projects referenced but not included

KDE Plasma, systemd, GRUB, NetworkManager, Konsole and PCManFM-Qt are installed
from Gentoo packages and remain under their upstream licenses. KDE and the KDE
logo are trademarks of KDE e.V. Gentoo is a trademark of the Gentoo Foundation.

The desktop wallpaper visible in the screenshots is the upstream KDE Plasma
wallpaper, used under its own license.

Auk is an independent project based on Gentoo Linux; it is not affiliated with
or endorsed by the Gentoo Foundation or the KDE community.
