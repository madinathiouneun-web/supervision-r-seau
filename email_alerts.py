"""
Module d'alertes email automatiques
Envoie un email quand CPU/MEM/DISK dépasse 90%
"""

import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ─── Configuration Email ──────────────────────────────────────────────────────
EMAIL_SENDER     = "votre.email@gmail.com"       # ← Ton email Gmail
EMAIL_PASSWORD   = "xxxx xxxx xxxx xxxx"          # ← Mot de passe d'application Gmail
EMAIL_RECEIVER   = "votre.email@gmail.com"        # ← Email destinataire (peut être le même)
SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587

# Anti-spam : ne pas envoyer 2 emails pour le même nœud en moins de 5 minutes
_last_alert_times = {}
_lock = threading.Lock()
ALERT_COOLDOWN = 300  # secondes (5 minutes)

# ─── Envoi email ─────────────────────────────────────────────────────────────

def send_alert_email(node_id, alerts):
    """Envoie un email d'alerte (dans un thread séparé pour ne pas bloquer)"""
    threading.Thread(
        target=_send_email_worker,
        args=(node_id, alerts),
        daemon=True
    ).start()

def _can_send_alert(node_id):
    """Vérifie le cooldown anti-spam"""
    with _lock:
        last = _last_alert_times.get(node_id, 0)
        now = datetime.now().timestamp()
        if now - last >= ALERT_COOLDOWN:
            _last_alert_times[node_id] = now
            return True
        return False

def _send_email_worker(node_id, alerts):
    """Worker qui envoie l'email"""
    if not _can_send_alert(node_id):
        print(f"[EMAIL] Cooldown actif pour {node_id}, email non envoyé")
        return

    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ─── Contenu HTML de l'email ──────────────────────────────────────
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; background:#f5f5f5; padding:20px;">
            <div style="background:white; border-radius:8px; padding:20px; max-width:600px; margin:auto;
                        border-left: 5px solid #e74c3c;">
                <h2 style="color:#e74c3c;">🚨 Alerte de Supervision Réseau</h2>
                <p><strong>Nœud :</strong> {node_id}</p>
                <p><strong>Date :</strong> {now}</p>
                <hr/>
                <h3>Alertes détectées :</h3>
                <ul>
                    {"".join(f'<li style="color:#e74c3c; font-weight:bold;">{a}</li>' for a in alerts)}
                </ul>
                <hr/>
                <p style="color:#888; font-size:12px;">
                    Système Distribué de Supervision Réseau — UN-CHK M1 SRIV 2025
                </p>
            </div>
        </body>
        </html>
        """

        # ─── Construction du message ──────────────────────────────────────
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚨 ALERTE Supervision — {node_id} — {now}"
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = EMAIL_RECEIVER
        msg.attach(MIMEText(html, "html"))

        # ─── Envoi via Gmail SMTP ─────────────────────────────────────────
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

        print(f"[EMAIL] ✅ Alerte envoyée pour {node_id} → {EMAIL_RECEIVER}")

    except smtplib.SMTPAuthenticationError:
        print("[EMAIL] ❌ Erreur authentification — vérifie ton mot de passe d'application Gmail")
    except smtplib.SMTPException as e:
        print(f"[EMAIL] ❌ Erreur SMTP : {e}")
    except Exception as e:
        print(f"[EMAIL] ❌ Erreur : {e}")
