#!/usr/bin/env python3
"""
rest_server.py — API REST Flask pour le système IoT GNL

Endpoints :
  GET  /api/v1/status          → état général du système
  GET  /api/v1/data/latest     → dernières mesures
  GET  /api/v1/data/history    → historique (paramètre : ?minutes=60)
  GET  /api/v1/ai/scores       → scores IA courants
  POST /api/v1/cmd/pompe       → commande pompe {action: "ON"|"OFF"}
  POST /api/v1/cmd/vanne       → commande vanne {action: "OPEN"|"CLOSE"}
  POST /api/v1/cmd/esd         → arrêt d'urgence
  GET  /api/v1/alerts          → journal alertes (30 dernières)
  GET  /health                 → health check systemd/Grafana

Sécurité : JWT Bearer token, HTTPS (via nginx reverse proxy)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from functools import wraps
from threading import Lock

from flask import Flask, jsonify, request, abort
import jwt

log = logging.getLogger("gnl.api")

# ── Config ─────────────────────────────────────────────────────────────────────
API_HOST     = "0.0.0.0"
API_PORT     = 5000
JWT_SECRET   = os.environ.get("GNL_JWT_SECRET", "gnl_jwt_secret_change_in_prod")
JWT_ALGO     = "HS256"
JWT_EXPIRY   = 3600  # 1 heure

# Credentials simples (en prod : utiliser une base)
USERS = {
    "admin":    {"password": "admin_GNL_2025!", "role": "admin"},
    "operator": {"password": "oper_GNL_2025!",  "role": "operator"},
}

app  = Flask(__name__)
_lock = Lock()

# État partagé (mis à jour par gnl_main.py via injection)
_latest_data: dict = {}
_alerts:      list = []   # max 100 alertes

# ── Helpers auth ────────────────────────────────────────────────────────────────

def generate_token(username: str, role: str) -> str:
    payload = {
        "sub":  username,
        "role": role,
        "iat":  int(time.time()),
        "exp":  int(time.time()) + JWT_EXPIRY,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_auth(role: str = "operator"):
    """Décorateur d'authentification JWT."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                abort(401, "Token manquant")
            token = auth_header[7:]
            payload = decode_token(token)
            if payload is None:
                abort(401, "Token invalide ou expiré")
            if role == "admin" and payload.get("role") != "admin":
                abort(403, "Droits insuffisants (admin requis)")
            request.user = payload
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ── Endpoints publics ───────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/api/v1/auth/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = body.get("username", "")
    password = body.get("password", "")

    user = USERS.get(username)
    if not user or user["password"] != password:
        abort(401, "Identifiants incorrects")

    token = generate_token(username, user["role"])
    log.info("Connexion réussie : %s (role=%s)", username, user["role"])
    return jsonify({"token": token, "role": user["role"], "expires_in": JWT_EXPIRY})


# ── Endpoints protégés ─────────────────────────────────────────────────────────

@app.route("/api/v1/status")
@require_auth("operator")
def status():
    with _lock:
        data = dict(_latest_data)
    ai = data.get("ai", {})
    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": "rpi4_edge",
        "connected": bool(data),
        "global_risk": ai.get("global_risk", 0),
        "gas_alert":   ai.get("gas_alert"),
        "pump":  data.get("pump", 0),
        "valve": data.get("valve", 0),
        "uptime_s": int(time.time()),
    })


@app.route("/api/v1/data/latest")
@require_auth("operator")
def data_latest():
    with _lock:
        data = dict(_latest_data)
    if not data:
        return jsonify({"error": "Aucune donnée disponible"}), 503

    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "niveau":  {"r1": data.get("n1"), "r2": data.get("n2")},
        "temperature": {"r1": data.get("t1"), "r2": data.get("t2")},
        "gaz":     {"adc": data.get("g"), "niveau": _gas_level(data.get("g", 0))},
        "pression": data.get("p"),
        "actuateurs": {"pompe": data.get("pump"), "vanne": data.get("valve")},
        "ia": data.get("ai", {}),
    })


@app.route("/api/v1/ai/scores")
@require_auth("operator")
def ai_scores():
    with _lock:
        ai = _latest_data.get("ai", {})
    return jsonify({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "isolation_forest": ai.get("isolation_forest", 0),
        "global_risk":      ai.get("global_risk", 0),
        "gas_alert":        ai.get("gas_alert"),
        "regression":       ai.get("regression", {}),
    })


@app.route("/api/v1/alerts")
@require_auth("operator")
def get_alerts():
    with _lock:
        alerts = list(reversed(_alerts[-30:]))
    return jsonify({"count": len(alerts), "alerts": alerts})


# ── Commandes (admin uniquement) ───────────────────────────────────────────────

@app.route("/api/v1/cmd/pompe", methods=["POST"])
@require_auth("admin")
def cmd_pompe():
    body   = request.get_json(silent=True) or {}
    action = body.get("action", "").upper()
    if action not in ("ON", "OFF"):
        abort(400, "action doit être ON ou OFF")
    _register_command(f"CMD:PUMP_{action}", request.user["sub"])
    return jsonify({"status": "queued", "command": f"CMD:PUMP_{action}"})


@app.route("/api/v1/cmd/vanne", methods=["POST"])
@require_auth("admin")
def cmd_vanne():
    body   = request.get_json(silent=True) or {}
    action = body.get("action", "").upper()
    if action not in ("OPEN", "CLOSE"):
        abort(400, "action doit être OPEN ou CLOSE")
    _register_command(f"CMD:VALVE_{action}", request.user["sub"])
    return jsonify({"status": "queued", "command": f"CMD:VALVE_{action}"})


@app.route("/api/v1/cmd/esd", methods=["POST"])
@require_auth("admin")
def cmd_esd():
    _register_command("CMD:ESD", request.user["sub"])
    log.critical("ESD déclenché via API par %s", request.user["sub"])
    return jsonify({"status": "queued", "command": "CMD:ESD"})


# ── File de commandes (partagée avec gnl_main.py) ─────────────────────────────
_cmd_queue: list = []

def _register_command(cmd: str, user: str):
    with _lock:
        _cmd_queue.append({"cmd": cmd, "user": user, "ts": time.time()})
        _add_alert("COMMANDE_MANUELLE", cmd, user)


def pop_command() -> str | None:
    """Appelé par gnl_main.py pour récupérer les commandes manuelles."""
    with _lock:
        if _cmd_queue:
            return _cmd_queue.pop(0)["cmd"]
    return None


def update_latest(data: dict):
    """Appelé par gnl_main.py pour mettre à jour les données courantes."""
    with _lock:
        _latest_data.clear()
        _latest_data.update(data)
        # Enregistrement alerte si nécessaire
        ai = data.get("ai", {})
        if ai.get("global_risk", 0) >= 70 or ai.get("gas_alert"):
            _add_alert(
                ai.get("gas_alert") or f"RISQUE_{ai.get('global_risk')}",
                data.get("g"),
                "auto_ia",
            )


def _add_alert(alert_type: str, value, source: str):
    """Ajoute une alerte au journal (max 100)."""
    _alerts.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type":   alert_type,
        "valeur": value,
        "source": source,
    })
    if len(_alerts) > 100:
        _alerts.pop(0)


def _gas_level(gas: int) -> str:
    if gas < 250:
        return "OK"
    if gas < 450:
        return "ATTENTION"
    return "DANGER"


# ── Démarrage ──────────────────────────────────────────────────────────────────

def start_api_server():
    """Lancé dans un thread daemon par gnl_main.py."""
    log.info("API REST démarrée sur %s:%d", API_HOST, API_PORT)
    # En production : gunicorn gnl.api:app --workers 2
    app.run(host=API_HOST, port=API_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    start_api_server()
