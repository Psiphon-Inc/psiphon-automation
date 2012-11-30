# Copyright (c) 2012, Psiphon Inc.
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


from mako.template import Template
from mako import exceptions
import pynliner


def format(data):
    '''
    Will throw exception is data does not match expected structure (that is,
    if the template rendering fails).
    '''

    assert(len(data) >= 3)

    try:
        rendered = Template(_template).render(data=data)
    except:
        raise Exception(exceptions.text_error_template().render())

    # Styles in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    return rendered


_template = \
'''
<%!
import yaml
%>

<%
    idx = 0

    sys_info = data[idx]
    idx += 1

    server_responses = data[idx]
    idx += 1

    # The diagnostic history only exists in the data array if there is any.
    diagnostic_history = None
    if len(data) > 3:
        diagnostic_history = data[idx]
        idx += 1

    status_history = data[idx]
    idx += 1
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

    .status-entry {
        margin-bottom: 0.3em;
    }

    .status-latter-line {
        margin-left: 2em;
    }

    .status-entry .timestamp {
        font-size: 0.8em;
    }

    hr {
        width: 80%;
        border: 0;
        background-color: lightGrey;
        height: 1px;
    }

    /* Make integers easier to visually compare. */
    .intcompare {
        text-align: right;
        font-family: monospace;
    }
</style>

<h1>System Info</h1>

## Display more human-friendly field names
<%def name="sys_info_key_map(key)">
    <%
    map = {
            'BRAND': 'Brand',
            'CPU_ABI': 'CPU ABI',
            'MANUFACTURER': 'Manufacturer',
            'MODEL': 'Model',
            'TAGS': 'Tags',
            'VERSION.CODENAME': 'Ver. Codename',
            'VERSION.RELEASE': 'OS Version',
            'VERSION.SDK_INT': 'SDK Version',
            'isRooted': 'Rooted',
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

<h2>Build Info</h2>
<table>
    % for k, v in sorted(sys_info['Build'].iteritems()):
        ${sys_info_row(k, v)}
    % endfor
    ${sys_info_row('isRooted', sys_info['isRooted'])}
</table>

<h2>Psiphon Info</h2>
<table>
    % for k, v in sorted(sys_info['psiphonEmbeddedValues'].iteritems()):
        ${sys_info_row(k, v)}
    % endfor
</table>

<%def name="server_response_row(name, ping)">
    <%
    ping_class = 'good'
    ping_str = '%dms' % ping
    if ping < 0:
        ping_class = 'bad'
        ping_str = 'none'
    elif ping > 2000:
        ping_class = 'warn'
    %>
    <tr>
        <th>${name}</th>
        <td class="intcompare ${ping_class}">${ping_str}</td>
    </tr>
</%def>

<h1>Server Response Checks</h1>
<table>
    % for resp in server_responses:
        ${server_response_row(resp['ipAddress'], resp['responseTime'])}
    % endfor
</table>

% if diagnostic_history:
<h1>Diagnostic History</h1>
<table>
    % for entry in diagnostic_history:
        <tr><td>${entry}</td></tr>
    % endfor
</table>
% endif

<%def name="status_history_row(entry, last_timestamp)">
    ## Put a separator between entries that are separated in time.
    % if last_timestamp and (entry['timestamp'] - last_timestamp).seconds > 30:
    <hr>
    % endif

    <div class="status-entry">
        <div class="status-first-line">
            <b>${entry['id']}:</b>
            <span class="timestamp">${entry['timestamp']}Z</span>

            <span class="format-args">
                % if entry['formatArgs'] and len(entry['formatArgs']) == 1:
                    ${entry['formatArgs'][0]}
                % elif entry['formatArgs'] and len(entry['formatArgs']) > 1:
                    ${repr(entry['formatArgs'])}
                %endif
            </span>
        </div>

        % if entry['throwable']:
            <div class="status-latter-line">
                <pre>${yaml.dump(entry['throwable'], default_flow_style=False)}</pre>
            </div>
        %endif
    </div>
</%def>

<h1>Status History</h1>
<% last_timestamp = None %>
% for entry in status_history:
    ${status_history_row(entry, last_timestamp)}
    <% last_timestamp = entry['timestamp'] %>
% endfor
'''
