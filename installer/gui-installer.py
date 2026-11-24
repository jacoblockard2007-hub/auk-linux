#!/usr/bin/env python3
"""Graphical "Install to internal disk" wizard for the Auk Linux prototype.

Runs as the live desktop user. The destructive work is delegated to
/usr/local/sbin/gentoo-install-to-disk through pkexec. The backend clones the
running USB system onto the chosen disk, so the install is offline and compiles
nothing.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

BACKEND = os.environ.get("GENTOO_INSTALL_BACKEND",
                         "/usr/local/sbin/gentoo-install-to-disk")
APP_ID = "org.auk.Installer"

PAGES = ["welcome", "disk", "user", "summary", "progress"]


def run_quiet(cmd):
    return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)


def list_disks():
    """Whole disks that are safe targets, with the live disk excluded."""
    live_src = run_quiet(["findmnt", "-no", "SOURCE", "/"]).strip()
    try:
        live_disk = run_quiet(["lsblk", "-no", "PKNAME", live_src]).strip().splitlines()[0]
    except Exception:
        live_disk = os.path.basename(live_src)
    data = json.loads(run_quiet(
        ["lsblk", "-J", "-o",
         "NAME,PATH,SIZE,TYPE,MODEL,TRAN,RM,MOUNTPOINTS"]))["blockdevices"]
    disks = []
    for dev in data:
        if dev.get("type") != "disk" or dev.get("name") == live_disk:
            continue
        name = dev.get("name", "")
        # Floppy, optical and virtual pseudo-disks are never install targets.
        if re.match(r"^(fd|sr|loop|ram|zram|nbd)", name):
            continue
        size = dev.get("size") or ""
        if not size or size in ("0B", "0"):
            continue
        mounts = []
        for child in dev.get("children") or []:
            mounts += [m for m in (child.get("mountpoints") or []) if m]
        mounts += [m for m in (dev.get("mountpoints") or []) if m]
        disks.append({
            "path": dev.get("path") or "/dev/" + dev["name"],
            "name": dev.get("name", "?"),
            "size": dev.get("size") or "?",
            "model": (dev.get("model") or "disk").strip(),
            "tran": (dev.get("tran") or "").strip(),
            "removable": bool(dev.get("rm")),
            "mounts": mounts,
        })
    return disks


class Installer(Gtk.Application):
    def __init__(self, opts):
        super().__init__(application_id=APP_ID)
        self.opts = opts
        self.disks = []
        self.page = 0
        self.proc = None
        self.install_state = None
        self.log_text = ""
        self.window = None
        self.config_path = None

    # ---------- UI construction ----------

    def do_activate(self):
        self.disks = list_disks()
        self.window = Gtk.ApplicationWindow(application=self,
                                            title="Install Auk Linux")
        self.window.set_default_size(960, 680)

        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label="Install Auk Linux"))
        self.window.set_titlebar(header)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.set_child(outer)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_vexpand(True)
        outer.append(self.stack)

        self.stack.add_named(self.page_welcome(), PAGES[0])
        self.stack.add_named(self.page_disk(), PAGES[1])
        self.stack.add_named(self.page_user(), PAGES[2])
        self.stack.add_named(self.page_summary(), PAGES[3])
        self.stack.add_named(self.page_progress(), PAGES[4])

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_margin_top(12)
        buttons.set_margin_bottom(12)
        buttons.set_margin_start(16)
        buttons.set_margin_end(16)
        self.status = Gtk.Label(label="", xalign=0)
        self.status.add_css_class("dim-label")
        self.status.set_hexpand(True)
        buttons.append(self.status)

        self.back_btn = Gtk.Button(label="Back")
        self.back_btn.connect("clicked", self.on_back)
        buttons.append(self.back_btn)

        self.next_btn = Gtk.Button(label="Next")
        self.next_btn.add_css_class("suggested-action")
        self.next_btn.connect("clicked", self.on_next)
        buttons.append(self.next_btn)
        outer.append(buttons)

        self.show_page(0)
        self.window.present()

        if self.opts.test_fill:
            GLib.idle_add(self.apply_test_fill)
        if self.opts.page is not None:
            GLib.idle_add(lambda: self.show_page(self.opts.page) or False)
        if self.opts.autostart:
            GLib.idle_add(lambda: self.show_page(3) or False)
            GLib.timeout_add(700, self.autostart_install)

    def page_welcome(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_top(48)
        box.set_margin_bottom(32)
        box.set_margin_start(64)
        box.set_margin_end(64)

        icon_path = "/usr/share/icons/hicolor/scalable/apps/gentoo-installer.svg"
        if os.path.exists(icon_path):
            icon = Gtk.Image.new_from_file(icon_path)
        else:
            icon = Gtk.Image.new_from_icon_name("gentoo-installer")
        icon.set_pixel_size(96)
        box.append(icon)

        title = Gtk.Label(label="Install Auk Linux on this computer")
        title.add_css_class("title-1")
        box.append(title)

        body = Gtk.Label(xalign=0)
        body.set_wrap(True)
        body.set_markup(
            "This wizard copies the complete Auk Linux system from this USB "
            "stick onto an internal disk.\n\n"
            "• No downloading and no compiling — the install is offline.\n"
            "• The selected disk will be <b>completely erased</b>.\n"
            "• The computer can boot the result with BIOS or UEFI.\n\n"
            "You will choose the target disk, the computer name and your user "
            "account on the next pages.")
        box.append(body)
        return box

    def page_disk(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(36)
        box.set_margin_start(56)
        box.set_margin_end(56)

        title = Gtk.Label(label="Where should it be installed?", xalign=0)
        title.add_css_class("title-2")
        box.append(title)

        info = Gtk.Label(xalign=0)
        info.set_wrap(True)
        info.add_css_class("dim-label")
        info.set_text("The USB stick you booted from is not listed and cannot "
                      "be selected. Disks with mounted partitions are also "
                      "excluded.")
        box.append(info)

        self.disk_labels = []
        for d in self.disks:
            if d["mounts"]:
                continue
            kind = "removable" if d["removable"] else "internal"
            label = f"{d['path']}  —  {d['model']}  —  {d['size']} ({kind})"
            self.disk_labels.append((label, d))

        self.disk_detail = Gtk.Label(xalign=0)
        self.disk_detail.set_wrap(True)
        if self.disk_labels:
            dropdown = Gtk.DropDown.new_from_strings([x[0] for x in self.disk_labels])
            dropdown.connect("notify::selected", self.on_disk_changed)
            self.disk_dropdown = dropdown
            box.append(dropdown)
            box.append(self.disk_detail)
            self.on_disk_changed(dropdown, None)
        else:
            self.disk_dropdown = None
            warn = Gtk.Label(xalign=0)
            warn.set_markup(
                "<b>No installable disk found.</b>\n\n"
                "Attach or insert a target disk, then reopen this installer. "
                "Internal disks with mounted partitions are intentionally "
                "excluded.")
            warn.set_wrap(True)
            box.append(warn)

        box.append(Gtk.Separator())
        note = Gtk.Label(xalign=0)
        note.set_wrap(True)
        note.add_css_class("dim-label")
        note.set_text("A 16 GB or larger disk is recommended. Everything on it "
                      "will be destroyed.")
        box.append(note)
        return box

    def page_user(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(36)
        box.set_margin_start(56)
        box.set_margin_end(56)

        title = Gtk.Label(label="Your account", xalign=0)
        title.add_css_class("title-2")
        box.append(title)

        grid = Gtk.Grid(column_spacing=16, row_spacing=12)
        box.append(grid)

        def row(r, text, widget):
            label = Gtk.Label(label=text, xalign=0)
            grid.attach(label, 0, r, 1, 1)
            grid.attach(widget, 1, r, 1, 1)

        self.host_entry = Gtk.Entry()
        self.host_entry.set_text("auk-pc")
        self.host_entry.set_hexpand(True)
        row(0, "Computer name", self.host_entry)

        self.user_entry = Gtk.Entry()
        self.user_entry.set_text("demo")
        self.user_entry.set_hexpand(True)
        row(1, "Username", self.user_entry)

        self.full_entry = Gtk.Entry()
        self.full_entry.set_placeholder_text("Optional")
        self.full_entry.set_hexpand(True)
        row(2, "Full name", self.full_entry)

        self.pass_entry = Gtk.PasswordEntry()
        self.pass_entry.set_show_peek_icon(True)
        self.pass_entry.set_hexpand(True)
        row(3, "Password", self.pass_entry)

        self.pass2_entry = Gtk.PasswordEntry()
        self.pass2_entry.set_show_peek_icon(True)
        self.pass2_entry.set_hexpand(True)
        row(4, "Repeat password", self.pass2_entry)

        self.user_error = Gtk.Label(xalign=0)
        self.user_error.add_css_class("error")
        self.user_error.set_wrap(True)
        box.append(self.user_error)

        note = Gtk.Label(xalign=0)
        note.set_wrap(True)
        note.add_css_class("dim-label")
        note.set_text("The account is added to the wheel, audio, video, usb "
                      "and plugdev groups. The root password is set to the "
                      "same value for this prototype.")
        box.append(note)
        return box

    def page_summary(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(36)
        box.set_margin_start(56)
        box.set_margin_end(56)

        title = Gtk.Label(label="Ready to install", xalign=0)
        title.add_css_class("title-2")
        box.append(title)

        self.summary = Gtk.Label(xalign=0)
        self.summary.set_wrap(True)
        self.summary.set_selectable(True)
        box.append(self.summary)

        self.confirm_check = Gtk.CheckButton(
            label="I understand that the selected disk will be completely erased")
        box.append(self.confirm_check)
        self.confirm_check.connect("toggled", lambda *_: self.update_next())
        return box

    def page_progress(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(24)
        box.set_margin_bottom(8)
        box.set_margin_start(24)
        box.set_margin_end(24)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.spinner = Gtk.Spinner()
        top.append(self.spinner)
        self.progress_label = Gtk.Label(label="Installing…", xalign=0)
        self.progress_label.add_css_class("title-3")
        top.append(self.progress_label)
        box.append(top)

        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_view.set_margin_top(8)
        self.log_view.set_margin_bottom(8)
        self.log_view.set_margin_start(8)
        self.log_view.set_margin_end(8)
        self.log_buffer = self.log_view.get_buffer()

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.log_view)
        scroller.add_css_class("frame")
        box.append(scroller)
        return box

    # ---------- navigation ----------

    def show_page(self, page):
        self.page = page
        self.stack.set_visible_child_name(PAGES[page])
        self.back_btn.set_sensitive(page in (1, 2, 3))
        if page == 3:
            self.refresh_summary()
        if page < 4:
            self.install_state = None
            self.next_btn.set_visible(True)
            self.next_btn.set_label("Install" if page == 3 else "Next")
            self.next_btn.set_sensitive(self.page_valid())
        elif page == 4:
            self.update_next()
        else:
            self.next_btn.set_visible(True)
        return False

    def page_valid(self):
        if self.page == 0:
            return True
        if self.page == 1:
            return self.disk_dropdown is not None
        if self.page == 2:
            return self.validate_user(show=False)
        if self.page == 3:
            return bool(getattr(self, "confirm_check", None)) and \
                self.confirm_check.get_active()
        return True

    def update_next(self):
        if not hasattr(self, "next_btn"):
            return
        if self.page == 4 and self.install_state is not None:
            self.next_btn.set_visible(True)
            self.next_btn.set_sensitive(True)
            self.next_btn.set_label("Reboot now" if self.install_state == "ok"
                                    else "Close")
        elif self.page < 4:
            self.next_btn.set_sensitive(self.page_valid())

    def on_back(self, *_):
        if self.page > 0 and self.page < 4:
            self.show_page(self.page - 1)

    def on_next(self, *_):
        if self.page == 4:
            if self.install_state == "ok":
                subprocess.Popen(["systemctl", "reboot"])
            else:
                self.window.close()
            return
        if self.page == 1 and self.disk_dropdown is None:
            return
        if self.page == 2 and not self.validate_user(show=True):
            return
        if self.page == 3:
            self.start_install()
            return
        self.show_page(self.page + 1)

    # ---------- validation / summary ----------

    def validate_user(self, show=False):
        host = self.host_entry.get_text().strip()
        user = self.user_entry.get_text().strip()
        pw = self.pass_entry.get_text()
        pw2 = self.pass2_entry.get_text()
        err = ""
        if not re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?", host):
            err = "Computer name: use letters, digits and hyphens (not at the ends)."
        elif not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
            err = "Username: lowercase letters, digits, _ and -, starting with a letter or _."
        elif user == "root":
            err = "Username 'root' is reserved."
        elif not pw:
            err = "Password must not be empty."
        elif pw != pw2:
            err = "The passwords do not match."
        elif any(c in (pw + host + user) for c in "\t\n"):
            err = "Tabs and newlines are not supported."
        if show:
            self.user_error.set_text(err)
        return not err

    def refresh_summary(self):
        if not self.disk_labels:
            self.summary.set_text("No target disk available.")
            return
        _, disk = self.selected_disk()
        model = GLib.markup_escape_text(disk["model"])
        full = GLib.markup_escape_text(self.full_entry.get_text().strip() or
                                       "no full name")
        text = (
            f"<b>Target disk:</b> {disk['path']} — {model}, "
            f"{disk['size']}\n"
            f"<b>Computer name:</b> {self.host_entry.get_text().strip()}\n"
            f"<b>User:</b> {self.user_entry.get_text().strip()}"
            f" ({full})\n"
            f"<b>Bootloader:</b> BIOS and UEFI\n\n"
            f"The entire disk {disk['path']} will be repartitioned and erased. "
            f"The system currently running from the USB stick is not touched.")
        self.summary.set_markup(text)
        self.update_next()

    def on_disk_changed(self, dropdown, _param):
        if not self.disk_labels:
            return
        idx = dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self.disk_labels):
            idx = 0
        _, d = self.disk_labels[idx]
        model = GLib.markup_escape_text(d["model"])
        self.disk_detail.set_markup(
            f"<b>{d['path']}</b> — {model}, {d['size']}, "
            f"{'removable' if d['removable'] else 'internal'}\n"
            f"This disk will be erased.")
        self.update_next()

    def selected_disk(self):
        idx = self.disk_dropdown.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION or idx >= len(self.disk_labels):
            idx = 0
        return self.disk_labels[idx]

    # ---------- install ----------

    def append_log(self, line):
        self.log_text += line + "\n"
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, line + "\n")
        try:
            self.log_view.scroll_to_iter(self.log_buffer.get_end_iter(),
                                         0.02, False, 0.0, 0.0)
        except Exception:
            pass
        return False

    def start_install(self):
        if not self.confirm_check.get_active():
            return
        if not self.disk_labels:
            return
        _, disk = self.selected_disk()
        user = self.user_entry.get_text().strip()
        host = self.host_entry.get_text().strip()
        full = self.full_entry.get_text().strip()
        pw = self.pass_entry.get_text()

        self.log_buffer.set_text("")
        self.log_text = ""
        self.show_page(4)
        self.spinner.start()
        self.progress_label.set_text("Installing…")
        self.status.set_text("Do not remove the USB stick.")
        self.next_btn.set_visible(False)
        self.back_btn.set_sensitive(False)

        config = "\t".join([disk["path"], user, pw, host, full]) + "\n"
        fd, self.config_path = tempfile.mkstemp(prefix="gentoo-install-",
                                                suffix=".cfg")
        with os.fdopen(fd, "w") as fh:
            fh.write(config)
        os.chmod(self.config_path, 0o600)

        cmd = [BACKEND, "--config", self.config_path, "--yes"]
        if self.opts.dry_run:
            cmd.append("--dry-run")
        if os.geteuid() != 0:
            cmd = ["pkexec"] + cmd
        self.append_log("$ " + " ".join(cmd))
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as exc:
            self.finish_install(1, str(exc))
            return
        threading.Thread(target=self.read_output, daemon=True).start()

    def read_output(self):
        assert self.proc is not None
        for line in self.proc.stdout:
            GLib.idle_add(self.append_log, line.rstrip("\n"))
        rc = self.proc.wait()
        GLib.idle_add(self.finish_install, rc, None)

    def finish_install(self, rc, error):
        self.spinner.stop()
        if self.config_path:
            try:
                os.unlink(self.config_path)
            except OSError:
                pass
            self.config_path = None
        ok = rc == 0 and error is None and (
            "INSTALL_OK" in self.log_text or
            (self.opts.dry_run and "DRY_RUN_OK" in self.log_text))
        self.install_state = "ok" if ok else "fail"
        if error:
            self.append_log("ERROR: " + error)
        if ok:
            self.progress_label.set_text("Installation complete")
            self.status.set_text("You can now reboot into the installed system.")
        else:
            self.progress_label.set_text("Installation failed")
            self.status.set_text("See the log above. Full log: /var/log/gentoo-install.log")
        self.update_next()
        return False

    # ---------- test hooks ----------

    def apply_test_fill(self):
        self.host_entry.set_text("testpc")
        self.user_entry.set_text("demo")
        self.full_entry.set_text("Demo User")
        self.pass_entry.set_text("demo")
        self.pass2_entry.set_text("demo")
        self.confirm_check.set_active(True)
        if self.disk_dropdown is not None:
            self.disk_dropdown.set_selected(0)
        self.update_next()
        return False

    def autostart_install(self):
        if self.opts.test_fill and self.validate_user(show=False):
            self.start_install()
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-fill", action="store_true",
                    help="prefill demo values (automation/testing)")
    ap.add_argument("--page", type=int, default=None,
                    help="open a specific page (0=welcome .. 4=progress)")
    ap.add_argument("--autostart", action="store_true",
                    help="start the install automatically after test-fill")
    ap.add_argument("--dry-run", action="store_true",
                    help="ask the backend to plan only, do not write")
    opts = ap.parse_args()
    app = Installer(opts)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
