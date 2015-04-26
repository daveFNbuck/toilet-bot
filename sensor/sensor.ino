#include <LowPower.h>
#include <avr/wdt.h>

#include <SPI.h>

#include <nRF24L01.h>
#include <RF24.h>
#include <RF24_config.h>


RF24* radio;
int TOILET = 0; // Make this unique for each sensor
int CHANNEL = 0x60;
int PIPE = 0x7272727069;

void setup() {
  // Serial.begin(9600);
  radio = new RF24(10, 9);
  radio->begin();
  delay(1000);
  radio->setPayloadSize(1);
  radio->setChannel(CHANNEL);
  radio->setDataRate(RF24_250KBPS);
  radio->setPALevel(RF24_PA_MAX);

  radio->openWritingPipe(PIPE);
  attachInterrupt(0, handleInterrupt, CHANGE);
}

void handleInterrupt() {
  wdt_disable(); // Disable watchdog timer
}

void sendStatus() {
  radio->powerUp();
  char v[1] = {digitalRead(2) | (TOILET << 1)};
  radio->write(v, 2);
  radio->powerDown();
}

void loop() {
  LowPower.powerDown(SLEEP_8S, ADC_OFF, BOD_OFF);
  sendStatus();
}
