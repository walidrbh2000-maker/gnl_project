#!/bin/sh
# ============================================================
# mosquitto-entrypoint.sh
# Crée le fichier passwd au démarrage à partir des variables
# d'environnement MQTT_USER / MQTT_PASSWORD.
#
# Fix Bug #2 : le fichier `passwd` n'était jamais créé.
# ============================================================
set -e

PASSWD_FILE="/mosquitto/config/passwd"
CONFIG_DIR="/mosquitto/config"
DATA_DIR="/mosquitto/data"
LOG_DIR="/mosquitto/log"

# --- Création des répertoires nécessaires ---
mkdir -p "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR"

# --- Vérification des variables obligatoires ---
if [ -z "$MQTT_USER" ]; then
  echo "[entrypoint] ERREUR : variable MQTT_USER non définie." >&2
  exit 1
fi

if [ -z "$MQTT_PASSWORD" ]; then
  echo "[entrypoint] ERREUR : variable MQTT_PASSWORD non définie." >&2
  exit 1
fi

# --- Création / mise à jour du fichier passwd ---
# -c : crée le fichier (écrase s'il existe)
# -b : mode batch (mot de passe en argument, pas interactif)
mosquitto_passwd -c -b "$PASSWD_FILE" "$MQTT_USER" "$MQTT_PASSWORD"
echo "[entrypoint] Fichier passwd créé pour l'utilisateur '$MQTT_USER'."

# --- Permissions strictes sur le fichier passwd ---
chmod 600 "$PASSWD_FILE"
chown mosquitto:mosquitto "$PASSWD_FILE" 2>/dev/null || true

# --- Lancement de Mosquitto ---
echo "[entrypoint] Démarrage de mosquitto..."
exec mosquitto -c /mosquitto/config/mosquitto.conf "$@"
