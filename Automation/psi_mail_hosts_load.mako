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

  /* Make numbers easier to visually compare. */
  .numcompare {
    text-align: right;
    font-family: monospace;
  }

  /* Some fields are easier to compare left-aligned. */
  .numcompare-left {
    text-align: left;
    font-family: monospace;
  }

  table {
    padding: 0;
    border-collapse: collapse;
    border-spacing: 0;
    font-size: 1em;
    font: inherit;
    border: 0;
  }

  tbody {
    margin: 0;
    padding: 0;
    border: 0;
    font-size: 0.8em;
  }

  table tr {
    border: 0;
    border-top: 1px solid #CCC;
    background-color: white;
    margin: 0;
    padding: 0;
  }

  table tr.row-even {
  }

  table tr.row-odd {
    background-color: #F8F8F8;
  }

  table tr th, table tr td {
    font-size: 1em;
    border: 1px solid #CCC;
    margin: 0;
    padding: 0.5em 1em;
  }

  table tr th {
   font-weight: bold;
    background-color: #F0F0F0;
  }
  
  tr .unreachable {
    color: red;
  }
  
  tr .reachable {
    color: black;
  }
</style>

<h1>Psiphon 3 Host Load</h1>
<%
    start_time, end_time, record = data
    import datetime
    import operator
    elapsed_time = datetime.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S.%f")
    total_users, unreachable_hosts, hosts = record
%>

<h3>Total Users Connected: ${total_users}</h3>
<h3>Unreachable Host Count: ${unreachable_hosts}</h3>
<table>
  <thead>
  <tr><th>Host</th><th>Users</th><th>Load</th><th>Free Mem</th><th>Free Swap</th></tr>
  </thead>
  <tbody>
    % for row_index, row in enumerate(hosts):
      <tr class="row-${'odd' if row_index%2 else 'even'}">
        <%
          host, (users, load, free_mem, free_swap) = row
          if users == -1 and load == -1 and free_mem == -1 and free_swap ==-1:
            status='unreachable'
          else:
            status='reachable'
        %>
        <td class=${status}>${host}</td>
        <td>
          ${float(users)}</td><td>${float(load)}</td><td>${float(free_mem)}</td><td>${float(free_swap)}
        </td>
      </tr>
    % endfor
  </tbody>
</table>

<h4>Start Time: ${start_time}</h4>
<h4>End Time: ${end_time}</h4>
<h4>Elapsed: ${elapsed_time}</h4>
