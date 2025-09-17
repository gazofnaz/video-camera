#!/usr/bin/env python3
import subprocess, sys, re, shutil, tkinter as tk
from tkinter import ttk, messagebox

DEFAULT_DEVICE = "/dev/video4"
CTRL_NAME = "white_balance_temperature"
AUTO_CTRL = "white_balance_automatic"
SATURATION_CTRL = "saturation"

def have_v4l2ctl():
    return shutil.which("v4l2-ctl") is not None

def run_cmd(args):
    # Run and return (rc, stdout, stderr)
    try:
        p = subprocess.run(args, capture_output=True, text=True, check=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 1, "", str(e)

def get_ctrl_range(dev, ctrl):
    """
    Parse `v4l2-ctl --device X --list-ctrls` to discover min/max/step/default.
    Returns (minv, maxv, step, default) or sensible fallbacks.
    """
    rc, out, err = run_cmd(["v4l2-ctl", "--device", dev, "--list-ctrls"])
    if rc != 0:
        return 2000, 10000, 10, 4500  # fallback if listing fails
    # Example line:
    # white_balance_temperature (int) : min=2800 max=6500 step=1 default=4000 value=4000
    pattern = rf"^{re.escape(ctrl)}.*?min=(\-?\d+)\s+max=(\-?\d+)\s+step=(\d+)\s+default=(\-?\d+)"
    m = re.search(pattern, out, re.MULTILINE)
    if not m:
        return 2000, 10000, 10, 4500
    return tuple(map(int, m.groups()))

def get_ctrl_value(dev, ctrl):
    rc, out, err = run_cmd(["v4l2-ctl", "--device", dev, f"--get-ctrl={ctrl}"])
    # Output like: white_balance_temperature=4000
    if rc == 0:
        m = out[out.rindex(':')+1:]
        if m:
            return int(m)
    return None

def set_ctrl(dev, ctrl, value):
    return run_cmd(["v4l2-ctl", "--device", dev, f"--set-ctrl={ctrl}={value}"])

def set_ctrl_bool(dev, ctrl, value_bool):
    return set_ctrl(dev, ctrl, 1 if value_bool else 0)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("V4L2 Control GUI")
        self.geometry("420x300")  # Increased height for new control
        self.resizable(False, False)

        if not have_v4l2ctl():
            messagebox.showerror("Missing v4l2-ctl", "Install v4l-utils first: sudo apt install v4l-utils")
            self.destroy()
            return

        # Device row
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Video device:").grid(row=0, column=0, sticky="w")
        self.dev_var = tk.StringVar(value=DEFAULT_DEVICE)
        self.dev_entry = ttk.Entry(frm, textvariable=self.dev_var, width=20)
        self.dev_entry.grid(row=0, column=1, sticky="w")
        ttk.Button(frm, text="Load", command=self.load_device).grid(row=0, column=2, padx=(8,0))

        # Auto checkbox
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_check = ttk.Checkbutton(frm, text="Auto white balance", variable=self.auto_var, command=self.on_auto_toggle)
        self.auto_check.grid(row=1, column=0, columnspan=3, sticky="w", pady=(12,0))

        # White balance temperature slider
        ttk.Label(frm, text="White balance temperature").grid(row=2, column=0, columnspan=3, sticky="w", pady=(12,2))
        self.scale_var = tk.IntVar(value=4000)
        self.scale = ttk.Scale(frm, from_=2000, to=10000, orient="horizontal", command=self.on_scale_move)
        self.scale.grid(row=3, column=0, columnspan=3, sticky="ew")

        # White balance temperature current value display
        self.val_label = ttk.Label(frm, text="4000 K")
        self.val_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6,0))

        # Saturation slider
        ttk.Label(frm, text="Saturation").grid(row=5, column=0, columnspan=3, sticky="w", pady=(12,2))
        self.sat_var = tk.IntVar(value=128)  # Default value of 128
        self.sat_scale = ttk.Scale(frm, from_=0, to=255, orient="horizontal", command=self.on_sat_scale_move)
        self.sat_scale.grid(row=6, column=0, columnspan=3, sticky="ew")

        # Saturation current value display
        self.sat_label = ttk.Label(frm, text="128")
        self.sat_label.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6,0))

        frm.columnconfigure(1, weight=1)

        # Status bar
        self.status = ttk.Label(self, text="", anchor="w", padding=(10, 4))
        self.status.pack(fill="x", side="bottom")

        self._pending_apply = None  # for debouncing white balance slider
        self._pending_sat_apply = None  # for debouncing saturation slider
        self.load_device()

    def load_device(self):
        dev = self.dev_var.get().strip()
        # Pull ranges
        minv, maxv, step, default = get_ctrl_range(dev, CTRL_NAME)
        self.scale.configure(from_=minv, to=maxv)
        # Fetch current auto/value
        auto = get_ctrl_value(dev, AUTO_CTRL)
        if auto is not None:
            self.auto_var.set(bool(auto))
        else:
            # If auto control not present, hide checkbox
            self.auto_check.state(["disabled"])
            self.auto_var.set(False)

        val = get_ctrl_value(dev, CTRL_NAME)
        if val is None:
            val = default
        self.scale_var.set(val)
        self.scale.set(val)
        self.val_label.configure(text=f"{val} K")
        # Enable/disable slider per auto
        self.scale.state(["disabled"] if self.auto_var.get() else ["!disabled"])

        # Saturation range (0-255) is static, but we may want to read current value
        sat_val = get_ctrl_value(dev, SATURATION_CTRL)
        if sat_val is not None:
            self.sat_var.set(sat_val)
            self.sat_scale.set(sat_val)
            self.sat_label.configure(text=f"{sat_val}")
        self.set_status(f"Loaded {dev} (range {minv}–{maxv}, step {step}, default {default})")

    def on_auto_toggle(self):
        dev = self.dev_var.get().strip()
        auto = self.auto_var.get()
        rc, out, err = set_ctrl_bool(dev, AUTO_CTRL, auto)
        if rc != 0:
            messagebox.showerror("Error", f"Failed to set {AUTO_CTRL}={int(auto)}:\n{err or out}")
            # Revert
            cur = get_ctrl_value(dev, AUTO_CTRL)
            self.auto_var.set(bool(cur) if cur is not None else False)
        self.scale.state(["disabled"] if auto else ["!disabled"])
        self.set_status(f"{AUTO_CTRL} set to {int(auto)}")

    def on_scale_move(self, _evt=None):
        v = int(float(self.scale.get()))
        self.val_label.configure(text=f"{v} K")
        # Debounce apply (apply 150ms after last move)
        if self._pending_apply is not None:
            self.after_cancel(self._pending_apply)
        self._pending_apply = self.after(150, self.apply_scale)

    def apply_scale(self):
        self._pending_apply = None
        dev = self.dev_var.get().strip()
        v = int(float(self.scale.get()))

        # First ensure auto white balance is turned off before setting temperature
        auto_state = get_ctrl_value(dev, AUTO_CTRL)
        if auto_state == 1:
            # If auto white balance is on, turn it off first
            rc, out, err = set_ctrl_bool(dev, AUTO_CTRL, False)
            if rc != 0:
                self.set_status(f"Error disabling auto white balance: {err or out}")
                return
            # Update the auto checkbox state
            self.auto_var.set(False)
            self.scale.state(["!disabled"])  # Enable the slider

        # Now set the white balance temperature
        rc, out, err = set_ctrl(dev, CTRL_NAME, v)
        if rc != 0:
            self.set_status(f"Error: {err or out}")
        else:
            self.set_status(f"Set {CTRL_NAME}={v}")

    def on_sat_scale_move(self, _evt=None):
        v = int(float(self.sat_scale.get()))
        self.sat_label.configure(text=f"{v}")
        # Debounce apply (apply 150ms after last move)
        if self._pending_sat_apply is not None:
            self.after_cancel(self._pending_sat_apply)
        self._pending_sat_apply = self.after(150, self.apply_saturation)

    def apply_saturation(self):
        self._pending_sat_apply = None
        dev = self.dev_var.get().strip()
        v = int(float(self.sat_scale.get()))

        # Set the saturation
        rc, out, err = set_ctrl(dev, SATURATION_CTRL, v)
        if rc != 0:
            self.set_status(f"Error: {err or out}")
        else:
            self.set_status(f"Set {SATURATION_CTRL}={v}")

    def set_status(self, msg):
        self.status.configure(text=msg)

if __name__ == "__main__":
    try:
        App().mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
