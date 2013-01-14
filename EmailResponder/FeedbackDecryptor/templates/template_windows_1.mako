## Copyright (c) 2013, Psiphon Inc.
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

<%!
  import yaml
  from operator import itemgetter
  import utils
%>

<%
  sys_info = data['SystemInformation']
  server_responses = data['ServerResponseCheck']
  status_history = data['StatusHistory']
%>

<style>
  th {
    text-align: right;
    padding-right: 0.3em;
  }

  .status-entry {
    margin-bottom: 0.3em;
  }

  .timestamp {
    font-size: 0.8em;
    font-family: monospace;
  }

  .status-entry-message {
    font-weight: bold;
  }

  .status-entry .debug {
    color: gray;
  }

  hr {
    width: 80%;
    border: 0;
    background-color: lightGray;
    height: 1px;
  }

  /* Make integers easier to visually compare. */
  .intcompare {
    text-align: right;
    font-family: monospace;
  }

  .server-response-checks .separated th,
  .server-response-checks .separated td {
    border-top: dotted thin gray;
  }
  </style>


## Display more human-friendly field names
<%def name="sys_info_key_map(key)">
  <%
  map = {
          'CLIENT_VERSION': 'Client Version',
          'PROPAGATION_CHANNEL_ID': 'Prop. Channel',
          'SPONSOR_ID': 'Sponsor'
        }
  %>
  % if key in map:
    ${map[key]}
  % else:
    ${key}
  % endif
</%def>

<%def name="sys_info_row(key, val)">
  <tr>
    <th>${sys_info_key_map(key)}</th>
    <td>${val}</td>
  </tr>
</%def>


##
## Brief System Info
##

<table>

  ${sys_info_row('OS', sys_info['OSInfo']['name'])}
  ${sys_info_row('User is', ', '.join([k for (k,v) in sys_info['UserInfo'].iteritems() if v]))}
  ${sys_info_row('AV', ', '.join([av['displayName'] for av in sys_info['SecurityInfo']['AntiVirusInfo']]))}
  ${sys_info_row('Uses proxy', 'yes' if [proxy for proxy in sys_info['NetworkInfo']['OriginalProxyInfo'] if proxy['flags'] != 'PROXY_TYPE_DIRECT'] else 'no')}

</table>

<a href="#sys_info">See full System Info</a>


##
## Server Response Checks
##

<%def name="server_response_row(entry, last_timestamp)">
  <%
    # Put a separator between entries that are separated in time.
    timestamp_separated_class = ''
    if last_timestamp and 'timestamp' in entry:
        if (entry['timestamp'] - last_timestamp).total_seconds() > 20:
            timestamp_separated_class = 'separated'

    ping_class = 'good'
    ping_str = '%dms' % entry['responseTime']
    if not entry['responded'] or entry['responseTime'] < 0:
        ping_class = 'bad'
        ping_str = 'none'
    elif entry['responseTime'] > 2000:
        ping_class = 'warn'
  %>
  <tr class="${timestamp_separated_class}">
    <th>${entry['ipAddress']}</th>
    <td class="intcompare ${ping_class}">${ping_str}</td>
    <td class="timestamp">${entry['timestamp'] if 'timestamp' in entry else ''}</td>
  </tr>
</%def>

<h1>Server Response Checks</h1>
<table class="server-response-checks">
  <% last_timestamp = None %>
  % for entry in server_responses:
    ${server_response_row(entry, last_timestamp)}
    <% last_timestamp = entry['timestamp'] if 'timestamp' in entry else None %>
  % endfor
</table>

##
## Status History and Diagnostic History
##

<%def name="status_history_row(entry, last_timestamp)">
  <%
    timestamp_diff_secs, timestamp_diff_str = utils.get_timestamp_diff(last_timestamp, entry['timestamp'])

    debug_class = 'debug' if entry['debug'] else ''
  %>

  ## Put a separator between entries that are separated in time.
  % if timestamp_diff_secs > 10:
    <hr>
  % endif

  <div class="status-entry">
    <div class="status-first-line">
      <span class="timestamp">${utils.timestamp_display(entry['timestamp'])} [+${timestamp_diff_str}s]</span>

      <span class="status-entry-message ${debug_class}">${entry['message']}</span>
    </div>
  </div>
</%def>

<h1>Status History</h1>
<%
  last_timestamp = None
%>
% for entry in status_history:
  ${status_history_row(entry, last_timestamp)}
  <% last_timestamp = entry['timestamp'] %>
% endfor


##
## System Info
##

<a name="sys_info"></a>
<h1>System Info</h1>

## OS Info

<h2>OS Info</h2>
<table>
  % for k, v in sorted(sys_info['OSInfo'].items()):
    ${sys_info_row(k, v)}
  % endfor
</table>

## Network Info

<h2>Network Info</h2>
<h3>Original Proxy</h3>
% for connection in sys_info['NetworkInfo']['OriginalProxyInfo']:
  <table>
    % for k, v in sorted(connection.items()):
      <% if k == 'connectionName' and not v: v = '[default]' %>
      ${sys_info_row(k, v)}
    % endfor
  </table>
% endfor
<h3>Current Connection Info</h3>
<table>
  % for k, v in sorted(sys_info['NetworkInfo'].items()):
    <% if k == 'OriginalProxyInfo': continue %>
    ${sys_info_row(k, v)}
  % endfor
</table>

## Security Info

<h2>Security Info</h2>
<h3>Anti-Virus</h3>
% for item in sys_info['SecurityInfo']['AntiVirusInfo']:
  <table>
    ${sys_info_row('', item['displayName'])}
    % for k, v in sorted(item[item['version']].items()):
      ${sys_info_row(k, v)}
    % endfor
  </table>
% endfor

## The anti-spyware info seems to often be identical to the anti-virus info,
## in which case we won't output it.
% if sys_info['SecurityInfo']['AntiSpywareInfo'] != sys_info['SecurityInfo']['AntiVirusInfo']:
  <h3>Anti-Spyware</h3>
  % for item in sys_info['SecurityInfo']['AntiSpywareInfo']:
    <table>
      ${sys_info_row('', item['displayName'])}
      % for k, v in sorted(item[item['version']].items()):
        ${sys_info_row(k, v)}
      % endfor
    </table>
  % endfor
% endif

% if sys_info['SecurityInfo']['FirewallInfo']:
  <h3>Firewall</h3>
  % for item in sys_info['SecurityInfo']['FirewallInfo']:
    <table>
      ${sys_info_row('', item['displayName'])}
      % for k, v in sorted(item[item['version']].items()):
        ${sys_info_row(k, v)}
      % endfor
    </table>
  % endfor
% endif

## Psiphon Info

<h2>Psiphon Info</h2>
<table>
  % for k, v in sorted(sys_info['PsiphonInfo'].items()):
    ${sys_info_row(k, v)}
  % endfor
</table>
