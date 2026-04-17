#!/usr/bin/env python3
import subprocess, sys, re, shutil, tkinter as tk, json, os
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

PRESETS_DIR = Path(__file__).resolve().parent / "presets"

DEFAULT_DEVICE = "/dev/video4"
CTRL_NAME = "white_balance_temperature"
AUTO_CTRL = "white_balance_automatic"
SATURATION_CTRL = "saturation"
CONTRAST_CTRL = "contrast"
AUTO_EXPOSURE_CTRL = "auto_exposure"
EXPOSURE_TIME_CTRL = "exposure_time_absolute"
EXPOSURE_DYN_FPS_CTRL = "exposure_dynamic_framerate"
GAIN_CTRL = "gain"

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
        # 'auto_exposure: 3 (Aperture Priority Mode)' -> '3'
        # 'brightness: 128' -> '128'
        # etc
        m = ''.join(filter(str.isdigit, out[out.rindex(':')+1:]))
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
        self.geometry("640x800")
        self.resizable(False, True)
        self.style = ttk.Style(self)
        # Larger slider handle to make grabbing easier with the mouse
        self.style.configure("Thick.Horizontal.TScale", sliderlength=32)

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
        self.scale = ttk.Scale(
            frm,
            from_=2000,
            to=10000,
            orient="horizontal",
            command=self.on_scale_move,
            style="Thick.Horizontal.TScale",
            length=360,
        )
        self.scale.grid(row=3, column=0, columnspan=3, sticky="ew")

        # White balance temperature current value display
        self.val_label = ttk.Label(frm, text="4000 K")
        self.val_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6,0))

        # Saturation slider
        ttk.Label(frm, text="Saturation").grid(row=5, column=0, columnspan=3, sticky="w", pady=(12,2))
        self.sat_var = tk.IntVar(value=128)  # Default value of 128
        self.sat_scale = ttk.Scale(
            frm,
            from_=0,
            to=255,
            orient="horizontal",
            command=self.on_sat_scale_move,
            style="Thick.Horizontal.TScale",
            length=360,
        )
        self.sat_scale.grid(row=6, column=0, columnspan=3, sticky="ew")

        # Saturation current value display
        self.sat_label = ttk.Label(frm, text="128")
        self.sat_label.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6,0))

        # Contrast slider
        ttk.Label(frm, text="Contrast").grid(row=8, column=0, columnspan=3, sticky="w", pady=(12,2))
        self.contrast_var = tk.IntVar(value=128)  # Default value of 128
        self.contrast_scale = ttk.Scale(
            frm,
            from_=0,
            to=255,
            orient="horizontal",
            command=self.on_contrast_scale_move,
            style="Thick.Horizontal.TScale",
            length=360,
        )
        self.contrast_scale.grid(row=9, column=0, columnspan=3, sticky="ew")

        # Contrast current value display
        self.contrast_label = ttk.Label(frm, text="128")
        self.contrast_label.grid(row=10, column=0, columnspan=3, sticky="w", pady=(6,0))

        # Auto Exposure radio buttons (only 1 and 3 are valid values)
        ttk.Label(frm, text="Auto Exposure").grid(row=11, column=0, columnspan=3, sticky="w", pady=(12,2))
        self.exp_auto_var = tk.IntVar(value=3)  # Default to Auto mode
        self.exp_auto_frame = ttk.Frame(frm)
        self.exp_auto_frame.grid(row=12, column=0, columnspan=3, sticky="w")

        # Radio button for Manual (value 1)
        ttk.Radiobutton(
            self.exp_auto_frame,
            text="Manual",
            variable=self.exp_auto_var,
            value=1,
            command=self.on_auto_exposure_change
        ).pack(side="left", padx=(0, 20))

        # Radio button for Auto (value 3)
        ttk.Radiobutton(
            self.exp_auto_frame,
            text="Auto",
            variable=self.exp_auto_var,
            value=3,
            command=self.on_auto_exposure_change
        ).pack(side="left")

        # Exposure Time slider
        ttk.Label(frm, text="Exposure Time").grid(row=13, column=0, columnspan=3, sticky="w", pady=(12,2))
        self.exp_time_var = tk.IntVar(value=500)  # Default from example
        self.exp_time_scale = ttk.Scale(
            frm,
            from_=3,
            to=2047,
            orient="horizontal",
            command=self.on_exp_time_move,
            style="Thick.Horizontal.TScale",
            length=360,
        )
        self.exp_time_scale.grid(row=14, column=0, columnspan=3, sticky="ew")

        # Exposure Time current value display
        self.exp_time_label = ttk.Label(frm, text="500")
        self.exp_time_label.grid(row=15, column=0, columnspan=3, sticky="w", pady=(6,0))

        # Exposure Dynamic Framerate toggle
        self.exp_dyn_fps_var = tk.BooleanVar(value=False)
        self.exp_dyn_fps_check = ttk.Checkbutton(
            frm, text="Exposure dynamic framerate",
            variable=self.exp_dyn_fps_var,
            command=self.on_exp_dyn_fps_toggle
        )
        self.exp_dyn_fps_check.grid(row=16, column=0, columnspan=3, sticky="w", pady=(12,0))

        # Gain slider
        ttk.Label(frm, text="Gain").grid(row=17, column=0, columnspan=3, sticky="w", pady=(12,2))
        self.gain_var = tk.IntVar(value=0)
        self.gain_scale = ttk.Scale(
            frm,
            from_=0,
            to=255,
            orient="horizontal",
            command=self.on_gain_scale_move,
            style="Thick.Horizontal.TScale",
            length=360,
        )
        self.gain_scale.grid(row=18, column=0, columnspan=3, sticky="ew")

        # Gain current value display
        self.gain_label = ttk.Label(frm, text="0")
        self.gain_label.grid(row=19, column=0, columnspan=3, sticky="w", pady=(6,0))

        # --- Presets section ---
        preset_frame = ttk.LabelFrame(frm, text="Presets", padding=8)
        preset_frame.grid(row=20, column=0, columnspan=3, sticky="ew", pady=(16, 0))

        ttk.Label(preset_frame, text="Preset:").grid(row=0, column=0, sticky="w")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, width=24, state="readonly")
        self.preset_combo.grid(row=0, column=1, padx=(4, 0), sticky="w")

        btn_frame = ttk.Frame(preset_frame)
        btn_frame.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(btn_frame, text="Load", command=self.load_preset).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Save current", command=self.save_preset).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Save as…", command=self.save_preset_as).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Delete", command=self.delete_preset).pack(side="left")

        frm.columnconfigure(1, weight=1)

        # Status bar
        self.status = ttk.Label(self, text="", anchor="w", padding=(10, 4))
        self.status.pack(fill="x", side="bottom")

        self._pending_apply = None
        self._pending_sat_apply = None
        self._pending_contrast_apply = None
        self._pending_exp_time_apply = None
        self._pending_gain_apply = None
        PRESETS_DIR.mkdir(exist_ok=True)
        self._refresh_preset_list()
        self.load_device()

    def _refresh_preset_list(self):
        names = sorted(p.stem for p in PRESETS_DIR.glob("*.json"))
        self.preset_combo["values"] = names
        if names and not self.preset_var.get():
            self.preset_var.set(names[0])

    def _gather_settings(self):
        return {
            "white_balance_temperature": int(float(self.scale.get())),
            "white_balance_automatic": self.auto_var.get(),
            "saturation": int(float(self.sat_scale.get())),
            "contrast": int(float(self.contrast_scale.get())),
            "auto_exposure": self.exp_auto_var.get(),
            "exposure_time_absolute": int(float(self.exp_time_scale.get())),
            "exposure_dynamic_framerate": self.exp_dyn_fps_var.get(),
            "gain": int(float(self.gain_scale.get())),
        }

    def _apply_settings(self, settings):
        dev = self.dev_var.get().strip()
        errors = []
        # Apply auto controls first
        if "white_balance_automatic" in settings:
            v = settings["white_balance_automatic"]
            rc, out, err = set_ctrl_bool(dev, AUTO_CTRL, v)
            if rc == 0:
                self.auto_var.set(v)
                self.scale.state(["disabled"] if v else ["!disabled"])
            else:
                errors.append(f"{AUTO_CTRL}: {err or out}")

        if "auto_exposure" in settings:
            v = settings["auto_exposure"]
            rc, out, err = set_ctrl(dev, AUTO_EXPOSURE_CTRL, v)
            if rc == 0:
                self.exp_auto_var.set(v)
            else:
                errors.append(f"{AUTO_EXPOSURE_CTRL}: {err or out}")

        ctrl_map = [
            ("white_balance_temperature", CTRL_NAME, self.scale, self.val_label, " K"),
            ("saturation", SATURATION_CTRL, self.sat_scale, self.sat_label, ""),
            ("contrast", CONTRAST_CTRL, self.contrast_scale, self.contrast_label, ""),
            ("exposure_time_absolute", EXPOSURE_TIME_CTRL, self.exp_time_scale, self.exp_time_label, ""),
            ("gain", GAIN_CTRL, self.gain_scale, self.gain_label, ""),
        ]
        for key, ctrl, scale_w, label_w, suffix in ctrl_map:
            if key in settings:
                v = settings[key]
                rc, out, err = set_ctrl(dev, ctrl, v)
                if rc == 0:
                    scale_w.set(v)
                    label_w.configure(text=f"{v}{suffix}")
                else:
                    errors.append(f"{ctrl}: {err or out}")

        if "exposure_dynamic_framerate" in settings:
            v = settings["exposure_dynamic_framerate"]
            rc, out, err = set_ctrl_bool(dev, EXPOSURE_DYN_FPS_CTRL, v)
            if rc == 0:
                self.exp_dyn_fps_var.set(v)
            else:
                errors.append(f"{EXPOSURE_DYN_FPS_CTRL}: {err or out}")

        if errors:
            self.set_status(f"Preset applied with errors: {'; '.join(errors)}")
        else:
            self.set_status("Preset applied successfully")

    def save_preset(self):
        name = self.preset_var.get().strip()
        if not name:
            return self.save_preset_as()
        path = PRESETS_DIR / f"{name}.json"
        path.write_text(json.dumps(self._gather_settings(), indent=2))
        self._refresh_preset_list()
        self.preset_var.set(name)
        self.set_status(f"Saved preset '{name}'")

    def save_preset_as(self):
        name = simpledialog.askstring("Save Preset", "Preset name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        path = PRESETS_DIR / f"{name}.json"
        if path.exists():
            if not messagebox.askyesno("Overwrite?", f"Preset '{name}' exists. Overwrite?"):
                return
        path.write_text(json.dumps(self._gather_settings(), indent=2))
        self._refresh_preset_list()
        self.preset_var.set(name)
        self.set_status(f"Saved preset '{name}'")

    def load_preset(self):
        name = self.preset_var.get().strip()
        if not name:
            messagebox.showwarning("No preset", "Select a preset first.")
            return
        path = PRESETS_DIR / f"{name}.json"
        if not path.exists():
            messagebox.showerror("Not found", f"Preset file not found: {path}")
            return
        settings = json.loads(path.read_text())
        self._apply_settings(settings)

    def delete_preset(self):
        name = self.preset_var.get().strip()
        if not name:
            return
        if not messagebox.askyesno("Delete?", f"Delete preset '{name}'?"):
            return
        path = PRESETS_DIR / f"{name}.json"
        if path.exists():
            path.unlink()
        self._refresh_preset_list()
        self.preset_var.set("")
        self.set_status(f"Deleted preset '{name}'")

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

        # Contrast range (0-255) is static, but we may want to read current value
        contrast_val = get_ctrl_value(dev, CONTRAST_CTRL)
        if contrast_val is not None:
            self.contrast_var.set(contrast_val)
            self.contrast_scale.set(contrast_val)
            self.contrast_label.configure(text=f"{contrast_val}")

        # Auto exposure: read and update UI elements
        exp_auto = get_ctrl_value(dev, AUTO_EXPOSURE_CTRL)
        if exp_auto is not None:
            self.exp_auto_var.set(exp_auto)
            # Exposure time is typically read-only in auto mode, but we can display its current value
            exp_time_val = get_ctrl_value(dev, EXPOSURE_TIME_CTRL)
            if exp_time_val is not None:
                self.exp_time_var.set(exp_time_val)
                self.exp_time_scale.set(exp_time_val)
                self.exp_time_label.configure(text=f"{exp_time_val}")

        # Exposure dynamic framerate: read and update checkbox
        exp_dyn_fps = get_ctrl_value(dev, EXPOSURE_DYN_FPS_CTRL)
        if exp_dyn_fps is not None:
            self.exp_dyn_fps_var.set(bool(exp_dyn_fps))

        # Gain: read and update slider
        gain_val = get_ctrl_value(dev, GAIN_CTRL)
        if gain_val is not None:
            self.gain_var.set(gain_val)
            self.gain_scale.set(gain_val)
            self.gain_label.configure(text=f"{gain_val}")

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

    def on_contrast_scale_move(self, _evt=None):
        v = int(float(self.contrast_scale.get()))
        self.contrast_label.configure(text=f"{v}")
        # Debounce apply (apply 150ms after last move)
        if self._pending_contrast_apply is not None:
            self.after_cancel(self._pending_contrast_apply)
        self._pending_contrast_apply = self.after(150, self.apply_contrast)

    def apply_contrast(self):
        self._pending_contrast_apply = None
        dev = self.dev_var.get().strip()
        v = int(float(self.contrast_scale.get()))

        # Set the contrast
        rc, out, err = set_ctrl(dev, CONTRAST_CTRL, v)
        if rc != 0:
            self.set_status(f"Error: {err or out}")
        else:
            self.set_status(f"Set {CONTRAST_CTRL}={v}")

    def on_auto_exposure_change(self):
        dev = self.dev_var.get().strip()
        mode = self.exp_auto_var.get()
        rc, out, err = set_ctrl(dev, AUTO_EXPOSURE_CTRL, mode)
        if rc != 0:
            messagebox.showerror("Error", f"Failed to set {AUTO_EXPOSURE_CTRL}={mode}:\n{err or out}")
            # Revert
            cur_mode = get_ctrl_value(dev, AUTO_EXPOSURE_CTRL)
            self.exp_auto_var.set(cur_mode if cur_mode is not None else 3)
        self.set_status(f"{AUTO_EXPOSURE_CTRL} set to {mode}")

    def on_exp_time_move(self, _evt=None):
        v = int(float(self.exp_time_scale.get()))
        self.exp_time_label.configure(text=f"{v}")
        # Debounce apply (apply 150ms after last move)
        if self._pending_exp_time_apply is not None:
            self.after_cancel(self._pending_exp_time_apply)
        self._pending_exp_time_apply = self.after(150, self.apply_exposure_time)

    def apply_exposure_time(self):
        self._pending_exp_time_apply = None
        dev = self.dev_var.get().strip()
        v = int(float(self.exp_time_scale.get()))

        # Set the exposure time
        rc, out, err = set_ctrl(dev, EXPOSURE_TIME_CTRL, v)
        if rc != 0:
            self.set_status(f"Error: {err or out}")
        else:
            self.set_status(f"Set {EXPOSURE_TIME_CTRL}={v}")

    def on_exp_dyn_fps_toggle(self):
        dev = self.dev_var.get().strip()
        enabled = self.exp_dyn_fps_var.get()
        rc, out, err = set_ctrl_bool(dev, EXPOSURE_DYN_FPS_CTRL, enabled)
        if rc != 0:
            messagebox.showerror("Error", f"Failed to set {EXPOSURE_DYN_FPS_CTRL}={int(enabled)}:\n{err or out}")
            # Revert
            cur = get_ctrl_value(dev, EXPOSURE_DYN_FPS_CTRL)
            self.exp_dyn_fps_var.set(bool(cur) if cur is not None else False)
        self.set_status(f"{EXPOSURE_DYN_FPS_CTRL} set to {int(enabled)}")

    def on_gain_scale_move(self, _evt=None):
        v = int(float(self.gain_scale.get()))
        self.gain_label.configure(text=f"{v}")
        # Debounce apply (apply 150ms after last move)
        if self._pending_gain_apply is not None:
            self.after_cancel(self._pending_gain_apply)
        self._pending_gain_apply = self.after(150, self.apply_gain)

    def apply_gain(self):
        self._pending_gain_apply = None
        dev = self.dev_var.get().strip()
        v = int(float(self.gain_scale.get()))

        # Set the gain
        rc, out, err = set_ctrl(dev, GAIN_CTRL, v)
        if rc != 0:
            self.set_status(f"Error: {err or out}")
        else:
            self.set_status(f"Set {GAIN_CTRL}={v}")

    def set_status(self, msg):
        self.status.configure(text=msg)

if __name__ == "__main__":
    try:
        App().mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
