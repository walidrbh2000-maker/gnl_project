#!/usr/bin/env python3
"""
arduino_simulator.py — Simulateur Arduino pour développement sans hardware

Simule les données JSON envoyées par l'Arduino Uno via Serial :
  {"n1":82,"n2":34,"t1":22.3,"t2":21.8,"p":1013.2,"g":145,"pump":0,"valve":0}

Peut publier directement sur MQTT (mode Docker) ou sur Serial virtuel.

Usage :
  python3 arduino_simulator.py --mode mqtt --host localhost --port 8883
  python3 arduino_simulator.py --mode serial --port /dev/ttyUSB0
"""

import argparse
import json
import math
import random
import time
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SIM] %(message)s")
log = logging.getLogger("gnl.simulator")

# ── État interne simulé ────────────────────────────────────────────────────────
class GNLSimulator:
    def __init__(self, scenario: str = "normal"):
        self.scenario   = scenario
        self.t          = 0           # temps simulé
        self.n1         = 50.0        # niveau R1 (%)
        self.n2         = 30.0        # niveau R2 (%)
        self.t1         = 22.0        # température R1 (°C)
        self.t2         = 21.5        # température R2 (°C)
        self.pression   = 1013.2      # hPa
        self.gas        = 80          # MQ-4 ADC
        self.pump_on    = False
        self.valve_open = False

    def step(self) -> dict:
        self.t += 1

        # ── Simulation selon scénario ──
        if self.scenario == "normal":
            self._step_normal()
        elif self.scenario == "fuite_gaz":
            self._step_gas_leak()
        elif self.scenario == "debordement":
            self._step_overflow()
        else:
            self._step_normal()

        # Bruit capteurs (réaliste)
        n1 = round(self.n1 + random.gauss(0, 0.3), 1)
        n2 = round(self.n2 + random.gauss(0, 0.3), 1)
        t1 = round(self.t1 + random.gauss(0, 0.1), 1)
        t2 = round(self.t2 + random.gauss(0, 0.1), 1)
        p  = round(self.pression + random.gauss(0, 0.2), 1)
        g  = max(0, min(1023, int(self.gas + random.gauss(0, 5))))

        return {
            "n1":    max(0, min(100, n1)),
            "n2":    max(0, min(100, n2)),
            "t1":    t1,
            "t2":    t2,
            "p":     p,
            "g":     g,
            "pump":  1 if self.pump_on  else 0,
            "valve": 1 if self.valve_open else 0,
        }

    def _step_normal(self):
        """Distribution normale : R1 se remplit, se vide vers R2."""
        # R1 se remplit progressivement (source)
        if self.n1 < 90:
            self.n1 += 0.2
        # Distribution automatique
        if self.n1 >= 90 and self.n2 < 95:
            self.pump_on    = True
            self.valve_open = True
            self.n1  -= 0.5
            self.n2  += 0.4
        elif self.n2 >= 95:
            self.pump_on    = False
            self.valve_open = False
        # Oscillation température sinusoïdale (réaliste)
        self.t1 = 22.0 + 0.5 * math.sin(self.t / 30)
        self.t2 = 21.5 + 0.3 * math.sin(self.t / 25)
        self.gas = 80 + 20 * abs(math.sin(self.t / 100))

    def _step_gas_leak(self):
        """Scénario fuite de gaz — monte progressivement."""
        self._step_normal()
        if self.t > 30:
            self.gas = min(1023, 80 + (self.t - 30) * 15)

    def _step_overflow(self):
        """Scénario débordement — R1 monte vite sans distribution."""
        self.pump_on    = False
        self.valve_open = False
        self.n1 = min(100, self.n1 + 0.8)
        self.gas = 80


def run_mqtt(sim: GNLSimulator, host: str, port: int, interval: float):
    """Publication directe sur MQTT (mode Docker)."""
    import paho.mqtt.client as mqtt

    client = mqtt.Client(client_id="gnl_arduino_sim")
    client.username_pw_set("gnl_publisher", "GNL_Secure_2025!")

    # TLS si port 8883
    if port == 8883:
        import ssl
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

    client.connect(host, port, keepalive=60)
    client.loop_start()

    log.info("Simulateur MQTT démarré → %s:%d (scénario: %s)", host, port, sim.scenario)

    try:
        while True:
            data = sim.step()
            payload = json.dumps(data)
            client.publish("gnl/sim/raw", payload, qos=0)
            log.debug("→ %s", payload)
            time.sleep(interval)
    except KeyboardInterrupt:
        log.info("Simulateur arrêté")
    finally:
        client.loop_stop()
        client.disconnect()


def run_stdout(sim: GNLSimulator, interval: float):
    """Sortie JSON sur stdout (pour remplacer Serial)."""
    log.info("Simulateur STDOUT démarré (scénario: %s)", sim.scenario)
    try:
        while True:
            data = sim.step()
            print(json.dumps(data), flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulateur Arduino GNL")
    parser.add_argument("--mode",     choices=["mqtt","stdout"], default="stdout")
    parser.add_argument("--host",     default="localhost")
    parser.add_argument("--port",     type=int, default=8883)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--scenario", choices=["normal","fuite_gaz","debordement"], default="normal")
    args = parser.parse_args()

    sim = GNLSimulator(scenario=args.scenario)

    if args.mode == "mqtt":
        run_mqtt(sim, args.host, args.port, args.interval)
    else:
        run_stdout(sim, args.interval)
