"""
Interface Web de Supervision - Flask
Accessible depuis n'importe quel navigateur sur le réseau
Lance avec : python web_app.py
Puis ouvre : http://127.0.0.1:5000
"""

from flask import Flask, jsonify, render_template_string
import sqlite3
import json

app = Flask(__name__)
DB_FILE = "supervision.db"

# ─── Connexion BD ─────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# ─── Template HTML ────────────────────────────────────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Supervision Réseau</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: #0f0f1a; color: #cdd6f4; }

        /* ── Header ── */
        header {
            background: linear-gradient(135deg, #1e1e2e, #313244);
            padding: 18px 30px;
            border-bottom: 2px solid #89b4fa;
            display: flex; justify-content: space-between; align-items: center;
        }
        header h1 { font-size: 1.4rem; color: #cdd6f4; }
        header h1 span { color: #89b4fa; }
        #last-update { font-size: 0.8rem; color: #6c7086; }

        /* ── Stats cards ── */
        .stats { display: flex; gap: 15px; padding: 20px 30px; flex-wrap: wrap; }
        .card {
            background: #1e1e2e; border-radius: 10px; padding: 18px 25px;
            min-width: 140px; text-align: center;
            border: 1px solid #313244; transition: transform 0.2s;
        }
        .card:hover { transform: translateY(-3px); }
        .card .val { font-size: 2rem; font-weight: bold; margin-top: 5px; }
        .card .lbl { font-size: 0.75rem; color: #6c7086; text-transform: uppercase; letter-spacing: 1px; }
        .blue .val { color: #89b4fa; }
        .green .val { color: #a6e3a1; }
        .red .val { color: #f38ba8; }
        .orange .val { color: #fab387; }

        /* ── Section ── */
        .section { padding: 0 30px 25px; }
        .section h2 { font-size: 1rem; color: #89b4fa; margin-bottom: 12px;
                      text-transform: uppercase; letter-spacing: 1px; }

        /* ── Table ── */
        table { width: 100%; border-collapse: collapse; background: #1e1e2e;
                border-radius: 10px; overflow: hidden; }
        th { background: #313244; padding: 12px 15px; text-align: left;
             font-size: 0.8rem; color: #9399b2; text-transform: uppercase; letter-spacing: 1px; }
        td { padding: 11px 15px; border-bottom: 1px solid #2a2a3d; font-size: 0.9rem; }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: #252535; }

        /* ── Badges ── */
        .badge {
            display: inline-block; padding: 3px 10px; border-radius: 20px;
            font-size: 0.75rem; font-weight: bold;
        }
        .badge-green { background: #1a3a2a; color: #a6e3a1; }
        .badge-red   { background: #3a1a1a; color: #f38ba8; }
        .badge-orange { background: #3a2a1a; color: #fab387; }

        /* ── Progress bars ── */
        .bar-wrap { background: #313244; border-radius: 10px; height: 8px; min-width: 80px; }
        .bar { height: 8px; border-radius: 10px; transition: width 0.5s; }
        .bar-ok   { background: #a6e3a1; }
        .bar-warn { background: #fab387; }
        .bar-crit { background: #f38ba8; }

        /* ── Charts ── */
        .charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
                  gap: 20px; padding: 0 30px 25px; }
        .chart-box { background: #1e1e2e; border-radius: 10px; padding: 20px;
                     border: 1px solid #313244; }
        .chart-box h3 { font-size: 0.85rem; color: #9399b2; margin-bottom: 15px;
                        text-transform: uppercase; letter-spacing: 1px; }

        /* ── Alerts ── */
        .alert-item {
            background: #2a1a0a; border-left: 4px solid #fab387;
            border-radius: 6px; padding: 10px 15px; margin-bottom: 8px;
            font-size: 0.88rem;
        }
        .alert-item .alert-node { color: #fab387; font-weight: bold; }
        .alert-item .alert-time { color: #6c7086; font-size: 0.78rem; float: right; }

        /* ── Footer ── */
        footer { text-align: center; padding: 15px; color: #45475a; font-size: 0.8rem;
                 border-top: 1px solid #1e1e2e; }
    </style>
</head>
<body>

<header>
    <h1>🖥️ Supervision <span>Réseau</span> — UN-CHK M1 SRIV</h1>
    <div id="last-update">Chargement...</div>
</header>

<!-- Stats -->
<div class="stats">
    <div class="card blue">
        <div class="lbl">Total nœuds</div>
        <div class="val" id="total">0</div>
    </div>
    <div class="card green">
        <div class="lbl">Actifs</div>
        <div class="val" id="active">0</div>
    </div>
    <div class="card red">
        <div class="lbl">En panne</div>
        <div class="val" id="down">0</div>
    </div>
    <div class="card orange">
        <div class="lbl">Alertes</div>
        <div class="val" id="alerts-count">0</div>
    </div>
</div>

<!-- Tableau nœuds -->
<div class="section">
    <h2>📡 Nœuds supervisés</h2>
    <table>
        <thead>
            <tr>
                <th>Node ID</th><th>OS</th><th>CPU%</th>
                <th>MEM%</th><th>DISK%</th><th>Uptime</th>
                <th>Statut</th><th>Dernière vue</th>
            </tr>
        </thead>
        <tbody id="nodes-tbody">
            <tr><td colspan="8" style="text-align:center;color:#6c7086;">Chargement...</td></tr>
        </tbody>
    </table>
</div>

<!-- Graphiques -->
<div class="charts">
    <div class="chart-box">
        <h3>📈 Évolution CPU (dernières métriques)</h3>
        <canvas id="cpuChart" height="120"></canvas>
    </div>
    <div class="chart-box">
        <h3>📈 Évolution Mémoire</h3>
        <canvas id="memChart" height="120"></canvas>
    </div>
</div>

<!-- Alertes récentes -->
<div class="section">
    <h2>⚠️ Alertes récentes</h2>
    <div id="alerts-list"><p style="color:#6c7086;">Aucune alerte.</p></div>
</div>

<footer>Système Distribué de Supervision Réseau — UN-CHK M1 SRIV Promo 2025</footer>

<script>
// ── Charts ────────────────────────────────────────────────────────────────────
const chartOpts = (label, color) => ({
    type: 'line',
    data: {
        labels: [],
        datasets: [{ label, data: [], borderColor: color,
                     backgroundColor: color + '22', tension: 0.4,
                     fill: true, pointRadius: 3 }]
    },
    options: {
        responsive: true, animation: false,
        scales: {
            y: { min: 0, max: 100, ticks: { color: '#6c7086' },
                 grid: { color: '#2a2a3d' } },
            x: { ticks: { color: '#6c7086', maxTicksLimit: 8 },
                 grid: { color: '#2a2a3d' } }
        },
        plugins: { legend: { labels: { color: '#cdd6f4' } } }
    }
});

const cpuChart = new Chart(document.getElementById('cpuChart'), chartOpts('CPU %', '#89b4fa'));
const memChart = new Chart(document.getElementById('memChart'), chartOpts('MEM %', '#a6e3a1'));

// ── Barre de progression ───────────────────────────────────────────────────────
function makeBar(val) {
    const cls = val >= 90 ? 'bar-crit' : val >= 70 ? 'bar-warn' : 'bar-ok';
    return `<div class="bar-wrap"><div class="bar ${cls}" style="width:${val}%"></div></div>
            <small>${val}%</small>`;
}

// ── Uptime lisible ────────────────────────────────────────────────────────────
function fmtUptime(s) {
    const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600),
          m = Math.floor((s%3600)/60);
    return d > 0 ? `${d}j ${h}h` : `${h}h ${m}m`;
}

// ── Rafraîchissement ──────────────────────────────────────────────────────────
async function refresh() {
    try {
        const res = await fetch('/api/data');
        const data = await res.json();

        // Stats
        document.getElementById('total').textContent = data.stats.total;
        document.getElementById('active').textContent = data.stats.active;
        document.getElementById('down').textContent = data.stats.down;
        document.getElementById('alerts-count').textContent = data.stats.alerts;

        // Tableau nœuds
        const tbody = document.getElementById('nodes-tbody');
        if (data.nodes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#6c7086;">Aucun nœud connecté</td></tr>';
        } else {
            tbody.innerHTML = data.nodes.map(n => {
                const badge = n.status === 'ACTIVE'
                    ? '<span class="badge badge-green">🟢 ACTIVE</span>'
                    : '<span class="badge badge-red">🔴 DOWN</span>';
                return `<tr>
                    <td><strong>${n.node_id}</strong></td>
                    <td>${n.os || '-'}</td>
                    <td>${makeBar(n.cpu || 0)}</td>
                    <td>${makeBar(n.mem || 0)}</td>
                    <td>${makeBar(n.disk || 0)}</td>
                    <td>${n.uptime ? fmtUptime(n.uptime) : '-'}</td>
                    <td>${badge}</td>
                    <td style="color:#6c7086;font-size:0.8rem">${n.last_seen || '-'}</td>
                </tr>`;
            }).join('');
        }

        // Graphiques (premier nœud)
        if (data.metrics.length > 0) {
            const labels = data.metrics.map(m => m.timestamp.substring(11,19)).reverse();
            const cpuVals = data.metrics.map(m => m.cpu).reverse();
            const memVals = data.metrics.map(m => m.memory).reverse();
            cpuChart.data.labels = labels;
            cpuChart.data.datasets[0].data = cpuVals;
            cpuChart.update();
            memChart.data.labels = labels;
            memChart.data.datasets[0].data = memVals;
            memChart.update();
        }

        // Alertes
        const alertsDiv = document.getElementById('alerts-list');
        if (data.alerts.length === 0) {
            alertsDiv.innerHTML = '<p style="color:#6c7086;">Aucune alerte.</p>';
        } else {
            alertsDiv.innerHTML = data.alerts.map(a =>
                `<div class="alert-item">
                    <span class="alert-node">${a.node_id}</span>
                    <span class="alert-time">${a.timestamp}</span>
                    <br/><span style="color:#cdd6f4">${a.message}</span>
                </div>`
            ).join('');
        }

        document.getElementById('last-update').textContent =
            'Mis à jour : ' + new Date().toLocaleTimeString();

    } catch(e) {
        console.error('Erreur fetch:', e);
    }
}

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""

# ─── Routes API ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/data')
def api_data():
    db = get_db()
    try:
        # Nœuds
        nodes_rows = db.execute("SELECT * FROM nodes ORDER BY last_seen DESC").fetchall()
        nodes = []
        for n in nodes_rows:
            # Dernières métriques du nœud
            m = db.execute(
                "SELECT * FROM metrics WHERE node_id=? ORDER BY id DESC LIMIT 1",
                (n["node_id"],)
            ).fetchone()
            nodes.append({
                "node_id": n["node_id"],
                "os": n["os"],
                "status": n["status"],
                "last_seen": n["last_seen"],
                "cpu":  round(m["cpu"], 1)    if m else 0,
                "mem":  round(m["memory"], 1) if m else 0,
                "disk": round(m["disk"], 1)   if m else 0,
                "uptime": m["uptime"]         if m else 0,
            })

        # Métriques récentes (premier nœud actif)
        first_node = next((n["node_id"] for n in nodes_rows if n["status"] == "ACTIVE"), None)
        metrics = []
        if first_node:
            rows = db.execute(
                "SELECT * FROM metrics WHERE node_id=? ORDER BY id DESC LIMIT 20",
                (first_node,)
            ).fetchall()
            metrics = [{"timestamp": r["timestamp"], "cpu": r["cpu"], "memory": r["memory"]} for r in rows]

        # Alertes récentes
        alert_rows = db.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT 10"
        ).fetchall()
        alerts = [{"node_id": a["node_id"], "message": a["message"], "timestamp": a["timestamp"]} for a in alert_rows]

        # Stats
        total  = len(nodes)
        active = sum(1 for n in nodes if n["status"] == "ACTIVE")
        down   = total - active
        total_alerts = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

        return jsonify({
            "nodes": nodes,
            "metrics": metrics,
            "alerts": alerts,
            "stats": {"total": total, "active": active, "down": down, "alerts": total_alerts}
        })
    finally:
        db.close()

# ─── Lancement ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("🌐 Interface Web de Supervision")
    print("   http://127.0.0.1:5000")
    print(f"   http://192.168.1.118:5000  (réseau local)")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
