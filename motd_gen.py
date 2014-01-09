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
import getpass
import optparse
import datetime


################################################################################
############################### Global variables ###############################
################################################################################

# Linux terminal colors
BOLD    = '\x1b[1m'
DGRAY1  = '\x1b[1;30m'
DGRAY0  = '\x1b[0;30m'
LGRAY1  = '\x1b[1;37m'
LGRAY0  = '\x1b[0;37m'
RED1    = '\x1b[1;31m'
RED0    = '\x1b[0;31m'
GREEN1  = '\x1b[1;32m'
GREEN0  = '\x1b[0;32m'
BLUE1   = '\x1b[1;34m'
BLUE0   = '\x1b[0;34m'
YELLOW1 = '\x1b[1;33m'
YELLOW0 = '\x1b[0;33m'
PURPLE1 = '\x1b[1;35m'
PURPLE0 = '\x1b[0;35m'
CYAN1   = '\x1b[1;36m'
CYAN0   = '\x1b[0;36m'
RESET   = '\x1b[0m'

# Color aliases
NUM_PRIMARY    = BLUE1
NUM_SECONDARY  = BLUE0
TEXT_PRIMARY   = LGRAY1
TEXT_SECONDARY = DGRAY1
WARNING        = YELLOW1

# Unicode block characters
UPPER_HALF_BLOCK = unichr(0x2580)
LOWER_HALF_BLOCK = unichr(0x2584)

# Logo definition
LOGO = (
    " %s ____    ____ %s                  %s\n"
    " %s|  _ \  / ___\%s ____  ____ _____ %s\n"
    " %s| | \ \/_/_ _ %s|  _ \| ___|_   _\%s\n"
    " %s| |_/ /____/ /%s| | | | ___| | |  %s\n"
    " %s|____/ \____/ %s|_| |_|____| |_|  %s\n"
)
LOGO_COLORS = (GREEN1, BLUE1, RESET) * 5

# Regex patterns
REGEX_CTIME = (
    r'[a-zA-Z]{3} [a-zA-Z]{3} [ 0-9]{2} '  # Day name, month, day
    r'[0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}' # HH:MM:SS YYYY
)

# Warning settings and thresholds
CPU_UTIL_WARN_LEVEL = 80.0      # CPU utilization in percents
CPU_LOAD_WARN_LEVEL = 0.8       # CPU normalized load (multiply number of cores)
RAM_WARN_LEVEL      = 80.0      # RAM usage in percents
DISK_WARN_LEVEL     = 80.0      # Disk usage in percents
NET_WARN_LEVEL      = 1048576.0 # Network usage in B/s

# Miscellaneous settings and configurations
CACHE_FREE = True # Is disk cache considered free memory or not?
FULL_HOSTNAME = False # Use the full FQDN hostname
STAT_PORT = 4004 # Port for the motd_netstat daemon
NETTRAF_DEVICE = 'eth0' # The network device to monitor
NETTRAF_INTERVAL = 600 # Time length in seconds to average the bandwidth over
NETTRAF_WEIGHT = 1.0 # Perform linear moving average weight
CPUUTIL_DEVICE = 'all' # Get the aggregate CPU utilization
CPUUTIL_WEIGHT = 0.0 # Straight average for CPU utilizaiton

opts,args = None, None
utf_support = None
rows, columns = None, None
info_list = []


################################################################################
############################### Helper functions ###############################
################################################################################

def exec_cmd(cmd):
    """Execute a command and retrieve standard output"""
    with os.popen(cmd + ' 2> /dev/null', 'r') as cmd_call:
        return cmd_call.readlines()


def read_file(path):
    with open(path, 'r') as proc_file:
        return proc_file.readlines()


def shell_escape(data):
    """Escape a string for use on shells"""
    return "'" + data.replace("'", "'\\''") + "'"


def colorize(text, color):
    """Colorize the text only if color is enabled"""
    global opts
    return color + unicode(text) + RESET if opts.color else text


def regex_find(line_list, regex_list, result_list, clear_results = True):
    """Accept list of regexes and append captures into results list"""
    if clear_results:
        while result_list:
            result_list.pop()
        for index in range(len(regex_list)):
            result_list.append(list())

    # Check every line
    for line in line_list:
        # Check every regex on each line
        for index in range(len(regex_list)):
            results = re.search(regex_list[index], line.rstrip())
            if results:
                result_list[index].append(results.groups())
    return bool([x for x in result_list if x])


def unitize(value, units, prefix_mode, width = 4, color = NUM_SECONDARY):
    """Apply prefix and units"""
    if prefix_mode == 'iec':
        mult = 1024
    elif prefix_mode == 'si':
        mult = 1000
    else:
        raise ValueError("Invalid prefix mode")

    prefixes = ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y']
    for order in range(len(prefixes)):
        if round(value) < mult:
            text = '%0.' + str(width-2) + 'f'
            text = text % value
            text = text[:width]
            if text[-1] == '.':
                text = text[:-1]
            prefix = prefixes[order]
            if prefix and (prefix_mode == 'iec'):
                prefix += 'i'
            text += ' ' + prefix + units
            return colorize(text,color)
        value = value / float(mult)
    raise ValueError("Unable to convert value to human readable format")


def si_unitize(value, units = '', prefix_mode = 'si', **kwargs):
    """Apply prefix using the SI standard"""
    return unitize(value, units, prefix_mode, **kwargs)


def iec_unitize(value, units = '', prefix_mode = 'iec', **kwargs):
    """Apply prefix using the IEC standard"""
    return unitize(value, units, prefix_mode, **kwargs)


def display_border(type, color = TEXT_SECONDARY):
    """Display a horizontal border of some character"""
    global opts, utf_support, rows, columns

    # Check for unicode support
    if utf_support is None:
        locale = ''.join(exec_cmd('locale charmap'))
        utf_support = bool('UTF' in locale)

    # Check for terminal size
    if rows is None and columns is None:
        try:
            rows, columns = ''.join(exec_cmd('stty size')).split()
            rows, columns = int(rows), int(columns)
        except ValueError:
            pass

    if opts.border and utf_support and columns:
        border = type * columns
        print colorize(border, color)


def display_upper_border():
    """Display the upper border"""
    display_border(UPPER_HALF_BLOCK)


def display_lower_border():
    """Display the lower border"""
    display_border(LOWER_HALF_BLOCK)


def display_welcome():
    """Display the welcome message"""
    os_issue = ''.join(read_file('/etc/issue')).strip()
    os_name = re.sub(r'\\[a-zA-Z]', '', os_issue).strip()
    cmd = 'hostname -f' if FULL_HOSTNAME else 'hostname'
    host_name = ''.join(exec_cmd(cmd)).strip()
    values = colorize(host_name, TEXT_PRIMARY), colorize(os_name, TEXT_PRIMARY)
    print " Welcome to %s running %s" % values


def display_logo():
    """Display the logo"""
    global opts
    print LOGO % (LOGO_COLORS if opts.color else tuple([''] * len(LOGO_COLORS)))


def display_info():
    """Display system statistical information"""
    global info_list
    max_length = max([len(key) for key, value in info_list])
    for key, value in info_list:
        key = (key + ':').ljust(max_length + 4, ' ')
        print " %s%s" % (colorize(key, TEXT_SECONDARY), value)


################################################################################
################################ Options parser ################################
################################################################################

epilog = """\
This is a custom message of the day (MOTD) designed to be as practical and
informative as possible. The truth is, no one actually reads the MOTD. As such,
the MOTD should contain useful, yet minimal, information about the host system
such that a quick glance at it when logging in may actually be worth a person's
precious time. This way, any potential issues are noticed and not naively
ignored. This MOTD generator scripts has the ability to output text in color.
Using this feature, potential issues can be highlighted for easy identification.

Warnings that can be highlighted:
 * The login time if this is the first login since a reboot
 * The last login hostname if it differs from the current login hostname
 * CPU utilization if it exceeds a threshold
 * CPU load if it exceeds a threshold
 * RAM usage if it exceeds a threshold
 * Disk usage if it exceeds a threshold
 * Network load if it exceeds a threshold

Author: Joe Tsai <joetsai@digital-static.net>
"""

# Create a config parser
opts_parser = optparse.OptionParser(add_help_option = False)
opts_parser.format_epilog = lambda x: '\n' + epilog
opts_parser.add_option(
    '-h', '--help', action = 'help',
    help = "Display this help and exit.",
)
opts_parser.add_option(
    '-c', '--color', default = False, action = "store_true",
    help = "Print the MOTD with color.",
)
opts_parser.add_option(
    '-w', '--warn', default = False, action = "store_true",
    help = (
        "Highlight any potential issues. If this option is selected, it will "
        "enable colored output."
    ),
)
opts_parser.add_option(
    '-b', '--border', default = False, action = "store_true",
    help = (
        "Print MOTD with an upper and lower border. This requires being able "
        "to determine the terminal width and also being able to detect that "
        "the locale supports unicode."
    ),
)
opts_parser.add_option(
    '-p', '--prefix_mode', default = None,
    help = (
        "Set the prefix mode to use either the SI or IEC stantard. Use 'si' "
        "for base 1000 units 'iec' for base 1024 units. Defaults to IEC for "
        "all values."
    ),
)
(opts, args) = opts_parser.parse_args()

# Color is enabled if warning is enabled
if opts.warn:
    opts.color = True

# Output is not a tty
if not hasattr(sys.stderr, "isatty") or not sys.stderr.isatty():
    opts.color = False
    opts.border = False

# Check prefix mode
if opts.prefix_mode and opts.prefix_mode not in ['si', 'iec']:
    print "Invalid prefix mode: %s" % opts.prefix_mode
    sys.exit(1)
units = si_unitize if (opts.prefix_mode == 'si') else iec_unitize


################################################################################
################################# Script start #################################
################################################################################

####################
# Generate info list
result_list = []

# Get last login
try:
    login_host = exec_cmd('last -n 2 -w -F $USER')
    regex = (
        r'([^\s]+)\s+' # Username
        r'([^\s]+)\s+' # Virtual terminal
        r'([^\s]*)\s+' # Hostname (blank if local terminal)
        r'(%s)[-\s]+(%s)?.*' % (REGEX_CTIME, REGEX_CTIME) # Date start-end
    )
    user, port, host, start, end = re.search(regex,login_host[1]).groups()
    if host in ['', ':0', ':0.0']:
        host = 'localhost'
    start = re.sub('\s+', ' ', start)
    assert bool(user == getpass.getuser())

    addr_now, addr_pre, reboot_time, start_time = None, None, 0, 0
    if opts.warn:
        # Get the previous login sources in address form
        login_addr = exec_cmd('last -n 2 -w -F -i $USER')
        login_now, login_pre = login_addr[:2]
        results_now = re.search(regex, login_now).groups()
        results_pre = re.search(regex, login_pre).groups()
        addr_now, start_now, end_now = results_now[2:]
        addr_pre, start_pre, end_pre = results_pre[2:]
        assert bool(results_now[0] == results_pre[0] == getpass.getuser())

        # Get the last reboot time and login time
        datetime, timedelta = datetime.datetime, datetime.timedelta
        uptime = ' '.join(read_file('/proc/uptime'))
        total_time, idle_time = [int(float(x)) for x in uptime.split()]
        reboot_time = datetime.now() - timedelta(seconds = total_time)
        start_time = datetime.strptime(start_pre, "%a %b %d %H:%M:%S %Y")

    # Hostname color (warn if login from different host)
    warn_check = bool(addr_now != addr_pre)
    color_host = WARNING if (opts.warn and warn_check) else TEXT_PRIMARY

    # Last login date color (warn if first login since reboot)
    warn_check = bool(reboot_time > start_time)
    color_start = WARNING if (opts.warn and warn_check) else TEXT_PRIMARY

    values = colorize(start, color_start), colorize(host,color_host)
    info_list.append(('Last login', '%s from %s' % values))
except:
    login = exec_cmd('lastlog -u $USER')
    info_list.append(('Last login', ' '.join(login[-1].split())))

# Get uptime
try:
    uptime = ' '.join(read_file('/proc/uptime'))
    total_time,idle_time = [int(float(x)) for x in uptime.split()]
    days = total_time/60/60/24
    hours = total_time/60/60 % 24
    minutes = total_time/60 % 60
    seconds = total_time % 60

    # Don't display leading empty units
    skip, message_list = True, []
    for unit in ['days', 'hours', 'minutes', 'seconds']:
        value = locals()[unit]
        if value:
            skip = False
        elif skip:
            continue
        message = '%s %s' % (colorize(str(value), NUM_PRIMARY), unit)
        message_list.append(message)
    if message_list:
        info_list.append(('Uptime', ', '.join(message_list)))
except:
    pass

# Get CPU information
try:
    cpu_info = read_file('/proc/cpuinfo')
    regex_list = [
        r'^processor\s*:\s*(.*?)\s*$',
        r'^model name\s*:\s*(.*?)\s*$',
        r'^flags\s*:.*\s+(lm)\s+.*$',
    ]
    regex_find(cpu_info, regex_list, result_list)

    # Get bus bit-width, model name, and number of cores
    cores = len(result_list[0])
    model = result_list[1][0][0]
    model = re.sub(r'\([rR]\)|\([tT][mM]\)', '', model)
    model = colorize(' '.join(model.split()), TEXT_PRIMARY)
    bus_width = '64-bit' if result_list[2] else '32-bit'
    message = '%s %s, %sx cores' % (bus_width, model, cores)
    info_list.append(('CPU information', message))
except:
    pass

# Get CPU utilization
try:
    utils = []
    for interval in [60, 300, 900]:
        # Query for CPU utilization
        query = {
            'cpu_util': {
                'device':   CPUUTIL_DEVICE,
                'interval': interval,
                'weight':   CPUUTIL_WEIGHT,
            }
        }
        query = shell_escape(json.dumps(query))
        command = 'echo %s | netcat localhost %s' % (query,STAT_PORT)
        util_usage = ''.join(exec_cmd(command)).strip()

        # Load the JSON data
        data = json.loads(util_usage)
        utils.append(data['utilization'] * 100.0)

    utils_text = []
    for util in utils:
        percent_text = '%.2f%%' % util
        warn_check = bool(util > CPU_UTIL_WARN_LEVEL)
        color = WARNING if (opts.warn and warn_check) else NUM_PRIMARY
        utils_text.append(colorize(percent_text,color))
    values = tuple(utils_text)
    message = "%s (1 minute) - %s (5 minutes) - %s (15 minutes)" % values
    info_list.append(('CPU utilization', message))
except:
    pass

# Get CPU load
try:
    cpu_load = ' '.join(read_file('/proc/loadavg')).strip()
    loads = [float(x) for x in cpu_load.split(None,3)[:3]]
    loads_text = []
    for load in loads:
        percent_text = '%.2f' % load
        warn_check = bool(load > CPU_LOAD_WARN_LEVEL*cores)
        color = WARNING if (opts.warn and warn_check) else NUM_PRIMARY
        loads_text.append(colorize(percent_text, color))
    values = tuple(loads_text)
    message = "%s (1 minute) - %s (5 minutes) - %s (15 minutes)" % values
    info_list.append(('CPU load', message))
except:
    pass

# Get memory usage
try:
    mem_info = read_file('/proc/meminfo')
    regex_list = [
        r'^MemTotal:\s+([0-9]+)\s+kB.*$',
        r'^MemFree:\s+([0-9]+)\s+kB.*$',
        r'^Buffers:\s+([0-9]+)\s+kB.*$',
        r'^Cached:\s+([0-9]+)\s+kB.*$',
    ]
    regex_find(mem_info, regex_list, result_list)

    # Get total, free, cached, and buffered memory
    total = int(result_list[0][0][0]) * 1024
    free = int(result_list[1][0][0]) * 1024
    if CACHE_FREE:
        free += (int(result_list[2][0][0]) + int(result_list[3][0][0]))*1024
    used = total - free
    percent = (float(used)/float(total)) * 100.0

    warn_check = bool(percent > RAM_WARN_LEVEL)
    color = WARNING if (opts.warn and warn_check) else NUM_PRIMARY
    percent_text = colorize('%.2f%%' % percent, color)
    values = percent_text,units(total, 'B'), units(used, 'B'), units(free, 'B')
    message = "%s - %s total, %s used, %s free" % values
    info_list.append(('Memory usage', message))
except:
    pass

# Get disk usage
try:
    disk_usage = exec_cmd('df -B 1 /')[-1].strip()
    label, total, used, free, others = disk_usage.split(None, 4)
    total, used, free = int(used)+int(free), int(used), int(free)
    percent = (float(used) / float(total)) * 100.0

    warn_check = bool(percent > DISK_WARN_LEVEL)
    color = WARNING if (opts.warn and warn_check) else NUM_PRIMARY
    percent_text = colorize('%.2f%%' % percent, color)
    values = percent_text, units(total, 'B'), units(used, 'B'), units(free, 'B')
    message = "%s - %s total, %s used, %s free" % values
    info_list.append(('Disk usage', message))
except:
    pass

# Get network usage
try:
    # Query for network statistic
    query = {
        'net_traf': {
            'device':   NETTRAF_DEVICE,
            'interval': NETTRAF_INTERVAL,
            'weight':   NETTRAF_WEIGHT,
        }
    }
    query = shell_escape(json.dumps(query))
    command = 'echo %s | netcat localhost %s' % (query, STAT_PORT)
    net_usage = ''.join(exec_cmd(command)).strip()

    # Load the JSON data
    data = json.loads(net_usage)
    rx_avg, tx_avg = data['rx_average'], data['tx_average']
    total = rx_avg + tx_avg

    warn_check = bool(total > NET_WARN_LEVEL)
    color = WARNING if (opts.warn and warn_check) else NUM_PRIMARY
    total_text = units(total, 'B/s', color = color)
    values = total_text,units(rx_avg, 'B/s'), units(tx_avg, 'B/s')
    message = "%s - %s down, %s up" % values
    info_list.append(('Network traffic', message))
except:
    pass

# Get processes
try:
    user_procs = len(exec_cmd('ps U $USER h'))
    total_procs = len(exec_cmd('ps -A h'))
    assert bool(total_procs or user_procs)
    assert bool(total_procs >= user_procs)
    values = colorize(user_procs,NUM_PRIMARY),colorize(total_procs,NUM_PRIMARY)
    message = "User running %s processes out of %s total" % values
    info_list.append(('Processes', message))
except:
    pass

####################
# Display the MOTD
display_upper_border()
display_welcome()
display_logo()
display_info()
display_lower_border()
