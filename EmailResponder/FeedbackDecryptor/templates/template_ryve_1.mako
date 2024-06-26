## Copyright (c) 2024, Psiphon Inc.
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
  metadata = data['Metadata']
  sys_info = data.get('SystemInformation', {})
  app_info = data.get('ApplicationInfo', {})
  psiphon_info = data.get('PsiphonInfo', {})
  app_logs = data.get('AppLogs', [])
  tunnel_core_logs = data.get('TunnelCoreLogs', [])
%>

<style>
  th {
    text-align: right;
    padding-right: 0.3em;
  }

  .good {
    color: green;
  }

  .warn {
    color: orange;
  }

  .bad {
    color: red;
  }

  .app-log-entry, .tunnel-core-log-entry {
    margin-bottom: 0.3em;
  }

  .timestamp {
    font-size: 0.8em;
    font-family: monospace;
  }

  .app-log-entry-message, .tunnel-core-log-entry-msg {
    font-weight: bold;
  }

  .app-log-entry .debug {
    color: gray;
  }

  .tunnel-core-log-entry-msg {
    color: purple;
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

  .english_message {
    margin: 1em 0px;
    border-left-width: 4px;
    border-left-style: solid;
    border-left-color: rgb(221, 221, 221);
    padding: 0px 1em;
    /* This renders newlines as newlines */
    white-space: pre-wrap;
  }

  .original_message {
    margin: 1em 0px;
    border-left-width: 4px;
    border-left-style: solid;
    border-left-color: rgb(221, 221, 221);
    padding: 0px 1em;
    /* This renders newlines as newlines */
    white-space: pre-wrap;
  }

  .smaller {
    font-size: 0.8em;
  }

  .rtl {
    direction: rtl;
  }

  .emoticon {
    font-size: 3em;
  }
</style>


<h1>Ryve</h1>

% if metadata:
  <h2>Metadata</h2>
  <pre>
${yaml.dump(metadata)}
  </pre>
% endif

% if app_info:
  <h2>Application Info</h2>
  <pre>
${yaml.dump(app_info)}
  </pre>
% endif

% if sys_info:
  <h2>System Information</h2>
  <pre>
${yaml.dump(sys_info)}
  </pre>
% endif

% if psiphon_info:
  <h2>Psiphon Information</h2>
  <pre>
${yaml.dump(psiphon_info)}
  </pre>
% endif

##
## Tunnel Core Logs and App Logs
##

<%def name="app_log_row(entry, last_timestamp)">
  <%
    timestamp_diff_secs, timestamp_diff_str = utils.get_timestamp_diff(last_timestamp, entry['timestamp'])

    log_level_class = entry['level'].lower()
  %>

  ## Put a separator between entries that are separated in time.
  % if timestamp_diff_secs > 10:
    <hr>
  % endif

  <div class="app-log-entry">
    <span class="timestamp">${utils.timestamp_display(entry['timestamp'])} [+${timestamp_diff_str}s]</span>

    <span class="app-log-entry-message ${log_level_class}">
      [${entry['level']}]:
      ${entry['message']}
      ${repr(entry['data']) if entry.get('data') else ''}
    </span>
  </div>
</%def>

<%def name="tunnel_core_log_row(entry, last_timestamp)">
  <%
    timestamp_diff_secs, timestamp_diff_str = utils.get_timestamp_diff(last_timestamp, entry['timestamp'])
  %>

  ## Put a separator between entries that are separated in time.
  % if timestamp_diff_secs > 10:
    <hr>
  % endif

  <div class="tunnel-core-log-entry">
    <span class="timestamp">${utils.timestamp_display(entry['timestamp'])} [+${timestamp_diff_str}s]</span>

    <span class="tunnel-core-log-entry-msg">${entry['noticeType']}</span>

    <span>${repr(entry['data'])}</span>
  </div>
</%def>

<h2>Logs</h2>
<%
  last_timestamp = None

  # We want the app logs to appear inline chronologically with the
  # tunnel core logs, so we'll merge the lists and process them together.
  all_logs = sorted(app_logs + tunnel_core_logs,
                    key=itemgetter('timestamp'))
%>
% for entry in all_logs:
  ## The presence of a 'level' field indicates a status entry
  % if 'level' in entry:
    ## We're not printing out debug entries.
    % if entry['level'].lower() != 'debug':
      ${app_log_row(entry, last_timestamp)}
      <% last_timestamp = entry['timestamp'] %>
    % endif
  % else:
    ${tunnel_core_log_row(entry, last_timestamp)}
    <% last_timestamp = entry['timestamp'] %>
  % endif
% endfor
