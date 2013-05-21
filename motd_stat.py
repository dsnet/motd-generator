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
REGEX_NETDEV = r'\s*([^\s]+):\s*' + ((r'([0-9]+)\s+'+(r'[0-9]+\s+'*7))*2)
REGEX_NETDEV = REGEX_NETDEV[:-1] + '*$'

net_stat = None
net_socket = None
sample_period = None
sample_size = None
terminate = False

################################################################################
################################ Helper classes ################################
################################################################################

class NetworkStatistic(threading.Thread):
    """Capture the number of bytes transmitted and received"""

    def __init__(self, period, size):
        """Initialize thread"""
        threading.Thread.__init__(self)
        self.interfaces = dict()
        self.period = period
        self.size = size
        self.sleep_event = threading.Event()
        self.lock = threading.Lock()
        self.terminate = False
        self.last_wake = None

    def run(self):
        """Run thread"""
        regex = re.compile(REGEX_NETDEV)
        self.last_wake = time.time()
        while not self.terminate:
            # Read the proc filesystem
            with open('/proc/net/dev','r') as net_devs:
                for line in net_devs.xreadlines():
                    results = regex.search(line)
                    if not results:
                        continue
                    device,rx_bytes,tx_bytes = results.groups()
                    rx_bytes,tx_bytes = int(rx_bytes),int(tx_bytes)

                    # Push results onto circular queue
                    self.lock.acquire()
                    try:
                        if self.interfaces.has_key(device):
                            values = self.interfaces[device]
                            line_buffer,rx_buffer,tx_buffer = values
                        else:
                            line_buffer = collections.deque(maxlen = self.size)
                            rx_buffer = collections.deque(maxlen = self.size)
                            tx_buffer = collections.deque(maxlen = self.size)
                            values = line_buffer,rx_buffer,tx_buffer
                            self.interfaces[device] = values
                        line_buffer.appendleft(line)
                        rx_buffer.appendleft(rx_bytes)
                        tx_buffer.appendleft(tx_bytes)
                    finally:
                        self.lock.release()

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
    global sample_period

    # Try and parse the arguments
    try:
        data = json.loads(data)
        assert len(data) <= 1
        debug = data.pop('debug',None)
        average = data.pop('average',{}) # Default action
        assert len(data) == 0
    except:
        return json.dumps({'error':"unable to parse arguments"})

    try:
        # Command is debug
        if isinstance(debug,basestring):
            net_stat.lock.acquire()
            try:
                line_buffer,rx_buffer,tx_buffer = net_stat.interfaces[debug]
                lines = [x for x in line_buffer]
                rx_samples = [x for x in rx_buffer]
                tx_samples = [x for x in tx_buffer]
                data = {'lines': lines,
                        'rx_samples': rx_samples,
                        'tx_samples': tx_samples}
            finally:
                net_stat.lock.release()
            return json.dumps(data)

        # Command is average
        if isinstance(average,dict):
            device = average.get('device','eth0') # The network device
            length = average.get('length',10) # Time length in seconds
            weight = average.get('weight',False) # Average weight constant

            # Check the time length
            size = int(round(float(length)/sample_period))
            assert size > 0

            # Check the average weight constant
            weight = float(weight)
            assert 1 >= weight >= 0

            rx_avg,tx_avg = compute_average(device, size, weight)
            return json.dumps({'rx_average':rx_avg,'tx_average':tx_avg})
    except Exception, ex:
        return json.dumps({'error':str(ex)})

def compute_average(device, size, weight = 0.0):
    """Compute the average bandwidth for a given device"""
    global net_stat

    rx_avg,tx_avg = (0,0)
    net_stat.lock.acquire()
    try:
        if net_stat.interfaces.has_key(device):
            line_buffer,rx_buffer,tx_buffer = net_stat.interfaces[device]
            request_size = size+1 # Account for extra sample to compute delta
            size = min(len(rx_buffer),len(tx_buffer),request_size)

            # Compute the average throughput
            offset = float(1-weight)
            slope = float(2*(weight/size))
            rx_pre,tx_pre = rx_buffer[0],tx_buffer[0]
            for index in xrange(1,size):
                rx_now,tx_now = rx_buffer[index],tx_buffer[index]

                # Compute "instantaneous" bandwidth
                rx_traf = (rx_pre-rx_now)/float(net_stat.period)
                tx_traf = (tx_pre-tx_now)/float(net_stat.period)

                # Add weighted value to running sum
                kval = slope*(size-index) + offset
                rx_avg += rx_traf*kval
                tx_avg += tx_traf*kval

                rx_pre,tx_pre = rx_now,tx_now
            rx_avg = rx_avg/float(size-1)
            tx_avg = tx_avg/float(size-1)
        else:
            raise Exception("interface device '%s' does not exist" % device)
    finally:
        net_stat.lock.release()

    return rx_avg,tx_avg

################################################################################
################################ Options parser ################################
################################################################################

# Create a config parser
opts_parser = optparse.OptionParser(add_help_option = False)
opts_parser.add_option('-h', '--help',
                       action = 'help',
                       help = "Display this help and exit.")
opts_parser.add_option('-r', '--sample_rate',
                       default = SAMPLE_RATE,
                       type = 'float',
                       help = "The rate to log network statistics. "
                              "Represented in samples per second [%default]")
opts_parser.add_option('-s', '--sample_size',
                       default = SAMPLE_SIZE,
                       type = 'int',
                       help = "The amount of samples to store before rolling. "
                              "[%default]")
opts_parser.add_option('-p', '--port',
                       default = PORT,
                       type = 'int',
                       help = "The port to report statistics on. "
                              "[%default]")
(opts, args) = opts_parser.parse_args()

if opts.sample_size <= 0:
    print "Sample size must be a positive value"
    sys.exit(1)

if opts.sample_rate <= 0:
    print "Sample rate must be a positive value"
    sys.exit(1)

sample_period = 1.0/opts.sample_rate
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
net_stat = NetworkStatistic(sample_period,sample_size)
net_stat.start()

# The main event loop
try:
    while not terminate:
        network_handler()
finally:
    net_stat.stop()
    net_socket.close()

# EOF
