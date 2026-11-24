# Measured performance

These are the numbers to compare the desktop options on the target hardware.
They are observations from `htop` on the real Chromebook, not automated
benchmarks.

## Test system

| Item | Value |
|---|---|
| CPU | 2 cores / 2 threads, x86-64 |
| RAM | 2 GB |
| Storage | 16 GB internal |
| OS | Auk Linux 0.1 (Gentoo-based), kernel 6.18.63-gentoo-dist-bin |
| Desktop | KDE Plasma 6.7.6 (Wayland) |
| Install source | prebuilt Gentoo binhost, 0 packages compiled |

## Idle baseline — KDE Plasma

Measured 2026-11-20 with `htop`, after the desktop had settled (2–3 minutes
after login) and with no applications open.

| Metric | Plasma 6.7.6 |
|---|---|
| CPU | **5–10%** |
| RAM | **~700 MB** |
| Applications open | none |

This is Plasma's baseline on 2 GB, not a leak or a background compile. It is
the number the i3 migration has to beat.

## i3 comparison

Pending. Planned lightweight stack:

- `x11-wm/i3`
- `x11-terms/xterm`
- `x11-misc/dmenu`
- `x11-misc/pcmanfm-qt` (already installed)

The measurement will use the same method: settle for 2–3 minutes, no windows
open, then record CPU and RAM from `htop`.
