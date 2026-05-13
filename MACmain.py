import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import subprocess
import json
import os
import threading
import platform
from pathlib import Path

# --- MAC DARK MODE FIX ---
_original_mac_ver = platform.mac_ver


def _patched_mac_ver():
    ver = _original_mac_ver()
    if not ver[0]: return ('10.15.0', ('', '', ''), 'x86_64')
    return ver


platform.mac_ver = _patched_mac_ver

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# --- PATH CONFIGURATION ---
APP_DIR = os.path.expanduser("~/.study_manager")
SESSIONS_DIR = os.path.join(APP_DIR, "sessions")
SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")
CHROME_USER_DATA = os.path.expanduser("~/Library/Application Support/Google/Chrome")


def setup():
    for d in [APP_DIR, SESSIONS_DIR]:
        if not os.path.exists(d): os.makedirs(d)
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump({"app_defaults": {}, "url_profiles": {}}, f)


def get_chrome_profiles():
    profiles = {"Default": "Default"}
    local_state = os.path.join(CHROME_USER_DATA, "Local State")
    try:
        with open(local_state, 'r', encoding='utf-8') as f:
            data = json.load(f)
            cache = data.get("profile", {}).get("info_cache", {})
            for folder, info in cache.items():
                profiles[info.get("name")] = folder
    except:
        pass
    return profiles


def save_setting(category, key, value):
    data = load_settings()
    data[category][key] = value
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=4)


def load_settings():
    default_structure = {"app_defaults": {}, "url_profiles": {}}
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            for key in default_structure:
                if key not in data: data[key] = {}
            return data
    except:
        return default_structure


# --- APPLESCRIPTS ---
def run_applescript(script):
    try:
        proc = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = proc.communicate()
        return out.decode('utf-8').strip() if proc.returncode == 0 else None
    except:
        return None


def get_all_chrome_tabs():
    script = '''
    tell application "Google Chrome"
        set tabData to {}
        try
            repeat with w in windows
                repeat with t in tabs of w
                    set end of tabData to (title of t & "###" & URL of t)
                end repeat
            end repeat
        end try
        set AppleScript's text item delimiters to "|||"
        return tabData as text
    end tell'''
    res = run_applescript(script)
    if not res: return []
    results = []
    seen = set()
    for item in res.split("|||"):
        if "###" in item:
            title, url = item.split("###")
            if url not in seen:
                results.append({"title": title, "url": url})
                seen.add(url)
    return results


def get_multiple_paths(app_name):
    app_target = "Preview" if app_name in ["Anteprima", "Preview"] else app_name
    doc_entities = {"Preview": ("documents", "path"), "Microsoft Word": ("documents", "full name"),
                    "Microsoft Excel": ("workbooks", "full name"),
                    "Microsoft PowerPoint": ("presentations", "full name")}
    if app_name not in doc_entities: return []
    entity, prop = doc_entities[app_name]
    script = f'tell application "{app_target}" to return {prop} of every {entity}'
    res = run_applescript(script)
    return [p.strip() for p in res.split(",") if p.strip()] if res else []


def get_active_apps():
    script = 'tell application "System Events" to return name of every application process whose visible is true'
    res = run_applescript(script)
    if not res: return []
    to_ignore = ["Finder", "Terminal", "Python", "Study Manager", "Code", "System Settings", "app_mode_loader"]
    return [app.strip() for app in res.split(',') if app.strip() not in to_ignore]


def center_window(window, width, height):
    window.update_idletasks()
    # Calcolo coordinate
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width / 2) - (width / 2))
    y = int((screen_height / 2) - (height / 2))

    # Imposta la geometria PRIMA di mostrare la finestra
    window.geometry(f"{width}x{height}+{x}+{y}")


class StudyManagerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title("Study Manager")
        self.attributes("-alpha", 0)
        setup()

        self.settings = load_settings()
        self.chrome_profiles = get_chrome_profiles()
        self.current_session_name = None
        self.saved_data = []
        self.found_items = {}
        self.checkbox_vars = {}
        self.app_frames = {}
        self.is_scanning = False

        self.lbl_session = ctk.CTkLabel(self, text="No Active Session", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_session.pack(pady=(15, 0))
        self.lbl_status = ctk.CTkLabel(self, text="New / Unsaved", font=ctk.CTkFont(size=12), text_color="gray")
        self.lbl_status.pack(pady=(0, 10))
        self.btn_scan = ctk.CTkButton(self, text="🔍 Refresh Current View", command=self.force_manual_scan)
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

        center_window(self, 750, 750)

        # Un piccolo delay assicura che il window manager abbia processato il geometry
        self.after(100, lambda: self.attributes("-alpha", 1.0))
        self.deiconify()
        self.trigger_scan()
        self.auto_scan_loop()

    def auto_scan_loop(self):
        self.trigger_scan()
        self.after(5000, self.auto_scan_loop)

    def force_manual_scan(self):
        """Eseguita quando l'utente clicca il tasto Refresh."""
        self.lbl_status.configure(text="Scanning...", text_color="#17a2b8")
        # Forziamo la scansione anche se il timer non è scaduto
        self.trigger_scan(force=True)

    def trigger_scan(self, force=False):
        """Avvia la scansione in background."""
        # Se non sta già scansionando, oppure se è un comando forzato
        if not self.is_scanning:
            self.is_scanning = True
            threading.Thread(target=self._background_scan, daemon=True).start()

    def _background_scan(self):
        current = {}
        url_profs = self.settings.get("url_profiles", {})

        # Chrome Scanning
        for t in get_all_chrome_tabs():
            # Recuperiamo il nome del profilo associato all'URL (se esiste)
            prof_name = url_profs.get(t['url'], "Default")

            # Creiamo un testo descrittivo che include il profilo
            display_text = f"🌐 [{prof_name}] {t['title']}"
            key = f"{display_text} | {t['url']}"

            current[key] = {
                "type": "url",
                "value": t['url'],
                "parent_app": "Google Chrome",
                "text": display_text,
                "default": False,
                "profile": prof_name
            }

        # Apps & Files Scanning
        for app in get_active_apps():
            if app == "Google Chrome": continue
            paths = get_multiple_paths(app)
            if paths:
                for p in paths:
                    key = f"📄 {os.path.basename(p)} | {p}"
                    current[key] = {"type": "file", "value": p, "parent_app": app, "text": f"📄 {os.path.basename(p)}",
                                    "default": True}
            else:
                key = f"🖥️ {app} | {app}"
                current[key] = {"type": "app", "value": app, "parent_app": app, "text": f"🖥️ {app}", "default": True}

        self.after(0, lambda: self._apply_results(current))

    def _apply_results(self, current):
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
                self._add_checkbox(d, k, self.app_frames[p_app])
                self.found_items[k] = d
            else:
                self.found_items[k].update(d)

        for app_name in sorted(self.app_frames.keys()):
            self.app_frames[app_name].pack(fill="x", pady=5)

        self.check_dirty_state()
        self.is_scanning = False
        if self.current_session_name:
            self.lbl_status.configure(text="Synced", text_color="gray")
        else:
            self.lbl_status.configure(text="Ready", text_color="gray")

    def _add_checkbox(self, data, key, parent_frame):
        chk = ctk.CTkCheckBox(parent_frame, text=data["text"], command=self.check_dirty_state)
        chk.pack(fill="x", padx=(25, 5), pady=2)
        p_app = data["parent_app"]
        pref = self.settings.get("app_defaults", {}).get(p_app, data["default"])
        if pref:
            chk.select()
        else:
            chk.deselect()
        self.checkbox_vars[key] = chk
        u_val = data.get("value") if data["type"] == "url" else None
        chk.bind("<Button-2>", lambda e, a=p_app, u=u_val: self.show_context_menu(e, a, u))
        chk.bind("<Button-3>", lambda e, a=p_app, u=u_val: self.show_context_menu(e, a, u))
        chk._text_label.bind("<Button-2>", lambda e, a=p_app, u=u_val: self.show_context_menu(e, a, u))
        chk._text_label.bind("<Button-3>", lambda e, a=p_app, u=u_val: self.show_context_menu(e, a, u))

    def show_context_menu(self, event, app_name, url=None):
        menu = tk.Menu(self, tearoff=0)
        if app_name == "Google Chrome" and url:
            p_menu = tk.Menu(menu, tearoff=0)
            for name in self.chrome_profiles.keys():
                p_menu.add_command(label=name, command=lambda n=name, u=url: self.set_url_profile(u, n))
            menu.add_cascade(label="Assign Chrome Profile", menu=p_menu)
            menu.add_separator()
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
            self.lbl_status.configure(text="Unsaved Changes" if is_dirty else "Synced")
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
        messagebox.showinfo("Saved", f"Session {self.current_session_name} updated.")

    def close_apps(self):
        apps = set(v["parent_app"] for k, v in self.found_items.items() if self.checkbox_vars[k].get() == 1)
        for a in apps: run_applescript(f'tell application "{a}" to quit')

    def restore_menu(self):
        files = [f.replace(".json", "") for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        pop = ctk.CTkToplevel(self);
        pop.title("Open Session");
        pop.attributes("-alpha", 0)
        center_window(pop, 500, 400);
        pop.transient(self)
        txt = ctk.CTkTextbox(pop, height=180, state="disabled")

        def preview(c):
            with open(os.path.join(SESSIONS_DIR, f"{c}.json"), 'r') as f: data = json.load(f)
            txt.configure(state="normal");
            txt.delete("1.0", "end")
            for i in data: txt.insert("end", f"{'🌐' if i['type'] == 'url' else '📄'} {i['parent_app']}: {i['value']}\n")
            txt.configure(state="disabled")

        if files:
            sel = ctk.StringVar(value=files[0])
            ctk.CTkOptionMenu(pop, variable=sel, values=files, command=preview).pack(pady=10, padx=30, fill="x")
            txt.pack(pady=10, padx=30, fill="both", expand=True);
            preview(files[0])
            ctk.CTkButton(pop, text="Open Selected",
                          command=lambda: [self._load_session(sel.get()), pop.destroy()]).pack(pady=5, padx=30,
                                                                                               fill="x")
        ctk.CTkButton(pop, text="➕ New Blank", fg_color="gray",
                      command=lambda: [self._new_session(), pop.destroy()]).pack(pady=10, padx=30, fill="x")
        pop.after(100, lambda: pop.attributes("-alpha", 1.0))

    def _new_session(self):
        self.current_session_name = None;
        self.saved_data = []
        for w in self.frame_list.winfo_children(): w.destroy()
        self.checkbox_vars.clear()
        self.found_items.clear()
        self.app_frames.clear()
        self.trigger_scan()

    def _load_session(self, name):
        self.current_session_name = name
        with open(os.path.join(SESSIONS_DIR, f"{name}.json"), 'r') as f:
            self.saved_data = json.load(f)
        for i in self.saved_data:
            if i["type"] == "url" and i["parent_app"] == "Google Chrome":
                folder = self.chrome_profiles.get(i.get("profile", "Default"), "Default")
                os.system(f"open -na 'Google Chrome' --args --profile-directory='{folder}' '{i['value']}'")
            else:
                subprocess.run(["open", i["value"]])
        self.after(2000, self.trigger_scan)


if __name__ == "__main__":
    app = StudyManagerGUI()
    app.mainloop()
