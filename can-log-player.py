import argparse
import can          # python-can
import json
import os
import pathlib
import sys
import time

from datetime import datetime

DEFAULT_CONFIG = 'default.json'

usleep = lambda x: time.sleep(x/1000000.0)

class CanPort:
    def __init__(self, ch):
        self.debug      = True
        self.chan       = ch['chan']
        self.interface  = ch['interface']
        self.bitrate    = ch['bitrate']
        self.txqueuelen = 10
        self.sent       = 0
        self.recieved   = 0

        self.configure()

        try:
            self.bus = can.interface.Bus(bustype='socketcan', channel=self.interface, bitrate=ch['bitrate'])
        except OSError as e:
            self.bus = None
            print('{}:   {}'.format(self.interface, str(e)))

    def isEnabled(self):
        return self.bus is not None

    def configure(self):
        os.system('sudo ifconfig {} down'.format(self.interface))
        os.system('sudo /sbin/ip link set {} type can bitrate {}'.format(self.interface, self.bitrate))
        os.system('sudo ifconfig {} txqueuelen {}'.format(self.interface, self.txqueuelen))
        #os.system('sudo /sbin/ip link set {} type can presume-ack on'.format(self.interface))
        os.system('sudo ifconfig {} up'.format(self.interface))
        print('{}: configured'.format(self.interface))

    def send(self, msg):
        try:
            self.bus.send(msg)
            self.sent += 1
            #if self.debug:
                #print('{} send: {}'.format(self.interface, msg))
            return True
        except can.CanError as e:
            #print('{}: disabled: {}'.format(self.interface, str(e)))
            self.bus = None
            return False

    def recv(self, timeout_sec):
        try:
            msg = self.bus.recv(timeout_sec)
            if msg is not None:
                self.recieved += 1
                if self.debug:
                    print('{} recv: {}'.format(self.interface, msg))
        except can.CanError as e:
            print('{}:   {}'.format(self.interface, str(e)))
            self.bus = None
            return False

        return msg


class CanPlayer:
    def __init__(self, channel_map):
        self.ports = []

        for ch in channel_map:
            self.ports.append(CanPort(ch))

    def play(self, ascfile):
        check_can = True

        reader = can.ASCReader(ascfile)
        ts_start = None
        start = datetime.now()

        for msg in reader:
            if check_can:
                for p in self.ports:
                    if p.isEnabled():
                        check_can = False
                        break

                if check_can:
                    # print('all CAN interfaces are disabed')
                    break

                check_can = False

            if ts_start is None:
                ts_start = msg.timestamp
            ms = round((msg.timestamp - ts_start) * 1000000.0)
            t = datetime.now() - start

            if ms < t.microseconds:
                usleep(t.microseconds - ms)
            
            for p in self.ports:
                if p.isEnabled() and msg.channel == p.chan:
                    if p.send(msg):
                        self.update_status()
                    else:
                        check_can = True


        self.update_status()
        print('\ndone')
    
    def update_status(self):
        status = ''
        for p in self.ports:
            if (p.isEnabled()):
                status += '  [{} s:{} r:{}]'.format(p.interface, p.sent, p.recieved)
            else:
                status += '  [{} s:{} r:{} DISABLED]'.format(p.interface, p.sent, p.recieved)
        print(status, end='\r')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--asc', type=str, required=True)

    args = parser.parse_args()

    ascfile = args.asc
    cfgfile = pathlib.Path(ascfile).with_suffix('.json')
    if not os.path.exists(cfgfile):
        cfgfile = DEFAULT_CONFIG

    print('ASC: {}'.format(ascfile))
    print('CFG: {}'.format(cfgfile))

    with open(cfgfile, 'r') as m:
        channels = json.load(m)

    player = CanPlayer(channels)

    try:
        player.play(ascfile)
    except can.CanError as e:
        print(str(e))
