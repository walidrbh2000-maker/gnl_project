#!/usr/bin/env python3
"""
gnl_main.py — Point d'entrée principal du système IoT GNL
Raspberry Pi 4 — Edge Computing Node

Rôle :
  - Lecture JSON depuis Arduino via Serial USB
  - Transmission aux modules IA, MQTT, BDD
  - Gestion watchdog et reconnexion automatique

Lancement : systemd → gnl.service
"""

import sys
import time
import json
import logging
import signal
import threading
from pathlib import Path

# Modules locaux
sys.path.insert(0, str(Path(__file__).parent))
from ai.anomaly_engine   import AnomalyEngine
from mqtt.mqtt_client    import GNLMQTTClient
from database.influx_writer import InfluxWriter
from api.rest_server     import start_api_server

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("/var/log/gnl/gnl_main.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("gnl.main")

# ── Config ─────────────────────────────────────────────────────────────────────
SERIAL_PORT  = "/dev/ttyUSB0"
SERIAL_BAUD  = 9600
RECONNECT_S  = 5       # secondes avant retry serial
LOOP_SLEEP   = 0.05    # secondes entre chaque lecture

# ── Arrêt propre ───────────────────────────────────────────────────────────────
_running = True

def _shutdown(sig, frame):
    global _running
    log.info("Signal %s reçu — arrêt propre…", sig)
    _running = False

signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT,  _shutdown)


def open_serial():
    """Ouvre le port série avec retry."""
    import serial
    while _running:
        try:
            ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=2)
            log.info("Port série ouvert : %s @ %d baud", SERIAL_PORT, SERIAL_BAUD)
            return ser
        except Exception as e:
            log.warning("Port série indisponible (%s) — retry dans %ds", e, RECONNECT_S)
            time.sleep(RECONNECT_S)
    return None


def parse_line(line: str) -> dict | None:
    """Parse une ligne JSON Arduino."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        data = json.loads(line)
        # Validation minimale
        required = {"n1", "n2", "t1", "t2", "p", "g"}
        if not required.issubset(data.keys()):
            return None
        return data
    except json.JSONDecodeError:
        return None


def main():
    log.info("=== Démarrage GNL Edge Node ===")

    # Initialisation modules
    ai_engine  = AnomalyEngine()
    mqtt_client = GNLMQTTClient()
    influx     = InfluxWriter()

    # API REST dans thread séparé
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()
    log.info("API REST démarrée (thread daemon)")

    # Connexion MQTT
    mqtt_client.connect()

    # Boucle principale
    ser = None
    while _running:
        if ser is None or not ser.is_open:
            ser = open_serial()
            if ser is None:
                break

        try:
            raw = ser.readline().decode("utf-8", errors="replace")
            data = parse_line(raw)
            if data is None:
                continue

            # ── Enrichissement IA ──
            ai_result = ai_engine.analyze(data)
            data["ai"] = ai_result

            # ── Publication MQTT ──
            mqtt_client.publish_all(data)

            # ── Écriture InfluxDB ──
            influx.write(data)

            # ── Commande Arduino si nécessaire ──
            cmd = ai_result.get("command")
            if cmd:
                ser.write((cmd + "\n").encode())
                log.warning("Commande envoyée à Arduino : %s", cmd)

        except OSError as e:
            log.error("Erreur série : %s — reconnexion…", e)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(RECONNECT_S)

        except Exception as e:
            log.exception("Erreur inattendue : %s", e)

        time.sleep(LOOP_SLEEP)

    # Nettoyage
    if ser and ser.is_open:
        ser.close()
    mqtt_client.disconnect()
    influx.close()
    log.info("=== GNL Edge Node arrêté proprement ===")


if __name__ == "__main__":
    main()
