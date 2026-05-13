import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import subprocess
import json
import os
import threading
import win32gui
import win32process
import psutil
import shutil
from pathlib import Path

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# --- WINDOWS PATH CONFIGURATION ---
APP_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'StudyManager')
SESSIONS_DIR = os.path.join(APP_DIR, 'sessions')
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
CHROME_USER_DATA = os.path.join(os.environ['LOCALAPPDATA'], 'Google/Chrome/User Data')


def setup():
    for d in [APP_DIR, SESSIONS_DIR]:
        if not os.path.exists(d): os.makedirs(d)
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump({"app_defaults": {}, "url_profiles": {}}, f)


def load_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            if "app_defaults" not in data: data["app_defaults"] = {}
            if "url_profiles" not in data: data["url_profiles"] = {}
            return data
    except:
        return {"app_defaults": {}, "url_profiles": {}}


def save_setting(category, key, value):
    data = load_settings()
    data[category][key] = value
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def get_chrome_profiles():
    profiles = {"Default": "Default"}
    local_state = os.path.join(CHROME_USER_DATA, "Local State")
    if os.path.exists(local_state):
        try:
            with open(local_state, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cache = data.get("profile", {}).get("info_cache", {})
                for folder, info in cache.items():
                    profiles[info.get("name")] = folder
        except:
            pass
    return profiles


# --- WINDOWS WINDOWS SCANNING ---
def get_active_apps_win():
    """Returns a list of visible windows titles and their process names."""
    results = []

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid)
                p_name = proc.name().replace(".exe", "").capitalize()
                # Ignore system apps
                if p_name not in ["Explorer", "Taskmgr", "Settings", "Python", "Studymanager"]:
                    results.append({"title": title, "p_name": p_name})
            except:
                pass

    win32gui.EnumWindows(enum_handler, None)
    return results


def get_chrome_tabs_win():
    """Windows doesn't allow easy URL reading. This is a simplified version."""
    # Nota: Leggere URL da Chrome su Win richiede estensioni o permessi admin.
    # Per ora catturiamo il titolo della finestra di Chrome.
    tabs = []
    for app in get_active_apps_win():
        if "Chrome" in app["p_name"]:
            tabs.append({"title": app["title"], "url": "N/A (Win Limitation)"})
    return tabs


class StudyManagerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Study Manager (Windows Version)")
        setup()

        self.settings = load_settings()
        self.chrome_profiles = get_chrome_profiles()
        self.current_session_name = None
        self.saved_data = []
        self.found_items = {}
        self.checkbox_vars = {}
        self.app_frames = {}
        self.is_scanning = False

        # UI
        self.lbl_session = ctk.CTkLabel(self, text="No Active Session", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_session.pack(pady=(15, 0))
        self.lbl_status = ctk.CTkLabel(self, text="Ready", font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_status.pack(pady=(0, 10))

        self.btn_scan = ctk.CTkButton(self, text="🔍 Refresh", command=self.force_manual_scan)
        self.btn_scan.pack(fill="x", padx=30, pady=5)

        self.frame_list = ctk.CTkScrollableFrame(self, label_text="Detected Elements")
        self.frame_list.pack(fill="both", expand=True, padx=30, pady=10)

        ctk.CTkButton(self, text="💾 Save Session", command=self.save_session, fg_color="#28a745").pack(fill="x",
                                                                                                       padx=30, pady=5)
        ctk.CTkButton(self, text="📂 Change Session", command=self.restore_menu, fg_color="#17a2b8").pack(fill="x",
                                                                                                         padx=30,
                                                                                                         pady=(10, 20))

        self.geometry("600x700")
        self.trigger_scan()
        self.auto_scan_loop()

    def auto_scan_loop(self):
        self.trigger_scan()
        self.after(5000, self.auto_scan_loop)

    def force_manual_scan(self):
        self.lbl_status.configure(text="Scanning...", text_color="#17a2b8")
        self.trigger_scan()

    def trigger_scan(self):
        if not self.is_scanning:
            self.is_scanning = True
            threading.Thread(target=self._background_scan, daemon=True).start()

    def _background_scan(self):
        current = {}
        apps = get_active_apps_win()
        for app in apps:
            p_app = app["p_name"]
            txt = app["title"]
            key = f"{p_app} | {txt}"
            # Default logic
            is_def = False if "Chrome" in p_app else True
            current[key] = {"type": "app", "value": txt, "parent_app": p_app, "text": txt, "default": is_def}

        self.after(0, lambda: self._apply_results(current))

    def _apply_results(self, current):
        # Sincronizzazione Delta (identica alla versione Mac)
        keys_to_remove = [k for k in list(self.found_items.keys()) if k not in current]
        for k in keys_to_remove:
            p_app = self.found_items[k]["parent_app"]
            if k in self.checkbox_vars:
                self.checkbox_vars[k].destroy()
                del self.checkbox_vars[k]
            del self.found_items[k]
            if p_app in self.app_frames:
                if len(self.app_frames[p_app].winfo_children()) <= 1:
                    self.app_frames[p_app].destroy()
                    del self.app_frames[p_app]

        for k, d in current.items():
            if k not in self.found_items:
                p_app = d["parent_app"]
                if p_app not in self.app_frames:
                    f = ctk.CTkFrame(self.frame_list, fg_color="transparent")
                    f.pack(fill="x", pady=5)
                    ctk.CTkLabel(f, text=p_app.upper(), font=ctk.CTkFont(size=13, weight="bold"),
                                 text_color="#17a2b8").pack(anchor="w", padx=5)
                    self.app_frames[p_app] = f

                chk = ctk.CTkCheckBox(self.app_frames[p_app], text=d["text"], command=self.check_dirty_state)
                chk.pack(fill="x", padx=(25, 5), pady=2)

                pref = self.settings.get("app_defaults", {}).get(p_app, d["default"])
                if pref:
                    chk.select()
                else:
                    chk.deselect()

                self.checkbox_vars[k] = chk
                self.found_items[k] = d

        for app_name in sorted(self.app_frames.keys()):
            self.app_frames[app_name].pack(fill="x", pady=5)

        self.is_scanning = False
        self.lbl_status.configure(text="Synced", text_color="gray")

    def check_dirty_state(self):
        pass  # Logica semplificata per Windows

    def save_session(self):
        if not self.current_session_name:
            name = ctk.CTkInputDialog(text="Session Name:", title="Save").get_input()
            if not name: return
            self.current_session_name = name

        to_save = [v for k, v in self.found_items.items() if self.checkbox_vars[k].get() == 1]
        with open(os.path.join(SESSIONS_DIR, f"{self.current_session_name}.json"), 'w') as f:
            json.dump(to_save, f, indent=4)
        messagebox.showinfo("Saved", "Session updated.")

    def restore_menu(self):
        files = [f.replace(".json", "") for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        pop = ctk.CTkToplevel(self);
        pop.title("Open");
        pop.geometry("400x300")
        if files:
            sel = ctk.StringVar(value=files[0])
            ctk.CTkOptionMenu(pop, variable=sel, values=files).pack(pady=20)
            ctk.CTkButton(pop, text="🚀 Open", command=lambda: [self._load_session(sel.get()), pop.destroy()]).pack()

    def _load_session(self, name):
        self.current_session_name = name
        with open(os.path.join(SESSIONS_DIR, f"{name}.json"), 'r') as f:
            data = json.load(f)
        for i in data:
            # Su Windows usiamo os.startfile che è universale
            try:
                os.startfile(i["value"])
            except:
                pass


if __name__ == "__main__":
    app = StudyManagerGUI()
    app.mainloop()
