#!/usr/bin/env python3
"""
mqtt_client.py — Client MQTT TLS pour le système GNL

Broker : Mosquitto sur localhost port 8883
Sécurité : TLS 1.3, certificats X.509, authentification username/password
Topics : gnl/niveau, gnl/temperature, gnl/gaz, gnl/pression, gnl/ia, gnl/alerte, gnl/cmd
"""

import json
import logging
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

log = logging.getLogger("gnl.mqtt")

# ── Configuration ───────────────────────────────────────────────────────────────
BROKER_HOST   = "localhost"
BROKER_PORT   = 8883
KEEPALIVE     = 60
CLIENT_ID     = "gnl_rpi4_edge"

# Credentials (lus depuis /etc/gnl/mqtt_credentials)
MQTT_USER     = "gnl_publisher"
MQTT_PASS     = "GNL_Secure_2025!"

# Certificats TLS
CA_CERT       = "/etc/mosquitto/certs/ca.crt"
CLIENT_CERT   = "/etc/mosquitto/certs/client.crt"
CLIENT_KEY    = "/etc/mosquitto/certs/client.key"

# Topics
TOPICS = {
    "niveau_r1":   ("gnl/niveau/r1",    1),
    "niveau_r2":   ("gnl/niveau/r2",    1),
    "temp_r1":     ("gnl/temperature/r1", 1),
    "temp_r2":     ("gnl/temperature/r2", 1),
    "gaz":         ("gnl/gaz/mq4",      2),
    "pression":    ("gnl/pression",      0),
    "ia_score":    ("gnl/ia/score",      1),
    "alerte":      ("gnl/alerte",        2),
    "cmd_pompe":   ("gnl/cmd/pompe",     2),
    "cmd_vanne":   ("gnl/cmd/vanne",     2),
    "cmd_esd":     ("gnl/cmd/esd",       2),
}

RECONNECT_DELAY = 5  # secondes


class GNLMQTTClient:
    """Client MQTT TLS avec reconnexion automatique pour le système IoT GNL."""

    def __init__(self):
        self._client = mqtt.Client(
            client_id=CLIENT_ID,
            clean_session=True,
            protocol=mqtt.MQTTv5,
        )
        self._connected = False
        self._setup_client()
        log.info("GNLMQTTClient initialisé")

    def _setup_client(self):
        # TLS
        self._client.tls_set(
            ca_certs=CA_CERT,
            certfile=CLIENT_CERT,
            keyfile=CLIENT_KEY,
        )
        self._client.tls_insecure_set(False)

        # Auth
        self._client.username_pw_set(MQTT_USER, MQTT_PASS)

        # Callbacks
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

        # Will message (LWT) pour détecter la déconnexion
        self._client.will_set(
            "gnl/status",
            json.dumps({"status": "offline", "node": CLIENT_ID}),
            qos=1,
            retain=True,
        )

    def connect(self):
        """Connexion au broker avec retry."""
        while True:
            try:
                self._client.connect(BROKER_HOST, BROKER_PORT, KEEPALIVE)
                self._client.loop_start()
                log.info("MQTT connecté : %s:%d", BROKER_HOST, BROKER_PORT)
                # Publication statut online
                time.sleep(0.5)
                self._client.publish(
                    "gnl/status",
                    json.dumps({"status": "online", "node": CLIENT_ID}),
                    qos=1,
                    retain=True,
                )
                return
            except Exception as e:
                log.warning("MQTT connexion échouée (%s) — retry %ds", e, RECONNECT_DELAY)
                time.sleep(RECONNECT_DELAY)

    def disconnect(self):
        self._client.publish(
            "gnl/status",
            json.dumps({"status": "offline", "node": CLIENT_ID}),
            qos=1,
            retain=True,
        )
        self._client.loop_stop()
        self._client.disconnect()
        log.info("MQTT déconnecté proprement")

    def publish_all(self, data: dict):
        """Publie toutes les mesures depuis le dict Arduino + IA enrichi."""
        ts = datetime.now(timezone.utc).isoformat()
        ai = data.get("ai", {})

        payloads = {
            "niveau_r1": {"valeur": data.get("n1"), "unite": "%",   "timestamp": ts},
            "niveau_r2": {"valeur": data.get("n2"), "unite": "%",   "timestamp": ts},
            "temp_r1":   {"valeur": data.get("t1"), "unite": "°C",  "timestamp": ts},
            "temp_r2":   {"valeur": data.get("t2"), "unite": "°C",  "timestamp": ts},
            "gaz":       {
                "valeur": data.get("g"),
                "unite": "ADC",
                "niveau": self._gas_level(data.get("g", 0)),
                "timestamp": ts,
            },
            "pression":  {"valeur": data.get("p"), "unite": "hPa",  "timestamp": ts},
            "ia_score":  {
                "isolation_forest": ai.get("isolation_forest", 0),
                "global_risk":      ai.get("global_risk", 0),
                "gas_alert":        ai.get("gas_alert"),
                "overflow_risk":    ai.get("regression", {}).get("overflow_risk", False),
                "timestamp": ts,
            },
        }

        for key, payload in payloads.items():
            topic, qos = TOPICS[key]
            self._publish(topic, payload, qos)

        # Alerte si nécessaire
        gas_alert = ai.get("gas_alert")
        if gas_alert and gas_alert != "ATTENTION":
            self._publish_alert(gas_alert, data.get("g", 0), ts)

        global_risk = ai.get("global_risk", 0)
        if global_risk >= 70:
            self._publish_alert(f"RISQUE_{global_risk}", global_risk, ts)

    def _publish(self, topic: str, payload: dict, qos: int = 1):
        if not self._connected:
            log.debug("MQTT non connecté — drop message %s", topic)
            return
        try:
            self._client.publish(topic, json.dumps(payload), qos=qos)
        except Exception as e:
            log.warning("Erreur publication %s : %s", topic, e)

    def _publish_alert(self, alert_type: str, value, timestamp: str):
        severity = "CRITIQUE" if "DANGER" in str(alert_type) else "ÉLEVÉ"
        payload = {
            "type":      alert_type,
            "severity":  severity,
            "valeur":    value,
            "timestamp": timestamp,
            "node":      CLIENT_ID,
        }
        topic, qos = TOPICS["alerte"]
        self._publish(topic, payload, qos)
        log.warning("ALERTE publiée : %s (valeur=%s)", alert_type, value)

    @staticmethod
    def _gas_level(gas: int) -> str:
        if gas < 250:
            return "OK"
        if gas < 450:
            return "ATTENTION"
        return "DANGER"

    # ── Callbacks MQTT ────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected = True
            log.info("MQTT connecté (rc=0)")
            # Souscription commandes
            for cmd_key in ("cmd_pompe", "cmd_vanne", "cmd_esd"):
                topic, qos = TOPICS[cmd_key]
                client.subscribe(topic, qos=qos)
                log.info("Souscrit : %s (QoS %d)", topic, qos)
        else:
            log.error("MQTT connexion refusée : rc=%d", rc)

    def _on_disconnect(self, client, userdata, rc, properties=None):
        self._connected = False
        log.warning("MQTT déconnecté (rc=%d) — reconnexion automatique…", rc)

    def _on_message(self, client, userdata, message):
        """Réception des commandes depuis le dashboard ou l'API."""
        topic   = message.topic
        payload = message.payload.decode("utf-8", errors="replace").strip()
        log.info("Commande reçue [%s] : %s", topic, payload)
        # Les commandes sont traitées par gnl_main.py via retour dans la boucle principale
