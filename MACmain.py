import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import subprocess
import json
import os
import threading
import platform
from pathlib import Path
import time

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
            json.dump({"app_defaults": {}, "url_profiles": {}, "item_defaults": {}}, f)


def load_settings():
    default_structure = {"app_defaults": {}, "url_profiles": {}, "item_defaults": {}}
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            for key in default_structure:
                if key not in data: data[key] = {}
            return data
    except:
        return default_structure


def save_setting(category, key, value):
    data = load_settings()
    data[category][key] = value
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=4)


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
    if app_name == "YouTube Music": return []

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
    current_script_name = Path(__file__).stem
    script = 'tell application "System Events" to return name of every application process whose visible is true'
    res = run_applescript(script)
    if not res: return []

    to_ignore = [
        "Finder", "Terminal", "Python", "Code", "System Settings",
        "app_mode_loader", "Activity Monitor",
        "Study Manager", "Study Handler", "StudyManager", "StudyHandler",
        current_script_name
    ]

    found_apps = []
    for app in res.split(','):
        name = app.strip()
        if name not in to_ignore and "study" not in name.lower():
            found_apps.append(name)

    return found_apps


def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width / 2) - (width / 2))
    y = int((screen_height / 2) - (height / 2))
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

        self.frame_list = ctk.CTkScrollableFrame(self, label_text="Elements (Right-Click for granular defaults)")
        self.frame_list.pack(fill="both", expand=True, padx=30, pady=10)

        # Pulsanti nel main GUI
        ctk.CTkButton(self, text="💾 Save Session", command=self.save_session, fg_color="#28a745").pack(fill="x",
                                                                                                       padx=30, pady=5)

        # Frame per i due tasti di gestione
        manage_frame = ctk.CTkFrame(self, fg_color="transparent")
        manage_frame.pack(fill="x", padx=30, pady=5)

        ctk.CTkButton(manage_frame, text="📂 Open Session", command=self.restore_menu, fg_color="#17a2b8",
                      width=150).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkButton(manage_frame, text="⚙️ Manage", command=self.manage_sessions, fg_color="gray", width=100).pack(
            side="right", fill="x", expand=True)

        ctk.CTkButton(self, text="🛑 Close Selected Apps", command=self.close_apps, fg_color="#dc3545").pack(fill="x",
                                                                                                            padx=30,
                                                                                                            pady=(5,
                                                                                                                  20))

        center_window(self, 750, 750)
        self.after(100, lambda: self.attributes("-alpha", 1.0))
        self.deiconify()
        self.trigger_scan()
        self.auto_scan_loop()

    def auto_scan_loop(self):
        self.trigger_scan()
        self.after(5000, self.auto_scan_loop)

    def force_manual_scan(self):
        self.lbl_status.configure(text="Scanning...", text_color="#17a2b8")
        self.trigger_scan(force=True)

    def trigger_scan(self, force=False):
        if not self.is_scanning:
            self.is_scanning = True
            threading.Thread(target=self._background_scan, daemon=True).start()

    def _background_scan(self):
        current = {}
        url_profs = self.settings.get("url_profiles", {})
        active_apps = get_active_apps()

        # Chrome Scanning (Solo se aperto, evita riavvii indesiderati)
        if "Google Chrome" in active_apps:
            for t in get_all_chrome_tabs():
                prof_name = url_profs.get(t['url'], "Default")
                display_text = f"🌐 [{prof_name}] {t['title']}"
                key = f"{t['url']}"

                current[key] = {
                    "type": "url", "value": t['url'], "parent_app": "Google Chrome",
                    "text": display_text, "default": False, "profile": prof_name
                }

        # Apps & Files Scanning
        for app in active_apps:
            if app == "Google Chrome": continue
            paths = get_multiple_paths(app)
            if paths:
                for p in paths:
                    key = p
                    current[key] = {"type": "file", "value": p, "parent_app": app, "text": f"📄 {os.path.basename(p)}",
                                    "default": True}
            else:
                key = app
                icon = "🎵" if app == "YouTube Music" else "🖥️"
                current[key] = {"type": "app", "value": app, "parent_app": app, "text": f"{icon} {app}",
                                "default": True}

        self.after(0, lambda: self._apply_results(current))

    def _apply_results(self, current):
        keys_to_remove = [k for k in list(self.found_items.keys()) if k not in current]
        for k in keys_to_remove:
            p_app = self.found_items[k]["parent_app"]
            if k in self.checkbox_vars:
                self.checkbox_vars[k].destroy()
                del self.checkbox_vars[k]
            del self.found_items[k]
            if p_app in self.app_frames and len(self.app_frames[p_app].winfo_children()) <= 1:
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

        self.check_dirty_state()
        self.is_scanning = False
        self.lbl_status.configure(text="Synced" if self.current_session_name else "Ready", text_color="gray")

    def _add_checkbox(self, data, key, parent_frame):
        chk = ctk.CTkCheckBox(parent_frame, text=data["text"], command=self.check_dirty_state)
        chk.pack(fill="x", padx=(25, 5), pady=2)

        p_app = data["parent_app"]

        # Default Logic
        item_pref = self.settings.get("item_defaults", {}).get(key, None)
        app_pref = self.settings.get("app_defaults", {}).get(p_app, None)

        final_state = data["default"]
        if app_pref is not None: final_state = app_pref
        if item_pref is not None: final_state = item_pref

        if final_state:
            chk.select()
        else:
            chk.deselect()

        self.checkbox_vars[key] = chk

        for widget in [chk, chk._text_label]:
            widget.bind("<Button-2>", lambda e, k=key, d=data: self.show_context_menu(e, k, d))
            widget.bind("<Button-3>", lambda e, k=key, d=data: self.show_context_menu(e, k, d))

    def show_context_menu(self, event, key, data):
        menu = tk.Menu(self, tearoff=0)
        app_name = data["parent_app"]
        val = data["value"]

        if app_name == "Google Chrome":
            p_menu = tk.Menu(menu, tearoff=0)
            for name in self.chrome_profiles.keys():
                p_menu.add_command(label=name, command=lambda n=name, u=val: self.set_url_profile(u, n))
            menu.add_cascade(label="Assign Chrome Profile", menu=p_menu)
            menu.add_separator()

        menu.add_command(label=f"Always SELECT THIS ITEM", command=lambda: self.set_granular_default(key, True))
        menu.add_command(label=f"Always DESELECT THIS ITEM", command=lambda: self.set_granular_default(key, False))
        menu.add_command(label=f"Reset Item Rule", command=lambda: self.set_granular_default(key, None))
        menu.add_separator()

        menu.add_command(label=f"Default SELECT all {app_name}", command=lambda: self.set_app_default(app_name, True))
        menu.add_command(label=f"Default DESELECT all {app_name}",
                         command=lambda: self.set_app_default(app_name, False))

        menu.tk_popup(event.x_root, event.y_root)

    def set_granular_default(self, key, state):
        data = load_settings()
        if state is None:
            if key in data["item_defaults"]: del data["item_defaults"][key]
        else:
            data["item_defaults"][key] = state
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        self.settings = load_settings()
        self.trigger_scan()

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
        messagebox.showinfo("Saved", f"Session {self.current_session_name} updated.")

    def close_apps(self):
        # Prendiamo solo gli elementi effettivamente spuntati
        selected_items = [v for k, v in self.found_items.items() if self.checkbox_vars[k].get() == 1]

        for item in selected_items:
            i_type = item["type"]
            app_name = item["parent_app"]
            # Facciamo l'escape di eventuali virgolette nel nome o nell'URL per non rompere l'AppleScript
            val = item["value"].replace('"', '\\"')

            # 1. CHIUSURA CHIRURGICA TAB DI CHROME
            if i_type == "url" and app_name == "Google Chrome":
                script = f'''
                tell application "Google Chrome"
                    try
                        repeat with w in windows
                            set i to 1
                            repeat while i ≤ (count of tabs of w)
                                if URL of tab i of w is "{val}" then
                                    close tab i of w
                                else
                                    set i to i + 1
                                end if
                            end repeat
                        end repeat
                    end try
                end tell
                '''
                run_applescript(script)

            # 2. CHIUSURA CHIRURGICA SINGOLI FILE/DOCUMENTI
            elif i_type == "file":
                app_target = "Preview" if app_name in ["Anteprima", "Preview"] else app_name
                doc_entities = {
                    "Preview": ("document", "path"),
                    "Microsoft Word": ("document", "full name"),
                    "Microsoft Excel": ("workbook", "full name"),
                    "Microsoft PowerPoint": ("presentation", "full name")
                }

                if app_target in doc_entities:
                    entity, prop = doc_entities[app_target]
                    script = f'''
                    tell application "{app_target}"
                        try
                            close (every {entity} whose {prop} is "{val}")
                        end try
                    end tell
                    '''
                    run_applescript(script)

            # 3. CHIUSURA APP STANDALONE (Es. WhatsApp, YouTube Music)
            elif i_type == "app":
                run_applescript(f'tell application "{app_name}" to quit')

        # Diamo tempo a macOS di chiudere le finestre e aggiorniamo la UI
        self.after(1000, self.trigger_scan)

    # --- SESSION MANAGEMENT ---
    def manage_sessions(self):
        files = [f.replace(".json", "") for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
        if not files:
            messagebox.showinfo("Manage", "No saved sessions found.")
            return

        pop = ctk.CTkToplevel(self)
        pop.title("Manage Sessions")

        # 1. Rendi la finestra completamente trasparente appena nasce
        pop.attributes("-alpha", 0)

        # 2. Posizionala al centro mentre è invisibile
        center_window(pop, 400, 500)

        # 3. Rendila "figlia" della finestra principale, così non sta sopra le altre app del Mac
        pop.transient(self)

        scroll = ctk.CTkScrollableFrame(pop)
        scroll.pack(fill="both", expand=True, padx=20, pady=20)

        def refresh_manager():
            for child in scroll.winfo_children(): child.destroy()
            current_files = [f.replace(".json", "") for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
            for f_name in current_files:
                f_frame = ctk.CTkFrame(scroll)
                f_frame.pack(fill="x", pady=5)
                ctk.CTkLabel(f_frame, text=f_name, anchor="w").pack(side="left", padx=10, fill="x", expand=True)

                ctk.CTkButton(f_frame, text="✏️", width=30, fg_color="gray",
                              command=lambda n=f_name: self.rename_session(n, refresh_manager)).pack(side="left",
                                                                                                     padx=2)
                ctk.CTkButton(f_frame, text="🗑️", width=30, fg_color="#dc3545",
                              command=lambda n=f_name: self.delete_session(n, refresh_manager)).pack(side="left",
                                                                                                     padx=2)

        refresh_manager()

        # 4. Falli riapparire dolcemente un attimo dopo, quando è già al centro
        pop.after(100, lambda: pop.attributes("-alpha", 1.0))

    def delete_session(self, name, refresh_callback):
        if messagebox.askyesno("Delete", f"Are you sure you want to delete '{name}'?"):
            os.remove(os.path.join(SESSIONS_DIR, f"{name}.json"))
            if self.current_session_name == name:
                self._new_session()
            refresh_callback()

    def rename_session(self, old_name, refresh_callback):
        new_name = ctk.CTkInputDialog(text=f"Rename '{old_name}' to:", title="Rename").get_input()
        if new_name and new_name != old_name:
            old_path = os.path.join(SESSIONS_DIR, f"{old_name}.json")
            new_path = os.path.join(SESSIONS_DIR, f"{new_name}.json")
            if os.path.exists(new_path):
                messagebox.showerror("Error", "A session with this name already exists.")
            else:
                os.rename(old_path, new_path)
                if self.current_session_name == old_name:
                    self.current_session_name = new_name
                    self.check_dirty_state()
                refresh_callback()

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
            txt.pack(pady=10, padx=30, fill="both", expand=True)
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
        self.checkbox_vars.clear();
        self.found_items.clear();
        self.app_frames.clear();
        self.trigger_scan()

    def _load_session(self, name):
        self.current_session_name = name
        try:
            with open(os.path.join(SESSIONS_DIR, f"{name}.json"), 'r') as f:
                self.saved_data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load session file: {e}")
            return

        # Recuperiamo gli URL già aperti per evitare duplicati
        open_urls = []
        if "Google Chrome" in get_active_apps():
            open_urls = [t['url'] for t in get_all_chrome_tabs()]

        chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

        # 1. GESTIONE APPLICAZIONI (Tornata semplice e pulita per le vere App come WhatsApp)
        for i in self.saved_data:
            if i["type"] == "app":
                app_name = i["value"]
                # Cerca di aprire l'app nativa. Il flag -a dice a macOS di cercare l'applicazione ovunque sia.
                subprocess.run(["open", "-a", app_name])
                time.sleep(0.5)

        # 2. GESTIONE FILE (Documenti, PDF, ecc.)
        for i in self.saved_data:
            if i["type"] == "file":
                subprocess.run(["open", i["value"]])

        # 3. GESTIONE URL CHROME
        for i in self.saved_data:
            if i["type"] == "url" and i["parent_app"] == "Google Chrome":

                if i["value"] in open_urls:
                    continue

                folder = self.settings.get("url_profiles", {}).get(i["value"], "Default")

                # ---> LA MOSSA DEL CAVALLO PER YOUTUBE MUSIC <---
                if "music.youtube.com" in i["value"]:
                    # Intercettiamo l'URL e forziamo l'apertura dell'App fisica!
                    # L'app fisica sa già in automatico quale profilo e utente usare.
                    subprocess.run(["open", "-a", "YouTube Music"])
                    time.sleep(0.5)
                    continue  # Passa al prossimo link

                # ---> APERTURA TAB NORMALI BROWSER <---
                if os.path.exists(chrome_bin):
                    subprocess.Popen([chrome_bin, f"--profile-directory={folder}", i['value']])
                else:
                    os.system(f"open -na 'Google Chrome' --args --profile-directory='{folder}' '{i['value']}'")

                time.sleep(0.5)

        self.after(2000, self.trigger_scan)


if __name__ == "__main__":
    app = StudyManagerGUI()
    app.mainloop()
