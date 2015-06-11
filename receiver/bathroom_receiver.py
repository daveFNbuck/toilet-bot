#!/usr/bin/python

import atexit
import json
import multiprocessing
import os.path
import socket
import time
import urllib

import pymysql
import yaml

import RPi.GPIO as GPIO
import spidev
from lib_nrf24 import NRF24

GPIO.setmode(GPIO.BCM)

with open(os.path.join(os.path.dirname(__file__), 'slack_conf.yaml')) as conf:
  CONF = yaml.load(conf)
SLACK_URL = 'https://houzz.slack.com/services/hooks/incoming-webhook?token=%(webhook_token)s' % CONF
SLACK_CHANNEL = '#toilet-bot'
CHANNEL_TOPIC_URL = 'https://slack.com/api/channels.setTopic?token=%(api_token)s&channel=%(channel)s&topic=' % CONF

SQL_WRITE = 'INSERT INTO `availability` (`toilet`, `occupied`, `time`) VALUES (%s, %s, NOW())'

led = 16
switch = 19

GPIO.setup(led, GPIO.OUT)
GPIO.output(led, 0)
GPIO.setup(switch, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
atexit.register(GPIO.cleanup)

pipes = [[0x72, 0x72, 0x72, 0x70, 0x69], [0xc2, 0xc2, 0xc2, 0xc2, 0xc2]]
radio = NRF24(GPIO, spidev.SpiDev())
radio.begin(0, 17)

radio.setPayloadSize(1)
radio.setChannel(0x60)
radio.setDataRate(NRF24.BR_250KBPS)
radio.setPALevel(NRF24.PA_MAX)
#radio.setAutoAck(True)
#radio.enableDynamicPayloads()
#radio.enableAckPayload()

radio.openReadingPipe(0, map(ord, 'rrrpi'))
radio.printDetails()

radio.startListening()

manager = multiprocessing.Manager()
message = manager.Array('i', [-1, -1])  # hard-coded for 2 toilets


def chat_msg(state):
  if all(s == 0 for s in state):
    return 'both stalls free'
  elif state[0] == 0:
    return 'left stall free'
  elif state[1] == 0:
    return 'right stall free'
  else:
    return 'both stalls occupied'


def post_manager(state):
  prev_state = state[:]
  while True:
    state_value = state[:]
    if state_value != prev_state:
      for toilet, value in enumerate(state_value):
        if value != prev_state[toilet]:
          print 'posting from manager'
          toilet_post(toilet, value)
      post_status(state_value)
      prev_state = state_value
    time.sleep(2)

p = multiprocessing.Process(target=post_manager, args=(message,))


def post_status(state):
  msg = chat_msg(state)
  try:
    urllib.urlopen(CHANNEL_TOPIC_URL + urllib.quote(msg))
    print msg
  except IOError:
    pass


def toilet_post(toilet, status):
  conn = pymysql.connect(host='localhost', user='bathroom', db='bathroom', passwd='bathroom_bot')
  try:
    with conn.cursor() as cursor:
      cursor.execute(SQL_WRITE, (toilet, status))
    conn.commit()
  finally:
    conn.close()


p.start()
while True:
  pipe = [0]
  # wait for incoming packet from transmitter
  while not radio.available(pipe):
    time.sleep(10000/1000000.0)
  recv_buffer = []
  radio.read(recv_buffer)
  toilet, status = recv_buffer[0] >> 1, recv_buffer[0] & 1
  message[toilet] = status
  print 'message changed:', message[:]
  #toilet_post(msg >> 1, msg & 1)

