#!/usr/bin/env python3
from time import sleep, time
from libAnt.drivers.serial import SerialDriver
from libAnt.drivers.usb import USBDriver
from libAnt.node import Node
from twilio.rest import Client
from collections import deque
from datetime import datetime
import logging

class Twilio:
    def __init__(self, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_CALL_URL, ALERT_NUMBERS):
        self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        self.TWILIO_FROM_NUMBER = TWILIO_FROM_NUMBER
        self.TWILIO_CALL_URL = TWILIO_CALL_URL
        self.ALERT_NUMBERS = ALERT_NUMBERS
        self.logger = logging.getLogger("Twilio")

    def send_sms(self, msg):
        ret = ""
        for number in self.ALERT_NUMBERS:
            try:
                response = self.client.messages.create(to=number, from_=self.TWILIO_FROM_NUMBER, body=msg)
                self.logger.debug(response)
                ret += "SMS:{} SENT\n".format(number)
            except Exception as ex:
                self.logger.error('{}: {}'.format(type(ex), ex))
                ret += "SMS:{} FAILED\n".format(number)
        return ret

    def make_call(self, msg):
        ret = ""
        for number in self.ALERT_NUMBERS:
            try:
                response = self.client.api.account.calls.create(to=number, from_=self.twilio_number, url=self.TWILIO_CALL_URL)
                self.logger.debug(response)
                ret += "Call:{} SENT\n".format(number)
            except Exception as ex:
                self.logger.error('{}: {}'.format(type(ex), ex))
                ret += "Call:{} FAILED\n".format(number)
        return ret


class HRM:
    def __init__(self, node, twilio):
        self.logger = logging.getLogger("HRM")
        self.antnode = node
        self.twilio = twilio
        self.prev_alert_ts = 0
        self.prev_hr_ts = time()
        self.hist_hrs = deque([RESTING_HR] * MOVING_AVG_SIZE, MOVING_AVG_SIZE)

    def start(self):
        self.antnode.enableRxScanMode()
        self.antnode.start(self.callback, self.eCallback)

    def eCallback(self, e):
        self.logger.info(e)

    def callback(self, data):
        # ignore any data till next sampling interval
        curr_ts = time()
        if curr_ts - self.prev_hr_ts < HR_SAMPLING_FREQ:
            return

        # heart rate is the last value in hex
        hr = int(str(data).split()[-1], 16)
        self.hist_hrs.append(hr)
        curr_avg_hr = sum(self.hist_hrs) // len(self.hist_hrs)
        self.logger.info("hr={}, cur_avg_hr={}".format(hr, curr_avg_hr))

        # log hr as csv
        curr_ts_fmt = datetime.fromtimestamp(curr_ts).strftime("%m/%d/%Y %H:%M:%S")
        hr_log = "{},{},{}".format(curr_ts_fmt, hr, curr_avg_hr)
        with open("hr_log.csv", "a") as f:
            f.write(hr_log + "\n")

        # critical heart rate, call & sms every 1 min
        if curr_avg_hr > CRITICAL_THRESHOLD:
            msg =  "Critical: HR of {} BPM was detected at {}.".format(hr, curr_ts_fmt)
            self.logger.info(msg)
            if time() - self.prev_alert_ts > 60:
                self.logger.info(self.twilio.send_sms(msg))
                self.logger.info(self.twilio.make_call(msg))
                self.prev_alert_ts = curr_ts
            else:
                self.logger.info("Alert was sent less than 60 seconds ago, no alert will be sent.")

        # warning heart rate, sms every minute 5 min
        elif curr_avg_hr > WARNING_THRESHOLD:
            msg =  "Warning: HR of {} BPM was detected at {}.".format(hr, curr_ts_fmt)
            self.logger.info(msg)
            if time() - self.prev_alert_ts > 60 * 5:
                self.logger.info(self.twilio.send_sms(msg))
                self.prev_alert_ts = curr_ts
            else:
                self.logger.info("Alert was sent less than 5 min ago, no alert will be sent.")
        self.prev_hr_ts = curr_ts


# AppConfig
TWILIO_CALL_URL = "https://handler.twilio.com/twiml/EH45d33797a5de5078025c83c420f1df32"
TWILIO_ACCOUNT_SID = ""
TWILIO_AUTH_TOKEN = ""
TWILIO_FROM_NUMBER = ""
ALERT_NUMBERS = ""
RESTING_HR = 80
HR_SAMPLING_FREQ = 5
MOVING_AVG_SIZE = 12
WARNING_THRESHOLD = 110
CRITICAL_THRESHOLD = 120

with Node(SerialDriver("/dev/ttyUSB0"), 'AntNode') as node:
    logging.basicConfig(format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s', level = logging.INFO)
    twilio = Twilio(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_CALL_URL, ALERT_NUMBERS.split(";"))
    hrm = HRM(node, twilio)
    hrm.start()
    sleep(60 * 60 * 8)
