#!/usr/bin/env python3
"""
gnl_main.py — Point d'entrée principal du système IoT GNL
Raspberry Pi 4 — Edge Computing Node

Rôle :
  - Lecture JSON depuis Arduino via Serial USB  (mode physique)
  - Lecture JSON depuis MQTT gnl/sim/raw        (mode SIMULATED)
  - Transmission aux modules IA, MQTT, BDD
  - Gestion watchdog et reconnexion automatique

CORRECTIONS :
  BUG #2 — SERIAL_PORT lu depuis os.environ (valeur hardcodée supprimée).
            Si SERIAL_PORT == "SIMULATED", la boucle principale est alimentée
            par un abonné MQTT sur gnl/sim/raw (publié par arduino_simulator.py)
            via une queue thread-safe, sans modifier le pipeline IA/MQTT/InfluxDB.

  ROBUSTESSE — Le répertoire de log /var/log/gnl est créé au démarrage si
               absent, pour éviter un FileNotFoundError fatal avant le premier log.

Lancement : systemd → gnl.service  |  Docker → gnl_edge_node
"""

import os
import queue
import sys
import time
import json
import logging
import signal
import threading
from pathlib import Path

import paho.mqtt.client as mqtt

# Modules locaux
sys.path.insert(0, str(Path(__file__).parent))
from ai.anomaly_engine      import AnomalyEngine
from mqtt.mqtt_client       import GNLMQTTClient
from database.influx_writer import InfluxWriter
from api.rest_server        import start_api_server

# ── Répertoire de log — créé ici pour éviter FileNotFoundError ─────────────────
_LOG_DIR  = Path("/var/log/gnl")
_LOG_FILE = _LOG_DIR / "gnl_main.log"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(_LOG_FILE)),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("gnl.main")

# ── Config — lecture depuis l'environnement ────────────────────────────────────
SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyUSB0")
SERIAL_BAUD = int(os.environ.get("SERIAL_BAUD", "9600"))

MQTT_HOST = os.environ.get("MQTT_HOST",           "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT",        "1883"))
MQTT_USER = os.environ.get("MQTT_USER_PUBLISHER",  "gnl_publisher")
MQTT_PASS = os.environ.get("MQTT_PASS_PUBLISHER",  "GNL_Secure_2025!")

SIM_TOPIC         = "gnl/sim/raw"   # topic publié par arduino_simulator.py
RECONNECT_S       = 5               # secondes avant retry (série ou MQTT)
LOOP_SLEEP        = 0.05            # secondes entre lectures en mode série
SIM_QUEUE_MAXSIZE = 100             # messages en attente max (protection RAM)

# ── Arrêt propre ───────────────────────────────────────────────────────────────
_running = True


def _shutdown(sig, frame):
    global _running
    log.info("Signal %s reçu — arrêt propre…", sig)
    _running = False


signal.signal(signal.SIGTERM, _shutdown)
signal.signal(signal.SIGINT,  _shutdown)


# ══════════════════════════════════════════════════════════════════════════════
# MODE SÉRIE (hardware réel)
# ══════════════════════════════════════════════════════════════════════════════

def open_serial():
    """Ouvre le port série avec retry. Retourne None si _running devient False."""
    import serial
    while _running:
        try:
            ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=2)
            log.info("Port série ouvert : %s @ %d baud", SERIAL_PORT, SERIAL_BAUD)
            return ser
        except Exception as exc:
            log.warning(
                "Port série indisponible (%s) — retry dans %ds", exc, RECONNECT_S
            )
            time.sleep(RECONNECT_S)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# MODE SIMULATED — abonné MQTT sur gnl/sim/raw
# ══════════════════════════════════════════════════════════════════════════════

# Queue thread-safe : callback MQTT (thread paho) → boucle principale
_sim_queue: queue.Queue = queue.Queue(maxsize=SIM_QUEUE_MAXSIZE)


def _build_sim_subscriber() -> mqtt.Client:
    """
    Crée un client paho-mqtt abonné à SIM_TOPIC.
    Les messages reçus sont déposés dans _sim_queue.
    Utilise VERSION1 (callbacks à 3/4 paramètres) suffisant pour un abonné simple.
    """

    def on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
        if rc == 0:
            client.subscribe(SIM_TOPIC, qos=0)
            log.info("Mode SIMULATED — abonné à '%s'", SIM_TOPIC)
        else:
            log.error(
                "Mode SIMULATED — connexion MQTT refusée (rc=%d). "
                "Vérifier MQTT_USER_PUBLISHER / MQTT_PASS_PUBLISHER.",
                rc,
            )

    def on_disconnect(client: mqtt.Client, userdata, rc: int) -> None:
        if rc != 0:
            log.warning(
                "Mode SIMULATED — déconnexion MQTT inattendue (rc=%d) "
                "— paho tentera la reconnexion automatique.",
                rc,
            )

    def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            payload = msg.payload.decode("utf-8")
            _sim_queue.put_nowait(payload)
        except queue.Full:
            # Un message perdu est préférable à un deadlock
            log.debug("Mode SIMULATED — queue pleine, message ignoré")
        except Exception as exc:
            log.warning("Mode SIMULATED — erreur décodage message : %s", exc)

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        client_id="gnl_edge_sim_sub",
        clean_session=True,   # VERSION1 + MQTTv3 : clean_session est valide ici
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    # Reconnexion automatique intégrée paho (1 s → 120 s)
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    return client


def _connect_sim_subscriber(client: mqtt.Client) -> None:
    """
    Connexion initiale avec retry bloquant.
    Exécuté dans un thread daemon pour ne pas bloquer main().
    """
    while _running:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            log.info(
                "Mode SIMULATED — client MQTT connecté à %s:%d",
                MQTT_HOST, MQTT_PORT,
            )
            return
        except Exception as exc:
            log.warning(
                "Mode SIMULATED — connexion MQTT échouée (%s) — retry dans %ds",
                exc, RECONNECT_S,
            )
            time.sleep(RECONNECT_S)


def start_sim_subscriber() -> mqtt.Client:
    """Lance l'abonné MQTT dans un thread daemon et retourne le client."""
    client = _build_sim_subscriber()
    threading.Thread(
        target=_connect_sim_subscriber,
        args=(client,),
        daemon=True,
        name="gnl-sim-subscriber",
    ).start()
    return client


# ══════════════════════════════════════════════════════════════════════════════
# PARSING COMMUN (série + simulateur)
# ══════════════════════════════════════════════════════════════════════════════

def parse_line(line: str) -> dict | None:
    """
    Parse une ligne JSON Arduino / simulateur.
    Champs obligatoires : n1, n2, t1, t2, p, g
    Retourne None si la ligne est invalide ou incomplète.
    """
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        data = json.loads(line)
        required = {"n1", "n2", "t1", "t2", "p", "g"}
        if not required.issubset(data.keys()):
            log.debug("JSON incomplet (champs manquants) : %s", line)
            return None
        return data
    except json.JSONDecodeError as exc:
        log.debug("JSON invalide : %s — %s", line, exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE COMMUN IA / MQTT / INFLUX
# ══════════════════════════════════════════════════════════════════════════════

def process(
    data: dict,
    ai_engine: AnomalyEngine,
    mqtt_client: GNLMQTTClient,
    influx: InfluxWriter,
    ser=None,
) -> None:
    """
    Enrichit les données via l'IA, les publie sur MQTT, les écrit en base.
    Si `ser` est fourni (mode série), envoie aussi les commandes Arduino.
    """
    ai_result  = ai_engine.analyze(data)
    data["ai"] = ai_result

    mqtt_client.publish_all(data)
    influx.write(data)

    if ser is not None:
        cmd = ai_result.get("command")
        if cmd:
            ser.write((cmd + "\n").encode())
            log.warning("Commande envoyée à Arduino : %s", cmd)


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    log.info("=== Démarrage GNL Edge Node ===")
    log.info("SERIAL_PORT=%s | MQTT_HOST=%s:%d", SERIAL_PORT, MQTT_HOST, MQTT_PORT)

    # Initialisation des modules
    ai_engine   = AnomalyEngine()
    mqtt_client = GNLMQTTClient()
    influx      = InfluxWriter()

    # API REST dans thread daemon séparé
    threading.Thread(target=start_api_server, daemon=True, name="gnl-api").start()
    log.info("API REST démarrée (thread daemon)")

    # Connexion MQTT publication
    mqtt_client.connect()

    # ── Sélection du mode d'acquisition ───────────────────────────────────────
    if SERIAL_PORT == "SIMULATED":
        _run_simulated(ai_engine, mqtt_client, influx)
    else:
        _run_serial(ai_engine, mqtt_client, influx)

    # Nettoyage commun
    mqtt_client.disconnect()
    influx.close()
    log.info("=== GNL Edge Node arrêté proprement ===")


# ── Boucle mode simulé ────────────────────────────────────────────────────────

def _run_simulated(
    ai_engine: AnomalyEngine,
    mqtt_client: GNLMQTTClient,
    influx: InfluxWriter,
) -> None:
    """
    Boucle principale en mode SIMULATED.
    Lit les messages JSON depuis _sim_queue (alimentée par l'abonné MQTT
    sur gnl/sim/raw) et les injecte dans le pipeline IA/MQTT/InfluxDB.
    ser=None : pas de commandes Arduino envoyées en mode simulé.
    """
    log.info("Mode SIMULATED activé — écoute MQTT topic '%s'", SIM_TOPIC)
    sim_client = start_sim_subscriber()

    while _running:
        try:
            raw = _sim_queue.get(timeout=1.0)
        except queue.Empty:
            continue

        data = parse_line(raw)
        if data is None:
            continue

        try:
            process(data, ai_engine, mqtt_client, influx, ser=None)
        except Exception as exc:
            log.exception("Erreur traitement données simulées : %s", exc)

    # Arrêt propre du client MQTT abonné
    try:
        sim_client.loop_stop()
        sim_client.disconnect()
    except Exception:
        pass
    log.info("Mode SIMULATED — abonné MQTT arrêté")


# ── Boucle mode série (hardware réel) ────────────────────────────────────────

def _run_serial(
    ai_engine: AnomalyEngine,
    mqtt_client: GNLMQTTClient,
    influx: InfluxWriter,
) -> None:
    """
    Boucle principale en mode série (Arduino physique).
    Reconnexion automatique sur erreur OSError.
    """
    log.info("Mode SÉRIE activé — port %s @ %d baud", SERIAL_PORT, SERIAL_BAUD)
    ser = None

    while _running:
        if ser is None or not ser.is_open:
            ser = open_serial()
            if ser is None:
                break  # _running est False

        try:
            raw  = ser.readline().decode("utf-8", errors="replace")
            data = parse_line(raw)
            if data is None:
                time.sleep(LOOP_SLEEP)
                continue

            process(data, ai_engine, mqtt_client, influx, ser=ser)

        except OSError as exc:
            log.error("Erreur série : %s — reconnexion…", exc)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(RECONNECT_S)

        except Exception as exc:
            log.exception("Erreur inattendue : %s", exc)

        time.sleep(LOOP_SLEEP)

    # Nettoyage port série
    if ser and ser.is_open:
        ser.close()
    log.info("Mode SÉRIE — port fermé")


if __name__ == "__main__":
    main()
