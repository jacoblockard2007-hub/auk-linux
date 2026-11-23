# Auk fastfetch

`fastfetch` is **not in Gentoo's official binhost** at the time of writing, so
compiling it through Portage would break the project's zero-compile rule.

This directory vendors the official upstream Linux x86-64 release instead:

- Version: **2.71.0**
- Source: https://github.com/fastfetch-cli/fastfetch/releases/tag/2.71.0
- Asset: `fastfetch-linux-amd64.tar.gz`
- License: MIT (`LICENSE`)
- SHA-256 of `fastfetch` binary: `a26789e98c21c14e16e9e47e22ed6bd6be8dbe618098ee3d3c1db9a9641ce9b8`

The binary is dynamically linked only against `libc` and `libm`; it needs no
Vulkan, X11 or image libraries. It is installed as `/usr/local/bin/fastfetch`,
outside Portage, so package operations never try to rebuild it.

`auk.txt` is the Snares penguin logo in fastfetch's `$1`–`$9` colour format.
`config.jsonc` installs to `/etc/fastfetch/config.jsonc`. The `auk` wrapper lets
users run `auk` instead of `fastfetch`.
