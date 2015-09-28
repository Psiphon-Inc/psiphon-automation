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
<style>
    table {
        padding: 0;
        border: 1px solid black;
        width: 100%
    }
    
    table tr {
        border: 0;
        border-top: 1px solid #CCC;
        background-color: white;
        margin: 0;
        /*padding: 0; */
    }
    
    table, tbody tr, td{
        border: 1px solid black;
        padding-left: 5px;
        vertical-align: top;
        padding-top: 5px;
    }
    
    table#stdoutTable td.message {
        font-size: smaller;
    }
    
</style>

<h1>Psiphon 3 Ansible Stats</h1>
<%

start_time, end_time, playbook_file, hosts_processed, hosts_dark, hosts_failed, hosts_changed, hosts_skipped, hosts_summary, hosts_output, hosts_errs, hosts_info = data

import datetime
import operator

elapsed_time = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f")

count_processed = len(hosts_processed)
count_unreachable = len(hosts_dark)
count_failed = len(hosts_failed)
count_changed = len(hosts_changed)
count_skipped = len(hosts_skipped)

if hosts_output is None:
    hosts_output = []
endif

%>

<h2>Playbook: ${playbook_file}</h2>

<p>
	Start Time: ${start_time}<br>
	End Time: ${end_time}<br>
	Elapsed: ${elapsed_time}<br>
</p>

<h3>Host Stats</h3>
<ul>
	<li>Unreachable: ${count_unreachable}</li>
	<li>Processed: ${count_processed} </li>
	<li>Failed: ${count_failed}</li>
	<li>Changed: ${count_changed}</li>
	<li>Skipped: ${count_skipped}</li>
</ul>

<hr>
 

<h3>Unreachable Hosts: ${count_unreachable}</h3>
% if count_unreachable > 0:
	<tbody>
	% for c in hosts_dark:
		<tr>${c}</tr>
	% endfor
	</tbody>
% endif
<hr>

<h3>Host STDERR: ${len(hosts_errs)}</h3>
% if len(hosts_errs) > 0:
    <table>
	<thead>
    <tr>
        <th width="20%">Host</th>
        <th width="33%">Message</th>
        <th width="15%">OS Release</th>
    </tr>
    </thead>
    <tbody>
	% for c in hosts_errs:
		<tr>
            <td>${c}</td>
            % if 'response' in hosts_errs[c]:
                <td>
                    % for line in hosts_errs[c]['response0']['stderr'].split('\n'):
                        ${line}<br>
                    % endfor
                </td>
            % endif
            <td>${hosts_info[c]['ansible_lsb']['codename']}</td>
        </tr>
	% endfor
	</tbody>
    </table>
% endif
<hr>

% if len(hosts_output) > 0:
<h3>Host STDOUT_LINES: ${len(hosts_output)}</h3>
    <table id="stdoutTable">
	<thead>
    <tr>
        <th width="20%">Host</th>
        <th>Message</th>
        <th width="15%">OS Release</th>
    </tr>
    </thead>
    <tbody>
	% for c in hosts_output:
		<tr>
            <td class="default">${c}</td>
            <td class="message">
                % for details in hosts_output[c]:
                    <p>
                    Module: ${details['module_name']} : ${details['module_details']}<br>
                    Result:<br>
                    % for line in details['stdout_lines']:
                        <%
                            link = ''
                            if 'apt-get' in details['module_details']:
                                if '=>' in line and ',' in line:
                                    line, link = line.split(',', 1)
                                
                                if len(link) > 0:
                                    link = "<a href=" + link.strip() + ">link</a>"
                        %>
                        ${line} ${link | n}<br>
                    % endfor
                    <hr></p>
                % endfor
            </td>
            <td>${hosts_info[c]['ansible_lsb']['codename']}</td>
        </tr>
	% endfor
	</tbody>
    </table>
% endif

<hr width=100%>

<h3>Changed Hosts: ${count_changed}</h3>
% if count_changed > 0:
<p>${hosts_changed}</p>
% endif
<hr>

<h3>Failed Hosts: ${count_failed}</h3>
% if count_failed> 0:
<p>${hosts_failed}</p>
% endif
<hr>


<h3>Processed Hosts: ${count_processed}</h3>
% if count_processed > 0:
<p>${hosts_processed}</p>
% endif
<hr>


