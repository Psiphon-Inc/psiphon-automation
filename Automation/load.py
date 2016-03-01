#!/usr/bin/python
## Copyright (c) 2014, Psiphon Inc.
## All rights reserved.
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.

import ast
import os
import errno
import shutil
import sys
import json
import logging
import pprint
import operator
import datetime
import pynliner
from multiprocessing.pool import ThreadPool

from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions

# Using the FeedbackDecryptor's mail capabilities
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder')))
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder', 'FeedbackDecryptor')))
import sender
from config import config

import psi_ops

def check_load_on_host(host):
    try:
        log_diagnostics('checking host: %s' % (host.id))
        users = g_psinet._PsiphonNetwork__count_users_on_host(host.id)
        load_metrics = g_psinet.run_command_on_host(host,
            'uptime | cut -d , -f 4 | cut -d : -f 2; grep "model name" /proc/cpuinfo | wc -l').split('\n')
        load_threshold = 4.0 * float(load_metrics[1].strip()) - 1
        load = str(float(load_metrics[0].strip())/load_threshold * 100.0)
        free = g_psinet.run_command_on_host(host, 'free | grep "buffers/cache" | awk \'{print $4/($3+$4) * 100.0}\'')
        free_swap = g_psinet.run_command_on_host(host, 'free | grep "Swap" | awk \'{if ($2 == 0) {print 0} else {print $4/$2 * 100.0}}\'')
        processes_to_check = ['psi_web.py', 'redis-server', 'badvpn-udpgw', 'xinetd', 'xl2tpd', 'cron', 'rsyslogd', 'fail2ban-server', 'ntpd', 'systemctl']
        if host.meek_server_port:
            processes_to_check.append('meek-server')
        process_counts = g_psinet.run_command_on_host(host,
            '; '.join(['pgrep -xc ' + process for process in processes_to_check])).split('\n')
        process_alerts = []
        for index, process in enumerate(processes_to_check):
            alert = False
            instances = int(process_counts[index])
            if process == 'cron':
                alert = instances < 1
            elif process == 'xl2tpd':
                alert = instances != len([server.id for server in g_psinet.get_servers() if server.host_id == host.id])
            elif process == 'systemctl':
                alert = instances > 0
            else:
                alert = instances != 1
            if alert:
                process_alerts.append(process)
        return (host.id, users, load, free.rstrip(), free_swap.rstrip(), ', '.join(process_alerts))
    except Exception as e:
        log_diagnostics('failed host: %s %s' % (host.id, str(e)))
        return (host.id, -1, -1, -1, -1, '')

# TODO: print if server is discovery or propagation etc
def check_load_on_hosts(psinet, hosts):
    loads = {}

    pool = ThreadPool(25)
    global g_psinet
    g_psinet = psinet
    log_diagnostics('Checking Hosts...')
    results = pool.map(check_load_on_host, hosts)
    log_diagnostics('...done checking hosts')

    # retry failed hosts
    failed_hosts = [psinet._PsiphonNetwork__hosts[result[0]] for result in results if result[1] == -1 or result[5]]
    if len(failed_hosts):
        log_diagnostics('Retrying failed hosts')
    new_results = pool.map(check_load_on_host, failed_hosts)

    for result in results + new_results:
        loads[result[0]] = result[1:]

    cur_users = sum([load[0] for load in loads.itervalues() if load[0] > 0])
    unreachable_hosts = len([load for load in loads.itervalues() if load[0] == -1])
    
    loads = sorted(loads.iteritems(), key=operator.itemgetter(1), reverse=True)
    unreachable = [load for load in loads if load[1][0] == -1]
    process_alerts = [load for load in loads if load[1][4]]
    high_load = [load for load in loads if float(load[1][1]) >= 100.0]
    low_memory = [load for load in loads if float(load[1][2]) < 20.0 or float(load[1][3]) < 20.0]

    for load in low_memory + high_load + process_alerts + unreachable:
        loads.insert(0, loads.pop(loads.index(load)))

    pprint.pprint(loads)
    return cur_users, len(loads), unreachable_hosts, loads

def check_load_on_all_hosts(psinet):
    return check_load_on_hosts(psinet, psinet.get_hosts())

def check_load():
    PSI_OPS_DB_FILENAME = os.path.join(os.path.abspath('.'), 'psi_ops_stats.dat')
    psinet = psi_ops.PsiphonNetwork.load_from_file(PSI_OPS_DB_FILENAME)

    hosts = psinet.get_hosts()
    for h in hosts:
        if h.ssh_username == '' and h.ssh_password == '':
            h.ssh_username = h.stats_ssh_username
            h.ssh_password = h.stats_ssh_password

    return check_load_on_hosts(psinet, hosts)

def log_load():
    start_time = datetime.datetime.now()
    results = check_load()
    end_time = datetime.datetime.now()
    results = (str(start_time), str(end_time), (results))
    print "Run completed at: %s\nTotal run time: %s" % (str(end_time), str(end_time-start_time))
    with open('psi_host_load_results.log', 'a') as outfile:
        outfile.write(str(results))
        outfile.write('\n')
    send_mail(results)

def log_diagnostics(line):
    with open('psi_host_load_diagnostics.log', 'a') as log_file:
        log_file.write(line + '\n')

def send_mail(record):
    template_filename = 'psi_mail_hosts_load.mako'
    template_lookup = TemplateLookup(directories=[os.path.dirname(os.path.abspath('__file__'))])
    # SECURITY IMPORTANT: `'h'` in the `default_filters` list causes HTML
    # escaping to be applied to all expression tags (${...}) in this
    # template. Because we're output untrusted user-supplied data, this is
    # essential.
    template = Template(filename=template_filename, default_filters=['unicode', 'h'], lookup=template_lookup)
    try:
        rendered = template.render(data=record)
    except:
        raise Exception(exceptions.text_error_template().render())

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)
    log_diagnostics('Sending email...')
    sender.send(config['statsEmailRecipients'], config['emailUsername'], 'Psiphon 3 Host Load Stats', repr(record), rendered)
    log_diagnostics('Email sent.')


FILENAME = 'psi_host_load_results.log'
REPORTS_DIRNAME = 'host_reports'
REPORTS_DIR = REPORTS_DIRNAME
STAGING_DIR = os.path.join(REPORTS_DIR, 'staging')
DATA_DIRNAME = 'data'
DATA_DIR = os.path.join(STAGING_DIR, DATA_DIRNAME)
REPORT_EXT = '.dat'
FRESH_AGE = datetime.timedelta(2)
REPORT_LIST_FILENAME = 'data.json'
REPORT_LIST_FILEPATH = os.path.join(STAGING_DIR, REPORT_LIST_FILENAME)

def dump_host_reports(fresh_hosts_only=True):
    # Note: this routine keeps a file handle open per host; adjust ulimits accordlingly

    # Delete any leftover file
    shutil.rmtree(STAGING_DIR, ignore_errors=True)
    _makedirs(STAGING_DIR)
    _makedirs(DATA_DIR)

    # Like { hostname: [host_fp, host_fname, max_date], ... }
    host_files = {}

    with open(FILENAME, 'r') as f:
        for line in f:
            data = ast.literal_eval(line)
            start_time = data[0]
            end_time = data[1]
            loads = data[2]
            if len(loads) != 3:
                # old format, skip
                continue
            total_users = loads[0]
            nonresponding_hosts = loads[1]
            host_loads = loads[2]
            for host_load in host_loads:
                hostname =  host_load[0]
                host_load = host_load[1][0]
                if not hostname in host_files:
                    fname = os.path.join(DATA_DIR, hostname + REPORT_EXT)
                    host_files[hostname] = [open(fname, 'w'), fname, None]

                host_file = host_files[hostname]
                host_file[0].write('%s,%s\n' % (end_time.replace(' ', 'T'), host_load))
                host_file[2] = max(end_time, host_file[2])
            # print end_time

    # Collect data file info to put into the JSON index file
    data_files = []

    for host_file in host_files.itervalues():
        host_file[0].close()
        if fresh_hosts_only and datetime.datetime.strptime(host_file[2], '%Y-%m-%d %H:%M:%S.%f') + FRESH_AGE < datetime.datetime.now():
            # Defunct. Delete.
            os.unlink(host_file[1])
        else:
            fname = os.path.basename(host_file[1])
            hostname = os.path.splitext(fname)[0]
            data_files.append((hostname, './'+DATA_DIRNAME+'/'+fname))

    # Dump the file list to a JSON index file.
    with open(REPORT_LIST_FILEPATH, 'w') as listfile:
        json.dump(data_files, listfile, indent=2)

    # Move from staging to the final location
    os.unlink(os.path.join(REPORTS_DIR, REPORT_LIST_FILENAME))
    shutil.move(REPORT_LIST_FILEPATH, os.path.join(REPORTS_DIR, REPORT_LIST_FILENAME))
    shutil.rmtree(os.path.join(REPORTS_DIR, DATA_DIRNAME))
    shutil.move(DATA_DIR, os.path.join(REPORTS_DIR, DATA_DIRNAME))


def _makedirs(path):
    try:
        os.makedirs(path)
    except OSError as ex:
        if ex.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


if __name__ == "__main__":
    log_load()
    #dump_host_reports()

