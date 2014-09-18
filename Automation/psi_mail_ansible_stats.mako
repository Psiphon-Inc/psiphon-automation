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
start_time, end_time, playbook_file, hosts_processed, hosts_dark, hosts_failed, hosts_changed, hosts_skipped, hosts_summary = data

import datetime
import operator

elapsed_time = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f")

count_processed = len(hosts_processed)
count_unreachable = len(hosts_dark)
count_failed = len(hosts_failed)
count_changed = len(hosts_changed)
count_skipped = len(hosts_skipped)

%>

<h2>Playbook: ${playbook_file}</h2>

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
		<tr>${c}, ${hosts_dark[c]}, ${len(hosts_dark)}</tr>
	% endfor
	</tbody>
% endif
<hr>

<h3>Failed Hosts: ${count_failed}</h3>
% if count_failed > 0:
	<tbody>
	% for c in hosts_failed:
		<tr>${c}</tr>
	% endfor
	</tbody>
% endif
<hr>

<h3>Skipped Hosts: ${count_skipped}</h3>
% if count_skipped > 0:
	<tbody>
	% for c in hosts_skipped:
		<tr>${c}</tr>
	% endfor
	</tbody>
% endif
<hr>

<h3>Processed Hosts: ${count_processed}</h3>
% if count_processed > 0:
	<tbody>
	% for c in hosts_processed:
		<tr>${c}</tr>
	% endfor
	</tbody>
% endif
<hr>

<h3>Changed Hosts: ${count_changed}</h3>
% if count_changed > 0:
	<tbody>
	% for c in hosts_changed:
		<tr>${c}</tr>
	% endfor
	</tbody>
% endif
<hr>

<p>
	<sub>
	Start Time: ${start_time}
	End Time: ${end_time}
	Elapsed: ${elapsed_time}
	</sub>
</p>