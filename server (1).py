"""
Serveur de supervision - Multi-clients avec pool de threads
Interface graphique Tkinter + SQLite avec pool de connexions
"""

import socket
import json
import threading
import time
import logging
import queue
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ─── Configuration ───────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 9999
MAX_WORKERS = 20          # Pool de threads (ThreadPoolExecutor)
DB_POOL_SIZE = 5          # Pool de connexions BD
TIMEOUT_INACTIVE = 90     # secondes avant de considérer un nœud en panne
DB_FILE = "supervision.db"
LOG_FILE = "supervision.log"

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ─── Pool de connexions SQLite ────────────────────────────────────────────────
class DBConnectionPool:
    """Pool de connexions SQLite pour accès concurrent"""
    def __init__(self, db_file, pool_size):
        self.db_file = db_file
        self.pool = queue.Queue(maxsize=pool_size)
        for _ in range(pool_size):
            conn = sqlite3.connect(db_file, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self.pool.put(conn)
        logger.info(f"Pool BD initialisé avec {pool_size} connexions")

    def get_connection(self, timeout=10):
        return self.pool.get(timeout=timeout)

    def release_connection(self, conn):
        self.pool.put(conn)

    def execute(self, query, params=()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor
        finally:
            self.release_connection(conn)

    def fetchall(self, query, params=()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            self.release_connection(conn)

    def fetchone(self, query, params=()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
        finally:
            self.release_connection(conn)

# ─── Initialisation BD ───────────────────────────────────────────────────────
def init_database(pool):
    conn = pool.get_connection()
    try:
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT UNIQUE NOT NULL,
                os TEXT,
                cpu_type TEXT,
                last_seen TEXT,
                status TEXT DEFAULT 'ACTIVE'
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                cpu REAL,
                memory REAL,
                disk REAL,
                uptime INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_id INTEGER,
                node_id TEXT,
                service_name TEXT,
                status TEXT,
                timestamp TEXT
            );

            CREATE TABLE IF NOT EXISTS ports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_id INTEGER,
                node_id TEXT,
                port INTEGER,
                status TEXT,
                timestamp TEXT
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT,
                message TEXT,
                timestamp TEXT DEFAULT (datetime('now')),
                resolved INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                message TEXT,
                timestamp TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        logger.info("Base de données initialisée")
    finally:
        pool.release_connection(conn)

# ─── Gestionnaire de client ───────────────────────────────────────────────────
class ClientHandler:
    def __init__(self, conn, addr, pool, server_ref):
        self.conn = conn
        self.addr = addr
        self.pool = pool
        self.server = server_ref
        self.node_id = None
        self.last_seen = time.time()
        self.running = True

    def handle(self):
        logger.info(f"Nouvelle connexion: {self.addr}")
        buffer = ""
        self.conn.settimeout(5)
        try:
            while self.running:
                try:
                    data = self.conn.recv(4096).decode('utf-8')
                    if not data:
                        break
                    buffer += data
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if line.strip():
                            self.process_message(line.strip())
                except socket.timeout:
                    # Vérifier timeout inactivité
                    if time.time() - self.last_seen > TIMEOUT_INACTIVE:
                        self.mark_node_down()
                        break
                    continue
                except Exception as e:
                    logger.error(f"Erreur réception [{self.addr}]: {e}")
                    break
        finally:
            self.cleanup()

    def process_message(self, raw_msg):
        """Valide et traite un message reçu"""
        try:
            data = json.loads(raw_msg)
        except json.JSONDecodeError:
            logger.warning(f"Message invalide de {self.addr}: {raw_msg[:100]}")
            return

        if not self.validate_message(data):
            logger.warning(f"Message mal formaté de {self.addr}")
            return

        self.last_seen = time.time()
        msg_type = data.get("type", "METRICS")

        if msg_type == "METRICS":
            self.node_id = data.get("node")
            self.save_metrics(data)
            self.server.update_node_display(data)

    def validate_message(self, data):
        """Valide le format du message"""
        required = ["node", "timestamp", "cpu", "memory", "disk", "uptime"]
        return all(k in data for k in required)

    def save_metrics(self, data):
        """Sauvegarde les métriques dans la BD"""
        try:
            node_id = data["node"]
            ts = data["timestamp"]

            # Upsert nœud
            self.pool.execute("""
                INSERT INTO nodes (node_id, os, cpu_type, last_seen, status)
                VALUES (?, ?, ?, ?, 'ACTIVE')
                ON CONFLICT(node_id) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    status='ACTIVE',
                    os=excluded.os,
                    cpu_type=excluded.cpu_type
            """, (node_id, data.get("os",""), data.get("cpu_type",""), ts))

            # Métriques
            cur = self.pool.execute("""
                INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, uptime)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (node_id, ts, data["cpu"], data["memory"], data["disk"], data["uptime"]))

            metric_id = cur.lastrowid

            # Services
            for svc, status in data.get("services", {}).items():
                self.pool.execute("""
                    INSERT INTO services (metric_id, node_id, service_name, status, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (metric_id, node_id, svc, status, ts))

            # Ports
            for port, status in data.get("ports", {}).items():
                self.pool.execute("""
                    INSERT INTO ports (metric_id, node_id, port, status, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (metric_id, node_id, int(port), status, ts))

            # Alertes
            for alert in data.get("alerts", []):
                self.pool.execute("""
                    INSERT INTO alerts (node_id, message) VALUES (?, ?)
                """, (node_id, alert))
                logger.warning(f"ALERTE [{node_id}]: {alert}")
                self.pool.execute(
                    "INSERT INTO logs (level, message) VALUES ('ALERT', ?)",
                    (f"[{node_id}] {alert}",)
                )

        except Exception as e:
            logger.error(f"Erreur sauvegarde BD: {e}")

    def mark_node_down(self):
        if self.node_id:
            self.pool.execute(
                "UPDATE nodes SET status='DOWN' WHERE node_id=?",
                (self.node_id,)
            )
            self.pool.execute(
                "INSERT INTO logs (level, message) VALUES ('DOWN', ?)",
                (f"Nœud {self.node_id} considéré en panne (timeout {TIMEOUT_INACTIVE}s)",)
            )
            logger.warning(f"Nœud EN PANNE: {self.node_id}")
            self.server.notify_node_down(self.node_id)

    def send_command(self, action, target=""):
        """Envoie une commande au client"""
        try:
            cmd = json.dumps({"type": "COMMAND", "action": action, "target": target}) + "\n"
            self.conn.sendall(cmd.encode('utf-8'))
            logger.info(f"Commande [{action}→{target}] envoyée à {self.node_id}")
        except Exception as e:
            logger.error(f"Erreur envoi commande: {e}")

    def cleanup(self):
        self.running = False
        try:
            self.conn.close()
        except Exception:
            pass
        if self.node_id:
            self.server.remove_client(self.node_id)
        logger.info(f"Client déconnecté: {self.addr}")


# ─── Serveur TCP ──────────────────────────────────────────────────────────────
class SupervisionServer:
    def __init__(self):
        self.pool = DBConnectionPool(DB_FILE, DB_POOL_SIZE)
        init_database(self.pool)
        self.clients = {}          # node_id -> ClientHandler
        self.clients_lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self.running = False
        self.gui = None
        self.server_sock = None

    def start(self):
        self.running = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((HOST, PORT))
        self.server_sock.listen(50)
        self.server_sock.settimeout(1)
        logger.info(f"Serveur démarré sur {HOST}:{PORT}")
        logger.info(f"Pool de threads: ThreadPoolExecutor (max={MAX_WORKERS})")

        threading.Thread(target=self.accept_loop, daemon=True).start()
        threading.Thread(target=self.watchdog_loop, daemon=True).start()

    def accept_loop(self):
        while self.running:
            try:
                conn, addr = self.server_sock.accept()
                handler = ClientHandler(conn, addr, self.pool, self)
                self.executor.submit(handler.handle)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Erreur accept: {e}")

    def watchdog_loop(self):
        """Surveille les nœuds inactifs"""
        while self.running:
            time.sleep(30)
            with self.clients_lock:
                for nid, handler in list(self.clients.items()):
                    if time.time() - handler.last_seen > TIMEOUT_INACTIVE:
                        handler.mark_node_down()

    def remove_client(self, node_id):
        with self.clients_lock:
            self.clients.pop(node_id, None)

    def update_node_display(self, data):
        """Mise à jour de l'interface GUI"""
        node_id = data["node"]
        with self.clients_lock:
            pass  # déjà géré dans handle
        if self.gui:
            self.gui.update_node(data)

    def notify_node_down(self, node_id):
        if self.gui:
            self.gui.notify_down(node_id)

    def send_command_to_node(self, node_id, action, target):
        with self.clients_lock:
            handler = self.clients.get(node_id)
        if handler:
            handler.send_command(action, target)
            return True
        return False

    def get_all_nodes(self):
        return self.pool.fetchall("SELECT * FROM nodes ORDER BY last_seen DESC")

    def get_recent_metrics(self, node_id, limit=20):
        return self.pool.fetchall(
            "SELECT * FROM metrics WHERE node_id=? ORDER BY id DESC LIMIT ?",
            (node_id, limit)
        )

    def get_recent_alerts(self, limit=50):
        return self.pool.fetchall(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        )

    def get_logs(self, limit=100):
        return self.pool.fetchall(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
        )

    def stop(self):
        self.running = False
        self.executor.shutdown(wait=False)
        if self.server_sock:
            self.server_sock.close()


# ─── Interface Graphique Tkinter ──────────────────────────────────────────────
class SupervisionGUI:
    def __init__(self, server):
        self.server = server
        server.gui = self
        self.root = tk.Tk()
        self.root.title("🖥️  Serveur de Supervision Réseau")
        self.root.geometry("1100x700")
        self.root.configure(bg="#1e1e2e")
        self.node_data = {}  # node_id -> dernières données
        self._build_ui()
        self._start_refresh()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#1e1e2e", borderwidth=0)
        style.configure("TNotebook.Tab", background="#313244", foreground="white",
                        padding=[12, 5], font=("Helvetica", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#89b4fa")])
        style.configure("Treeview", background="#313244", foreground="white",
                        fieldbackground="#313244", font=("Courier", 9))
        style.configure("Treeview.Heading", background="#45475a", foreground="white",
                        font=("Helvetica", 9, "bold"))

        # ─── Titre ───
        header = tk.Frame(self.root, bg="#181825", pady=8)
        header.pack(fill="x")
        tk.Label(header, text="🖥️  Système Distribué de Supervision Réseau",
                 font=("Helvetica", 15, "bold"), bg="#181825", fg="#cdd6f4").pack()
        tk.Label(header, text=f"Serveur: {HOST}:{PORT}  |  Pool threads: {MAX_WORKERS}  |  BD Pool: {DB_POOL_SIZE}",
                 font=("Helvetica", 9), bg="#181825", fg="#6c7086").pack()

        # ─── Onglets ───
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_tab_nodes()
        self._build_tab_metrics()
        self._build_tab_alerts()
        self._build_tab_logs()
        self._build_tab_admin()

    # ── Onglet 1 : Nœuds ──────────────────────────────────────────────────────
    def _build_tab_nodes(self):
        frame = tk.Frame(self.notebook, bg="#1e1e2e")
        self.notebook.add(frame, text="📡 Nœuds")

        # Stats rapides
        stats_frame = tk.Frame(frame, bg="#1e1e2e")
        stats_frame.pack(fill="x", padx=10, pady=5)
        self.lbl_total = self._stat_box(stats_frame, "Total nœuds", "0", "#89b4fa")
        self.lbl_active = self._stat_box(stats_frame, "Actifs", "0", "#a6e3a1")
        self.lbl_down = self._stat_box(stats_frame, "En panne", "0", "#f38ba8")
        self.lbl_alerts = self._stat_box(stats_frame, "Alertes", "0", "#fab387")

        # Tableau nœuds
        cols = ("Node ID", "OS", "CPU%", "MEM%", "DISK%", "Uptime", "Statut", "Dernière vue")
        self.tree_nodes = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        for col in cols:
            self.tree_nodes.heading(col, text=col)
            self.tree_nodes.column(col, width=120, anchor="center")
        self.tree_nodes.column("Node ID", width=160)
        self.tree_nodes.column("OS", width=150)

        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree_nodes.yview)
        self.tree_nodes.configure(yscrollcommand=scroll.set)
        self.tree_nodes.pack(side="left", fill="both", expand=True, padx=(10,0), pady=5)
        scroll.pack(side="right", fill="y", pady=5, padx=(0,10))

        # Couleurs statut
        self.tree_nodes.tag_configure("active", foreground="#a6e3a1")
        self.tree_nodes.tag_configure("down", foreground="#f38ba8")
        self.tree_nodes.tag_configure("alert", foreground="#fab387")

    def _stat_box(self, parent, label, value, color):
        f = tk.Frame(parent, bg="#313244", relief="flat", padx=15, pady=8)
        f.pack(side="left", padx=6)
        tk.Label(f, text=label, bg="#313244", fg="#9399b2", font=("Helvetica", 8)).pack()
        lbl = tk.Label(f, text=value, bg="#313244", fg=color, font=("Helvetica", 16, "bold"))
        lbl.pack()
        return lbl

    # ── Onglet 2 : Métriques ──────────────────────────────────────────────────
    def _build_tab_metrics(self):
        frame = tk.Frame(self.notebook, bg="#1e1e2e")
        self.notebook.add(frame, text="📊 Métriques")

        top = tk.Frame(frame, bg="#1e1e2e")
        top.pack(fill="x", padx=10, pady=5)
        tk.Label(top, text="Nœud :", bg="#1e1e2e", fg="#cdd6f4").pack(side="left")
        self.node_var = tk.StringVar()
        self.node_combo = ttk.Combobox(top, textvariable=self.node_var, width=25)
        self.node_combo.pack(side="left", padx=5)
        tk.Button(top, text="Afficher", command=self.load_metrics,
                  bg="#89b4fa", fg="#1e1e2e", font=("Helvetica", 9, "bold")).pack(side="left")

        cols = ("Timestamp", "CPU%", "MEM%", "DISK%", "Uptime (s)")
        self.tree_metrics = ttk.Treeview(frame, columns=cols, show="headings", height=20)
        for col in cols:
            self.tree_metrics.heading(col, text=col)
            self.tree_metrics.column(col, width=180, anchor="center")
        scroll2 = ttk.Scrollbar(frame, orient="vertical", command=self.tree_metrics.yview)
        self.tree_metrics.configure(yscrollcommand=scroll2.set)
        self.tree_metrics.pack(side="left", fill="both", expand=True, padx=(10,0), pady=5)
        scroll2.pack(side="right", fill="y", pady=5, padx=(0,10))

    # ── Onglet 3 : Alertes ────────────────────────────────────────────────────
    def _build_tab_alerts(self):
        frame = tk.Frame(self.notebook, bg="#1e1e2e")
        self.notebook.add(frame, text="⚠️ Alertes")

        cols = ("ID", "Node ID", "Message", "Timestamp")
        self.tree_alerts = ttk.Treeview(frame, columns=cols, show="headings", height=22)
        widths = [50, 160, 500, 200]
        for col, w in zip(cols, widths):
            self.tree_alerts.heading(col, text=col)
            self.tree_alerts.column(col, width=w, anchor="w")
        self.tree_alerts.tag_configure("alert_row", foreground="#fab387")
        scroll3 = ttk.Scrollbar(frame, orient="vertical", command=self.tree_alerts.yview)
        self.tree_alerts.configure(yscrollcommand=scroll3.set)
        self.tree_alerts.pack(side="left", fill="both", expand=True, padx=(10,0), pady=10)
        scroll3.pack(side="right", fill="y", pady=10, padx=(0,10))

    # ── Onglet 4 : Logs ───────────────────────────────────────────────────────
    def _build_tab_logs(self):
        frame = tk.Frame(self.notebook, bg="#1e1e2e")
        self.notebook.add(frame, text="📋 Logs")

        self.log_text = scrolledtext.ScrolledText(
            frame, bg="#181825", fg="#cdd6f4",
            font=("Courier", 9), state="disabled", wrap="word"
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text.tag_config("ALERT", foreground="#fab387")
        self.log_text.tag_config("DOWN", foreground="#f38ba8")
        self.log_text.tag_config("INFO", foreground="#a6e3a1")

    # ── Onglet 5 : Administration ─────────────────────────────────────────────
    def _build_tab_admin(self):
        frame = tk.Frame(self.notebook, bg="#1e1e2e")
        self.notebook.add(frame, text="⚙️ Administration")

        tk.Label(frame, text="Envoyer une commande à un nœud",
                 bg="#1e1e2e", fg="#cdd6f4", font=("Helvetica", 12, "bold")).pack(pady=15)

        form = tk.Frame(frame, bg="#1e1e2e")
        form.pack()

        tk.Label(form, text="Nœud :", bg="#1e1e2e", fg="#cdd6f4").grid(row=0, column=0, padx=8, pady=8, sticky="e")
        self.cmd_node = ttk.Combobox(form, width=25)
        self.cmd_node.grid(row=0, column=1, padx=8, pady=8)

        tk.Label(form, text="Commande :", bg="#1e1e2e", fg="#cdd6f4").grid(row=1, column=0, padx=8, pady=8, sticky="e")
        self.cmd_action = ttk.Combobox(form, values=["UP", "DOWN", "STATUS"], width=25)
        self.cmd_action.set("UP")
        self.cmd_action.grid(row=1, column=1, padx=8, pady=8)

        tk.Label(form, text="Service cible :", bg="#1e1e2e", fg="#cdd6f4").grid(row=2, column=0, padx=8, pady=8, sticky="e")
        self.cmd_target = tk.Entry(form, width=27, bg="#313244", fg="white", insertbackground="white")
        self.cmd_target.insert(0, "http")
        self.cmd_target.grid(row=2, column=1, padx=8, pady=8)

        tk.Button(form, text="▶  Envoyer la commande",
                  command=self.send_command,
                  bg="#a6e3a1", fg="#1e1e2e",
                  font=("Helvetica", 11, "bold"), padx=20, pady=8).grid(row=3, columnspan=2, pady=15)

        self.cmd_result = tk.Label(frame, text="", bg="#1e1e2e", fg="#89b4fa",
                                   font=("Helvetica", 10))
        self.cmd_result.pack()

    # ─── Actions ──────────────────────────────────────────────────────────────
    def send_command(self):
        node = self.cmd_node.get().strip()
        action = self.cmd_action.get().strip()
        target = self.cmd_target.get().strip()
        if not node or not action:
            messagebox.showwarning("Attention", "Remplissez le nœud et la commande.")
            return
        ok = self.server.send_command_to_node(node, action, target)
        if ok:
            self.cmd_result.config(text=f"✅ Commande [{action}→{target}] envoyée à {node}", fg="#a6e3a1")
        else:
            self.cmd_result.config(text=f"❌ Nœud {node} non connecté", fg="#f38ba8")

    def load_metrics(self):
        node_id = self.node_var.get().strip()
        if not node_id:
            return
        rows = self.server.get_recent_metrics(node_id)
        self.tree_metrics.delete(*self.tree_metrics.get_children())
        for row in rows:
            self.tree_metrics.insert("", "end", values=(
                row["timestamp"], row["cpu"], row["memory"], row["disk"], row["uptime"]
            ))

    # ─── Mise à jour temps réel ───────────────────────────────────────────────
    def update_node(self, data):
        """Appelé depuis le serveur quand nouvelles métriques arrivent"""
        self.node_data[data["node"]] = data
        self.root.after(0, self._refresh_nodes_tab)

    def notify_down(self, node_id):
        self.root.after(0, lambda: self._append_log(f"🔴 PANNE: {node_id}", "DOWN"))
        self.root.after(0, self._refresh_nodes_tab)

    def _refresh_nodes_tab(self):
        rows = self.server.get_all_nodes()
        self.tree_nodes.delete(*self.tree_nodes.get_children())
        active = 0
        down = 0
        for row in rows:
            status = row["status"]
            nd = self.node_data.get(row["node_id"], {})
            cpu = nd.get("cpu", "-")
            mem = nd.get("memory", "-")
            disk = nd.get("disk", "-")
            uptime = nd.get("uptime", "-")
            tag = "active" if status == "ACTIVE" else "down"
            icon = "🟢" if status == "ACTIVE" else "🔴"
            self.tree_nodes.insert("", "end", values=(
                row["node_id"], row["os"] or "-",
                cpu, mem, disk, uptime,
                f"{icon} {status}", row["last_seen"] or "-"
            ), tags=(tag,))
            if status == "ACTIVE":
                active += 1
            else:
                down += 1

        self.lbl_total.config(text=str(len(rows)))
        self.lbl_active.config(text=str(active))
        self.lbl_down.config(text=str(down))

        # Alertes count
        alerts = self.server.get_recent_alerts(limit=1000)
        self.lbl_alerts.config(text=str(len(alerts)))

        # Mettre à jour combos
        node_ids = [row["node_id"] for row in rows]
        self.node_combo["values"] = node_ids
        self.cmd_node["values"] = node_ids

        self._refresh_alerts()
        self._refresh_logs()

    def _refresh_alerts(self):
        alerts = self.server.get_recent_alerts(50)
        self.tree_alerts.delete(*self.tree_alerts.get_children())
        for a in alerts:
            self.tree_alerts.insert("", "end", values=(
                a["id"], a["node_id"], a["message"], a["timestamp"]
            ), tags=("alert_row",))

    def _refresh_logs(self):
        logs = self.server.get_logs(100)
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        for log in reversed(logs):
            tag = log["level"] if log["level"] in ("ALERT", "DOWN", "INFO") else "INFO"
            self.log_text.insert("end", f"[{log['timestamp']}] [{log['level']}] {log['message']}\n", tag)
        self.log_text.config(state="disabled")
        self.log_text.see("end")

    def _append_log(self, msg, tag="INFO"):
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n", tag)
        self.log_text.config(state="disabled")
        self.log_text.see("end")

    def _start_refresh(self):
        """Rafraîchissement automatique toutes les 10 secondes"""
        self._refresh_nodes_tab()
        self.root.after(10000, self._start_refresh)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def on_close(self):
        self.server.stop()
        self.root.destroy()


# ─── Point d'entrée ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    server = SupervisionServer()
    server.start()
    gui = SupervisionGUI(server)
    gui.run()
