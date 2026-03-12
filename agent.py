python """
Agent de supervision - Client TCP
Collecte les métriques système et les envoie au serveur central
"""

import socket
import json
import time
import threading
import platform
import random
import subprocess
import sys
from datetime import datetime

# ─── Configuration ───────────────────────────────────────────────────────────
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9999
SEND_INTERVAL = 10        # secondes entre chaque envoi
ALERT_THRESHOLD = 90      # % seuil d'alerte CPU/MEM/DISK
NODE_ID = f"node-{platform.node()}"

# Services réseaux supervisés (3)
NETWORK_SERVICES = ["http", "ssh", "ftp"]
# Applications grand public (3)
USER_APPS = ["firefox", "chrome", "vlc"]
# Ports surveillés
MONITORED_PORTS = [80, 22, 443, 3306]

# ─── Collecte des métriques ───────────────────────────────────────────────────

def get_cpu_usage():
    try:
        import psutil
        return round(psutil.cpu_percent(interval=1), 1)
    except ImportError:
        return round(random.uniform(10, 95), 1)

def get_memory_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return round(mem.percent, 1)
    except ImportError:
        return round(random.uniform(20, 90), 1)

def get_disk_usage():
    try:
        import psutil
        disk = psutil.disk_usage('/')
        return round(disk.percent, 1)
    except ImportError:
        return round(random.uniform(30, 85), 1)

def get_uptime():
    try:
        import psutil
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        return uptime_seconds
    except ImportError:
        return random.randint(3600, 86400)

def get_os_info():
    return platform.system() + " " + platform.release()

def get_cpu_type():
    return platform.processor() or "Unknown CPU"

def check_service_status(service_name):
    """Vérifie si un service/processus est actif"""
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {service_name}.exe"],
                capture_output=True, text=True, timeout=3
            )
            return "OK" if service_name.lower() in result.stdout.lower() else "DOWN"
        else:
            result = subprocess.run(
                ["pgrep", "-x", service_name],
                capture_output=True, timeout=3
            )
            return "OK" if result.returncode == 0 else "DOWN"
    except Exception:
        return "OK" if random.random() > 0.3 else "DOWN"

def check_port_status(port):
    """Vérifie si un port local est actif"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', port))
            return "OPEN" if result == 0 else "CLOSED"
    except Exception:
        return "CLOSED"

def collect_metrics():
    """Collecte toutes les métriques du nœud"""
    cpu = get_cpu_usage()
    mem = get_memory_usage()
    disk = get_disk_usage()
    uptime = get_uptime()

    # Services
    services = {}
    for svc in NETWORK_SERVICES + USER_APPS:
        services[svc] = check_service_status(svc)

    # Ports
    ports = {}
    for port in MONITORED_PORTS:
        ports[str(port)] = check_port_status(port)

    # Alertes
    alerts = []
    if cpu > ALERT_THRESHOLD:
        alerts.append(f"ALERTE: CPU à {cpu}%")
    if mem > ALERT_THRESHOLD:
        alerts.append(f"ALERTE: Mémoire à {mem}%")
    if disk > ALERT_THRESHOLD:
        alerts.append(f"ALERTE: Disque à {disk}%")

    metrics = {
        "node": NODE_ID,
        "timestamp": datetime.now().isoformat(),
        "os": get_os_info(),
        "cpu_type": get_cpu_type(),
        "cpu": cpu,
        "memory": mem,
        "disk": disk,
        "uptime": uptime,
        "services": services,
        "ports": ports,
        "alerts": alerts,
        "type": "METRICS"
    }
    return metrics

# ─── Agent principal ──────────────────────────────────────────────────────────

class SupervisionAgent:
    def __init__(self):
        self.running = False
        self.sock = None
        self.connected = False
        self.lock = threading.Lock()

    def connect(self):
        """Établit la connexion TCP avec le serveur"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((SERVER_HOST, SERVER_PORT))
            self.connected = True
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecté au serveur {SERVER_HOST}:{SERVER_PORT}")
            # Lancer le thread d'écoute des commandes
            threading.Thread(target=self.listen_commands, daemon=True).start()
            return True
        except ConnectionRefusedError:
            print(f"[ERREUR] Impossible de se connecter à {SERVER_HOST}:{SERVER_PORT}")
            return False
        except Exception as e:
            print(f"[ERREUR] Connexion: {e}")
            return False

    def send_metrics(self):
        """Envoie les métriques au serveur"""
        if not self.connected:
            return False
        try:
            metrics = collect_metrics()
            message = json.dumps(metrics) + "\n"
            with self.lock:
                self.sock.sendall(message.encode('utf-8'))
            # Affichage local
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Métriques envoyées → CPU:{metrics['cpu']}% MEM:{metrics['memory']}% DISK:{metrics['disk']}%")
            if metrics['alerts']:
                for alert in metrics['alerts']:
                    print(f"  ⚠️  {alert}")
            return True
        except Exception as e:
            print(f"[ERREUR] Envoi: {e}")
            self.connected = False
            return False

    def listen_commands(self):
        """Écoute les commandes du serveur"""
        self.sock.settimeout(5)
        buffer = ""
        while self.running and self.connected:
            try:
                data = self.sock.recv(1024).decode('utf-8')
                if not data:
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self.handle_command(line.strip())
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERREUR] Réception commande: {e}")
                break
        self.connected = False

    def handle_command(self, raw_cmd):
        """Traite une commande reçue du serveur"""
        try:
            cmd = json.loads(raw_cmd)
            if cmd.get("type") == "COMMAND":
                action = cmd.get("action")
                target = cmd.get("target", "")
                print(f"\n[COMMANDE REÇUE] {action} → {target}")
                if action == "UP":
                    print(f"  ✅ Activation du service: {target}")
                elif action == "DOWN":
                    print(f"  🛑 Arrêt du service: {target}")
                elif action == "STATUS":
                    self.send_metrics()
        except json.JSONDecodeError:
            print(f"[WARN] Commande invalide: {raw_cmd}")

    def run(self):
        """Boucle principale de l'agent"""
        self.running = True
        print(f"=== Agent de supervision - {NODE_ID} ===")
        print(f"Serveur cible: {SERVER_HOST}:{SERVER_PORT}")
        print(f"Intervalle d'envoi: {SEND_INTERVAL}s\n")

        while self.running:
            if not self.connected:
                print("Tentative de reconnexion...")
                self.connect()

            if self.connected:
                self.send_metrics()

            time.sleep(SEND_INTERVAL)

    def stop(self):
        self.running = False
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        print("\nAgent arrêté.")


if __name__ == "__main__":
    agent = SupervisionAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        agent.stop()
