#!/usr/bin/env bash
# Boot the finished image in a local KVM virtual machine.
#
#   bin/boot-kvm.sh                  # windowed, BIOS
#   bin/boot-kvm.sh --uefi           # windowed, UEFI firmware
#   bin/boot-kvm.sh --console        # serial console in this terminal
#   bin/boot-kvm.sh --snapshot       # throw away changes on exit
#
# Environment: MEM (default 8192), CPUS (default 6), IMAGE (override path).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=${IMAGE:-$ROOT/dist/gentoo-kde-usb.img}
MEM=${MEM:-8192}
CPUS=${CPUS:-6}
UEFI=0
CONSOLE=0
SNAPSHOT=0
VNC=0

for arg in "$@"; do
    case "$arg" in
        --uefi) UEFI=1 ;;
        --console) CONSOLE=1 ;;
        --snapshot) SNAPSHOT=1 ;;
        --vnc) VNC=1 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

die() { echo "error: $*" >&2; exit 1; }

[ -f "$IMAGE" ] || die "image not found: $IMAGE (run bin/build_usb.py first)"
[ -r /dev/kvm ] && [ -w /dev/kvm ] || die "KVM is not accessible (/dev/kvm)"
command -v qemu-system-x86_64 >/dev/null || die "qemu-system-x86_64 not installed"

ARGS=(
    -accel kvm -cpu host -smp "$CPUS" -m "$MEM"
    -name "Gentoo KDE"
    -drive "file=$IMAGE,format=raw,if=virtio,cache=writeback"
    -nic user,model=virtio-net-pci
    -boot c
)
[ "$SNAPSHOT" = 1 ] && ARGS+=(-snapshot)

if [ "$UEFI" = 1 ]; then
    CODE=${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}
    VARS_SRC=${OVMF_VARS:-/usr/share/OVMF/OVMF_VARS_4M.fd}
    [ -f "$CODE" ] && [ -f "$VARS_SRC" ] || die "OVMF firmware not found"
    VARS="$ROOT/work/OVMF_VARS.gentoo.fd"
    cp -f "$VARS_SRC" "$VARS"
    ARGS+=(
        -machine q35
        -drive "if=pflash,format=raw,unit=0,readonly=on,file=$CODE"
        -drive "if=pflash,format=raw,unit=1,file=$VARS"
    )
fi

if [ "$CONSOLE" = 1 ]; then
    ARGS+=(-display none -serial stdio -monitor none)
elif [ "$VNC" = 1 ] || { [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; }; then
    ARGS+=(-display none -serial file:"$ROOT/logs/kvm-console.log"
           -vnc 127.0.0.1:5)
    echo "[*] no local display detected; VNC on 127.0.0.1:5905"
    echo "[*] serial log: $ROOT/logs/kvm-console.log"
else
    # virtio-vga + usb-tablet gives a usable pointer inside Wayland sessions.
    ARGS+=(-vga virtio -usb -device usb-tablet
           -serial file:"$ROOT/logs/kvm-console.log")
fi

echo "[*] image:  $IMAGE"
echo "[*] boot:   $([ "$UEFI" = 1 ] && echo UEFI || echo BIOS)"
echo "[*] memory: ${MEM} MiB, ${CPUS} vCPU"
echo "[*] login:  demo / demo   (root / gentoo on the serial console)"
exec qemu-system-x86_64 "${ARGS[@]}"
