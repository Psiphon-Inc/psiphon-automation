import psi_ops
import psi_ssh
import sys
import os
import paramiko
path  = "/home/iyoshinoya/psiphon/providers/"
csv_file = f'{path}hosts'
psinet = psi_ops.PsiphonNetwork.load(lock=False)
hosts = [host for host in psinet.get_hosts() if host.is_TCS]
df = open(csv_file, "w")
try:
    for i in range(0,len(hosts)):
        #df.write(hosts[i].id + "\t" + hosts[i].ip_address + "\t" + hosts[i].ssh_password + "\n")
        df.write(hosts[i].id + "\t" + hosts[i].ip_address + "\t" + hosts[i].ssh_password + "\t" + hosts[i].provider + "\n")
except Exception as e:
    print("Failed", hosts[i], str(e))
df.close()
