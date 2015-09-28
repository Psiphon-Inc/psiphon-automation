## Copyright (c) 2015, Psiphon Inc.
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

</style>

<h1>Psiphon 3 Stats Processing</h1>

<%
stats_process_start_date, synced_hosts_total, synced_hosts_success, synced_hosts_failed, synced_hosts_elapsed_time, processed_count, sorted_hosts_sync_times, xenos = data
%>

<h3>${stats_process_start_date}</h3>
<h3>Total Records Added: ${processed_count}</h3>
<hr />
<h3>Hosts Sync Summary</h3>
<p>
    ${synced_hosts_elapsed_time}<br>
    Hosts Successful: ${synced_hosts_success}<br>
    Hosts Failed: ${synced_hosts_failed}<br>
    Hosts Total: ${synced_hosts_total}<br>
</p>
<hr />
<h3>Hosts Processing Summary</h3>
<tbody>
    <tr>
        <th>Host</th>
        <th>Processing Time</th>
    </tr>
% for host, process_time in sorted_hosts_sync_times:
    <tr>
        <td>${host}</td>
        <td>${process_time}</td>
    </tr>
% endfor
</tbody>

<hr />
<h3>Stats Processing Errors: ${len(xenos)}</h3>
% if len(xenos) > 0:
    % for x in xenos:
        ${x}<br />
    % endfor
% endif
