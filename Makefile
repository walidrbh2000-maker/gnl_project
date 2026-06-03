# ==============================================================================
#  GNL IoT Edge — Makefile (prototype sans TLS)
#  À placer à la RACINE du projet : gnl_project/Makefile
#  ⚠️  Port MQTT : 1883 (plain). TLS désactivé pour développement local.
#  Usage : make help
# ==============================================================================

.DEFAULT_GOAL := help
.PHONY: all help start stop restart status logs clean fclean \
        install install-python install-system install-docker \
        setup-security setup-influx setup-mqtt \
        up down build rebuild \
        sim sim-leak sim-overflow sim-stop \
        test test-verbose test-coverage \
        download-gemma4 start-gemma4 stop-gemma4 \
        backup restore \
        check-deps check-ports check-serial \
        update-passwords \
        api-status api-login api-data api-alerts \
        mqtt-listen mqtt-publish-test \
        influx-query influx-backup \
        grafana-open dashboard-open \
        lint format \
        docker-clean docker-logs docker-ps

# ── Couleurs ───────────────────────────────────────────────────────────────────
RED    := \033[0;31m
GREEN  := \033[0;32m
YELLOW := \033[1;33m
BLUE   := \033[0;34m
CYAN   := \033[0;36m
BOLD   := \033[1m
NC     := \033[0m

# ── Variables (chemins relatifs à la racine du projet) ─────────────────────────
PROJECT_DIR   := $(shell pwd)
DOCKER_DIR    := $(PROJECT_DIR)/docker
RPI_DIR       := $(PROJECT_DIR)/raspberry_pi
TESTS_DIR     := $(PROJECT_DIR)/tests

COMPOSE        := docker compose -f $(DOCKER_DIR)/docker-compose.yml
COMPOSE_SIM    := $(COMPOSE) --profile simulation
COMPOSE_GEMMA  := $(COMPOSE) -f $(DOCKER_DIR)/docker-compose.gemma4.yml

PYTHON         := python3
PIP            := pip3

# Chargement des variables .env si présent
-include .env
export

# IP du RPi ou localhost si Docker
RPI_HOST       ?= localhost
API_URL        := http://$(RPI_HOST):5000/api/v1
GRAFANA_URL    := http://$(RPI_HOST):3000
INFLUX_URL     ?= http://$(RPI_HOST):8086

# Port MQTT — lu depuis .env (MQTT_PORT=1883 en mode prototype sans TLS)
MQTT_PORT      ?= 1883

# Token JWT (récupéré dynamiquement)
JWT_TOKEN      := $(shell curl -s -X POST $(API_URL)/auth/login \
                   -H "Content-Type: application/json" \
                   -d '{"username":"admin","password":"admin_GNL_2025!"}' \
                   2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('token',''))" 2>/dev/null)

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🚀  COMMANDE PRINCIPALE
# ── ══════════════════════════════════════════════════════════════════════════ ──

## start       : Télécharge tout et lance le projet complet (Docker)
start: check-deps .env
	@echo -e "$(BOLD)$(CYAN)╔══════════════════════════════════════════════════╗$(NC)"
	@echo -e "$(BOLD)$(CYAN)║     🚀  Démarrage GNL IoT Edge Node              ║$(NC)"
	@echo -e "$(BOLD)$(CYAN)╚══════════════════════════════════════════════════╝$(NC)"
	@echo -e "$(GREEN)► Étape 1/5 — Vérification des dépendances Python...$(NC)"
	@$(MAKE) install-python --no-print-directory
	@echo -e "$(GREEN)► Étape 2/5 — Construction des images Docker...$(NC)"
	@$(MAKE) build --no-print-directory
	@echo -e "$(GREEN)► Étape 3/5 — Lancement des services (MQTT, InfluxDB, Grafana)...$(NC)"
	@$(COMPOSE_SIM) up -d
	@echo -e "$(GREEN)► Étape 4/5 — Attente démarrage services (30s)...$(NC)"
	@sleep 5 && echo -e "  . 5s" && sleep 5 && echo -e "  .. 10s" && \
	 sleep 5 && echo -e "  ... 15s" && sleep 5 && echo -e "  .... 20s" && \
	 sleep 5 && echo -e "  ..... 25s" && sleep 5 && echo -e "  ...... 30s ✓"
	@echo -e "$(GREEN)► Étape 5/5 — Vérification de l'état des services...$(NC)"
	@$(MAKE) status --no-print-directory
	@echo ""
	@echo -e "$(BOLD)$(GREEN)✅  GNL IoT Edge opérationnel !$(NC)"
	@echo -e ""
	@echo -e "$(BOLD)Accès aux interfaces :$(NC)"
	@echo -e "  $(CYAN)Dashboard HTML$(NC)  →  http://$(RPI_HOST):5000"
	@echo -e "  $(CYAN)API REST$(NC)        →  http://$(RPI_HOST):5000/api/v1"
	@echo -e "  $(CYAN)Grafana$(NC)         →  http://$(RPI_HOST):3000  (gnl_admin / GNL_Grafana_2025!)"
	@echo -e "  $(CYAN)InfluxDB$(NC)        →  http://$(RPI_HOST):8086  (gnl_admin / GNL_Influx_2025!)"
	@echo -e "  $(CYAN)MQTT plain$(NC)      →  mqtt://$(RPI_HOST):$(MQTT_PORT)  (sans TLS)"
	@echo -e ""
	@echo -e "  $(YELLOW)make logs$(NC)       → voir les logs en direct"
	@echo -e "  $(YELLOW)make stop$(NC)       → arrêter tous les services"
	@echo -e "  $(YELLOW)make help$(NC)       → toutes les commandes disponibles"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🛑  CONTRÔLE DU SYSTÈME
# ── ══════════════════════════════════════════════════════════════════════════ ──

## stop        : Arrête tous les conteneurs Docker
stop:
	@echo -e "$(YELLOW)► Arrêt des services GNL...$(NC)"
	@$(COMPOSE_SIM) down
	@echo -e "$(GREEN)✓ Services arrêtés$(NC)"

## restart     : Redémarre tous les services
restart: stop
	@sleep 2
	@$(MAKE) up --no-print-directory

## up          : Lance les services (sans rebuild)
up:
	@echo -e "$(GREEN)► Lancement des services...$(NC)"
	@$(COMPOSE_SIM) up -d
	@echo -e "$(GREEN)✓ Services démarrés$(NC)"

## down        : Arrête et supprime les conteneurs
down:
	@$(COMPOSE_SIM) down --remove-orphans

## build       : Construit les images Docker
build:
	@echo -e "$(BLUE)► Construction des images Docker...$(NC)"
	@$(COMPOSE) build --no-cache
	@echo -e "$(GREEN)✓ Images construites$(NC)"

## rebuild     : Force la reconstruction complète
rebuild:
	@echo -e "$(YELLOW)► Reconstruction forcée...$(NC)"
	@$(COMPOSE_SIM) down
	@$(COMPOSE) build --no-cache --pull
	@$(COMPOSE_SIM) up -d

## status      : Affiche l'état de tous les services
status:
	@echo -e "$(BOLD)$(BLUE)══ État des services GNL ══$(NC)"
	@$(COMPOSE) ps
	@echo ""
	@echo -e "$(BOLD)$(BLUE)══ Santé des endpoints ══$(NC)"
	@echo -n "  API REST    : " && \
	 curl -sf http://$(RPI_HOST):5000/health > /dev/null 2>&1 \
	 && echo -e "$(GREEN)● UP$(NC)" || echo -e "$(RED)● DOWN$(NC)"
	@echo -n "  InfluxDB    : " && \
	 curl -sf http://$(RPI_HOST):8086/ping > /dev/null 2>&1 \
	 && echo -e "$(GREEN)● UP$(NC)" || echo -e "$(RED)● DOWN$(NC)"
	@echo -n "  Grafana     : " && \
	 curl -sf http://$(RPI_HOST):3000/api/health > /dev/null 2>&1 \
	 && echo -e "$(GREEN)● UP$(NC)" || echo -e "$(RED)● DOWN$(NC)"
	@echo -n "  MQTT        : " && \
	 docker exec gnl_mosquitto mosquitto_sub \
	   -h localhost -p $(MQTT_PORT) \
	   -u gnl_dashboard -P "GNL_Dash_2025!" \
	   -t '$$SYS/broker/uptime' -C 1 --quiet -W 3 \
	   > /dev/null 2>&1 \
	 && echo -e "$(GREEN)● UP$(NC)" || echo -e "$(RED)● DOWN$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  📦  INSTALLATION
# ── ══════════════════════════════════════════════════════════════════════════ ──

## install     : Installation complète (système + Python)
install: install-system install-python
	@echo -e "$(GREEN)✓ Installation complète$(NC)"

## install-system : Installe les dépendances système (apt)
install-system:
	@echo -e "$(BLUE)► Installation dépendances système...$(NC)"
	@which apt-get > /dev/null 2>&1 || (echo -e "$(YELLOW)  apt-get non disponible — skip$(NC)" && exit 0)
	@sudo apt-get update -qq
	@sudo apt-get install -y -qq \
	    python3-pip python3-venv python3-serial \
	    mosquitto mosquitto-clients \
	    git curl openssl ufw fail2ban \
	    libopenblas-dev libatlas-base-dev 2>/dev/null || true
	@echo -e "$(GREEN)✓ Dépendances système installées$(NC)"

## install-python : Installe les packages Python depuis requirements.txt
install-python:
	@echo -e "$(BLUE)► Installation packages Python...$(NC)"
	@[ -f "$(RPI_DIR)/requirements.txt" ] || \
	  (echo -e "$(RED)✗ Fichier non trouvé : $(RPI_DIR)/requirements.txt$(NC)" && exit 1)
	@$(PIP) install --break-system-packages -q -r $(RPI_DIR)/requirements.txt
	@echo -e "$(GREEN)✓ Packages Python installés$(NC)"

## install-docker : Installe Docker et Docker Compose
install-docker:
	@echo -e "$(BLUE)► Installation Docker...$(NC)"
	@which docker > /dev/null 2>&1 && echo -e "$(YELLOW)  Docker déjà installé$(NC)" && exit 0 || true
	@curl -fsSL https://get.docker.com | sudo bash
	@sudo usermod -aG docker $$USER
	@echo -e "$(GREEN)✓ Docker installé$(NC)"
	@echo -e "$(YELLOW)  → Redémarrer la session pour activer les droits Docker$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🔒  SÉCURITÉ
# ── ══════════════════════════════════════════════════════════════════════════ ──

## setup-security : Configure UFW, fail2ban, SSH (sans TLS MQTT en mode prototype)
setup-security:
	@echo -e "$(BLUE)► Configuration sécurité (sans TLS MQTT)...$(NC)"
	@sudo bash $(RPI_DIR)/security/setup_security.sh

## update-passwords : Met à jour les mots de passe MQTT dans le conteneur
update-passwords:
	@echo -e "$(YELLOW)► Mise à jour des mots de passe MQTT...$(NC)"
	@read -p "Nouveau mot de passe pour gnl_publisher : " p1 && \
	 docker exec gnl_mosquitto mosquitto_passwd \
	   -b /mosquitto/config/passwd gnl_publisher "$$p1" && \
	 echo -e "$(GREEN)✓ gnl_publisher mis à jour$(NC)"
	@read -p "Nouveau mot de passe pour gnl_dashboard : " p2 && \
	 docker exec gnl_mosquitto mosquitto_passwd \
	   -b /mosquitto/config/passwd gnl_dashboard "$$p2" && \
	 echo -e "$(GREEN)✓ gnl_dashboard mis à jour$(NC)"
	@docker exec gnl_mosquitto kill -HUP 1 2>/dev/null || true

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🤖  SIMULATEUR ARDUINO
# ── ══════════════════════════════════════════════════════════════════════════ ──

## sim         : Lance le simulateur Arduino (scénario normal)
sim:
	@echo -e "$(GREEN)► Simulateur Arduino — scénario NORMAL$(NC)"
	@$(COMPOSE_SIM) up -d arduino_simulator
	@echo -e "$(GREEN)✓ Simulateur démarré$(NC)"

## sim-leak    : Simule une fuite de gaz progressive
sim-leak:
	@echo -e "$(YELLOW)► Simulateur Arduino — scénario FUITE_GAZ$(NC)"
	@docker run --rm -d \
	  --network gnl_net \
	  --name gnl_sim_leak \
	  -e MQTT_HOST=mosquitto \
	  -e MQTT_PORT=$(MQTT_PORT) \
	  -e MQTT_USER=gnl_publisher \
	  -e MQTT_PASS="GNL_Secure_2025!" \
	  gnl_arduino_sim python3 arduino_simulator.py \
	    --mode mqtt \
	    --host mosquitto \
	    --port $(MQTT_PORT) \
	    --scenario fuite_gaz \
	  2>/dev/null || true
	@echo -e "$(YELLOW)⚠  Scénario fuite gaz actif — surveiller les alertes$(NC)"

## sim-overflow : Simule un débordement de réservoir
sim-overflow:
	@echo -e "$(RED)► Simulateur Arduino — scénario DÉBORDEMENT$(NC)"
	@docker run --rm -d \
	  --network gnl_net \
	  --name gnl_sim_overflow \
	  -e MQTT_HOST=mosquitto \
	  -e MQTT_PORT=$(MQTT_PORT) \
	  -e MQTT_USER=gnl_publisher \
	  -e MQTT_PASS="GNL_Secure_2025!" \
	  gnl_arduino_sim python3 arduino_simulator.py \
	    --mode mqtt \
	    --host mosquitto \
	    --port $(MQTT_PORT) \
	    --scenario debordement \
	  2>/dev/null || true
	@echo -e "$(RED)⚠  Scénario débordement actif — ESD attendu !$(NC)"

## sim-stop    : Arrête tous les simulateurs
sim-stop:
	@echo -e "$(YELLOW)► Arrêt des simulateurs...$(NC)"
	@docker stop gnl_sim_leak gnl_sim_overflow 2>/dev/null || true
	@$(COMPOSE) stop arduino_simulator 2>/dev/null || true
	@echo -e "$(GREEN)✓ Simulateurs arrêtés$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🧪  TESTS
# ── ══════════════════════════════════════════════════════════════════════════ ──

## test        : Lance les tests unitaires (pytest)
test:
	@echo -e "$(BLUE)► Exécution des tests unitaires...$(NC)"
	@$(PIP) install --break-system-packages -q pytest pytest-cov 2>/dev/null || true
	@cd $(PROJECT_DIR) && $(PYTHON) -m pytest $(TESTS_DIR)/ -v --tb=short
	@echo -e "$(GREEN)✓ Tests terminés$(NC)"

## test-verbose : Tests avec sortie détaillée
test-verbose:
	@cd $(PROJECT_DIR) && $(PYTHON) -m pytest $(TESTS_DIR)/ -vvv --tb=long -s

## test-coverage : Tests avec rapport de couverture HTML
test-coverage:
	@echo -e "$(BLUE)► Tests avec couverture de code...$(NC)"
	@$(PIP) install --break-system-packages -q pytest pytest-cov 2>/dev/null || true
	@cd $(PROJECT_DIR) && $(PYTHON) -m pytest $(TESTS_DIR)/ \
	  --cov=$(RPI_DIR)/ai \
	  --cov-report=html:coverage_html \
	  --cov-report=term-missing \
	  -v
	@echo -e "$(GREEN)✓ Rapport HTML : $(PROJECT_DIR)/coverage_html/index.html$(NC)"

## lint        : Vérifie la qualité du code Python (flake8)
lint:
	@$(PIP) install --break-system-packages -q flake8 2>/dev/null || true
	@echo -e "$(BLUE)► Analyse statique du code...$(NC)"
	@flake8 $(RPI_DIR) --max-line-length=100 --exclude=__pycache__ || true

## format      : Formate le code Python (black)
format:
	@$(PIP) install --break-system-packages -q black 2>/dev/null || true
	@echo -e "$(BLUE)► Formatage du code...$(NC)"
	@black $(RPI_DIR) $(TESTS_DIR) --line-length=100
	@echo -e "$(GREEN)✓ Code formaté$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🧠  GEMMA4 — IA LOCALE (EDGE LLM)
# ── ══════════════════════════════════════════════════════════════════════════ ──

## download-gemma4 : Télécharge le modèle Gemma4 E2B Q4_K_M (~3.5GB)
download-gemma4:
	@echo -e "$(BLUE)► Téléchargement de Gemma4 E2B Q4_K_M...$(NC)"
	@echo -e "$(YELLOW)  Taille estimée : ~3.5 GB — connexion internet requise$(NC)"
	@[ -f .env ] && . ./.env || true
	@mkdir -p $(DOCKER_DIR)/models/gemma4
	@$(PIP) install --break-system-packages -q huggingface_hub 2>/dev/null || true
	@$(PYTHON) -c "\
from huggingface_hub import hf_hub_download; \
import os; \
token = os.environ.get('HF_TOKEN'); \
print('  → Téléchargement modèle GGUF...'); \
hf_hub_download( \
    repo_id='bartowski/google_gemma-4-e2b-it-GGUF', \
    filename='google_gemma-4-e2b-it-Q4_K_M.gguf', \
    local_dir='$(DOCKER_DIR)/models/gemma4', \
    token=token \
); \
print('  → Téléchargement mmproj...'); \
hf_hub_download( \
    repo_id='bartowski/google_gemma-4-e2b-it-GGUF', \
    filename='mmproj-google_gemma-4-e2b-it-bf16.gguf', \
    local_dir='$(DOCKER_DIR)/models/gemma4', \
    token=token \
); \
print('Modèles téléchargés !') \
"
	@echo -e "$(GREEN)✓ Gemma4 téléchargé dans $(DOCKER_DIR)/models/gemma4$(NC)"

## start-gemma4 : Lance le serveur llama.cpp avec Gemma4
start-gemma4:
	@echo -e "$(BLUE)► Lancement Gemma4 (llama.cpp server)...$(NC)"
	@[ -f "$(DOCKER_DIR)/models/gemma4/$(GEMMA4_MODEL_FILE)" ] || \
	 (echo -e "$(RED)✗ Modèle non trouvé — lancer : make download-gemma4$(NC)" && exit 1)
	@$(COMPOSE_GEMMA) up -d gemma4
	@echo -e "$(GREEN)✓ Gemma4 démarré sur http://$(RPI_HOST):8080$(NC)"
	@echo -e "$(YELLOW)  Attendre ~30s pour le chargement du modèle$(NC)"

## stop-gemma4 : Arrête le serveur Gemma4
stop-gemma4:
	@$(COMPOSE_GEMMA) stop gemma4 2>/dev/null || \
	 docker stop gnl_gemma4 2>/dev/null || true
	@echo -e "$(GREEN)✓ Gemma4 arrêté$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  📊  MQTT
# ── ══════════════════════════════════════════════════════════════════════════ ──

## setup-mqtt  : Initialise les utilisateurs Mosquitto dans le conteneur
setup-mqtt:
	@echo -e "$(BLUE)► Configuration des utilisateurs Mosquitto...$(NC)"
	@docker exec gnl_mosquitto sh -c "\
	  mosquitto_passwd -c -b /mosquitto/config/passwd \
	    gnl_publisher 'GNL_Secure_2025!' && \
	  mosquitto_passwd    -b /mosquitto/config/passwd \
	    gnl_dashboard 'GNL_Dash_2025!'  && \
	  mosquitto_passwd    -b /mosquitto/config/passwd \
	    gnl_admin 'GNL_Admin_2025!'" \
	  2>/dev/null || true
	@docker exec gnl_mosquitto kill -HUP 1 2>/dev/null || true
	@echo -e "$(GREEN)✓ Utilisateurs MQTT créés$(NC)"
	@echo -e "$(YELLOW)  → Si erreur de connexion, relancer : make setup-mqtt$(NC)"

## mqtt-listen : Écoute tous les topics MQTT en temps réel (plain, sans TLS)
mqtt-listen:
	@echo -e "$(BLUE)► Écoute MQTT plain (port $(MQTT_PORT)) — Ctrl+C pour arrêter...$(NC)"
	@docker exec gnl_mosquitto mosquitto_sub \
	  -h localhost \
	  -p $(MQTT_PORT) \
	  -u gnl_dashboard \
	  -P "GNL_Dash_2025!" \
	  -t "gnl/#" \
	  -v \
	  2>/dev/null || \
	mosquitto_sub \
	  -h $(RPI_HOST) \
	  -p $(MQTT_PORT) \
	  -u gnl_dashboard \
	  -P "GNL_Dash_2025!" \
	  -t "gnl/#" \
	  -v

## mqtt-publish-test : Publie un message de test MQTT (plain, sans TLS)
mqtt-publish-test:
	@echo -e "$(BLUE)► Publication message test MQTT (port $(MQTT_PORT))...$(NC)"
	@docker exec gnl_mosquitto mosquitto_pub \
	  -h localhost \
	  -p $(MQTT_PORT) \
	  -u gnl_publisher \
	  -P "GNL_Secure_2025!" \
	  -t "gnl/test" \
	  -m '{"test":true,"source":"makefile","timestamp":"$(shell date -Iseconds)"}' \
	  && echo -e "$(GREEN)✓ Message publié$(NC)" \
	  || echo -e "$(RED)✗ Échec — broker accessible ?$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🗄️  INFLUXDB
# ── ══════════════════════════════════════════════════════════════════════════ ──

## setup-influx : Initialise InfluxDB (organisation + bucket)
setup-influx:
	@echo -e "$(BLUE)► Configuration InfluxDB...$(NC)"
	@sleep 3
	@docker exec gnl_influxdb influx setup \
	  --username gnl_admin \
	  --password "GNL_Influx_2025!" \
	  --org gnl_org \
	  --bucket gnl_monitoring \
	  --retention 30d \
	  --force 2>/dev/null || echo -e "$(YELLOW)  InfluxDB déjà configuré$(NC)"
	@echo -e "$(GREEN)✓ InfluxDB configuré$(NC)"

## influx-query : Requête rapide des dernières mesures
influx-query:
	@echo -e "$(BOLD)$(BLUE)══ Dernières mesures InfluxDB ══$(NC)"
	@curl -sf -XPOST "$(INFLUX_URL)/api/v2/query" \
	  -H "Authorization: Token $(INFLUX_TOKEN)" \
	  -H "Content-Type: application/vnd.flux" \
	  -d 'from(bucket:"gnl_monitoring") |> range(start: -5m) |> last()' \
	  2>/dev/null | head -50 || echo -e "$(YELLOW)  InfluxDB non accessible$(NC)"

## influx-backup : Sauvegarde les données InfluxDB
influx-backup:
	@echo -e "$(BLUE)► Sauvegarde InfluxDB...$(NC)"
	@mkdir -p $(PROJECT_DIR)/backups
	@docker exec gnl_influxdb influx backup /tmp/influx_backup 2>/dev/null && \
	 docker cp gnl_influxdb:/tmp/influx_backup \
	   $(PROJECT_DIR)/backups/influx_$(shell date +%Y%m%d_%H%M%S)/ && \
	 echo -e "$(GREEN)✓ Sauvegarde effectuée$(NC)" || \
	 echo -e "$(RED)✗ Échec sauvegarde$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🌐  API REST
# ── ══════════════════════════════════════════════════════════════════════════ ──

## api-status  : Vérifie l'état de l'API REST
api-status:
	@echo -e "$(BOLD)$(BLUE)══ API REST — Health Check ══$(NC)"
	@curl -sf $(API_URL)/../health | python3 -m json.tool 2>/dev/null || \
	 echo -e "$(RED)✗ API non accessible$(NC)"

## api-login   : Obtient un token JWT admin
api-login:
	@echo -e "$(BOLD)$(BLUE)══ Authentification API ══$(NC)"
	@curl -s -X POST $(API_URL)/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"admin","password":"admin_GNL_2025!"}' \
	  | python3 -m json.tool

## api-data    : Lit les dernières mesures (JWT requis)
api-data:
	@echo -e "$(BOLD)$(BLUE)══ Dernières mesures ══$(NC)"
	@TOKEN=$$(curl -s -X POST $(API_URL)/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"admin","password":"admin_GNL_2025!"}' \
	  | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))") && \
	curl -s $(API_URL)/data/latest \
	  -H "Authorization: Bearer $$TOKEN" \
	  | python3 -m json.tool

## api-alerts  : Lit le journal des alertes
api-alerts:
	@echo -e "$(BOLD)$(BLUE)══ Journal des alertes ══$(NC)"
	@TOKEN=$$(curl -s -X POST $(API_URL)/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"admin","password":"admin_GNL_2025!"}' \
	  | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))") && \
	curl -s $(API_URL)/alerts \
	  -H "Authorization: Bearer $$TOKEN" \
	  | python3 -m json.tool

## api-esd     : Déclenche un arrêt d'urgence via API
api-esd:
	@echo -e "$(RED)⚠  DÉCLENCHEMENT ESD VIA API...$(NC)"
	@read -p "Confirmer ESD [oui/NON] : " confirm && [ "$$confirm" = "oui" ] || exit 1
	@TOKEN=$$(curl -s -X POST $(API_URL)/auth/login \
	  -H "Content-Type: application/json" \
	  -d '{"username":"admin","password":"admin_GNL_2025!"}' \
	  | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))") && \
	curl -s -X POST $(API_URL)/cmd/esd \
	  -H "Authorization: Bearer $$TOKEN" \
	  | python3 -m json.tool

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  📋  LOGS
# ── ══════════════════════════════════════════════════════════════════════════ ──

## logs        : Affiche les logs de tous les services (live)
logs:
	@$(COMPOSE_SIM) logs -f --tail=50

## logs-edge   : Logs du nœud Edge (API + IA)
logs-edge:
	@$(COMPOSE) logs -f --tail=100 gnl_edge

## logs-mqtt   : Logs du broker Mosquitto
logs-mqtt:
	@$(COMPOSE) logs -f --tail=100 mosquitto

## logs-influx : Logs InfluxDB
logs-influx:
	@$(COMPOSE) logs -f --tail=50 influxdb

## logs-sim    : Logs du simulateur Arduino
logs-sim:
	@$(COMPOSE) logs -f --tail=100 arduino_simulator

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  📺  INTERFACES WEB
# ── ══════════════════════════════════════════════════════════════════════════ ──

## grafana-open : Ouvre Grafana dans le navigateur
grafana-open:
	@xdg-open $(GRAFANA_URL) 2>/dev/null || open $(GRAFANA_URL) 2>/dev/null || \
	 echo -e "$(CYAN)  → Ouvrir manuellement : $(GRAFANA_URL)$(NC)"

## dashboard-open : Ouvre le Dashboard HTML
dashboard-open:
	@xdg-open http://$(RPI_HOST):5000 2>/dev/null || open http://$(RPI_HOST):5000 2>/dev/null || \
	 echo -e "$(CYAN)  → Ouvrir manuellement : http://$(RPI_HOST):5000$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🔌  DIAGNOSTIC
# ── ══════════════════════════════════════════════════════════════════════════ ──

## check-deps  : Vérifie que toutes les dépendances sont présentes
check-deps:
	@echo -e "$(BLUE)► Vérification des dépendances...$(NC)"
	@echo -n "  docker         : " && which docker > /dev/null 2>&1 \
	  && echo -e "$(GREEN)✓$(NC)" || (echo -e "$(RED)✗ non trouvé$(NC)" && exit 1)
	@echo -n "  docker compose : " && docker compose version > /dev/null 2>&1 \
	  && echo -e "$(GREEN)✓$(NC)" || (echo -e "$(RED)✗ non trouvé$(NC)" && exit 1)
	@echo -n "  python3        : " && which python3 > /dev/null 2>&1 \
	  && echo -e "$(GREEN)✓ ($(shell python3 --version))$(NC)" || echo -e "$(RED)✗$(NC)"
	@echo -n "  pip3           : " && which pip3 > /dev/null 2>&1 \
	  && echo -e "$(GREEN)✓$(NC)" || echo -e "$(RED)✗$(NC)"
	@echo -n "  curl           : " && which curl > /dev/null 2>&1 \
	  && echo -e "$(GREEN)✓$(NC)" || echo -e "$(YELLOW)⚠ non trouvé$(NC)"
	@echo -e "$(GREEN)✓ Vérification terminée$(NC)"

## check-ports : Vérifie que les ports requis sont disponibles
check-ports:
	@echo -e "$(BOLD)$(BLUE)══ Vérification des ports ══$(NC)"
	@for port in $(MQTT_PORT) 8086 5000 3000 8080; do \
	  echo -n "  Port $$port : "; \
	  if ss -tlnp 2>/dev/null | grep -q ":$$port " || \
	     netstat -tlnp 2>/dev/null | grep -q ":$$port "; then \
	    echo -e "$(YELLOW)⚠ occupé$(NC)"; \
	  else \
	    echo -e "$(GREEN)✓ libre$(NC)"; \
	  fi; \
	done

## check-serial : Détecte les ports série Arduino
check-serial:
	@echo -e "$(BOLD)$(BLUE)══ Ports série détectés ══$(NC)"
	@ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo -e "$(YELLOW)  Aucun port série détecté$(NC)"
	@dmesg 2>/dev/null | grep -E "tty|usb" | tail -5 || true

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  💾  SAUVEGARDE / RESTAURATION
# ── ══════════════════════════════════════════════════════════════════════════ ──

## backup      : Sauvegarde complète (config + données)
backup:
	@echo -e "$(BLUE)► Sauvegarde complète...$(NC)"
	@mkdir -p $(PROJECT_DIR)/backups
	@BACKUP_NAME="gnl_backup_$(shell date +%Y%m%d_%H%M%S)" && \
	 mkdir -p $(PROJECT_DIR)/backups/$$BACKUP_NAME && \
	 cp -r $(RPI_DIR) $(PROJECT_DIR)/backups/$$BACKUP_NAME/ && \
	 cp .env $(PROJECT_DIR)/backups/$$BACKUP_NAME/.env 2>/dev/null || true && \
	 tar -czf $(PROJECT_DIR)/backups/$$BACKUP_NAME.tar.gz \
	   -C $(PROJECT_DIR)/backups $$BACKUP_NAME && \
	 rm -rf $(PROJECT_DIR)/backups/$$BACKUP_NAME && \
	 echo -e "$(GREEN)✓ Sauvegarde : $(PROJECT_DIR)/backups/$$BACKUP_NAME.tar.gz$(NC)"

## restore     : Restaure depuis une sauvegarde (BACKUP=chemin)
restore:
	@[ -n "$(BACKUP)" ] || (echo -e "$(RED)✗ Spécifier : make restore BACKUP=chemin/backup.tar.gz$(NC)" && exit 1)
	@echo -e "$(YELLOW)► Restauration depuis $(BACKUP)...$(NC)"
	@tar -xzf $(BACKUP) -C $(PROJECT_DIR)/backups/
	@echo -e "$(GREEN)✓ Restauration terminée$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  🧹  NETTOYAGE
# ── ══════════════════════════════════════════════════════════════════════════ ──

## clean       : Supprime les fichiers temporaires Python
clean:
	@echo -e "$(YELLOW)► Nettoyage fichiers temporaires...$(NC)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@find . -name "*.pyo" -delete 2>/dev/null || true
	@rm -rf .pytest_cache coverage_html .coverage 2>/dev/null || true
	@echo -e "$(GREEN)✓ Nettoyage terminé$(NC)"

## docker-clean : Supprime les conteneurs, images et volumes GNL
docker-clean:
	@echo -e "$(YELLOW)⚠  Suppression des ressources Docker GNL...$(NC)"
	@read -p "Confirmer [oui/NON] : " c && [ "$$c" = "oui" ] || exit 1
	@$(COMPOSE_SIM) down -v --rmi local --remove-orphans
	@docker volume prune -f 2>/dev/null || true
	@echo -e "$(GREEN)✓ Nettoyage Docker terminé$(NC)"

## fclean      : Nettoyage complet (Python + Docker + backups)
fclean: clean docker-clean
	@rm -rf $(PROJECT_DIR)/backups 2>/dev/null || true
	@echo -e "$(GREEN)✓ Nettoyage complet$(NC)"

## docker-ps   : Affiche les conteneurs Docker GNL
docker-ps:
	@docker ps --filter "name=gnl_" --format \
	 "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

## docker-logs : Logs Docker de tous les conteneurs GNL
docker-logs:
	@docker logs --tail=30 gnl_edge_node 2>/dev/null && \
	 docker logs --tail=20 gnl_mosquitto 2>/dev/null || \
	 echo -e "$(YELLOW)  Aucun conteneur GNL actif$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  📄  GÉNÉRATION .env
# ── ══════════════════════════════════════════════════════════════════════════ ──

## .env        : Crée le fichier .env s'il n'existe pas
.env:
	@echo -e "$(YELLOW)► Fichier .env non trouvé — création avec valeurs par défaut...$(NC)"
	@printf '%s\n' \
	  '# GNL IoT Edge — Configuration générée automatiquement' \
	  '# ⚠  TLS désactivé — prototype localhost uniquement' \
	  '# ⚠  Modifier les mots de passe avant tout déploiement !' \
	  '' \
	  'HF_TOKEN=' \
	  'GEMMA4_VARIANT=e2b' \
	  'GEMMA4_QUANT=Q4_K_M' \
	  'GEMMA4_DEST=docker/models/gemma4' \
	  'GEMMA4_MODEL_FILE=google_gemma-4-e2b-it-Q4_K_M.gguf' \
	  'GEMMA4_MMPROJ_FILE=mmproj-google_gemma-4-e2b-it-bf16.gguf' \
	  'GEMMA4_CTX=4096' \
	  'GEMMA4_THREADS=4' \
	  'GEMMA4_GPU_LAYERS=0' \
	  'GEMMA4_SERVER_PORT=8080' \
	  'GEMMA4_HOST=0.0.0.0' \
	  '' \
	  'INFLUX_URL=http://influxdb:8086' \
	  'INFLUX_TOKEN=gnl_influx_token_secret_2025' \
	  'INFLUX_ORG=gnl_org' \
	  'INFLUX_BUCKET=gnl_monitoring' \
	  'DOCKER_INFLUXDB_INIT_MODE=setup' \
	  'DOCKER_INFLUXDB_INIT_USERNAME=gnl_admin' \
	  'DOCKER_INFLUXDB_INIT_PASSWORD=GNL_Influx_2025!' \
	  'DOCKER_INFLUXDB_INIT_ORG=gnl_org' \
	  'DOCKER_INFLUXDB_INIT_BUCKET=gnl_monitoring' \
	  'DOCKER_INFLUXDB_INIT_RETENTION=30d' \
	  'DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=gnl_influx_token_secret_2025' \
	  '' \
	  'MQTT_HOST=mosquitto' \
	  'MQTT_PORT=1883' \
	  'MQTT_USER_PUBLISHER=gnl_publisher' \
	  'MQTT_PASS_PUBLISHER=GNL_Secure_2025!' \
	  'MQTT_USER_DASHBOARD=gnl_dashboard' \
	  'MQTT_PASS_DASHBOARD=GNL_Dash_2025!' \
	  'MQTT_USER_ADMIN=gnl_admin' \
	  'MQTT_PASS_ADMIN=GNL_Admin_2025!' \
	  '' \
	  'GF_SECURITY_ADMIN_USER=gnl_admin' \
	  'GF_SECURITY_ADMIN_PASSWORD=GNL_Grafana_2025!' \
	  'GF_USERS_ALLOW_SIGN_UP=false' \
	  '' \
	  'GNL_JWT_SECRET=gnl_jwt_secret_change_in_prod' \
	  'API_HOST=0.0.0.0' \
	  'API_PORT=5000' \
	  '' \
	  'SERIAL_PORT=SIMULATED' \
	  'SERIAL_BAUD=9600' \
	  '' \
	  'GAS_WARN=250' \
	  'GAS_DANGER=450' \
	  'LEVEL_HIGH=95' \
	  'LEVEL_LOW=10' \
	  'CONFIRM_GAS=3' \
	  > .env
	@echo -e "$(GREEN)✓ .env créé$(NC)"

# ── ══════════════════════════════════════════════════════════════════════════ ──
##  ❓  AIDE
# ── ══════════════════════════════════════════════════════════════════════════ ──

## help        : Affiche cette aide
help:
	@echo -e ""
	@echo -e "$(BOLD)$(CYAN)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo -e "$(BOLD)$(CYAN)║   GNL IoT Edge — Makefile  (M2 RSID 2025-2026, sans TLS)  ║$(NC)"
	@echo -e "$(BOLD)$(CYAN)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo -e ""
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //' | \
	  awk 'BEGIN{FS=":"} \
	    /^[A-Z]/ {printf "  $(BOLD)$(YELLOW)%-20s$(NC) %s\n", $$1, $$2; next} \
	    {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo -e ""
	@echo -e "$(BOLD)Exemples rapides :$(NC)"
	@echo -e "  $(GREEN)make start$(NC)              → Tout démarrer (première fois)"
	@echo -e "  $(GREEN)make setup-mqtt$(NC)         → Créer les utilisateurs MQTT"
	@echo -e "  $(GREEN)make mqtt-listen$(NC)        → Écouter les topics MQTT"
	@echo -e "  $(GREEN)make sim-leak$(NC)           → Simuler une fuite de gaz"
	@echo -e "  $(GREEN)make test$(NC)               → Lancer les tests unitaires"
	@echo -e "  $(GREEN)make logs$(NC)               → Voir les logs en direct"
	@echo -e "  $(GREEN)make api-data$(NC)           → Lire les mesures capteurs"
	@echo -e "  $(GREEN)make download-gemma4$(NC)    → Télécharger l'IA locale"
	@echo -e ""
	@echo -e "$(BOLD)Structure du projet :$(NC)"
	@echo -e "  $(CYAN)$(PROJECT_DIR)/$(NC)"
	@echo -e "  ├── Makefile          ← CE fichier (à la racine)"
	@echo -e "  ├── .env              ← Variables d'environnement"
	@echo -e "  ├── docker/           ← Docker Compose, Dockerfiles"
	@echo -e "  ├── raspberry_pi/     ← Code Python Edge Node"
	@echo -e "  ├── arduino/          ← Code Arduino .ino"
	@echo -e "  └── tests/            ← Tests unitaires pytest"
	@echo -e ""
	@echo -e "$(BOLD)$(YELLOW)⚠  Mode prototype (sans TLS) — MQTT port 1883$(NC)"
	@echo -e "$(YELLOW)   Pour la production : activer TLS (port 8883) + certificats X.509$(NC)"
	@echo -e ""

# Alias pratiques
all: start
run: up
ps: docker-ps
