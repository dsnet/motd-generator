#!/usr/bin/env python

import re
import os
import sys
import optparse

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

# Unicode block characters
UPPER_HALF_BLOCK = unichr(0x2580)
LOWER_HALF_BLOCK = unichr(0x2584)

# Logo definition
LOGO = " %s ____    ____ %s\n" \
       " %s|  _ \  / ___\%s%s ____  ___ _____ %s\n" \
       " %s| | \ \/_/_ _ %s%s|  _ \| __|_   _\%s\n" \
       " %s| |_/ /____/ /%s%s| | | | __| | |  %s\n" \
       " %s|____/ \____/ %s%s|_| |_|___| |_|  %s\n"
LOGO_COLORS = []
for index in range(5):
    LOGO_COLORS += [GREEN1,RESET]
    if index > 0:
        LOGO_COLORS += [BLUE1,RESET]

opts,args = None,None
rows,columns = None,None
info_list = []

################################################################################
############################### Helper functions ###############################
################################################################################

def exec_cmd(cmd):
    lines = os.popen(cmd + ' 2> /dev/null', 'r').readlines()
    return [line.rstrip() for line in lines]

def byte_unit(bytes, color = BLUE1):
    global opts
    units = ['B','KB','MB','GB','TB','PB','EB','ZB','YB']
    value = bytes
    for order in range(len(units)):
        if round(value) < 1000:
            text = "%d %s" % (round(value),units[order])
            if color and opts.color:
                return color+text+RESET
            else:
                return text
        value = value/1000.0
    raise ValueError("Unable to convert bytes to human readable format")

def display_border(type):
    global opts, rows, columns

    # Check for terminal size
    if rows is None and columns is None:
        try:
            rows,columns = ''.join(exec_cmd('stty size')).split()
            rows,columns = int(rows),int(columns)
        except ValueError:
            pass

    if opts.border and columns:
        print type * columns

def display_upper_border():
    display_border(UPPER_HALF_BLOCK)

def display_lower_border():
    display_border(LOWER_HALF_BLOCK)

def display_welcome():
    global opts
    os_issue = ''.join(exec_cmd('/bin/cat /etc/issue')).strip()
    os_name = re.sub(r'\\[a-zA-Z]','',os_issue).strip()
    full_name = ''.join(exec_cmd('domainname -f')).strip()
    if opts.color:
        full_name = DGRAY1+full_name+RESET
        os_name = DGRAY1+os_name+RESET
    welcome = " Welcome to %s running %s" % (full_name,os_name)
    print welcome

def display_logo():
    global opts
    if opts.color:
        print LOGO % tuple(LOGO_COLORS)
    else:
        print LOGO % tuple(['' for x in LOGO_COLORS])

def display_info():
    global opts, info_list
    max_length = 0
    for key,value in info_list:
        max_length = max(len(key),max_length)
    for key,value in info_list:
        key = key.ljust(max_length+3,' ')
        if opts.color:
            key = DGRAY0+key+RESET
        print " %s%s" % (key,value)

################################################################################
################################ Options parser ################################
################################################################################

# Create a config parser
opts_parser = optparse.OptionParser(add_help_option = False)
opts_parser.add_option('-h', '--help',
                       action = 'help',
                       help = "Display this help and exit.")
opts_parser.add_option('-c', '--color',
                       default = False,
                       action = "store_true",
                       help = "Print the MOTD with color. ")
opts_parser.add_option('-b', '--border',
                       default = False,
                       action = "store_true",
                       help = "Print MOTD with a upper and lower border. "
                              "Requires being to determine terminal width. ")
(opts, args) = opts_parser.parse_args()

################################################################################
################################# Script start #################################
################################################################################

####################
# Generate info list

# Get last login
login = exec_cmd('lastlog -u $USER')[-1].strip()
try:
    user,port,host,last = login.split(None,3)
    if opts.color:
        last = DGRAY1+last+RESET
        host = DGRAY1+host+RESET
    info_list.append(('Last login:', '%s from %s' % (last,host)))
except:
    info_list.append(('Last login:', ' '.join(login.split())))

# Get uptime
uptime = ''.join(exec_cmd('/bin/cat /proc/uptime')).strip()
try:
    total_time,idle_time = [int(float(x)) for x in uptime.split()]
    days = total_time/60/60/24
    hours = total_time/60/60%24
    minutes = total_time/60%60
    seconds = total_time%60

    if opts.color:
        days = BLUE1+str(days)+RESET
        hours = BLUE1+str(hours)+RESET
        minutes = BLUE1+str(minutes)+RESET
        seconds = BLUE1+str(seconds)+RESET

    message_list = []
    message_list.append('%s days' % days)
    message_list.append('%s hours' % hours)
    message_list.append('%s minutes' % minutes)
    message_list.append('%s seconds' % seconds)

    if message_list:
        info_list.append(('Uptime:', ', '.join(message_list)))
except:
    info_list.append(('Uptime:', uptime))

# Get CPU information
cpu_info = exec_cmd('/bin/cat /proc/cpuinfo')
try:
    # Get model
    model = ''
    for line in cpu_info:
        line_sub = re.sub(r'^model name\s*:','',line)
        if line != line_sub:
            model = re.sub(r'\([rR]\)|\([tT][mM]\)','',line_sub)
            model = ' '.join(model.strip().split())
            break

    # Get cores
    cores = 0
    for line in cpu_info:
        if re.match(r'^processor\s*:',line):
            cores += 1
    cores = "%sx cores" % cores

    if model and cores:
        if opts.color:
            model = DGRAY1+model+RESET
        message = '%s, %s' % (model,cores)
        info_list.append(('CPU information:', message))
except:
    pass

# Get CPU load
cpu_load = ''.join(exec_cmd('/bin/cat /proc/loadavg')).strip()
try:
    loads = [float(x) for x in cpu_load.split(None,3)[:3]]
    loads_text = []
    for load in loads:
        percent_text = '%.2f%%' % load
        if opts.color:
            percent_text = BLUE0+percent_text+RESET
        loads_text.append(percent_text)
    values = tuple(loads_text)
    message = "%s (1 minute) - %s (5 minutes) - %s (15 minutes)" % values
    info_list.append(('CPU load:', message))
except:
    pass

# Get memory usage
mem_usage = exec_cmd('free -b')
try:
    mem_line = ''
    for line in mem_usage:
        if re.search(r'^Mem:',line):
            mem_line = line.strip()
            break
    if mem_line:
        label,total,used,free,others = mem_line.split(None,4)
        total,used,free = int(total),int(used),int(free)
        percent = (float(used)/float(total))*100.0
        percent_text = '%.2f%%' % percent
        if opts.color:
            percent_text = BLUE0+percent_text+RESET
        values = percent_text,byte_unit(total),byte_unit(used),byte_unit(free)
        message = "%s - %s total, %s used, %s free" % values
        info_list.append(('Memory usage:', message))
except:
    pass

# Get disk usage
disk_usage = exec_cmd('df -B 1 /')[-1].strip()
try:
    label,blocks,used,free,others = disk_usage.split(None,4)
    total,used,free = int(used)+int(free),int(used),int(free)
    percent = (float(used)/float(total))*100.0
    percent_text = '%.2f%%' % percent
    if opts.color:
        percent_text = BLUE0+percent_text+RESET
    values = percent_text,byte_unit(total),byte_unit(used),byte_unit(free)
    message = "%s - %s total, %s used, %s free" % values
    info_list.append(('Disk usage:', message))
except:
    pass

# Get processes
user_procs = len(exec_cmd('ps U $USER h'))
total_procs = len(exec_cmd('ps -A h'))
try:
    if (total_procs or user_procs) and (total_procs >= user_procs):
        if opts.color:
            user_procs = BLUE1+str(user_procs)+RESET
            total_procs = BLUE1+str(total_procs)+RESET
        values = user_procs,total_procs
        message = "User running %s processes out of %s total" % values
        info_list.append(('Processes:', message))
except:
    pass

####################
# Display the MOTD
display_upper_border()
display_welcome()
display_logo()
display_info()
display_lower_border()

# EOF
