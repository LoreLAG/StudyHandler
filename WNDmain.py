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
from pywinauto import Application
import platform

# --- CONFIGURAZIONE ---
APP_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'StudyManager')
SESSIONS_DIR = os.path.join(APP_DIR, 'sessions')
SETTINGS_FILE = os.path.join(APP_DIR, 'settings.json')
CHROME_USER_DATA = os.path.join(os.environ['LOCALAPPDATA'], 'Google/Chrome/User Data')


def setup():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
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


def get_browser_url(hwnd):
    try:
        app = Application(backend="uia").connect(handle=hwnd, timeout=0.1)
        window = app.window(handle=hwnd)
        # Tenta di trovare la barra degli indirizzi in Italiano o Inglese
        url_wrapper = window.child_window(title_re=".*Address and search bar.*|.*Barra degli indirizzi.*",
                                          control_type="Edit")
        return url_wrapper.get_value()
    except:
        return None


def center_window(window, width, height):
    window.update_idletasks()
    x = int((window.winfo_screenwidth() / 2) - (width / 2))
    y = int((window.winfo_screenheight() / 2) - (height / 2))
    window.geometry(f"{width}x{height}+{x}+{y}")


# --- MAIN CLASS ---
class StudyManagerWin(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Study Manager Pro - Windows")
        setup()

        self.settings = load_settings()
        self.chrome_profiles = get_chrome_profiles()
        self.current_session_name = None
        self.saved_data = []
        self.found_items = {}
        self.checkbox_vars = {}
        self.app_frames = {}
        self.is_scanning = False

        # UI Header
        self.lbl_session = ctk.CTkLabel(self, text="No Active Session", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_session.pack(pady=(15, 0))
        self.lbl_status = ctk.CTkLabel(self, text="New / Unsaved", font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_status.pack(pady=(0, 10))

        self.btn_scan = ctk.CTkButton(self, text="🔍 Refresh Current View", command=self.trigger_scan)
        self.btn_scan.pack(fill="x", padx=30, pady=5)

        self.frame_list = ctk.CTkScrollableFrame(self, label_text="Elements (Right-Click for Profiles/Defaults)")
        self.frame_list.pack(fill="both", expand=True, padx=30, pady=10)

        ctk.CTkButton(self, text="💾 Save Session", command=self.save_session, fg_color="#28a745").pack(fill="x",
                                                                                                       padx=30, pady=5)
        ctk.CTkButton(self, text="🛑 Close Selected Apps", command=self.close_apps, fg_color="#dc3545").pack(fill="x",
                                                                                                            padx=30,
                                                                                                            pady=5)
        ctk.CTkButton(self, text="📂 Change / Open Session", command=self.restore_menu, fg_color="#17a2b8").pack(
            fill="x", padx=30, pady=(10, 20))

        center_window(self, 650, 800)
        self.trigger_scan()
        self.auto_scan_loop()

    def auto_scan_loop(self):
        self.trigger_scan()
        self.after(7000, self.auto_scan_loop)

    def trigger_scan(self):
        if not self.is_scanning:
            self.is_scanning = True
            threading.Thread(target=self._background_scan, daemon=True).start()

    def _background_scan(self):
        current = {}
        url_profs = self.settings.get("url_profiles", {})

        def enum_handler(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    p_name = proc.name().lower()

                    if "chrome.exe" in p_name:
                        url = get_browser_url(hwnd)
                        if url:
                            prof = url_profs.get(url, "Default")
                            txt = f"🌐 [{prof}] {title[:50]}..."
                            current[f"{url}_{hwnd}"] = {"type": "url", "value": url, "parent_app": "Google Chrome",
                                                        "text": txt, "default": False, "profile": prof}
                    elif p_name not in ["explorer.exe", "python.exe", "taskmgr.exe", "studymanager.exe"]:
                        txt = f"🖥️ {title[:60]}"
                        current[f"{title}_{hwnd}"] = {"type": "app", "value": title,
                                                      "parent_app": p_name.replace(".exe", "").capitalize(),
                                                      "text": txt, "default": True}
                except:
                    pass

        win32gui.EnumWindows(enum_handler, None)
        self.after(0, lambda: self._apply_results(current))

    def _apply_results(self, current):
        # 1. Rimozione Delta
        keys_to_remove = [k for k in list(self.found_items.keys()) if k not in current]
        for k in keys_to_remove:
            p_app = self.found_items[k]["parent_app"]
            self.checkbox_vars[k].destroy()
            del self.checkbox_vars[k], self.found_items[k]
            if p_app in self.app_frames and len(self.app_frames[p_app].winfo_children()) <= 1:
                self.app_frames[p_app].destroy()
                del self.app_frames[p_app]

        # 2. Aggiunta Delta
        for k, d in current.items():
            if k not in self.found_items:
                p_app = d["parent_app"]
                if p_app not in self.app_frames:
                    f = ctk.CTkFrame(self.frame_list, fg_color="transparent")
                    f.pack(fill="x", pady=5)
                    ctk.CTkLabel(f, text=p_app.upper(), font=ctk.CTkFont(weight="bold"), text_color="#17a2b8").pack(
                        anchor="w")
                    self.app_frames[p_app] = f

                chk = ctk.CTkCheckBox(self.app_frames[p_app], text=d["text"], command=self.check_dirty_state)
                chk.pack(fill="x", padx=25, pady=2)

                pref = self.settings.get("app_defaults", {}).get(p_app, d["default"])
                if pref:
                    chk.select()
                else:
                    chk.deselect()

                self.checkbox_vars[k] = chk
                self.found_items[k] = d
                chk.bind("<Button-3>",
                         lambda e, a=p_app, u=d.get("value") if d["type"] == "url" else None: self.show_context_menu(e,
                                                                                                                     a,
                                                                                                                     u))

        self.is_scanning = False
        self.check_dirty_state()

    def show_context_menu(self, event, app_name, url=None):
        menu = tk.Menu(self, tearoff=0)
        if app_name == "Google Chrome" and url:
            p_menu = tk.Menu(menu, tearoff=0)
            for name in self.chrome_profiles.keys():
                p_menu.add_command(label=name, command=lambda n=name, u=url: self.set_url_profile(u, n))
            menu.add_cascade(label="Assign Chrome Profile", menu=p_menu)
        menu.add_command(label=f"Default SELECT {app_name}", command=lambda: self.set_app_default(app_name, True))
        menu.add_command(label=f"Default DESELECT {app_name}", command=lambda: self.set_app_default(app_name, False))
        menu.tk_popup(event.x_root, event.y_root)

    def set_url_profile(self, url, profile):
        save_setting("url_profiles", url, profile)
        self.settings = load_settings()
        messagebox.showinfo("Profile Assigned", f"URL linked to profile: {profile}")

    def set_app_default(self, app, state):
        save_setting("app_defaults", app, state)
        self.settings = load_settings()
        self.trigger_scan()

    def check_dirty_state(self):
        curr = sorted([v["value"] for k, v in self.found_items.items() if self.checkbox_vars[k].get() == 1])
        saved = sorted([v["value"] for v in self.saved_data])
        is_dirty = curr != saved
        if self.current_session_name:
            self.lbl_session.configure(text=f"{self.current_session_name}{' (*)' if is_dirty else ''}",
                                       text_color="#dc3545" if is_dirty else "white")
        else:
            self.lbl_session.configure(text="New Session", text_color="gray")

    def save_session(self):
        if not self.current_session_name:
            name = ctk.CTkInputDialog(text="Session Name:", title="Save").get_input()
            if not name: return
            self.current_session_name = name
        to_save = [v for k, v in self.found_items.items() if self.checkbox_vars[k].get() == 1]
        self.saved_data = to_save
        with open(os.path.join(SESSIONS_DIR, f"{self.current_session_name}.json"), 'w') as f:
            json.dump(to_save, f, indent=4)
        self.check_dirty_state()

    def close_apps(self):
        selected_pids = set()
        for k, v in self.found_items.items():
            if self.checkbox_vars[k].get() == 1:
                # Trova i PID associati al nome dell'app
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'].lower() == v['parent_app'].lower() + ".exe":
                        proc.terminate()

    def restore_menu(self):
        files = [f.replace(".json", "") for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        pop = ctk.CTkToplevel(self);
        pop.title("Open Session");
        center_window(pop, 500, 450);
        pop.transient(self)
        txt = ctk.CTkTextbox(pop, height=200, state="disabled")

        def preview(c):
            with open(os.path.join(SESSIONS_DIR, f"{c}.json"), 'r') as f: data = json.load(f)
            txt.configure(state="normal");
            txt.delete("1.0", "end")
            for i in data: txt.insert("end", f"{'🌐' if i['type'] == 'url' else '📄'} {i['parent_app']}: {i['value']}\n")
            txt.configure(state="disabled")

        if files:
            sel = ctk.StringVar(value=files[0])
            ctk.CTkOptionMenu(pop, variable=sel, values=files, command=preview).pack(pady=10)
            txt.pack(pady=10, padx=20, fill="both")
            preview(files[0])
            ctk.CTkButton(pop, text="🚀 Open", command=lambda: [self._load_session(sel.get()), pop.destroy()]).pack(
                pady=5)

    def _load_session(self, name):
        self.current_session_name = name
        with open(os.path.join(SESSIONS_DIR, f"{name}.json"), 'r') as f:
            self.saved_data = json.load(f)
        for i in self.saved_data:
            if i["type"] == "url":
                prof = self.chrome_profiles.get(i.get("profile", "Default"), "Default")
                # Avvio con profilo specifico su Windows
                subprocess.Popen(f'start chrome --profile-directory="{prof}" "{i["value"]}"', shell=True)
            else:
                os.startfile(i["value"])
        self.after(2000, self.trigger_scan)


if __name__ == "__main__":
    app = StudyManagerWin()
    app.mainloop()
