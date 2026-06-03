#!/usr/bin/env python3
"""
arduino_simulator.py — Simulateur Arduino pour développement sans hardware

Simule les données JSON envoyées par l'Arduino Uno via Serial :
  {"n1":82,"n2":34,"t1":22.3,"t2":21.8,"p":1013.2,"g":145,"pump":0,"valve":0}

Peut publier directement sur MQTT (mode Docker) ou sur stdout (mode développement).

⚠️  Connexion MQTT plain (sans TLS) — prototype localhost uniquement.
    Port 1883 par défaut (variable d'environnement MQTT_PORT).

Compatible : paho-mqtt 2.0.0 (CallbackAPIVersion.VERSION1 pour usage simple)

Usage :
  # Via variables d'environnement (Docker Compose)
  MQTT_HOST=mosquitto MQTT_PORT=1883 python3 arduino_simulator.py --mode mqtt

  # En ligne de commande (développement direct)
  python3 arduino_simulator.py --mode mqtt --host localhost --port 1883
  python3 arduino_simulator.py --mode stdout
"""

import argparse
import json
import math
import os
import random
import sys
import time
import logging

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SIM] %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("gnl.simulator")


# ── État interne simulé ────────────────────────────────────────────────────────

class GNLSimulator:
    """Modèle physique simplifié d'un système GNL à deux réservoirs."""

    def __init__(self, scenario: str = "normal") -> None:
        self.scenario   = scenario
        self.t          = 0       # temps simulé (ticks)
        self.n1         = 50.0    # niveau R1 (%)
        self.n2         = 30.0    # niveau R2 (%)
        self.t1         = 22.0    # température R1 (°C)
        self.t2         = 21.5    # température R2 (°C)
        self.pression   = 1013.2  # pression (hPa)
        self.gas        = 80      # concentration MQ-4 (ADC 0–1023)
        self.pump_on    = False
        self.valve_open = False

    def step(self) -> dict:
        """Avance d'un tick et retourne la mesure brute simulée."""
        self.t += 1

        if self.scenario == "normal":
            self._step_normal()
        elif self.scenario == "fuite_gaz":
            self._step_gas_leak()
        elif self.scenario == "debordement":
            self._step_overflow()
        else:
            self._step_normal()

        # Bruit gaussien réaliste sur chaque capteur
        n1 = round(self.n1 + random.gauss(0, 0.3), 1)
        n2 = round(self.n2 + random.gauss(0, 0.3), 1)
        t1 = round(self.t1 + random.gauss(0, 0.1), 1)
        t2 = round(self.t2 + random.gauss(0, 0.1), 1)
        p  = round(self.pression + random.gauss(0, 0.2), 1)
        g  = int(self.gas + random.gauss(0, 5))

        return {
            "n1":    max(0.0, min(100.0, n1)),
            "n2":    max(0.0, min(100.0, n2)),
            "t1":    t1,
            "t2":    t2,
            "p":     p,
            "g":     max(0, min(1023, g)),
            "pump":  1 if self.pump_on  else 0,
            "valve": 1 if self.valve_open else 0,
        }

    # ── Scénarios ──────────────────────────────────────────────────────────────

    def _step_normal(self) -> None:
        """Distribution normale : R1 se remplit, transfert vers R2."""
        if self.n1 < 90:
            self.n1 += 0.2
        if self.n1 >= 90 and self.n2 < 95:
            self.pump_on    = True
            self.valve_open = True
            self.n1 -= 0.5
            self.n2 += 0.4
        elif self.n2 >= 95:
            self.pump_on    = False
            self.valve_open = False
        # Oscillations thermiques sinusoïdales (réalistes)
        self.t1 = 22.0 + 0.5 * math.sin(self.t / 30)
        self.t2 = 21.5 + 0.3 * math.sin(self.t / 25)
        self.gas = 80 + 20 * abs(math.sin(self.t / 100))

    def _step_gas_leak(self) -> None:
        """Scénario fuite de gaz : concentration MQ-4 monte progressivement."""
        self._step_normal()
        if self.t > 30:
            self.gas = min(1023, 80 + (self.t - 30) * 15)

    def _step_overflow(self) -> None:
        """Scénario débordement : R1 monte sans distribution (pompe bloquée)."""
        self.pump_on    = False
        self.valve_open = False
        self.n1  = min(100.0, self.n1 + 0.8)
        self.gas = 80


# ── Modes de sortie ───────────────────────────────────────────────────────────

def run_mqtt(sim: GNLSimulator, host: str, port: int, interval: float) -> None:
    """Publication directe sur MQTT plain (sans TLS)."""

    connected = False

    # paho-mqtt 2.0.0 — VERSION1 suffit pour le simulateur (pas de MQTTv5)
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        client_id="gnl_arduino_sim",
        clean_session=True,
    )

    # Credentials depuis l'environnement ou valeurs par défaut
    mqtt_user = os.environ.get("MQTT_USER", "gnl_publisher")
    mqtt_pass = os.environ.get("MQTT_PASS", "GNL_Secure_2025!")
    client.username_pw_set(mqtt_user, mqtt_pass)

    # Callbacks minimaux
    def on_connect(c, userdata, flags, rc):
        nonlocal connected
        if rc == 0:
            connected = True
            log.info("MQTT connecté (rc=0)")
        else:
            log.error("MQTT connexion refusée (rc=%d)", rc)

    def on_disconnect(c, userdata, rc):
        nonlocal connected
        connected = False
        log.warning("MQTT déconnecté (rc=%d)", rc)

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect

    # Connexion avec retry
    while True:
        try:
            client.connect(host, port, keepalive=60)
            break
        except Exception as exc:
            log.warning("Connexion MQTT échouée (%s) — retry dans 5s…", exc)
            time.sleep(5)

    client.loop_start()
    log.info(
        "Simulateur démarré — broker=%s:%d scénario=%s intervalle=%.1fs",
        host, port, sim.scenario, interval,
    )

    try:
        while True:
            data    = sim.step()
            payload = json.dumps(data)
            if connected:
                client.publish("gnl/sim/raw", payload, qos=0)
                log.debug("→ %s", payload)
            else:
                log.debug("MQTT non connecté — tick ignoré")
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("Simulateur arrêté (KeyboardInterrupt)")
    finally:
        client.loop_stop()
        client.disconnect()


def run_stdout(sim: GNLSimulator, interval: float) -> None:
    """Sortie JSON sur stdout — remplace la lecture du port Serial."""
    log.info("Simulateur STDOUT démarré (scénario=%s)", sim.scenario)
    try:
        while True:
            data = sim.step()
            print(json.dumps(data), flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("Simulateur STDOUT arrêté")


# ── Point d'entrée ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Simulateur Arduino GNL (prototype sans TLS)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["mqtt", "stdout"],
        # Priorité : variable d'environnement, sinon "stdout"
        default=os.environ.get("SIM_MODE", "stdout"),
        help="Mode de sortie : mqtt (Docker) ou stdout (développement)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MQTT_HOST", "localhost"),
        help="Adresse du broker MQTT",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MQTT_PORT", "1883")),
        help="Port MQTT (1883 = plain, 8883 = TLS)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("SIM_INTERVAL", "2.0")),
        help="Intervalle entre deux mesures (secondes)",
    )
    parser.add_argument(
        "--scenario",
        choices=["normal", "fuite_gaz", "debordement"],
        default=os.environ.get("SIM_SCENARIO", "normal"),
        help="Scénario de simulation",
    )
    args = parser.parse_args()

    simulator = GNLSimulator(scenario=args.scenario)

    if args.mode == "mqtt":
        run_mqtt(simulator, args.host, args.port, args.interval)
    else:
        run_stdout(simulator, args.interval)
