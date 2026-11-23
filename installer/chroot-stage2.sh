#!/bin/bash
# Prototype installer, stage 2. Runs chrooted into the new system as root.
#
# Goal: a complete KDE Plasma desktop with zero source compilation.
# Every package comes from Gentoo's multi-variant official binary host.
set -Eeuo pipefail
trap 'rc=$?; echo "STAGE2_FAILED rc=$rc line=$LINENO"' ERR

export TERM=linux
TARGET_DISK="${TARGET_DISK:-/dev/vda}"
PROTO_DRY_RUN="${PROTO_DRY_RUN:-0}"
source /etc/profile
SECONDS=0

BINHOST="https://distfiles.gentoo.org/releases/amd64/binpackages/23.0/x86-64/"
JOBS="--jobs=6 --load-average=8"
# binpkg-respect-use=y is essential: the binhost carries several build
# variants per package (systemd/elogind, ABI, feature flags) and Portage
# must be allowed to pick the one matching this system's USE.
# --autounmask-continue lets Portage accept the USE changes that KDE's
# metapackage requires (e.g. kwin[lock]) without a human running etc-update.
# The flags it picks are the ones the binhost was built with, so the
# matching binary variant gets selected.
# --autounmask-backtrack=y is what the resolver asks for explicitly when it
# gives up; without it a single unsatisfiable variant aborts the whole graph.
EMERGE_OPTS="--getbinpkg --binpkg-respect-use=y --autounmask=y --autounmask-use=y --autounmask-write=y --autounmask-continue=y --autounmask-backtrack=y $JOBS"
# --usepkgonly makes "never compile" a hard guarantee: a missing binary
# aborts the install instead of silently starting a source build.
EMERGE_BIN="emerge $EMERGE_OPTS --usepkgonly"
EMERGE_ANY="emerge $EMERGE_OPTS"

echo "===== STAGE2 START $(date -u) dry_run=$PROTO_DRY_RUN ====="
# readlink fails while make.profile still dangles (tree not synced yet); with
# `set -E` that failure would trip the ERR trap from inside $( ) even though
# the echo itself succeeds, producing a bogus STAGE2_FAILED line.
PROFILE_TARGET=$(readlink -f /etc/portage/make.profile 2>/dev/null || true)
echo "profile: ${PROFILE_TARGET:-unresolved (tree not synced yet)}"
# a VM killed mid-write can leave NUL bytes in a text file; sanitize
tr -d '\000' < /etc/portage/make.conf > /tmp/make.conf.clean
cat /tmp/make.conf.clean > /etc/portage/make.conf
rm -f /tmp/make.conf.clean
grep -E '^(CHOST|CFLAGS|USE|ABI_X86)=' /etc/portage/make.conf || true

echo "--- portage tree ---"
if [ ! -d /var/db/repos/gentoo/metadata ]; then
    echo "no ebuild tree in stage3, fetching snapshot"
    mkdir -p /var/db/repos/gentoo
    # emerge-webrsync can exit non-zero on the initial repos.conf check
    emerge-webrsync || true
fi
if [ ! -d /var/db/repos/gentoo/metadata ]; then
    echo "ERROR: no ebuild tree available"
    exit 1
fi

echo "--- select the profile the binhost was built from ---"
PLASMA_PROFILE="default/linux/amd64/23.0/desktop/plasma/systemd"
PROFILE_DIR="/var/db/repos/gentoo/profiles/$PLASMA_PROFILE"
if [ -d "$PROFILE_DIR" ]; then
    ln -sfn "../../var/db/repos/gentoo/profiles/$PLASMA_PROFILE" /etc/portage/make.profile
else
    echo "WARN: $PROFILE_DIR missing, adding KDE flags manually"
    mkdir -p /etc/portage/package.use
    printf 'kde-plasma/kwin lock\nkde-plasma/kwin-x11 lock\n' > /etc/portage/package.use/kde
fi
echo "profile now: $(readlink -f /etc/portage/make.profile)"
# powerdevil accepts tuned | power-profiles-daemon | tlp. Only the latter
# two are relevant here, and tuned is not in the binhost, so prefer ppd.
mkdir -p /etc/portage/package.mask /etc/portage/package.use
echo "sys-apps/tuned" > /etc/portage/package.mask/zz-proto

# drkonqi needs psutil; the binhost build carries python3_13+python3_14,
# so enable the extra target to match it instead of compiling psutil.
echo "dev-python/psutil python_targets_python3_13" >> /etc/portage/package.use/zz-proto

# The binhost lags the ebuild tree by a few days: installkernel 70-r1 has no
# binary, 68-r1 does. Pin to the version the binhost actually carries.
echo ">sys-kernel/installkernel-68-r1" >> /etc/portage/package.mask/zz-proto

echo "available plasma profiles:"
ls -d /var/db/repos/gentoo/profiles/default/linux/amd64/23.0/desktop/plasma* 2>/dev/null || true

echo "--- configure the binary host ---"
mkdir -p /etc/portage/binrepos.conf
cat > /etc/portage/binrepos.conf/gentoo.conf <<EOF
[gentoo-binhost]
priority = 9999
sync-uri = $BINHOST
EOF
# drop any previous prototype block so re-runs stay idempotent
sed -i '/# ---- prototype: binary packages only ----/,$d' /etc/portage/make.conf
if ! grep -q 'getbinpkg' /etc/portage/make.conf; then
    cat >> /etc/portage/make.conf <<'EOF'

# ---- prototype: binary packages only ----
FEATURES="${FEATURES} getbinpkg"
EMERGE_DEFAULT_OPTS="${EMERGE_DEFAULT_OPTS} --getbinpkg --binpkg-respect-use=y --jobs=6 --load-average=8"
# 32-bit multilib ABIs are only partially covered by the official binhost:
# sys-libs/glibc ships a 32-bit build but x11-libs/libX11 does not, so the
# resolver picks a 32-bit libXext and then cannot satisfy it. Disabling the
# x86 ABI keeps every package on the fully-built 64-bit variant set.
ABI_X86="64"
USE="${USE} -abi_x86_32"
EOF
fi
sync
tail -6 /etc/portage/make.conf

sync
echo "--- import binhost signing key ---"
getuto || echo "WARN: getuto failed, continuing"

echo "--- resolve plasma (informational; USE changes listed) ---"
emerge -pv --getbinpkg --binpkg-respect-use=y --autounmask=y --autounmask-use=y \
    --autounmask-backtrack=y kde-plasma/plasma-meta > /tmp/plan.txt 2>&1 || true
head -40 /tmp/plan.txt
grep -A1000 'USE changes are necessary' /tmp/plan.txt | head -60 || true
TOTAL=$(grep -cE '^\[' /tmp/plan.txt || true)
BINARY=$(grep -c '\[binary' /tmp/plan.txt || true)
EBUILD=$(grep -c '\[ebuild' /tmp/plan.txt || true)
echo "PLAN total=$TOTAL binary=$BINARY ebuild=$EBUILD"
echo "$TOTAL $BINARY $EBUILD" > /root/plan-counts.txt
grep -E '^\[' /tmp/plan.txt | tail -20
if [ "$EBUILD" -gt 0 ]; then
    echo "--- packages that would compile (first 40) ---"
    grep '\[ebuild' /tmp/plan.txt | head -40
fi

if [ "$PROTO_DRY_RUN" = "1" ]; then
    if [ "$EBUILD" -gt 0 ]; then
        echo "DRYRUN_FAIL binary=$BINARY ebuild=$EBUILD (zero-compile contract broken)"
        exit 2
    fi
    echo "DRYRUN_OK binary=$BINARY ebuild=$EBUILD"
    exit 0
fi
sync

echo "--- install KDE Plasma from binary packages ---"
( time $EMERGE_BIN kde-plasma/plasma-meta ) 2>&1 | tee /root/emerge-kde.log
grep -c '^>>> Compiling source' /root/emerge-kde.log > /root/compiled-count.txt || true
echo "COMPILED_PACKAGES=$(cat /root/compiled-count.txt)"

echo "--- desktop extras: Konsole and PCManFM-Qt ---"
$EMERGE_BIN kde-apps/konsole x11-misc/pcmanfm-qt

echo "--- Wi-Fi firmware (Debian non-free-firmware) ---"
# The Gentoo binhost has no linux-firmware build. Pull the redistributable
# firmware blobs from Debian instead; the script keeps their copyright files.
if [ "${PROTO_SKIP_FIRMWARE:-0}" != "1" ]; then
    python3 /root/install-wifi-firmware.py / || echo "WARN: Wi-Fi firmware install failed"
fi

echo "--- prebuilt kernel + bootloader ---"
# The binhost carries no kernels. sys-kernel/gentoo-kernel-bin installs a
# prebuilt image (no compilation), but its "initramfs" USE flag pulls in
# sys-kernel/installkernel[dracut], which the desktop profile masks. So we
# disable that flag and generate the initramfs ourselves further down.
mkdir -p /etc/portage/package.use
echo 'sys-kernel/gentoo-kernel-bin -initramfs' > /etc/portage/package.use/proto-kernel
# gentoo-kernel-bin is not in the binhost (it is already a prebuilt-kernel
# package), but installing it runs no compiler either.
$EMERGE_ANY sys-kernel/gentoo-kernel-bin sys-boot/grub
KV=$(ls -1 /lib/modules | sort -V | tail -1)
echo "kernel version in image: $KV"
if ! ls /boot/initramfs-* >/dev/null 2>&1; then
    echo "no initramfs found, generating with dracut"
    command -v dracut >/dev/null || $EMERGE_BIN sys-kernel/dracut
    dracut --force "/boot/initramfs-${KV}.img" "$KV"
fi
ls -lh /boot

echo "--- base system configuration ---"
cat > /etc/fstab <<'EOF'
/dev/vda1  /  ext4  defaults,noatime  0 1
EOF
echo gentoo-proto > /etc/hostname
grep -q gentoo-proto /etc/hosts || echo '127.0.1.1 gentoo-proto' >> /etc/hosts

echo 'root:gentoo' | chpasswd
id demo >/dev/null 2>&1 || useradd -m -G wheel,audio,video,usb,plugdev,portage -s /bin/bash demo
echo 'demo:demo' | chpasswd

if [ -f /etc/default/grub ]; then
    sed -i 's|^GRUB_CMDLINE_LINUX=.*|GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200"|' /etc/default/grub
    grep -q '^GRUB_CMDLINE_LINUX=' /etc/default/grub || echo 'GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200"' >> /etc/default/grub
    grep -q '^GRUB_TIMEOUT=' /etc/default/grub || echo 'GRUB_TIMEOUT=3' >> /etc/default/grub
fi

echo "--- bootloader ---"
grub-install --target=i386-pc "$TARGET_DISK"
grub-mkconfig -o /boot/grub/grub.cfg

echo "--- enable services ---"
systemctl enable serial-getty@ttyS0.service || true
systemctl enable sddm.service || true
systemctl enable NetworkManager.service || true
systemctl set-default graphical.target || true

echo "--- desktop autologin for the demo user ---"
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/10-autologin.conf <<'EOF'
[Autologin]
User=demo
Session=plasma
Relogin=false
EOF

echo "--- report ---"
{
    echo "profile: $(readlink -f /etc/portage/make.profile)"
    echo "plan_total: $(cut -d' ' -f1 /root/plan-counts.txt)"
    echo "plan_binary: $(cut -d' ' -f2 /root/plan-counts.txt)"
    echo "plan_ebuild: $(cut -d' ' -f3 /root/plan-counts.txt)"
    echo "compiled_packages: $(cat /root/compiled-count.txt)"
    echo "elapsed_seconds: $SECONDS"
    echo "kernel: $(ls -1 /lib/modules)"
} | tee /root/proto-report.txt

echo "STAGE2_OK $(date -u)"
