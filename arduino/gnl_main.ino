/*
====================================================
  PROTOTYPE IoT GNL — Arduino Uno
  Projet fin d'études M2 RSID
  Auteur : Etudiant M2 RSID 2025-2026
====================================================

COMPOSANTS :
  HC-SR04 R1  : TRIG=D9,  ECHO=D10
  HC-SR04 R2  : TRIG=D3,  ECHO=D4
  DS18B20 R1  : Data=D5  + résistance 4.7kΩ
  DS18B20 R2  : Data=D2  + résistance 4.7kΩ
  BMP280      : SDA=A4,  SCL=A5  (3.3V !)
  MQ-4        : AOUT=A0
  LCD I2C     : SDA=A4,  SCL=A5  (5V)
  LED Verte   : D11 + résistance 220Ω
  LED Jaune   : D12 + résistance 220Ω
  LED Rouge   : D13 + résistance 220Ω
  Buzzer      : D6
  Relais IN1  : D7  → pompe
  Relais IN2  : D8  → électrovanne

LIBRARIES :
  - OneWire
  - DallasTemperature
  - LiquidCrystal_I2C
  - Adafruit BMP280

FORMAT SERIAL (JSON) vers Raspberry Pi :
  {"n1":82,"n2":34,"t1":22.3,"t2":21.8,
   "p":1013.2,"g":145,"pump":0,"valve":0}

SEUILS GAZ MQ-4 :
  < 250  = Normal  (LED verte)
  250-450 = Attention (LED jaune + bip)
  > 450  = DANGER  (LED rouge + buzzer continu)

HAUTEUR RÉSERVOIRS (à ajuster selon tes réservoirs) :
  HAUTEUR_R1 = 20.0 cm (distance vide = réservoir vide)
  HAUTEUR_R2 = 20.0 cm
====================================================
*/

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_BMP280.h>

// =============================================
// CONFIGURATION RÉSERVOIRS
// =============================================
#define HAUTEUR_R1  20.0   // cm — ajuster selon ton réservoir
#define HAUTEUR_R2  20.0   // cm — ajuster selon ton réservoir
#define NIVEAU_PLEIN_R1  90  // % — déclenche distribution
#define NIVEAU_BAS_R2    20  // % — arrête distribution

// =============================================
// PINS
// =============================================
#define TRIG1       9
#define ECHO1       10
#define TRIG2       3
#define ECHO2       4

#define TEMP_R1     5
#define TEMP_R2     2

#define MQ4_PIN     A0

#define LED_GREEN   11
#define LED_YELLOW  12
#define LED_RED     13
#define BUZZER      6

#define RELAY_POMPE  7    // LOW = pompe ON
#define RELAY_VANNE  8    // LOW = vanne ouverte

// =============================================
// OBJETS
// =============================================
LiquidCrystal_I2C lcd(0x27, 16, 2);   // si ça marche pas : essayer 0x3F

OneWire ow1(TEMP_R1);
DallasTemperature ts1(&ow1);

OneWire ow2(TEMP_R2);
DallasTemperature ts2(&ow2);

Adafruit_BMP280 bmp;

// =============================================
// VARIABLES GLOBALES
// =============================================
float dist1, dist2;          // distances cm
float niveau1, niveau2;      // niveaux %
float temp1, temp2;          // températures °C
float pression;              // pression hPa
int   gasValue;              // valeur brute MQ-4
bool  pumpON  = false;
bool  valveON = false;
int   lcdPage = 0;           // page LCD (0 ou 1)
unsigned long lastLcdSwitch = 0;
unsigned long lastSerialSend = 0;

// =============================================
// FONCTIONS
// =============================================

// Mesure distance HC-SR04
float readDistance(int trig, int echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  long dur = pulseIn(echo, HIGH, 30000); // timeout 30ms
  if (dur == 0) return -1;               // erreur
  return dur * 0.034 / 2.0;
}

// Convertit distance → niveau %
float distToNiveau(float dist, float hauteur) {
  if (dist < 0) return -1;
  float niv = ((hauteur - dist) / hauteur) * 100.0;
  if (niv < 0)   niv = 0;
  if (niv > 100) niv = 100;
  return niv;
}

// Contrôle pompe
void setPump(bool on) {
  pumpON = on;
  digitalWrite(RELAY_POMPE, on ? LOW : HIGH); // LOW = actif
}

// Contrôle vanne
void setValve(bool open) {
  valveON = open;
  digitalWrite(RELAY_VANNE, open ? LOW : HIGH);
}

// Alerte LED + buzzer selon gaz
void handleGasAlert(int gas) {
  if (gas < 250) {
    // Normal
    digitalWrite(LED_GREEN,  HIGH);
    digitalWrite(LED_YELLOW, LOW);
    digitalWrite(LED_RED,    LOW);
    noTone(BUZZER);
  }
  else if (gas < 450) {
    // Attention
    digitalWrite(LED_GREEN,  LOW);
    digitalWrite(LED_YELLOW, HIGH);
    digitalWrite(LED_RED,    LOW);
    tone(BUZZER, 1000, 150);
  }
  else {
    // DANGER
    digitalWrite(LED_GREEN,  LOW);
    digitalWrite(LED_YELLOW, LOW);
    digitalWrite(LED_RED,    HIGH);
    tone(BUZZER, 2500);   // continu
    setPump(false);       // sécurité : couper pompe
    setValve(false);      // fermer vanne
  }
}

// Affichage LCD — alterne 2 pages
void updateLCD() {
  if (millis() - lastLcdSwitch < 3000) return;
  lastLcdSwitch = millis();
  lcdPage = 1 - lcdPage;

  lcd.clear();
  if (lcdPage == 0) {
    // Page 1 : niveaux
    lcd.setCursor(0, 0);
    lcd.print("R1:");
    lcd.print((int)niveau1);
    lcd.print("%  R2:");
    lcd.print((int)niveau2);
    lcd.print("%");
    lcd.setCursor(0, 1);
    lcd.print("T1:");
    lcd.print(temp1, 1);
    lcd.print("C T2:");
    lcd.print(temp2, 1);
  } else {
    // Page 2 : gaz + état
    lcd.setCursor(0, 0);
    lcd.print("Gaz:");
    lcd.print(gasValue);
    lcd.print(" P:");
    lcd.print((int)pression);
    lcd.setCursor(0, 1);
    lcd.print("Pmp:");
    lcd.print(pumpON ? "ON " : "OFF");
    lcd.print(" Vnn:");
    lcd.print(valveON ? "O" : "F");
  }
}

// Envoi JSON vers Raspberry Pi
void sendJSON() {
  if (millis() - lastSerialSend < 2000) return;
  lastSerialSend = millis();

  Serial.print("{");
  Serial.print("\"n1\":");  Serial.print((int)niveau1);
  Serial.print(",\"n2\":"); Serial.print((int)niveau2);
  Serial.print(",\"t1\":"); Serial.print(temp1, 1);
  Serial.print(",\"t2\":"); Serial.print(temp2, 1);
  Serial.print(",\"p\":"); Serial.print(pression, 1);
  Serial.print(",\"g\":"); Serial.print(gasValue);
  Serial.print(",\"pump\":"); Serial.print(pumpON ? 1 : 0);
  Serial.print(",\"valve\":"); Serial.print(valveON ? 1 : 0);
  Serial.println("}");
}

// Lecture commandes depuis Raspberry Pi
void readCommands() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if      (cmd == "CMD:PUMP_ON")     setPump(true);
  else if (cmd == "CMD:PUMP_OFF")    setPump(false);
  else if (cmd == "CMD:VALVE_OPEN")  setValve(true);
  else if (cmd == "CMD:VALVE_CLOSE") setValve(false);
  else if (cmd == "CMD:ESD") {
    // Emergency Shutdown
    setPump(false);
    setValve(false);
    tone(BUZZER, 3000);
    digitalWrite(LED_RED, HIGH);
  }
}

// Logique automatique de distribution
void autoDistribution() {
  if (gasValue >= 450) return; // pas de distribution si danger gaz

  if (niveau1 >= NIVEAU_PLEIN_R1 && niveau2 <= 95) {
    // R1 plein → ouvrir vanne + démarrer pompe
    setValve(true);
    delay(500);
    setPump(true);
  }
  else if (niveau2 >= 95 || niveau1 <= NIVEAU_BAS_R2) {
    // R2 plein ou R1 trop bas → arrêter
    setPump(false);
    delay(500);
    setValve(false);
  }
}

// =============================================
// SETUP
// =============================================
void setup() {
  Serial.begin(9600);

  // Pins HC-SR04
  pinMode(TRIG1, OUTPUT); pinMode(ECHO1, INPUT);
  pinMode(TRIG2, OUTPUT); pinMode(ECHO2, INPUT);

  // Pins LED + Buzzer
  pinMode(LED_GREEN,  OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(LED_RED,    OUTPUT);
  pinMode(BUZZER,     OUTPUT);

  // Relais — HIGH par défaut = tout éteint
  pinMode(RELAY_POMPE, OUTPUT); digitalWrite(RELAY_POMPE, HIGH);
  pinMode(RELAY_VANNE, OUTPUT); digitalWrite(RELAY_VANNE, HIGH);

  // LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0); lcd.print("GNL Monitor v1");
  lcd.setCursor(0, 1); lcd.print("Demarrage...");

  // DS18B20
  ts1.begin();
  ts2.begin();

  // BMP280
  if (!bmp.begin(0x76)) {
    if (!bmp.begin(0x77)) {  // essayer l'autre adresse
      lcd.setCursor(0, 1); lcd.print("BMP280 ERREUR!");
      delay(2000);
    }
  }

  // Test séquentiel LED + buzzer au démarrage
  digitalWrite(LED_GREEN,  HIGH); delay(400);
  digitalWrite(LED_YELLOW, HIGH); delay(400);
  digitalWrite(LED_RED,    HIGH); delay(400);
  tone(BUZZER, 1000, 200);
  delay(400);
  digitalWrite(LED_GREEN,  LOW);
  digitalWrite(LED_YELLOW, LOW);
  digitalWrite(LED_RED,    LOW);

  lcd.clear();
  lcd.print("Systeme OK !");
  delay(1000);
  lcd.clear();
}

// =============================================
// LOOP
// =============================================
void loop() {

  // ── Lecture capteurs ──
  dist1   = readDistance(TRIG1, ECHO1);
  dist2   = readDistance(TRIG2, ECHO2);
  niveau1 = distToNiveau(dist1, HAUTEUR_R1);
  niveau2 = distToNiveau(dist2, HAUTEUR_R2);

  ts1.requestTemperatures();
  ts2.requestTemperatures();
  temp1 = ts1.getTempCByIndex(0);
  temp2 = ts2.getTempCByIndex(0);

  pression = bmp.readPressure() / 100.0;

  gasValue = analogRead(MQ4_PIN);

  // ── Gestion alertes ──
  handleGasAlert(gasValue);

  // ── Distribution automatique ──
  autoDistribution();

  // ── Affichage LCD ──
  updateLCD();

  // ── Envoi JSON Serial ──
  sendJSON();

  // ── Lecture commandes RPi ──
  readCommands();

  delay(500);
}
