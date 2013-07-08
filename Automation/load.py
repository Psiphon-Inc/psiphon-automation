#!/usr/bin/python

import pprint
import operator

# TODO: print if server is discovery or propagation etc
def check_load_on_hosts(psinet, hosts):
    cur_users = 0
    loads = {}
    for host in hosts:
        try:
            users = psinet._PsiphonNetwork__count_users_on_host(host.id)
            cur_users += users
            free = psinet.run_command_on_host(host, 'free | grep "buffers/cache" | awk \'{print $4/($3+$4) * 100.0}\'')
            free_swap = psinet.run_command_on_host(host, 'free | grep "Swap" | awk \'{print $4/$2 * 100.0}\'')
            psi_web = psinet.run_command_on_host(host, 'pgrep psi_web')
            udpgw = psinet.run_command_on_host(host, 'pgrep badvpn-udpgw')
            xinetd = psinet.run_command_on_host(host, 'pgrep xinetd')
            loads[host.id] = (users, free.rstrip(), free_swap.rstrip(), psi_web.rstrip(), udpgw.rstrip(), xinetd.rstrip())
        except Exception as e:
            loads[host.id] = (-1, -1)
    pprint.pprint(sorted(loads.iteritems(), key=operator.itemgetter(1)))
    return cur_users, loads

def check_load(psinet):
    return check_load_on_hosts(psinet, psinet.get_hosts())
    