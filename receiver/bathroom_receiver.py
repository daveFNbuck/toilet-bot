#!/usr/bin/python

import atexit
import itertools
import multiprocessing
import os.path
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

TOILET_MARKERS = [':green_toilet:', ':red_toilet:']
DEAD_SENSOR = ':gray_toilet:'

CHANNEL_TOPIC_URL = 'https://slack.com/api/channels.setTopic?' \
    'token=%(api_token)s&channel=%(channel)s&topic=' % CONF

SQL_WRITE = 'INSERT INTO `availability` (`toilet`, `occupied`, `time`) VALUES (%s, %s, NOW())'
NUM_TOILETS = 2

LEDS = [15, 14]

BLINK_HZ = 2
DEAD_TIMEOUT = 60


def chat_msg(state):
    msg = []
    dead = set(dead_sensors())
    for sensor, status in enumerate(state):
        if sensor in dead or status == -1:
            msg.append(DEAD_SENSOR)
        else:
            msg.append(TOILET_MARKERS[status])
    return ''.join(msg)


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


def dead_sensors():
    for sensor, timestamp in enumerate(last_heard[:]):
        if time.time() - timestamp > DEAD_TIMEOUT:
            yield sensor


def blink_dead_lights(last_heard):
    for tick in itertools.cycle((0, 1)):
        for sensor in dead_sensors():
            GPIO.output(LEDS[sensor], tick)
        time.sleep(1.0 / BLINK_HZ)


if __name__ == '__main__':
    for led in LEDS:
        GPIO.setup(led, GPIO.OUT)
        GPIO.output(led, 0)
    atexit.register(GPIO.cleanup)

    radio = NRF24(GPIO, spidev.SpiDev())
    radio.begin(0, 17)

    radio.setPayloadSize(1)
    radio.setChannel(0x60)
    radio.setDataRate(NRF24.BR_250KBPS)
    radio.setPALevel(NRF24.PA_MAX)

    radio.openReadingPipe(0, map(ord, 'rrrpi'))
    radio.printDetails()

    radio.startListening()

    message = multiprocessing.Array('i', [-1] * NUM_TOILETS)
    last_heard = multiprocessing.Array('i', [int(time.time())] * NUM_TOILETS)

    multiprocessing.Process(target=post_manager, args=(message,)).start()
    multiprocessing.Process(target=blink_dead_lights, args=(last_heard,)).start()

    while True:
        pipe = [0]
        # wait for incoming packet from transmitter
        while not radio.available(pipe):
            time.sleep(0.01)
        recv_buffer = []
        radio.read(recv_buffer)
        toilet, status = recv_buffer[0] >> 1, recv_buffer[0] & 1
        message[toilet] = status
        last_heard[toilet] = int(time.time())
        GPIO.output(LEDS[toilet], 1 - status)
        print 'message changed:', message[:]
