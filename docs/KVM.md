# Running it in KVM

`bin/boot-kvm.sh` boots the finished USB image as a normal local VM. No root
privileges are needed; only `/dev/kvm` access.

```sh
bin/boot-kvm.sh                 # windowed VM, BIOS boot
bin/boot-kvm.sh --uefi          # windowed VM, UEFI (OVMF) boot
bin/boot-kvm.sh --console       # serial console in the terminal, no window
bin/boot-kvm.sh --snapshot      # discard all changes when the VM exits
```

| Option | Meaning |
|---|---|
| `--uefi` | boot through OVMF instead of SeaBIOS (tests the USB EFI path) |
| `--console` | `-display none -serial stdio`; log in as `root` / `gentoo` |
| `--snapshot` | QEMU `-snapshot`; the image file is never modified |
| `--vnc` | no local window; VNC on `127.0.0.1:5905` |

Environment variables: `MEM` (MiB, default 8192), `CPUS` (default 6), and
`IMAGE` (default `dist/auk-linux-usb.img`).

The VM uses virtio disk, virtio network (user-mode NAT), virtio-vga and a USB
tablet for an absolute pointer. Plasma runs on Wayland; graphics are software
rendered inside the guest, so a 6-vCPU VM is noticeably smoother than 2.

## Login

- Graphical: autologin as `demo` (`demo`).
- Serial: `root` / `gentoo`.
- The serial console is also enabled inside the guest as `ttyS0`.

## Headless verification

The automated check boots the image, waits for systemd, confirms SDDM and the
Plasma session, and captures a screenshot:

```sh
python3 bin/verify_image.py            # BIOS -> work/verify-bios.png
python3 bin/verify_image.py --uefi     # UEFI -> work/verify-uefi.png
```

Logs are written to `logs/verify-<tag>-console.log`.

## Troubleshooting

- **`KVM is not accessible`** — your user needs membership in the `kvm` group.
- **UEFI boot drops to the GRUB shell** — check that
  `/boot/efi/EFI/BOOT/grub.cfg` exists in the image and points at the root
  UUID. `grub-install --removable` must have run successfully.
- **No window appears** — the script falls back to VNC when neither `DISPLAY`
  nor `WAYLAND_DISPLAY` is set. Connect to `127.0.0.1:5905`.
- **Changes persist when you wanted a clean boot** — use `--snapshot`.
