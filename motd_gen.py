#!/usr/bin/env python

import re
import os
import sys

# Logo definition
LOGO = "  ____    ____                   \n" \
       " |  _ \  / ___\ ____  ___ _____  \n" \
       " | | \ \/_/_ _ |  _ \| __|_   _\ \n" \
       " | |_/ /____/ /| | | | __| | |   \n" \
       " |____/ \____/ |_| |_|___| |_|   \n"

def exec_cmd(cmd):
    lines = os.popen(cmd + ' 2> /dev/null', 'r').readlines()
    return [line.rstrip() for line in lines]

info_list = []

# Get last login
login = exec_cmd('lastlog -u $USER')[-1].strip()
user,port,host,last = login.split(None,3)
info_list.append(('Last login:', '%s from %s' % (last,host)))

# Get uptime
uptime = ''.join(exec_cmd('cat /proc/uptime')).strip()
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
info_list.append(('Uptime:', ', '.join(message_list)))

# Get CPU information
cpu_info = exec_cmd('cat /proc/cpuinfo')

model = ''
for line in cpu_info:
    line_sub = re.sub(r'^model name\s*:','',line)
    if line != line_sub:
        model = re.sub(r'\([rR]\)|\([tT][mM]\)','',line_sub)
        model = ' '.join(model.strip().split())
        break
cores = 0
for line in cpu_info:
    if re.match(r'^processor\s*:',line):
        cores += 1
message = '%s, %sx cores' % (model,cores)
info_list.append(('CPU info:', message))

# Get CPU load
cpu_load = ''.join(exec_cmd('cat /proc/loadavg')).strip()
loads = [float(x) for x in cpu_load.split(None,3)[:3]]
loads_text = []
for load in loads:
    percent_text = '%.2f%%' % load
    loads_text.append(percent_text)
values = tuple(loads_text)
message = "%s (1 minute) - %s (5 minutes) - %s (15 minutes)" % values
info_list.append(('CPU load:', message))

# Get memory usage
mem_usage = exec_cmd('free -m')
label,total,used,free,others = mem_usage[1].split(None,4)
total,used,free = int(total),int(used),int(free)
percent = '%.2f%%' % ((float(used)/float(total))*100.0)
values = percent,total,used,free
message = "%s - %sMB total, %sMB used, %sMB free" % values
info_list.append(('Memory usage:', message))

# Get disk usage
disk_usage = exec_cmd('df -h /')[-1].strip()
label,total,used,free,percent,others = disk_usage.split(None,5)
values = percent,total,used,free
message = "%s - %sB total, %sB used, %sB free" % values
info_list.append(('Disk usage:', message))

# Get processes
user_procs = len(exec_cmd('ps U $USER h'))
total_procs = len(exec_cmd('ps -A h'))
values = user_procs,total_procs
message = "Running %s processes out of %s total" % values
info_list.append(('Processes:', message))

# Print the welcome message
os_issue = ''.join(exec_cmd('cat /etc/issue')).strip()
os_name = re.sub(r'\\[a-zA-Z]','',os_issue).strip()
full_name = ''.join(exec_cmd('domainname -f')).strip()
print " Welcome to %s running %s" % (full_name,os_name)

# Print the logo
print LOGO

# Print all of the info
for key,value in info_list:
    print " %s\t%s" % (key,value)

# EOF
