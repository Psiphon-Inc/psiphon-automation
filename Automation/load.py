#!/usr/bin/python

import pprint
import operator
from multiprocessing.pool import ThreadPool

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

def check_load(psinet):
    return check_load_on_hosts(psinet, psinet.get_hosts())
    