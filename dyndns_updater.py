import tkinter as tk
from tkinter import messagebox
import requests
from requests.auth import HTTPBasicAuth
import threading
import time
import json
import os
import pystray
import sys
from PIL import Image

CONFIG_FILE = "dyndns_config.json"
DYNDNS_URL = "https://dyndns.strato.com/nic/update"

def get_public_ip():
    try:
        return requests.get("https://api.ipify.org").text.strip()
    except:
        return None

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class DomainEntry:
    def __init__(self, master, row):
        self.row = row
        self.hostname_var = tk.StringVar()
        tk.Entry(master, textvariable=self.hostname_var, width=20).grid(row=row, column=0, padx=5, pady=3, sticky="w")
        self.username_var = tk.StringVar()
        tk.Entry(master, textvariable=self.username_var, width=20).grid(row=row, column=1, padx=5, pady=3, sticky="w")
        self.password_var = tk.StringVar()
        tk.Entry(master, textvariable=self.password_var, width=20, show="*").grid(row=row, column=2, padx=5, pady=3, sticky="w")

        self.use_current_ip = tk.BooleanVar(value=True)
        self.ip_checkbox = tk.Checkbutton(master, variable=self.use_current_ip, command=self.toggle_ip_mode)
        self.ip_checkbox.grid(row=row, column=3, sticky="w", padx=(5,0), pady=3)

        self.manual_ip_var = tk.StringVar()
        self.manual_ip_entry = tk.Entry(master, textvariable=self.manual_ip_var, width=20, state="disabled")
        self.manual_ip_entry.grid(row=row, column=3, padx=(70,5), pady=3, sticky="w")
        self.manual_ip_entry.bind("<KeyRelease>", self.format_ip_input)

        self.interval_var = tk.IntVar(value=30)
        tk.Entry(master, textvariable=self.interval_var, width=6).grid(row=row, column=4, padx=5, pady=3)

        self.auto_var = tk.BooleanVar(value=False)
        self.auto_button = tk.Button(master, text="OFF", width=6, bg="red", command=self.toggle_auto)
        self.auto_button.grid(row=row, column=5, padx=5, pady=3)

        self.active = tk.BooleanVar(value=False)
        self.update_button = tk.Button(master, text="Inaktiv", width=10, bg="red", command=self.toggle_active)
        self.update_button.grid(row=row, column=6, padx=5, pady=3)

        self.status_var = tk.StringVar(value="Noch nicht aktualisiert")
        tk.Label(master, textvariable=self.status_var, width=25, anchor="w").grid(row=row, column=7, padx=5, pady=3)

        self.last_update_time = None
        self.time_since_var = tk.StringVar(value="-")
        tk.Label(master, textvariable=self.time_since_var, width=15, anchor="w").grid(row=row, column=8, padx=5, pady=3)

    def toggle_ip_mode(self):
        self.manual_ip_entry.config(state="disabled" if self.use_current_ip.get() else "normal")

    def format_ip_input(self, event=None):
        value = ''.join(c for c in self.manual_ip_var.get() if c.isdigit() or c == '.')
        parts = [p[:3] for p in value.split('.')][:4]
        self.manual_ip_var.set('.'.join(parts)[:15])

    def toggle_auto(self):
        self.auto_var.set(not self.auto_var.get())
        self.auto_button.config(text="ON" if self.auto_var.get() else "OFF",
                                bg="green" if self.auto_var.get() else "red")
        if not self.auto_var.get():
            self.active.set(False)
            self.update_button.config(text="Inaktiv", bg="red")

    def toggle_active(self):
        self.active.set(not self.active.get())
        self.update_button.config(text="Aktiv" if self.active.get() else "Inaktiv",
                                  bg="green" if self.active.get() else "red")

    def get_ip_to_use(self):
        return get_public_ip() if self.use_current_ip.get() else self.manual_ip_var.get()

    def update_time_since(self):
        if self.last_update_time and self.active.get() and self.auto_var.get():
            self.time_since_var.set(f"{int(time.time() - self.last_update_time)}s")
        elif not self.active.get():
            self.time_since_var.set("-")

class DynDNSApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("DynDNS Updater")
        self.root.geometry("1200x200")

        headers = ["Domain","User","Passwort","Manuell IP","Updatezeit","Automatik","Update","Status","Letztes Update"]
        for col, text in enumerate(headers):
            tk.Label(self.root, text=text, width=15, anchor="w").grid(row=0, column=col, padx=5, pady=3)

        self.domains = [DomainEntry(self.root, row=i+1) for i in range(5)]
        self.running = True
        self.load_config()

        threading.Thread(target=self.background_update_loop, daemon=True).start()
        threading.Thread(target=self.update_timers_loop, daemon=True).start()

        # Fenster schließen → nur in Tray
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Fenster standardmäßig versteckt
        self.root.withdraw()
        self.create_tray_icon()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            for i, domain in enumerate(data.get("domains", [])):
                if i >= len(self.domains): break
                d = self.domains[i]
                d.hostname_var.set(domain.get("hostname",""))
                d.username_var.set(domain.get("username",""))
                d.password_var.set(domain.get("password",""))
                d.use_current_ip.set(domain.get("use_current_ip", True))
                d.manual_ip_var.set(domain.get("manual_ip",""))
                d.interval_var.set(domain.get("interval",30))
                d.auto_var.set(domain.get("auto",False))
                d.auto_button.config(text="ON" if d.auto_var.get() else "OFF",
                                     bg="green" if d.auto_var.get() else "red")
                d.active.set(domain.get("active",False))
                d.update_button.config(text="Aktiv" if d.active.get() else "Inaktiv",
                                       bg="green" if d.active.get() else "red")
                d.toggle_ip_mode()

    def save_config(self):
        data = {"domains":[{
            "hostname": d.hostname_var.get(),
            "username": d.username_var.get(),
            "password": d.password_var.get(),
            "use_current_ip": d.use_current_ip.get(),
            "manual_ip": d.manual_ip_var.get(),
            "interval": d.interval_var.get(),
            "auto": d.auto_var.get(),
            "active": d.active.get()
        } for d in self.domains]}
        with open(CONFIG_FILE,"w") as f:
            json.dump(data,f,indent=2)

    def background_update_loop(self):
        while self.running:
            now = time.time()
            for d in self.domains:
                if d.active.get() and d.auto_var.get():
                    if not d.last_update_time or now - d.last_update_time >= d.interval_var.get():
                        ip = d.get_ip_to_use()
                        if ip:
                            try:
                                url = f"{DYNDNS_URL}?hostname={d.hostname_var.get()}&myip={ip}"
                                r = requests.get(url, auth=HTTPBasicAuth(d.username_var.get(), d.password_var.get()))
                                d.status_var.set(r.text.strip())
                                d.last_update_time = now
                            except Exception as e:
                                d.status_var.set(f"Fehler: {e}")
            self.save_config()
            time.sleep(1)

    def update_timers_loop(self):
        while self.running:
            for d in self.domains:
                d.update_time_since()
            time.sleep(1)

    def stop(self):
        self.running = False
        if getattr(self, "tray_icon", None):
            try: self.tray_icon.stop()
            except: pass
        if getattr(self, "root", None):
            try: self.root.destroy()
            except: pass
        sys.exit()
        
    def create_tray_icon(self):
        menu = pystray.Menu(
            pystray.MenuItem("Öffnen", self.show_window),
            pystray.MenuItem("Beenden", self.exit_app)
        )
        image = Image.open(resource_path("dns.ico"))
        self.tray_icon = pystray.Icon("DynDNS Updater", image, "DynDNS Updater", menu)
        
        # Startet den Tray-Icon-Thread als daemon
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()

    def exit_app(self, icon=None, item=None):
        """Programm komplett beenden"""
        self.running = False
        if getattr(self, "tray_icon", None):
            try:
                self.tray_icon.stop()  # Icon stoppen
            except:
                pass
        if getattr(self, "root", None):
            try:
                self.root.destroy()
            except:
                pass
        sys.exit()

    def show_window(self, icon=None, item=None):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(500, lambda: self.root.attributes("-topmost", False))

    def on_close(self):
        """Fenster schließen → nur in den Tray"""
        self.root.withdraw()
        if self.tray_icon:
            try: self.tray_icon.notify("DynDNS läuft weiter im Hintergrund")
            except: pass

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = DynDNSApp()
    app.run()
