#!/usr/bin/env python

import re
import os
import sys

################################################################################
############################### Global variables ###############################
################################################################################

# Logo definition
LOGO = "  ____    ____                   \n" \
       " |  _ \  / ___\ ____  ___ _____  \n" \
       " | | \ \/_/_ _ |  _ \| __|_   _\ \n" \
       " | |_/ /____/ /| | | | __| | |   \n" \
       " |____/ \____/ |_| |_|___| |_|   \n"

info_list = []

################################################################################
############################### Helper functions ###############################
################################################################################

def exec_cmd(cmd):
    lines = os.popen(cmd + ' 2> /dev/null', 'r').readlines()
    return [line.rstrip() for line in lines]

def byte_unit(bytes):
    units = ['B','KB','MB','GB','TB','PB','EB','ZB','YB']
    value = bytes
    for order in range(len(units)):
        if round(value) < 1000:
            return "%d %s" % (round(value),units[order])
        value = value/1000.0
    raise ValueError("Unable to convert bytes to human readable format")

def display_welcome():
    os_issue = ''.join(exec_cmd('/bin/cat /etc/issue')).strip()
    os_name = re.sub(r'\\[a-zA-Z]','',os_issue).strip()
    full_name = ''.join(exec_cmd('domainname -f')).strip()
    welcome = " Welcome to %s running %s" % (full_name,os_name)
    print welcome

def display_logo():
    print LOGO

def display_info():
    global info_list
    max_length = 0
    for key,value in info_list:
        max_length = max(len(key),max_length)
    for key,value in info_list:
        key = key.ljust(max_length+3,' ')
        print " %s%s" % (key,value)

################################################################################
################################# Script start #################################
################################################################################

####################
# Generate info list

# Get last login
login = exec_cmd('lastlog -u $USER')[-1].strip()
try:
    user,port,host,last = login.split(None,3)
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
        values = user_procs,total_procs
        message = "User running %s processes out of %s total" % values
        info_list.append(('Processes:', message))
except:
    pass

####################
# Display the MOTD
display_welcome()
display_logo()
display_info()

# EOF
