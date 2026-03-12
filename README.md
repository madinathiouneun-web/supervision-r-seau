# Système Distribué de Supervision Réseau

**Université Numérique Cheikh Hamidou Kane — M1 SRIV Promo 2025**
Projet Systèmes Répartis — Session 1 — Février/Mars 2026

---

## Structure du projet

```
supervision/
├── server.py       # Serveur multi-threads + interface GUI Tkinter
├── agent.py        # Agent de supervision (client TCP)
├── init_db.sql     # Script de création de la base de données SQLite
├── supervision.db  # Base de données (générée automatiquement)
├── supervision.log # Fichier de logs (généré automatiquement)
└── README.md       # Ce fichier
```

---

## Prérequis

- Python 3.8 ou supérieur
- Bibliothèque `psutil` (optionnelle — si absente, les métriques sont simulées)

```bash
pip install psutil
```

Tkinter est inclus par défaut avec Python. Si absent :
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# Windows / macOS : inclus avec Python
```

---

## Lancement

### 1. Démarrer le serveur (en premier)

```bash
python server.py
```

L'interface graphique s'ouvre automatiquement.
Le serveur écoute sur le port **9999**.

### 2. Démarrer un ou plusieurs agents (clients)

Dans un ou plusieurs terminaux séparés :

```bash
python agent.py
```

L'agent se connecte automatiquement au serveur local (`127.0.0.1:9999`) et envoie ses métriques toutes les **10 secondes**.

Pour simuler plusieurs nœuds, lancer `agent.py` depuis plusieurs machines ou terminaux.

---

## Configuration

### Dans `agent.py`
| Variable | Valeur par défaut | Description |
|---|---|---|
| `SERVER_HOST` | `127.0.0.1` | Adresse IP du serveur |
| `SERVER_PORT` | `9999` | Port TCP du serveur |
| `SEND_INTERVAL` | `10` | Intervalle d'envoi (secondes) |
| `ALERT_THRESHOLD` | `90` | Seuil d'alerte CPU/MEM/DISK (%) |

### Dans `server.py`
| Variable | Valeur par défaut | Description |
|---|---|---|
| `PORT` | `9999` | Port d'écoute |
| `MAX_WORKERS` | `20` | Taille du pool de threads |
| `DB_POOL_SIZE` | `5` | Taille du pool de connexions BD |
| `TIMEOUT_INACTIVE` | `90` | Timeout nœud inactif (secondes) |

---

## Protocole de communication

Format **JSON** sur TCP, messages délimités par `\n`.

### Agent → Serveur (métriques)
```json
{
  "type": "METRICS",
  "node": "node-hostname",
  "timestamp": "2026-03-12T10:30:00.000",
  "os": "Linux 5.15",
  "cpu_type": "Intel Core i7",
  "cpu": 35.2,
  "memory": 62.1,
  "disk": 45.8,
  "uptime": 123456,
  "services": {
    "http": "OK", "ssh": "OK", "ftp": "DOWN",
    "firefox": "OK", "chrome": "DOWN", "vlc": "OK"
  },
  "ports": {
    "80": "OPEN", "22": "OPEN", "443": "CLOSED", "3306": "CLOSED"
  },
  "alerts": ["ALERTE: CPU à 92%"]
}
```

### Serveur → Agent (commande)
```json
{
  "type": "COMMAND",
  "action": "UP",
  "target": "http"
}
```

---

## Fonctionnalités

- ✅ Connexion TCP multi-clients avec **ThreadPoolExecutor**
- ✅ Pool de connexions SQLite (5 connexions simultanées)
- ✅ Collecte métriques réelles via `psutil` (ou simulées)
- ✅ Alertes automatiques si CPU/MEM/DISK > 90%
- ✅ Détection nœud en panne après 90s d'inactivité
- ✅ Interface GUI Tkinter (nœuds, métriques, alertes, logs, admin)
- ✅ Envoi de commandes UP/DOWN/STATUS depuis le serveur
- ✅ Journalisation des événements (fichier + BD)
- ✅ Reconnexion automatique de l'agent

---

## Lien Git

> https://github.com/[votre-username]/supervision-reseau

---

*Dr. Maurice D. FAYE — Projet Systèmes Répartis — UN-CHK M1 SRIV 2025*
