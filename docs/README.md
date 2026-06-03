# Système IoT GNL — Surveillance et Gestion Intelligente des Réservoirs
## Projet de Fin d'Études M2 RSID — 2025-2026

**Titre officiel** : *Système IoT distribué de surveillance et de gestion intelligente des réservoirs GNL avec Edge Computing, détection de fuites et sécurité réseau*

---

## 📋 Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture du système](#architecture)
3. [Structure du projet](#structure)
4. [Matériel requis](#matériel)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Démarrage](#démarrage)
8. [API REST](#api-rest)
9. [Base de données](#base-de-données)
10. [Sécurité](#sécurité)
11. [Tests](#tests)
12. [Monitoring Grafana](#grafana)
13. [Analyse HAZOP](#hazop)
14. [Troubleshooting](#troubleshooting)

---

## Vue d'ensemble

Prototype IoT simulant la surveillance de **réservoirs GNL** (Gaz Naturel Liquéfié) avec de l'eau. Le système implémente :

- **Edge Computing** : traitement IA local sur Raspberry Pi 4 (pas de cloud)
- **IA embarquée** : Isolation Forest + Régression linéaire + Seuil adaptatif σ×2
- **Sécurité réseau** : MQTT over TLS 1.3, certificats X.509, ACL, firewall UFW
- **Monitoring temps réel** : Dashboard HTML + Grafana OSS + InfluxDB 2.x
- **Sécurité industrielle** : Analyse HAZOP conforme IEC 61511

### Couverture des axes M2 RSID

| Axe | Implémentation |
|-----|----------------|
| **Réseaux** | MQTT over TLS 1.3, QoS 0/1/2, pub/sub, I2C, Serial |
| **Systèmes distribués** | Arduino (nœud acquisition) + RPi4 (nœud Edge) |
| **Intelligence artificielle** | Isolation Forest, régression linéaire, σ×2 adaptatif |
| **Sécurité** | TLS 1.3, X.509, ACL MQTT, UFW, fail2ban, SSH durci |
| **IoT industriel** | HC-SR04, DS18B20, BMP280, MQ-4, pompe, électrovanne |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    COUCHE 6 — VISUALISATION                      │
│            Grafana OSS · Dashboard HTML · InfluxDB               │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/WebSocket
┌────────────────────────────▼────────────────────────────────────┐
│                   COUCHE 5 — SÉCURITÉ RÉSEAU                     │
│         Mosquitto TLS 1.3 · X.509 · ACL · UFW · fail2ban        │
└────────────────────────────┬────────────────────────────────────┘
                             │ MQTT/TLS port 8883
┌────────────────────────────▼────────────────────────────────────┐
│               COUCHE 3+4 — EDGE COMPUTING + IA                  │
│      Raspberry Pi 4 · Python 3.11 · Isolation Forest · Flask    │
│      InfluxDB writer · MQTT publisher · API REST JWT            │
└────────────────────────────┬────────────────────────────────────┘
                             │ USB Serial JSON @ 9600 baud
┌────────────────────────────▼────────────────────────────────────┐
│                COUCHE 2 — CONTRÔLE LOCAL (ARDUINO)               │
│         Arduino Uno · C++ · LCD 1602 · LED · Buzzer · Relais     │
└────────────────────────────┬────────────────────────────────────┘
                             │ GPIO / I2C / OneWire / Analogique
┌────────────────────────────▼────────────────────────────────────┐
│                   COUCHE 1 — TERRAIN (CAPTEURS)                  │
│   HC-SR04×2 · DS18B20×2 · BMP280 · MQ-4 · Pompe · Électrovanne  │
└─────────────────────────────────────────────────────────────────┘
```

### Flux de données

```
Capteurs → Arduino (JSON Serial 2s) → RPi4 → IA Analysis
       → MQTT TLS → InfluxDB → Grafana
       → API REST → Dashboard HTML
       → Commandes → Arduino → Actionneurs
```

---

## Structure du projet

```
gnl_project/
│
├── arduino/
│   └── gnl_main.ino              # Code Arduino Uno complet
│
├── raspberry_pi/
│   ├── gnl_main.py               # Point d'entrée principal
│   ├── requirements.txt          # Dépendances Python
│   │
│   ├── ai/
│   │   └── anomaly_engine.py     # Moteur IA (Isolation Forest + régression)
│   │
│   ├── mqtt/
│   │   ├── mqtt_client.py        # Client MQTT TLS paho
│   │   ├── mosquitto.conf        # Configuration broker Mosquitto
│   │   └── acl                   # Contrôle d'accès topics MQTT
│   │
│   ├── database/
│   │   └── influx_writer.py      # Écriture InfluxDB 2.x time series
│   │
│   ├── api/
│   │   └── rest_server.py        # API REST Flask + JWT
│   │
│   ├── dashboard/
│   │   ├── gnl_dashboard.html    # Dashboard HTML/JS temps réel
│   │   └── grafana_dashboard.json # Dashboard Grafana (import JSON)
│   │
│   ├── security/
│   │   └── setup_security.sh     # Script TLS + UFW + fail2ban + SSH
│   │
│   ├── scripts/
│   │   ├── install.sh            # Installation complète sur RPi4
│   │   └── arduino_simulator.py  # Simulateur Arduino (sans hardware)
│   │
│   └── systemd/
│       └── gnl.service           # Service systemd avec watchdog
│
├── docker/
│   └── docker-compose.yml        # Environnement dev complet (Docker)
│
├── tests/
│   └── test_ai_engine.py         # Tests unitaires pytest (15 tests)
│
└── docs/
    ├── README.md                 # Ce fichier
    └── architecture_gnl_iot.png  # Schéma architecture
```

---

## Matériel requis

| Composant | Qté | Pin Arduino | Rôle | Statut |
|-----------|-----|-------------|------|--------|
| Raspberry Pi 4 (4GB) | ×1 | USB Serial | Edge Computing, IA, MQTT | Disponible |
| Arduino Uno | ×1 | — | Acquisition + contrôle | Acheté |
| HC-SR04 (ultrason) | ×2 | R1:D9/D10, R2:D3/D4 | Niveau réservoirs | Acheté |
| DS18B20 (température) | ×2 | R1:D5, R2:D2 + 4.7kΩ | Température eau | Acheté |
| BMP280 (pression) | ×1 | A4/A5 (**3.3V !**) | Pression ambiante | Acheté |
| MQ-4 (gaz méthane) | ×1 | A0 | Détection fuite GNL | À acheter |
| Pompe 12V | ×1 | via Relais D7 | Transfert eau R1→R2 | Acheté |
| Électrovanne NC | ×1 | via Relais D8 | Circuit eau | À acheter |
| Relais 2 canaux | ×1 | IN1:D7, IN2:D8 | Commande pompe+vanne | Acheté |
| LCD 1602 I2C | ×1 | A4/A5 | Affichage local | Acheté |
| LED ×3 (R/J/V) | ×3 | D11/D12/D13 + 220Ω | Indicateurs état | Acheté |
| Buzzer | ×1 | D6 | Alarme sonore | Acheté |
| Alimentation 12V 2A | ×1 | — | Pompe + vanne | Acheté |

### ⚠️ Règles critiques de câblage

```
DS18B20  : résistance 4.7kΩ entre Data et 5V  → sans elle : -127°C toujours
BMP280   : 3.3V uniquement, JAMAIS 5V          → le 5V le détruit définitivement
Relais   : LOW = pompe ON / HIGH = pompe OFF   → logique inversée !
```

---

## Installation

### Option A — Sur Raspberry Pi 4 (production)

```bash
# 1. Cloner le projet
git clone https://github.com/votre_repo/gnl_project.git
cd gnl_project

# 2. Installation complète (en root)
sudo bash raspberry_pi/scripts/install.sh

# 3. Démarrage
sudo systemctl start gnl
sudo systemctl status gnl
```

### Option B — Docker (développement sans hardware)

```bash
cd gnl_project/docker

# Démarrer tous les services
docker compose up -d

# Avec simulateur Arduino
docker compose --profile simulation up -d

# Logs
docker compose logs -f gnl_edge
```

### Option C — Manuel

```bash
# 1. Dépendances Python
pip3 install -r raspberry_pi/requirements.txt --break-system-packages

# 2. Mosquitto
sudo apt install mosquitto mosquitto-clients
sudo bash raspberry_pi/security/setup_security.sh

# 3. InfluxDB
# Voir : https://docs.influxdata.com/influxdb/v2/install/

# 4. Lancement
cd raspberry_pi
python3 gnl_main.py
```

---

## Configuration

### Variables d'environnement

```bash
# /etc/gnl/gnl.env
SERIAL_PORT=/dev/ttyUSB0       # port Arduino (USB)
MQTT_HOST=localhost
MQTT_PORT=8883
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=gnl_influx_token_secret_2025
GNL_JWT_SECRET=gnl_jwt_secret_change_in_prod
```

### Seuils IA (anomaly_engine.py)

```python
GAS_WARN    = 250   # ADC → LED jaune + MQTT ATTENTION
GAS_DANGER  = 450   # ADC → LED rouge + ESD si confirmé 3×
LEVEL_HIGH  = 95    # % → débordement imminent
LEVEL_LOW   = 10    # % → cavitation pompe
CONFIRM_GAS = 3     # mesures consécutives pour confirmer alarme gaz
```

---

## Démarrage

```bash
# Démarrer le service
sudo systemctl start gnl

# Voir les logs en temps réel
journalctl -fu gnl

# Statut
sudo systemctl status gnl

# Arrêt propre
sudo systemctl stop gnl
```

### Accès aux interfaces

| Interface | URL | Identifiants |
|-----------|-----|--------------|
| Dashboard HTML | `http://<IP_RPi>:5000` | admin / admin_GNL_2025! |
| API REST | `http://<IP_RPi>:5000/api/v1/` | JWT via `/auth/login` |
| Grafana | `http://<IP_RPi>:3000` | gnl_admin / GNL_Grafana_2025! |
| InfluxDB | `http://<IP_RPi>:8086` | gnl_admin / GNL_Influx_2025! |

---

## API REST

Base URL : `http://<IP>:5000/api/v1`

### Authentification

```bash
curl -X POST /api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin_GNL_2025!"}'
# → {"token": "eyJ...", "role": "admin", "expires_in": 3600}
```

### Endpoints

| Méthode | Endpoint | Rôle | Auth |
|---------|----------|------|------|
| GET | `/health` | Health check | Non |
| POST | `/auth/login` | Obtenir token JWT | Non |
| GET | `/status` | État général | operator |
| GET | `/data/latest` | Dernières mesures | operator |
| GET | `/ai/scores` | Scores IA courants | operator |
| GET | `/alerts` | Journal alertes | operator |
| POST | `/cmd/pompe` | Commande pompe | **admin** |
| POST | `/cmd/vanne` | Commande vanne | **admin** |
| POST | `/cmd/esd` | Arrêt d'urgence | **admin** |

```bash
# Exemple commande pompe
curl -X POST /api/v1/cmd/pompe \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"ON"}'
```

---

## Base de données

### InfluxDB — Measurements

| Measurement | Tags | Fields | Fréquence |
|-------------|------|--------|-----------|
| `niveau` | reservoir (R1/R2) | valeur (%), prediction_30s | 2s |
| `temperature` | capteur | valeur (°C) | 2s |
| `gaz` | capteur, niveau | valeur_adc (0-1023) | 2s |
| `pression` | capteur | valeur_hpa | 2s |
| `actuateurs` | — | pompe (0/1), vanne (0/1) | 2s |
| `ia_scores` | — | isolation_forest, global_risk, overflow_risk | 2s |
| `alertes` | type, source | valeur, global_risk | événement |

### Requête Flux exemple

```flux
from(bucket: "gnl_monitoring")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "niveau" and r.reservoir == "R1")
  |> aggregateWindow(every: 10s, fn: mean)
```

---

## Sécurité

### Mesures implémentées

| Couche | Mesure | Norme |
|--------|--------|-------|
| Transport | MQTT over TLS 1.3 | IEC 62443-3-3 |
| Authentification | Username/password + JWT API | NIST SP 800-183 |
| Autorisation | ACL MQTT par topic et rôle | IEC 62443-3-3 |
| Réseau | UFW firewall (SSH limité, API LAN only) | — |
| Anti-brute force | fail2ban SSH + MQTT | — |
| SSH | Root login désactivé, password auth désactivé | CIS Benchmark |
| Journalisation | Logs horodatés : Mosquitto + systemd journal | IEC 61511 |

### MQTT Topics — Droits d'accès

| Topic | gnl_publisher | gnl_dashboard | gnl_admin |
|-------|--------------|---------------|-----------|
| `gnl/niveau/#` | Write | Read | R/W |
| `gnl/gaz/mq4` | Write | Read | R/W |
| `gnl/ia/score` | Write | Read | R/W |
| `gnl/alerte` | Write | Read | R/W |
| `gnl/cmd/pompe` | Read | — | Write |
| `gnl/cmd/esd` | Read | — | Write |

---

## Tests

```bash
# Exécution des tests unitaires
cd gnl_project
pip3 install pytest --break-system-packages
python3 -m pytest tests/ -v

# Couverture
python3 -m pytest tests/ -v --tb=short
```

### Tests couverts (15 tests)

- Initialisation moteur IA
- Retour des clés requises
- Données normales → risque bas
- Classification gaz (seuils 250/450)
- Confirmation alarme gaz (3 mesures)
- Déclenchement ESD automatique
- Arrêt pompe si niveau bas
- Régression disponible après N échantillons
- Détection overflow risk
- Score global risque
- Reset compteur gaz

---

## Grafana

### Import du dashboard

1. Ouvrir Grafana → `http://<IP>:3000`
2. `Dashboards → Import`
3. Charger le fichier `raspberry_pi/dashboard/grafana_dashboard.json`
4. Sélectionner la datasource InfluxDB GNL
5. Cliquer `Import`

### Panels disponibles

- Jauges : Niveau R1, Niveau R2, Score IA, Gaz MQ-4
- Graphes temporels : Évolution niveaux (1h), Températures, Pression
- Tableau : Journal alertes 24h
- Annotations : Marqueurs automatiques sur événements critiques

---

## Analyse HAZOP

10 scénarios de risque identifiés (conforme IEC 61511) :

| Nœud | Déviation | Gravité | Action automatique |
|------|-----------|---------|-------------------|
| Réservoir R1 | Niveau trop élevé | **CRITIQUE** | Pompe STOP + Vanne fermée + MQTT |
| Réservoir R1 | Niveau trop bas | ÉLEVÉ | Pompe STOP + Alerte LCD |
| Réservoir R2 | Niveau trop élevé | ÉLEVÉ | Vanne fermée + Arrêt pompe |
| Tuyauterie | Fuite gaz (MQ-4) | **CRITIQUE** | ESD complet + Buzzer + LED Rouge |
| Pompe | Panne pompe | MOYEN | Alerte MQTT + Log |
| Électrovanne | Vanne bloquée ouverte | ÉLEVÉ | Coupure alimentation + ESD |
| MQ-4 | Fausse alarme | FAIBLE | Confirmation 3 mesures avant alarme |
| Raspberry Pi | Panne système | ÉLEVÉ | Watchdog systemd < 30s |
| Réseau MQTT | Interruption | MOYEN | Arduino continue en mode local |
| Alimentation 12V | Chute tension | MOYEN | Séquençage pompe/vanne |

---

## Troubleshooting

### Arduino non détecté

```bash
ls /dev/ttyUSB*          # vérifier le port
dmesg | grep tty         # voir les connexions récentes
sudo usermod -aG dialout pi  # ajouter l'utilisateur au groupe serial
```

### BMP280 toujours à 0

```bash
i2cdetect -y 1           # scanner le bus I2C (doit montrer 0x76 ou 0x77)
# Si absent → vérifier le câblage (3.3V !)
```

### DS18B20 retourne -127°C

```
→ Résistance pull-up 4.7kΩ manquante entre Data et 5V
```

### MQTT connexion refusée

```bash
sudo systemctl status mosquitto
mosquitto_sub -h localhost -p 8883 \
  --cafile /etc/mosquitto/certs/ca.crt \
  -u gnl_dashboard -P "GNL_Dash_2025!" \
  -t "gnl/#" -v
```

### InfluxDB write error

```bash
influx ping                         # vérifier connexion
journalctl -fu gnl | grep Influx    # logs écriture
```

### Logs système

```bash
journalctl -fu gnl                  # logs service principal
tail -f /var/log/gnl/gnl_main.log   # logs fichier
tail -f /var/log/mosquitto/mosquitto.log  # logs MQTT
```

---

## Budget total

| Composant | Coût estimé (DA) |
|-----------|-----------------|
| Matériel Arduino + capteurs | ~6 500 DA |
| MQ-4 + Électrovanne + Tuyaux | ~2 190 DA |
| **Total** | **~8 690 DA** |

*Raspberry Pi 4 et Arduino Uno déjà disponibles*

---

## Références

- IEC 61511 — Functional Safety — SIS for Process Industry
- IEC 62443-3-3 — Industrial Communication Networks Security
- NIST SP 800-183 — Networks of Things (IoT Reference Architecture)
- IIC (Industrial Internet Consortium) — Reference Architecture 2023
- Isolation Forest : Liu et al., 2008 — *Isolation Forest*, IEEE ICDM
- Mosquitto MQTT Broker : https://mosquitto.org
- InfluxDB 2.x : https://www.influxdata.com
- Grafana OSS : https://grafana.com

---

*Projet M2 RSID 2025–2026 — Système IoT GNL Edge Computing*
