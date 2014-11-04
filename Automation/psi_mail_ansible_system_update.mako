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

<h1>Psiphon 3 Ansible Stats</h1>
<%

start_time, end_time, playbook_file, hosts_processed, hosts_dark, hosts_failed, hosts_changed, hosts_skipped, hosts_summary, hosts_output, hosts_errs, hosts_info = data

import datetime
import operator

elapsed_time = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f")

%>

<h2>Playbook: ${playbook_file}</h2>

<p>
	Start Time: ${start_time}<br>
	End Time: ${end_time}<br>
	Elapsed: ${elapsed_time}<br>
</p>

<h3>Host Stats</h3>
<ul>
	<li>Unreachable: ${len(hosts_dark)}</li>
	<li>Processed: ${len(hosts_processed)} </li>
	<li>Failed: ${len(hosts_failed)}</li>
	<li>Changed: ${len(hosts_changed)}</li>
	<li>Skipped: ${len(hosts_skipped)}</li>
</ul>

<hr>

% if len(hosts_dark) > 0:
    <h3>Unreachable Hosts: ${len(hosts_dark)}</h3>
	<tbody>
	% for host in hosts_dark:
		<tr>
            % for d in [3]:
                <td>
                    ${host}
                </td>
            % endfor
        </tr>
	% endfor
	</tbody>
    <hr>
% endif

% if len(hosts_failed) > 0:
    <h3>Failed Hosts: ${len(hosts_failed)}</h3>
	<tbody>
	% for host in hosts_failed:
		<tr>
            % for d in [3]:
                <td>
                    ${host}
                </td>
            % endfor
        </tr>
	% endfor
	</tbody>
    <hr>
% endif

% if len(hosts_skipped) > 0:
    <h3>Skipped Hosts: ${len(hosts_skipped)}</h3>
	<tbody>
	% for host in hosts_skipped:
		<tr>
            % for d in [3]:
                <td>
                    ${host}
                </td>
            % endfor
        </tr>
	% endfor
	</tbody>
    <hr>
% endif

% if len(hosts_changed) > 0:
    <h3>Changed Hosts: ${len(hosts_changed)}</h3>
	<tbody>
	% for host in hosts_changed:
		<tr>
            % for d in [3]:
                <td>
                    ${host}
                </td>
            % endfor
        </tr>
	% endfor
	</tbody>
    <hr>
% endif

% if len(hosts_processed) > 0:
    <h3>Processed Hosts: ${len(hosts_processed)}</h3>
	<tbody>
	% for host in hosts_processed:
		<tr>
            % for d in [3]:
                <td>
                    ${host}
                </td>
            % endfor
        </tr>
	% endfor
	</tbody>
    <hr>
% endif


% if len(hosts_errs) > 0:
    <h3>Host STDERR: ${len(hosts_errs)}</h3>
	<tbody>
    <tr>
        <th width="33%">Host</th>
        <th width="33%">Message</th>
        <th width="33%">OS Release</th>
    </tr>
	% for c in hosts_errs:
		<tr>
            <td>${c}</td>
            <td>${hosts_errs[c]['cmd_result']['stderr']}</td>
            <td>${hosts_info[c]['ansible_lsb']['codename']}</td>
        </tr>
	% endfor
	</tbody>
    <hr>
% endif


% if len(hosts_output) > 0:
    <h3>Host STDOUT: ${len(hosts_output)}</h3>
	<tbody>
    <tr>
        <th width="33%">Host</th>
        <th width="33%">Message</th>
        <th width="33%">OS Release</th>
    </tr>
	% for c in hosts_output:
		<tr>
            <td>${c}</td>
            <td>${hosts_output[c]['cmd_result']['stdout']}</td>
            <td>${hosts_info[c]['ansible_lsb']['codename']}</td>
        </tr>
	% endfor
	</tbody>
% endif

<hr width=100%>


