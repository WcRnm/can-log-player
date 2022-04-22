import argparse
import can          # python-can
import json
import os
import pathlib
import sys
import time

from datetime import datetime

DEFAULT_CONFIG = 'default.json'

msleep = lambda x: time.sleep(x/1000.0)

def log_error(msg):
    import inspect
    lineno = inspect.currentframe().f_back.f_lineno
    print(f'ERR:{lineno}: {msg}')

class CanPort:
    def __init__(self, ch, init, debug):
        self.debug      = debug
        self.chan       = ch['chan']
        self.interface  = ch['interface']
        self.bitrate    = ch['bitrate']
        self.txqueuelen = 10
        self.sent       = 0
        self.recieved   = 0

        if init:
            self.configure()

        try:
            self.bus = can.interface.Bus(bustype='socketcan', channel=self.interface, bitrate=ch['bitrate'])
        except OSError as e:
            log_error(f'{self.interface}:   {str(e)}')
            print(f'{ch} disabled')
            self.bus = None

    def isEnabled(self):
        return self.bus is not None

    def configure(self):
        os.system('sudo ifconfig {} down'.format(self.interface))
        os.system('sudo /sbin/ip link set {} type can bitrate {}'.format(self.interface, self.bitrate))
        os.system('sudo ifconfig {} txqueuelen {}'.format(self.interface, self.txqueuelen))
        #os.system('sudo /sbin/ip link set {} type can presume-ack on'.format(self.interface))
        os.system('sudo ifconfig {} up'.format(self.interface))
        #print('{}: configured'.format(self.interface))

    def send(self, msg):
        try:
            self.bus.send(msg)
            self.sent += 1
            if self.debug:
                print('{} send: {}'.format(self.interface, msg))
            return True
        except can.CanError as e:
            log_error(f'SEND {self.interface}: disabled: {str(e)}')
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
            log_error(f'RECV {self.interface}: disabled: {str(e)}')
            self.bus = None
            return False

        return msg


class CanPlayer:
    def __init__(self, channel_map, init, verbose):
        self.verbose = verbose
        self.ports = []
        
        for ch in channel_map:
            self.ports.append(CanPort(ch, init, verbose))

    def play(self, ascfile):
        check_can = True

        reader = can.ASCReader(ascfile)
        ts_start = None
        start = datetime.now()
        t = 0

        for msg in reader:
            if check_can:
                for p in self.ports:
                    if p.isEnabled():
                        check_can = False
                        break

                if check_can:
                    # log('all CAN interfaces are disabed')
                    break

                check_can = False

            if ts_start is None:
                ts_start = msg.timestamp
            ms = round((msg.timestamp - ts_start) * 1000.0)
            t = (datetime.now() - start)/1000.0

            if ms > t.microseconds:
                msleep(ms - t.microseconds)
            
            for p in self.ports:
                if p.isEnabled() and msg.channel == p.chan:
                    if p.send(msg):
                        self.update_status(t)
                    else:
                        check_can = True


        self.update_status(t)
        print('\ndone')
    
    def update_status(self, t):
        status = ''
        for p in self.ports:
            if (p.isEnabled()):
                status += f'  [{p.interface} s:{p.sent} r:{p.recieved}]'
            else:
                status += f'  [{p.interface} s:{p.sent} r:{p.recieved} DISABLED]'
        print(f'   {t} {status}', end='\r')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--asc', type=str, required=True)
    parser.add_argument('--init', action='store_true', help='Initalize the CAN ports')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose mode')

    args = parser.parse_args()

    ascfile = args.asc
    cfgfile = pathlib.Path(ascfile).with_suffix('.json')
    if not os.path.exists(cfgfile):
        cfgfile = DEFAULT_CONFIG

    print('ASC: {}'.format(ascfile))
    print('CFG: {}'.format(cfgfile))

    with open(cfgfile, 'r') as m:
        channels = json.load(m)

    player = CanPlayer(channels, args.init, args.verbose)

    try:
        player.play(ascfile)
    except can.CanError as e:
        log_error(str(e))
    except KeyboardInterrupt:
        pass
