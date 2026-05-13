import customtkinter as ctk
from tkinter import messagebox, simpledialog
import subprocess
import json
import os

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

CARTELLA_PROFILI = "sessioni_studio_mac"


def setup():
    if not os.path.exists(CARTELLA_PROFILI):
        os.makedirs(CARTELLA_PROFILI)


def esegui_applescript(script):
    try:
        process = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = process.communicate()
        if process.returncode == 0:
            return out.decode('utf-8').strip()
        return None
    except Exception:
        return None


def ottieni_percorsi_multipli(app_name):
    """Esegue un loop in AppleScript per trovare TUTTI i file aperti di quell'app."""
    app_target = app_name
    if app_name == "Anteprima":
        app_target = "Preview"

    # Dizionario che dice ad AppleScript dove cercare in base all'app
    doc_entities = {
        "Preview": ("documents", "path"),
        "Anteprima": ("documents", "path"),
        "Microsoft Word": ("documents", "full name"),
        "Microsoft Excel": ("workbooks", "full name"),
        "Microsoft PowerPoint": ("presentations", "full name")
    }

    if app_name not in doc_entities:
        return []

    entita, proprieta = doc_entities[app_name]

    # Questo script interroga tutte le finestre dell'app e unisce i percorsi con un separatore "|||"
    script = f'''
    tell application "{app_target}"
        set pathList to {{}}
        repeat with doc in {entita}
            try
                set docPath to {proprieta} of doc
                if docPath is not missing value then
                    set end of pathList to docPath
                end if
            end try
        end repeat
        set AppleScript's text item delimiters to "|||"
        return pathList as text
    end tell
    '''

    risultato = esegui_applescript(script)
    if risultato:
        # Separiamo la stringa in una vera lista Python
        return [p.strip() for p in risultato.split("|||") if p.strip()]
    return []


def ottieni_app_attive():
    script = '''
    tell application "System Events"
        set activeApps to name of every application process whose visible is true
    end tell
    set AppleScript's text item delimiters to ","
    return activeApps as text
    '''
    risultato = esegui_applescript(script)
    if risultato:
        app_list = [app.strip() for app in risultato.split(',')]
        da_ignorare = ["Finder", "Terminal", "Python", "Mac Study Manager", "Code", "System Settings"]
        return [app for app in app_list if app not in da_ignorare]
    return []


def ottieni_url_browser(browser_name):
    if browser_name == "Safari":
        return esegui_applescript('tell application "Safari" to return URL of front document')
    elif browser_name in ["Google Chrome", "Chrome"]:
        return esegui_applescript('tell application "Google Chrome" to return URL of active tab of front window')
    return None


class StudyManagerGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mac Study Manager v3")
        self.geometry("500x650")

        setup()
        self.elementi_trovati = {}
        self.checkbox_vars = {}

        # UI Principale
        self.label_titolo = ctk.CTkLabel(self, text="📚 Gestore Studio Avanzato",
                                         font=ctk.CTkFont(size=20, weight="bold"))
        self.label_titolo.pack(pady=15)

        self.btn_scansiona = ctk.CTkButton(self, text="🔍 Scansiona App e File Aperti", command=self.scansiona)
        self.btn_scansiona.pack(fill="x", padx=30, pady=5)

        self.frame_lista = ctk.CTkScrollableFrame(self, label_text="Elementi Rilevati")
        self.frame_lista.pack(fill="both", expand=True, padx=30, pady=15)

        self.btn_salva = ctk.CTkButton(self, text="💾 Salva Sessione", command=self.salva_sessione, fg_color="#28a745",
                                       hover_color="#218838")
        self.btn_salva.pack(fill="x", padx=30, pady=5)

        self.btn_chiudi = ctk.CTkButton(self, text="🛑 Chiudi App Selezionate", command=self.chiudi_sessione,
                                        fg_color="#dc3545", hover_color="#c82333")
        self.btn_chiudi.pack(fill="x", padx=30, pady=5)

        self.divisore = ctk.CTkFrame(self, height=2, fg_color=("gray70", "gray30"))
        self.divisore.pack(fill="x", padx=50, pady=10)

        self.btn_ripristina = ctk.CTkButton(self, text="🚀 Menu Ripristino Sessione", command=self.menu_ripristino,
                                            fg_color="#17a2b8", hover_color="#138496")
        self.btn_ripristina.pack(fill="x", padx=30, pady=(0, 20))

    def scansiona(self):
        # Pulisce UI
        for widget in self.frame_lista.winfo_children():
            widget.destroy()
        self.checkbox_vars.clear()
        self.elementi_trovati.clear()

        app_attive = ottieni_app_attive()

        for app in app_attive:
            # 1. Browser
            if app in ["Safari", "Google Chrome", "Chrome"]:
                url = ottieni_url_browser(app)
                if url and "http" in url:
                    self._aggiungi_checkbox("url", url, app, f"🌐 {app}: {url[:40]}...")
                else:
                    self._aggiungi_checkbox("app", app, app, f"🖥️ {app} (Nessuna pagina)")

            # 2. App Documenti (Supporta file multipli)
            elif app in ["Preview", "Anteprima", "Microsoft Word", "Microsoft Excel", "Microsoft PowerPoint"]:
                percorsi = ottieni_percorsi_multipli(app)
                if percorsi:
                    for percorso in percorsi:
                        nome_file = os.path.basename(percorso)
                        self._aggiungi_checkbox("file", percorso, app, f"📄 {app}: {nome_file}")
                else:
                    self._aggiungi_checkbox("app", app, app, f"🖥️ {app} (Aperta ma senza file)")

            # 3. App generiche
            else:
                self._aggiungi_checkbox("app", app, app, f"🖥️ {app}")

    def _aggiungi_checkbox(self, tipo, valore, app_madre, testo_display):
        """Metodo helper per creare le spunte grafiche"""
        # Creiamo una chiave unica nel caso ci siano file con lo stesso nome
        chiave = f"{testo_display} | {valore}"

        chk = ctk.CTkCheckBox(self.frame_lista, text=testo_display)
        chk.select()
        chk.pack(fill="x", padx=5, pady=5)

        self.checkbox_vars[chiave] = chk
        self.elementi_trovati[chiave] = {"tipo": tipo, "valore": valore, "app_madre": app_madre}

    def salva_sessione(self):
        if not self.checkbox_vars: return
        nome = simpledialog.askstring("Salva", "Nome materia (es. Matematica):")
        if not nome: return

        da_salvare = [self.elementi_trovati[chiave] for chiave, chk in self.checkbox_vars.items() if chk.get() == 1]

        with open(os.path.join(CARTELLA_PROFILI, f"{nome.lower()}.json"), 'w') as f:
            json.dump(da_salvare, f, indent=4)
        messagebox.showinfo("OK", "Sessione salvata con successo!")

    def chiudi_sessione(self):
        # NOTA: AppleScript usa il comando 'quit' sull'intera app, quindi chiuderà tutti i file di quell'app.
        app_da_chiudere = set(
            self.elementi_trovati[chiave]["app_madre"] for chiave, chk in self.checkbox_vars.items() if chk.get() == 1)
        for app in app_da_chiudere:
            esegui_applescript(f'tell application "{app}" to quit')

    def menu_ripristino(self):
        file_salvati = [f.replace(".json", "") for f in os.listdir(CARTELLA_PROFILI) if f.endswith(".json")]

        if not file_salvati:
            messagebox.showwarning("Attenzione", "Nessuna sessione salvata trovata.")
            return

        # Creiamo una sottofinestra elegante per scegliere
        popup = ctk.CTkToplevel(self)
        popup.title("Scegli Sessione")
        popup.geometry("350x200")
        popup.transient(self)  # Lega il popup alla finestra madre
        popup.grab_set()  # Blocca i bottoni sotto finché non chiudi il popup

        ctk.CTkLabel(popup, text="Seleziona la materia da avviare:", font=ctk.CTkFont(size=16, weight="bold")).pack(
            pady=(20, 10))

        # Menu a tendina nativo di CustomTkinter
        opzione_selezionata = ctk.StringVar(value=file_salvati[0])
        dropdown = ctk.CTkOptionMenu(popup, variable=opzione_selezionata, values=file_salvati)
        dropdown.pack(pady=10, padx=30, fill="x")

        def conferma_avvio():
            nome = opzione_selezionata.get()
            popup.destroy()  # Chiude il popup
            self._esegui_ripristino(nome)

        ctk.CTkButton(popup, text="🚀 Avvia", command=conferma_avvio, fg_color="#17a2b8").pack(pady=10)

    def _esegui_ripristino(self, nome_sessione):
        path = os.path.join(CARTELLA_PROFILI, f"{nome_sessione.lower()}.json")
        if not os.path.exists(path): return

        with open(path, 'r') as f:
            dati = json.load(f)

        for item in dati:
            if item["tipo"] == "file":
                subprocess.run(["open", item["valore"]])
            elif item["tipo"] == "url":
                subprocess.run(["open", "-a", item["app_madre"], item["valore"]])
            else:
                subprocess.run(["open", "-a", item["valore"]])


if __name__ == "__main__":
    app = StudyManagerGUI()
    app.after(100, lambda: app.focus_force())
    app.mainloop()
