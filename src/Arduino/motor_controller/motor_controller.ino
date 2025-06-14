// Motor pins (H-Bridge plus/minus and enable)
#define FL_PLUS_PIN    52   // Front-left positive input
#define FL_MINUS_PIN   53   // Front-left negative input
#define FL_EN_PIN      2    // Front-left enable (PWM)

#define FR_PLUS_PIN    50   // Front-right positive input
#define FR_MINUS_PIN   51   // Front-right negative input
#define FR_EN_PIN      3    // Front-right enable (PWM)

#define RL_PLUS_PIN    48   // Rear-left positive input
#define RL_MINUS_PIN   49   // Rear-left negative input
#define RL_EN_PIN      4    // Rear-left enable (PWM)

#define RR_PLUS_PIN    46   // Rear-right positive input
#define RR_MINUS_PIN   47   // Rear-right negative input
#define RR_EN_PIN      5    // Rear-right enable (PWM)

#define V_PLUS_PIN     44   // Vertical positive input
#define V_MINUS_PIN    45   // Vertical negative input
#define V_EN_PIN       6    // Vertical enable (PWM)

#define V2_PLUS_PIN    42   // Mirrored vertical motor positive input
#define V2_MINUS_PIN   43   // Mirrored vertical motor negative input
#define V2_EN_PIN      7    // Mirrored vertical motor enable (PWM)

void setup() {
  Serial.begin(115200);
  // Configure all H-bridge control pins
  int pins[] = {FL_PLUS_PIN, FL_MINUS_PIN, FL_EN_PIN,
                FR_PLUS_PIN, FR_MINUS_PIN, FR_EN_PIN,
                RL_PLUS_PIN, RL_MINUS_PIN, RL_EN_PIN,
                RR_PLUS_PIN, RR_MINUS_PIN, RR_EN_PIN,
                V_PLUS_PIN, V_MINUS_PIN, V_EN_PIN,
                V2_PLUS_PIN, V2_MINUS_PIN, V2_EN_PIN};  // Add V2

  for (int i = 0; i < sizeof(pins) / sizeof(pins[0]); i++) {
    pinMode(pins[i], OUTPUT);
    digitalWrite(pins[i], LOW);
  }
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (!line.startsWith("M,")) return;

    // Split tokens
    int values[10];
    int idx = 0;
    char *buf = strdup(line.c_str());
    char *tok = strtok(buf, ","); // "M"
    while (tok != NULL && idx < 10) {
      tok = strtok(NULL, ",");
      if (tok) values[idx++] = atoi(tok);
    }
    free(buf);

    if (idx == 10) {
      // Map values: FL_dir, FL_spd, FR_dir, FR_spd, RL_dir, RL_spd, RR_dir, RR_spd, V_dir, V_spd
      setMotor(FL_PLUS_PIN, FL_MINUS_PIN, FL_EN_PIN, values[0], values[1]);
      setMotor(FR_PLUS_PIN, FR_MINUS_PIN, FR_EN_PIN, values[2], values[3]);
      setMotor(RL_PLUS_PIN, RL_MINUS_PIN, RL_EN_PIN, values[4], values[5]);
      setMotor(RR_PLUS_PIN, RR_MINUS_PIN, RR_EN_PIN, values[6], values[7]);
      setMotor(V_PLUS_PIN,  V_MINUS_PIN,  V_EN_PIN,  values[8], values[9]);
      setMotor(V2_PLUS_PIN, V2_MINUS_PIN, V2_EN_PIN, values[8], values[9]); // Mirrored direction
    } else {
      Serial.println("Error: Invalid M command format");
    }
  }
}

/**
 * Drive one motor via H-Bridge plus/minus and PWM enable.
 * @param plusPin   Positive input pin
 * @param minusPin  Negative input pin
 * @param enPin     PWM enable pin
 * @param direction 0 = reverse, 1 = forward
 * @param speed     PWM value 0-255
 */
void setMotor(int plusPin, int minusPin, int enPin, int direction, int speed) {
  if (speed <= 0) {
    // Stop motor
    digitalWrite(plusPin, LOW);
    digitalWrite(minusPin, LOW);
    analogWrite(enPin, 0);
    return;
  }
  if (direction == 1) {
    digitalWrite(plusPin, HIGH);
    digitalWrite(minusPin, LOW);
  } else {
    digitalWrite(plusPin, LOW);
    digitalWrite(minusPin, HIGH);
  }
  analogWrite(enPin, constrain(speed, 0, 255));
}
