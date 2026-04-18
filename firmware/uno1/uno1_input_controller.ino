#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Fluid Ardule UNO-1 input firmware
// v2026-04-14h
//
// Uno -> Pi protocol:
//   UNO_READY
//   BTN:LEFT / UP / DOWN / RIGHT / SEL / ENC_PUSH
//   BTN:LEFT_LP / UP_LP / DOWN_LP / RIGHT_LP / SEL_LP
//   ENC:+N / ENC:-N
//   POT:<0-1023>
//   ACCEL:<1-3>
//
// Pi -> Uno protocol:
//   HELLO
//   HB
//   ACT:MIDI
//
// Behavior:
//   D13 : blink until Pi link established, then steady ON
//   D12 : PLAY status LED
//   D11 : activity pulse only on ACT:MIDI from Pi
//   1602 LCD : local input monitor only (no Pi state text)

LiquidCrystal_I2C lcd(0x27, 16, 2);

// ---- Pins ----
const uint8_t PIN_KEYPAD = A0;   // LCD keypad resistor ladder
const uint8_t PIN_ENC_A  = 2;
const uint8_t PIN_ENC_B  = 3;
const uint8_t PIN_ENC_SW = A1;   // active low, INPUT_PULLUP
const uint8_t PIN_POT    = A2;

const uint8_t PIN_LED_LINK = 13;
const uint8_t PIN_LED_PLAY = 12;
const uint8_t PIN_LED_MIDI = 11;

// ---- Timing ----
const unsigned long DEBOUNCE_MS = 45;
const unsigned long LONGPRESS_MS = 700;
const unsigned long READY_REPEAT_MS = 3000;
const unsigned long LCD_REFRESH_MS = 120;
const unsigned long POT_SEND_MS = 60;
const unsigned long LINK_TIMEOUT_MS = 3000;
const unsigned long LINK_BLINK_MS = 300;
const unsigned long MIDI_LED_PULSE_MS = 300;
const unsigned long PLAY_LED_BLINK_MS = 500;
const int           POT_DELTA_MIN = 4;

// ---- A0 thresholds (5.00V reference assumed) ----
const int TH_LEFT_MAX   = 119;
const int TH_UP_MAX     = 279;
const int TH_DOWN_MAX   = 449;
const int TH_RIGHT_MAX  = 649;
const int TH_SELECT_MAX = 899;

enum KeyCode {
  KEY_NONE = 0,
  KEY_LEFT,
  KEY_UP,
  KEY_DOWN,
  KEY_RIGHT,
  KEY_SELECT
};

struct AccelProfile {
  unsigned int tFast;    // <= tFast => x3
  unsigned int tMedium;  // <= tMedium => x2, else x1
};

const AccelProfile ACCEL_TABLE[3] = {
  {60, 120},
  {70, 160},
  {100, 220}
};

// ---- Link / LCD state ----
bool piLinked = false;
unsigned long lastPiSeenMs = 0;
unsigned long lastReadySentMs = 0;
unsigned long lastLcdRefreshMs = 0;
unsigned long lastBlinkMs = 0;
bool linkLedState = false;

unsigned long midiLedUntilMs = 0;
enum PlayLedMode { PLAY_LED_OFF = 0, PLAY_LED_ON = 1, PLAY_LED_BLINK = 2 };
PlayLedMode playLedMode = PLAY_LED_OFF;
bool playLedState = false;
unsigned long playLedLastToggleMs = 0;

String l1Text = "FluidArdule UNO";
String l2Text = "Booting...";

// ---- Keypad state ----
KeyCode stableKey = KEY_NONE;
KeyCode lastSampledKey = KEY_NONE;
unsigned long keyChangedMs = 0;
unsigned long keyPressedMs = 0;
bool keyLongSent = false;

// ---- Encoder state ----
int lastEncA = HIGH;
int lastEncB = HIGH;
int lastEncSw = HIGH;
bool encSwStable = HIGH;
unsigned long encSwChangedMs = 0;
unsigned long encSwPressedMs = 0;
bool encSwLongSent = false;
unsigned long lastEncStepMs = 0;

// ---- Pot state ----
int lastPotSent = -1000;
unsigned long lastPotSentMs = 0;

// ---- Accel config ----
uint8_t accelProfile = 2;
bool accelSettingMode = false;
uint8_t accelDraft = 2;

// ---- Serial RX ----
String rxLine;

KeyCode decodeKeyFromA0(int v) {
  if (v <= TH_LEFT_MAX)   return KEY_LEFT;
  if (v <= TH_UP_MAX)     return KEY_UP;
  if (v <= TH_DOWN_MAX)   return KEY_DOWN;
  if (v <= TH_RIGHT_MAX)  return KEY_RIGHT;
  if (v <= TH_SELECT_MAX) return KEY_SELECT;
  return KEY_NONE;
}

void sendLine(const char* s) {
  Serial.println(s);
}

void sendReady() {
  sendLine("UNO_READY");
  lastReadySentMs = millis();
}

void sendAccelProfile() {
  Serial.print(F("ACCEL:"));
  Serial.println(accelProfile);
}

void sendPotValue(int v) {
  Serial.print(F("POT:"));
  Serial.println(v);
}

void sendEncStep(int step) {
  Serial.print(F("ENC:"));
  if (step > 0) Serial.print('+');
  Serial.println(step);
}

void setLocalDisplay(const String &line1, const String &line2) {
  l1Text = line1;
  l2Text = line2;
}

void printPadded16(const String &s) {
  String t = s;
  if (t.length() > 16) t = t.substring(0, 16);
  while (t.length() < 16) t += ' ';
  lcd.print(t);
}

const __FlashStringHelper* accelName(uint8_t p) {
  switch (p) {
    case 1: return F("MILD");
    case 2: return F("NORM");
    case 3: return F("RELAX");
    default: return F("NORM");
  }
}

const __FlashStringHelper* keyName(KeyCode k) {
  switch (k) {
    case KEY_LEFT:   return F("LEFT");
    case KEY_UP:     return F("UP");
    case KEY_DOWN:   return F("DOWN");
    case KEY_RIGHT:  return F("RIGHT");
    case KEY_SELECT: return F("SEL");
    default:         return F("NONE");
  }
}

void showButtonEvent(const String &name, bool isLongPress) {
  String line1 = "BTN:" + name;
  String line2 = isLongPress ? "LONG" : "SHORT";
  setLocalDisplay(line1, line2);
}

void showEncoderEvent(int step) {
  String line1 = "ENC:";
  if (step > 0) line1 += "+";
  line1 += String(step);
  String line2 = "ACC:P" + String(accelProfile);
  setLocalDisplay(line1, line2);
}

void showPotEvent(int v) {
  String line1 = "POT:" + String(v);
  String line2 = piLinked ? "LINK OK" : "WAIT PI";
  setLocalDisplay(line1, line2);
}

void showAccelSetupScreen() {
  String line1 = "ACCEL SETUP";
  String line2 = "P" + String(accelDraft) + " ";
  line2 += String(accelName(accelDraft));
  if (accelDraft == accelProfile) line2 += " *";
  setLocalDisplay(line1, line2);
}

void drawStatus() {
  lcd.setCursor(0, 0);
  printPadded16(l1Text);
  lcd.setCursor(0, 1);
  printPadded16(l2Text);
}

void notePiSeen() {
  lastPiSeenMs = millis();
  piLinked = true;
}

void pulseMidiLed() {
  digitalWrite(PIN_LED_MIDI, HIGH);
  midiLedUntilMs = millis() + MIDI_LED_PULSE_MS;
}

void setPlayLedMode(PlayLedMode mode) {
  playLedMode = mode;
  playLedLastToggleMs = millis();
  if (mode == PLAY_LED_OFF) {
    playLedState = false;
    digitalWrite(PIN_LED_PLAY, LOW);
  } else if (mode == PLAY_LED_ON) {
    playLedState = true;
    digitalWrite(PIN_LED_PLAY, HIGH);
  } else {
    playLedState = true;
    digitalWrite(PIN_LED_PLAY, HIGH);
  }
}

void updatePlayLed() {
  if (playLedMode != PLAY_LED_BLINK) return;
  unsigned long now = millis();
  if (now - playLedLastToggleMs >= PLAY_LED_BLINK_MS) {
    playLedLastToggleMs = now;
    playLedState = !playLedState;
    digitalWrite(PIN_LED_PLAY, playLedState ? HIGH : LOW);
  }
}

void updateLinkLed() {
  unsigned long now = millis();

  if (piLinked && (now - lastPiSeenMs > LINK_TIMEOUT_MS)) {
    piLinked = false;
    setLocalDisplay("LINK LOST", "WAIT HELLO/HB");
  }

  if (piLinked) {
    digitalWrite(PIN_LED_LINK, HIGH);
    return;
  }

  if (now - lastBlinkMs >= LINK_BLINK_MS) {
    lastBlinkMs = now;
    linkLedState = !linkLedState;
    digitalWrite(PIN_LED_LINK, linkLedState ? HIGH : LOW);
  }
}

void updateMidiLed() {
  unsigned long now = millis();
  if (midiLedUntilMs != 0 && now >= midiLedUntilMs) {
    digitalWrite(PIN_LED_MIDI, LOW);
    midiLedUntilMs = 0;
  }
}

void setAccelDraftDelta(int delta) {
  int next = (int)accelDraft + delta;
  if (next < 1) next = 1;
  if (next > 3) next = 3;
  accelDraft = (uint8_t)next;
  showAccelSetupScreen();
}

int calcAccelMultiplier(unsigned long dt, uint8_t profile) {
  const AccelProfile &p = ACCEL_TABLE[profile - 1];
  if (dt <= p.tFast) return 3;
  if (dt <= p.tMedium) return 2;
  return 1;
}

void enterAccelSettingMode() {
  accelSettingMode = true;
  accelDraft = accelProfile;
  stableKey = KEY_NONE;
  lastSampledKey = KEY_NONE;
  keyLongSent = false;
  showAccelSetupScreen();
}

void applyAndExitAccelSettingMode() {
  accelProfile = accelDraft;
  accelSettingMode = false;
  sendAccelProfile();
  setLocalDisplay("ACCEL APPLIED", "P" + String(accelProfile) + " " + String(accelName(accelProfile)));
}

void sendButtonMessage(KeyCode k, bool isLongPress) {
  switch (k) {
    case KEY_LEFT:   sendLine(isLongPress ? "BTN:LEFT_LP"  : "BTN:LEFT"); break;
    case KEY_UP:     sendLine(isLongPress ? "BTN:UP_LP"    : "BTN:UP"); break;
    case KEY_DOWN:   sendLine(isLongPress ? "BTN:DOWN_LP"  : "BTN:DOWN"); break;
    case KEY_RIGHT:  sendLine(isLongPress ? "BTN:RIGHT_LP" : "BTN:RIGHT"); break;
    case KEY_SELECT: sendLine(isLongPress ? "BTN:SEL_LP"   : "BTN:SEL"); break;
    default: break;
  }
  showButtonEvent(String(keyName(k)), isLongPress);
}

void updateKeypad() {
  int raw = analogRead(PIN_KEYPAD);
  KeyCode sampled = decodeKeyFromA0(raw);
  unsigned long now = millis();

  if (sampled != lastSampledKey) {
    lastSampledKey = sampled;
    keyChangedMs = now;
  }

  if ((now - keyChangedMs) < DEBOUNCE_MS) return;

  if (sampled == stableKey) {
    if (stableKey != KEY_NONE && !keyLongSent && (now - keyPressedMs) >= LONGPRESS_MS) {
      if (!accelSettingMode) {
        sendButtonMessage(stableKey, true);
      }
      keyLongSent = true;
    }
    return;
  }

  KeyCode prevStable = stableKey;
  stableKey = sampled;

  // Previous key released: emit exactly one short event if long press was not sent.
  if (prevStable != KEY_NONE && stableKey == KEY_NONE) {
    if (!keyLongSent) {
      if (accelSettingMode) {
        switch (prevStable) {
          case KEY_UP:     setAccelDraftDelta(+1); break;
          case KEY_DOWN:   setAccelDraftDelta(-1); break;
          case KEY_SELECT: applyAndExitAccelSettingMode(); break;
          case KEY_LEFT:   accelSettingMode = false; setLocalDisplay("ACCEL CANCELED", "P" + String(accelProfile)); break;
          default: break;
        }
      } else {
        sendButtonMessage(prevStable, false);
      }
    }
    keyPressedMs = 0;
    keyLongSent = false;
    return;
  }

  // New key pressed: start timing only. Short press will be decided on release.
  if (stableKey != KEY_NONE) {
    keyPressedMs = now;
    keyLongSent = false;
  }
}

void updateEncoder() {
  int a = digitalRead(PIN_ENC_A);
  int b = digitalRead(PIN_ENC_B);
  unsigned long now = millis();

  if (a != lastEncA) {
    if (a == LOW) {
      int direction = (b == HIGH) ? +1 : -1;
      if (accelSettingMode) {
        setAccelDraftDelta(direction);
      } else {
        unsigned long dt = (lastEncStepMs == 0) ? 9999UL : (now - lastEncStepMs);
        int mult = calcAccelMultiplier(dt, accelProfile);
        int step = direction * mult;
        sendEncStep(step);
        showEncoderEvent(step);
        lastEncStepMs = now;
      }
    }
    lastEncA = a;
  }
  lastEncB = b;

  int sw = digitalRead(PIN_ENC_SW);
  if (sw != lastEncSw) {
    lastEncSw = sw;
    encSwChangedMs = now;
  }

  if ((now - encSwChangedMs) >= DEBOUNCE_MS && sw != encSwStable) {
    encSwStable = sw;

    if (encSwStable == LOW) {
      encSwPressedMs = now;
      encSwLongSent = false;
      if (!accelSettingMode) {
        sendLine("BTN:ENC_PUSH");
        setLocalDisplay("BTN:ENC_PUSH", "SHORT");
      }
    } else {
      encSwPressedMs = 0;
      encSwLongSent = false;
    }
  }

  if (encSwStable == LOW && !encSwLongSent && encSwPressedMs != 0 && (now - encSwPressedMs) >= LONGPRESS_MS) {
    if (!accelSettingMode) {
      enterAccelSettingMode();
    } else {
      applyAndExitAccelSettingMode();
    }
    encSwLongSent = true;
  }
}

void updatePot() {
  unsigned long now = millis();
  int raw = analogRead(PIN_POT);

  if (abs(raw - lastPotSent) >= POT_DELTA_MIN && (now - lastPotSentMs) >= POT_SEND_MS) {
    sendPotValue(raw);
    showPotEvent(raw);
    lastPotSent = raw;
    lastPotSentMs = now;
  }
}

void handleIncomingLine(String s) {
  s.trim();
  if (s.length() == 0) return;

  if (s == "HELLO") {
    bool wasLinked = piLinked;
    notePiSeen();
    if (!wasLinked) {
      setLocalDisplay("PI LINKED", "HELLO OK");
    }
    sendReady();
    sendAccelProfile();
    return;
  }

  if (s == "HB") {
    notePiSeen();
    return;
  }

  if (s == "ACT:MIDI") {
    notePiSeen();
    pulseMidiLed();
    return;
  }

  if (s == "PLAY:OFF") {
    notePiSeen();
    setPlayLedMode(PLAY_LED_OFF);
    return;
  }

  if (s == "PLAY:ON") {
    notePiSeen();
    setPlayLedMode(PLAY_LED_ON);
    return;
  }

  if (s == "PLAY:BLINK") {
    notePiSeen();
    setPlayLedMode(PLAY_LED_BLINK);
    return;
  }

  // Ignore legacy Pi->Uno messages such as SF:, VOL:, STATUS:, PAGE:, GAIN:
}

void updateSerialRx() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rxLine.length() > 0) {
        handleIncomingLine(rxLine);
        rxLine = "";
      }
    } else {
      if (rxLine.length() < 80) rxLine += c;
    }
  }
}

void setup() {
  pinMode(PIN_ENC_A, INPUT_PULLUP);
  pinMode(PIN_ENC_B, INPUT_PULLUP);
  pinMode(PIN_ENC_SW, INPUT_PULLUP);
  pinMode(PIN_LED_LINK, OUTPUT);
  pinMode(PIN_LED_PLAY, OUTPUT);
  pinMode(PIN_LED_MIDI, OUTPUT);

  digitalWrite(PIN_LED_LINK, LOW);
  digitalWrite(PIN_LED_PLAY, LOW);
  digitalWrite(PIN_LED_MIDI, LOW);

  Serial.begin(115200);
  analogReference(DEFAULT);

  lcd.init();
  lcd.backlight();
  lcd.clear();
  setLocalDisplay("FluidArdule UNO", "WAIT HELLO/HB");
  drawStatus();

  delay(80);
  sendReady();
  sendAccelProfile();
}

void loop() {
  updateSerialRx();
  updatePlayLed();
  updateKeypad();
  updateEncoder();
  updatePot();
  updateLinkLed();
  updateMidiLed();

  unsigned long now = millis();

  if ((now - lastReadySentMs) >= READY_REPEAT_MS) {
    sendReady();
  }

  if ((now - lastLcdRefreshMs) >= LCD_REFRESH_MS) {
    drawStatus();
    lastLcdRefreshMs = now;
  }
}
