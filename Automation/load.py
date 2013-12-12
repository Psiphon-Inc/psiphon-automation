#!/usr/bin/python

import pprint
import operator
from multiprocessing.pool import ThreadPool
import os
import logging
import psi_ops

def check_load_on_host(host):
    try:
        users = g_psinet._PsiphonNetwork__count_users_on_host(host.id)
        load = g_psinet.run_command_on_host(host, 'uptime | cut -d , -f 4 | cut -d : -f 2 | awk -F \. \'{print $1}\'')
        free = g_psinet.run_command_on_host(host, 'free | grep "buffers/cache" | awk \'{print $4/($3+$4) * 100.0}\'')
        free_swap = g_psinet.run_command_on_host(host, 'free | grep "Swap" | awk \'{print $4/$2 * 100.0}\'')
        #psi_web = g_psinet.run_command_on_host(host, 'pgrep psi_web')
        #udpgw = g_psinet.run_command_on_host(host, 'pgrep badvpn-udpgw')
        #xinetd = g_psinet.run_command_on_host(host, 'pgrep xinetd')
        return (host.id, users, load, free.rstrip(), free_swap.rstrip())#, psi_web.rstrip(), udpgw.rstrip(), xinetd.rstrip())
    except Exception as e:
        return (host.id, -1, -1, -1, -1)#, -1, -1, -1)

# TODO: print if server is discovery or propagation etc
def check_load_on_hosts(psinet, hosts):
    cur_users = 0
    loads = {}
    
    pool = ThreadPool(25)
    global g_psinet
    g_psinet = psinet
    results = pool.map(check_load_on_host, hosts)
    
    for result in results:
        if result[1] == -1:
            # retry a failed host
            print 'Retrying host ' + result[0]
            result = check_load_on_host(psinet._PsiphonNetwork__hosts[result[0]])

        cur_users += result[1]
        loads[result[0]] = result[1:]

    pprint.pprint(sorted(loads.iteritems(), key=operator.itemgetter(1)))
    return cur_users, loads

def check_all_servers_load(psinet):
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
    results = check_load()
    with open('psi_host_load_results.log', 'a') as outfile:
        outfile.write(str(results))

def log_load():
    results = check_load()
    with open('psi_host_load_results.log', 'a') as outfile:
        outfile.write(str(results))
        outfile.write('\n')

if __name__ == "__main__":
    log_load()
