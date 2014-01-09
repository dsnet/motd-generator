#!/usr/bin/env python

# Written in 2012 by Joe Tsai <joetsai@digital-static.net>
#
# ===================================================================
# The contents of this file are dedicated to the public domain. To
# the extent that dedication to the public domain is not available,
# everyone is granted a worldwide, perpetual, royalty-free,
# non-exclusive license to exercise all rights associated with the
# contents of this file for any purpose whatsoever.
# No rights are reserved.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ===================================================================

import re
import os
import sys
import json
import math
import time
import socket
import signal
import optparse
import threading
import collections


################################################################################
############################### Global variables ###############################
################################################################################

# Configuration options
HOST = '127.0.0.1' # The host to bind the socket to
PORT = 4004        # The port to listen on
SAMPLE_RATE = 1    # Samples per second
SAMPLE_SIZE = 3600 # Samples to store per channel

# Regex patterns
REGEX_CPUUTIL = r'^(cpu[0-9]*)([\s0-9]*)$'
REGEX_NETDEV = r'^\s*([^\s]+):\s*' + ((r'([0-9]+)\s+'+(r'[0-9]+\s+'*7))*2)
REGEX_NETDEV = REGEX_NETDEV[:-1] + '*$'
REGEX_STAT = r'cpu(\s+([0-9]+))'

net_stat = None
net_socket = None
sample_period = None
sample_size = None
terminate = False


################################################################################
################################ Helper classes ################################
################################################################################

class Statistic(threading.Thread):
    """Generic class to handle statistics gathering"""

    def __init__(self, period, size):
        """Initialize thread"""
        threading.Thread.__init__(self)
        self.devices = dict()
        self.ovf_exts = dict()
        self.period = period
        self.size = size
        self.sleep_event = threading.Event()
        self.lock = threading.Lock()
        self.terminate = False
        self.last_wake = None

    def run(self):
        """Run thread"""
        self.last_wake = time.time()
        while not self.terminate:
            # Obtain values from updator and append them to the buffer
            for device, values in self.update():
                device, values = self.fix_overflow(device, values)
                with self.lock:
                    buffer = self.get_device(device)
                    buffer.appendleft(values)

            # Adjust sleep time for jitter
            sleep_time = self.period + self.last_wake - time.time()
            if not (self.period*0.5 <= sleep_time <= self.period*1.5):
                sleep_time = self.period
            self.sleep_event.wait(sleep_time)
            self.last_wake = time.time()
            self.sleep_event.clear()

    def stop(self):
        """Stop thread"""
        self.terminate = True
        self.sleep_event.set()

    def get_device(self, device):
        """Get the buffer for a device"""
        if self.devices.has_key(device):
            return self.devices[device]
        else:
            buffer = collections.deque(maxlen = self.size)
            self.devices[device] = buffer
            return buffer

    def fix_overflow(self, device, values):
        """Fix numeric overflow"""
        self.ovf_exts.setdefault(device, dict())
        for index in xrange(len(values)):
            now_val = values[index]
            if isinstance(now_val, (int, long)):
                self.ovf_exts[device].setdefault(index, (0,0,0))
                offset, pre_val, bit_width = self.ovf_exts[device][index]
                try: # Python 2.7 and above
                    bit_width = max(bit_width, now_val.bit_length())
                except: # Below Python 2.7
                    bit_width = max(bit_width, len(bin(now_val))-2)
                if pre_val > now_val:
                    offset += 1
                values[index] += offset * (2**bit_width)
                self.ovf_exts[device][index] = (offset, now_val, bit_width)
        return device, values

    def average(self, device, interval, weight = 0.0):
        """Compute the moving average"""
        length = int(round(float(interval)/self.period))
        with self.lock:
            value_arrays = self.compute(device, length)
        averages = []
        for array in value_arrays:
            average = 0
            size = len(array)
            offset = float(1-weight)
            slope = float(2*(weight/(size+1)))
            for index,value in enumerate(array):
                kval = slope*(size-index) + offset
                average += value*kval
            averages.append(average/float(size))
        return averages


class NetworkStatistic(Statistic):
    """Capture the number of bytes transmitted and received"""

    def update(self):
        """Read the proc filesystem and give updates"""
        with open('/proc/net/dev','r') as net_devs:
            for line in net_devs.xreadlines():
                results = re.search(REGEX_NETDEV, line)
                if not results:
                    continue
                device, rx_bytes, tx_bytes = results.groups()
                yield device, [line, int(rx_bytes), int(tx_bytes)]

    def compute(self, device, length):
        """Compute the network bandwidth"""
        buffer = self.get_device(device)
        size = min(len(buffer), length+1) # Account for extra sample for delta

        # Compute "instantaneous" bandwidth for all deltas
        rx_results, tx_results = [], []
        for index in xrange(size):
            rx_now, tx_now = buffer[index][1], buffer[index][2]
            if index > 0:
                rx_traf = (rx_pre-rx_now)/float(self.period)
                tx_traf = (tx_pre-tx_now)/float(self.period)
                rx_results.append(rx_traf)
                tx_results.append(tx_traf)
            rx_pre, tx_pre = rx_now, tx_now
        return rx_results, tx_results


class ProcessorStatistic(Statistic):
    """Capture how each CPU spends cycles"""

    def update(self):
        """Read the proc filesystem and give updates"""
        with open('/proc/stat','r') as cpu_stats:
            for line in cpu_stats.xreadlines():
                results = re.search(REGEX_CPUUTIL, line)
                if not results:
                    continue
                device, values = results.groups()
                values = [line] + [int(x) for x in values.split()]
                yield device, values

    def compute(self, device, length):
        """Compute the utilization"""
        buffer = self.get_device(device)
        size = min(len(buffer), length+1) # Account for extra sample for delta

        # Compute "instantaneous" utilization for all deltas
        results = []
        for index in xrange(size):
            now_total, now_idle = sum(buffer[index][1:]), buffer[index][4]
            if index > 0:
                idle = float(now_idle-pre_idle) / float(now_total-pre_total)
                results.append(1.0 - idle)
            pre_total, pre_idle = now_total, now_idle
        return results,


################################################################################
############################### Helper functions ###############################
################################################################################

def interrupt_handler(sig_num, frame):
    """Handle system signal interrupts"""
    global terminate
    terminate = True


def network_handler():
    """Handle all new network requests"""
    global net_socket

    # Accept new incoming connections
    try:
        conn,addr = net_socket.accept()
        conn.settimeout(1)
        try:
            # Read data from client
            while not terminate:
                try:
                    data = conn.recv(1024)
                    if not data:
                        break
                    conn.sendall(process_request(data)+'\n')
                    break
                except socket.timeout:
                    pass
                except socket.error, ex:
                    if ex.errno == 4: break
                    raise ex
        finally:
            conn.close()
    except socket.timeout:
        pass
    except socket.error, ex:
        if ex.errno == 4: return
        raise ex


def process_request(data):
    """Process a client's request"""
    global cpu_stat, net_stat

    # Try and parse the arguments
    try:
        data = json.loads(data)
        assert isinstance(data, dict)
    except:
        return json.dumps({'error': "unable to parse arguments"})

    try:
        # Comamnd is debug
        if data.has_key('debug'):
            debug = data['debug']
            if debug in ['cpu_util', 'net_traf']:
                stat = cpu_stat if debug == 'cpu_util' else net_stat
                with stat.lock:
                    data = dict()
                    for device, buffer in stat.devices.items():
                        data[device] = list(buffer)
                    return json.dumps(data)
            else:
                raise Exception("Unknown debug target: %s" % debug)

        # Command is for network traffic
        if data.has_key('net_traf'):
            kwargs = data['net_traf']
            device = kwargs.get('device', 'eth0') # The network device
            interval = kwargs.get('interval', 10) # Time length in seconds
            weight = kwargs.get('weight', 0.0)    # Average weight constant

            rx_avg, tx_avg = net_stat.average(device, interval, weight = weight)
            return json.dumps({'rx_average': rx_avg, 'tx_average': tx_avg})

        # Command is for CPU utilization
        if data.has_key('cpu_util'):
            kwargs = data['cpu_util']
            device = kwargs.get('device', 'all')  # The network device
            interval = kwargs.get('interval', 10) # Time length in seconds
            weight = kwargs.get('weight', 0.0)    # Average weight constant
            if device == 'all':
                device = 'cpu'

            utilization, = cpu_stat.average(device, interval, weight = weight)
            return json.dumps({'utilization': utilization})

    except Exception, ex:
        return json.dumps({'error': str(ex)})


################################################################################
################################ Options parser ################################
################################################################################

# Create a config parser
opts_parser = optparse.OptionParser(add_help_option = False)
opts_parser.add_option(
    '-h', '--help', action = 'help',
    help = "Display this help and exit.",
)
opts_parser.add_option(
    '-r', '--sample_rate', default = SAMPLE_RATE, type = 'float',
    help = "Rate to log network statistics in samples per second [%default].",
)
opts_parser.add_option(
    '-s', '--sample_size', default = SAMPLE_SIZE, type = 'int',
    help = "The amount of samples to store before rolling [%default].",
)
opts_parser.add_option(
    '-p', '--port', default = PORT, type = 'int',
    help = "The port to report statistics on [%default].",
)
(opts, args) = opts_parser.parse_args()

if opts.sample_size <= 0:
    print "Sample size must be a positive value"
    sys.exit(1)

if opts.sample_rate <= 0:
    print "Sample rate must be a positive value"
    sys.exit(1)

sample_period = 1.0 / opts.sample_rate
sample_size = opts.sample_size


################################################################################
################################# Script start #################################
################################################################################

# Handle termination
signal.signal(signal.SIGINT, interrupt_handler)
signal.signal(signal.SIGTERM, interrupt_handler)

# Setup the network socket
net_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
net_socket.bind((HOST, opts.port))
net_socket.listen(5)
net_socket.settimeout(1)

# Start the network data gatherer
cpu_stat = ProcessorStatistic(sample_period,sample_size)
net_stat = NetworkStatistic(sample_period,sample_size)
cpu_stat.start()
net_stat.start()

# The main event loop
try:
    while not terminate:
        network_handler()
finally:
    cpu_stat.stop()
    net_stat.stop()
    net_socket.close()
