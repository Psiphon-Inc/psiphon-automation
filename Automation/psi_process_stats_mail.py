#!/usr/bin/python
#
# Copyright (c) 2015, Psiphon Inc.
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os
import sys
import re
import pynliner
import platform

MAKO_TEMPLATE='psi_process_stats_mail.mako'

from mako.template import Template
from mako.lookup import TemplateLookup
from mako import exceptions

# Using the FeedbackDecryptor's mail capabilities
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder')))
sys.path.append(os.path.abspath(os.path.join('..', 'EmailResponder', 'FeedbackDecryptor')))
import sender
from config import config

STATS_JOB_LOG='psi_stats_job.log'
LOGFILE=os.path.join(os.path.abspath('.'), STATS_JOB_LOG)

STATS_START_LINE="Process stats start time"
STATS_END_LINE="Total stats processing elapsed time"

LAST_RUN_ONLY = True

def process_stats_job_log(logfile=LOGFILE):
    try:
        run_starts = list()
        run_ends = list()
        run_details = list()
        run_data = list()

        if not os.path.isfile(logfile):
            raise "File not found: %s" % (logfile)

        with open(logfile, 'r') as f:
            data_lines = list(f)

        for num, line in enumerate(data_lines):
            if STATS_START_LINE in line:
                run_starts.append(num)
                run_data = list()
            
            run_data.append(line.strip())
            
            if STATS_END_LINE in line:
                run_ends.append(num)
                run_details.append(run_data)

        if len(run_starts) != len(run_ends):
            if len(run_starts) == (len(run_ends) + 1):
                run_starts.pop()

        return zip(run_starts, run_ends, run_details)
    
    except Exception as e:
        raise e

# This will consume a start line number, end line number and data
def process_stats_run(start_line_num, end_line_num, data):
    try:
        ## Host sync stats ########################################

        sync_log_line = 'sync log files from host '
        sync_log_success = 'completed host '
        sync_log_fail = 'failed host'
        sync_summary_line = 'Sync log files elapsed time'

        # 2480 new lines processed
        processed_string = 'new lines processed'

        common_strings = [
                re.compile("^Process stats start time.*"),
                re.compile(".*known_hosts updated.$"),
                re.compile("^Original contents retained as .*known_hosts.old$"),
                re.compile("^sync log files from host.*"),
                re.compile("^completed host.*"),
                re.compile("Sync log files elapsed time.*"),
                re.compile("new lines processed"),
                re.compile("^\[.*\]$"),
                re.compile("^\{.*\}"),
                re.compile("^$"),
                re.compile("^Total stats processing elapsed time.*"),
                re.compile("^processing psiphonv.log.*"),
                re.compile("^process stats from.*"),
        ]

        xenos = list()

        processed_count = 0
        synced_hosts_total = 0
        synced_hosts_success = 0
        synced_hosts_failed = 0
        synced_hosts_elapsed_time = 0
        failed_hosts = list()

        ###########################################################

        for line in data:
            if sync_log_line in line:
                synced_hosts_total +=1
            
            if sync_log_success in line:
                synced_hosts_success +=1
            elif sync_log_fail in line:
                synced_hosts_failed +=1
                failed_hosts.append(line)
            elif sync_summary_line in line:
                synced_hosts_elapsed_time = line.strip()
            elif processed_string in line: # split line, count records
                try:
                    processed_count += int(line.split(' ', 1)[0])
                except ValueError:
                    continue
            
            found = False
            for s in common_strings:
                match = s.search(line)
                if match:
                    found = True
                    continue
            
            if not found:
                xenos.append(line)
            
        # The 2nd last line should contain the times for each host
        host_sync_times = eval(data[-2].strip())
        if type(host_sync_times) == dict:
            sorted_hosts_sync_times = sorted(host_sync_times.items(), key=lambda x: x[1], reverse=True)

        results = (data[0].strip(), synced_hosts_total, synced_hosts_success, synced_hosts_failed, synced_hosts_elapsed_time, processed_count, sorted_hosts_sync_times, xenos)
        return results
    
    except Exception as e:
        raise e

def send_mail(record, subject='Psiphon Process Stats Email', 
              template_filename=MAKO_TEMPLATE):
    
    if not os.path.isfile(template_filename):
        raise

    template_lookup = TemplateLookup(directories=[os.path.dirname(os.path.abspath('__file__'))])
    template = Template(filename=template_filename, default_filters=['decode.utf8', 'unicode', 'h'], lookup=template_lookup)

    try:
        rendered = template.render(data=record)
    except:
        raise Exception(exceptions.text_error_template().render())

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    sender.send(config['emailRecipients'], config['emailUsername'], subject, repr(record), rendered)

'''
start_line_num = stats_processing_sets[0][0]
end_line_num = stats_processing_sets[0][1]
data = stats_processing_sets[0][2]
'''
def main():
    print "Process stats last run"

    node_name = platform.node()
    email_subject = 'Psiphon Process Stats Email - ' + str(node_name)
    
    # stats_processing_sets = (start_run_line, end_run_line, run_contents)
    stats_processing_sets = process_stats_job_log(LOGFILE)
    
    if LAST_RUN_ONLY:
        (stats_process_start_date, synced_hosts_total, synced_hosts_success, 
         synced_hosts_failed, synced_hosts_elapsed_time, processed_count, 
         sorted_hosts_sync_times, xenos,
        ) = process_stats_run(stats_processing_sets[-1][0], stats_processing_sets[-1][1], stats_processing_sets[-1][2])
        
        send_mail((stats_process_start_date, synced_hosts_total, synced_hosts_success, synced_hosts_failed, synced_hosts_elapsed_time, processed_count, sorted_hosts_sync_times, xenos), email_subject)
        
    else:
        for run in stats_processing_sets:
            (stats_process_start_date, synced_hosts_total, synced_hosts_success, synced_hosts_failed, 
             synced_hosts_elapsed_time, processed_count, sorted_hosts_sync_times, xenos,
             ) = process_stats_run(run[0], run[1], run[2])
            
            send_mail((stats_process_start_date, synced_hosts_total, synced_hosts_success, synced_hosts_failed, synced_hosts_elapsed_time, processed_count, sorted_hosts_sync_times, xenos), email_subject)

if __name__ == "__main__":
    main()
