#include <OneWire.h>
#include <DallasTemperature.h>

#define ONE_WIRE_BUS 2
#define RELAY_PIN 8

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

float temp_in = 0;
float temp_out = 0;
float tank_temp = 0;

void setup() {
  Serial.begin(9600);
  sensors.begin();
  pinMode(RELAY_PIN, OUTPUT);
}

void loop() {
  sensors.requestTemperatures();
  temp_in = sensors.getTempCByIndex(0);
  temp_out = sensors.getTempCByIndex(1);
  tank_temp = sensors.getTempCByIndex(2);

  Serial.print(temp_in);
  Serial.print(",");
  Serial.print(temp_out);
  Serial.print(",");
  Serial.println(tank_temp);

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    if (cmd == "ON") digitalWrite(RELAY_PIN, HIGH);
    else if (cmd == "OFF") digitalWrite(RELAY_PIN, LOW);
  }

  delay(2000);
}
