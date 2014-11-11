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

<%!
  import yaml
  from operator import itemgetter
  import utils
%>

<%
  metadata = data['Metadata']
  diagnostic_info = utils.coalesce(data, ('DiagnosticInfo',))

  sys_info = utils.coalesce(data, ('DiagnosticInfo', 'SystemInformation'))
  status_history = utils.coalesce(data, ('DiagnosticInfo', 'StatusHistory'))
  diagnostic_history = utils.coalesce(data, ('DiagnosticInfo', 'DiagnosticHistory'))

  feedback = data.get('Feedback')
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

  .status-entry, .diagnostic-entry {
    margin-bottom: 0.3em;
  }

  .status-latter-line {
    margin-left: 2em;
  }

  .timestamp {
    font-size: 0.8em;
    font-family: monospace;
  }

  .status-entry-id, .diagnostic-entry-msg {
    font-weight: bold;
  }

  .priority-info {
    color: green;
  }

  .priority-error {
    color: red;
  }

  .diagnostic-entry-msg {
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


<h1>Android</h1>

##
## Survey and feedback message, original and translation
##

% if feedback and feedback.get('Message') and feedback['Message'].get('text'):
<%
  # Through experimentation, we have found that the maximum number of urlencoded
  # UTF-8 characters that can successfully be put into a Google Translate URL
  # is about 600. So if there are more characters than that, we'll just link
  # to the blank form.
  gtranslate_url = 'https://translate.google.com/#auto/en/'
  urlencoded_msg = utils.urlencode(feedback['Message']['text'].encode('utf8'))
  if len(urlencoded_msg) < 600:
    gtranslate_url += urlencoded_msg

  # There are some special values that text_lang_code might have that indicate
  # a problem during translation.
  no_translation = feedback['Message']['text_lang_code'] in ('[INDETERMINATE]', '[TRANSLATION_FAIL]')
%>

  <h2>Feedback</h2>

  % if no_translation:
    <div>
      Auto-translate failed: ${feedback['Message']['text_lang_name']}
    </div>
  % else:
    <div class="english_message">
      ${feedback['Message']['text_translated']}
    </div>
  % endif

  % if feedback['Message']['text'] != feedback['Message']['text_translated']:
    % if not no_translation:
      <div class="smaller">
        Auto-translated from ${feedback['Message']['text_lang_name']}.
      </div>
      <br>
    % endif

    <% direction = 'rtl' if feedback['Message']['text_lang_code'] in ['fa', 'ar', 'iw', 'yi'] else '' %>
    <div class="original_message ${direction}">${feedback['Message']['text']}</div>

    <div class="smaller">
      <a href="${gtranslate_url}">Google Translate.</a>
    </div>

    <br>
  % endif

  <div>
    User email: ${feedback['email'] if feedback['email'] else '(not supplied)'}
  </div>
% endif

% if feedback and feedback.get('Survey') and feedback['Survey'].get('results'):
  <h2>Survey</h2>
  <table>
    % for result in feedback['Survey']['results']:
      ${sys_info_row_emoticon(result['title'], result['answer']==0)}
    % endfor
  </table>
% endif


##
## System Info
##

## Start of diagnostic info
% if diagnostic_info:

<h2>System Info</h2>

## Display more human-friendly field names
<%def name="sys_info_key_map(key)">
  <%
  map = {
          'BRAND': 'Brand',
          'CPU_ABI': 'CPU ABI',
          'MANUFACTURER': 'Manufacturer',
          'MODEL': 'Model',
          'DISPLAY': 'Build Number',
          'TAGS': 'Tags',
          'VERSION__CODENAME': 'Ver. Codename',
          'VERSION__RELEASE': 'OS Version',
          'VERSION__SDK_INT': 'SDK Version',
          'isRooted': 'Rooted',
          'isPlayStoreBuild': 'Play Store Build',
          'networkTypeName': 'Network Type',
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
<%def name="sys_info_row_emoticon(key, is_happy)">
  <tr>
    <th>${sys_info_key_map(key)}</th>
    <td class="emoticon">
      % if is_happy:
        &#9786;
      % else:
        &#9785;
      % endif
    </td>
  </tr>
</%def>


<h3>Build Info</h3>
<table>
  % for k, v in sorted(sys_info['Build'].iteritems()):
    ${sys_info_row(k, v)}
  % endfor
  ${sys_info_row('isRooted', sys_info['isRooted'])}
  ${sys_info_row('isPlayStoreBuild', sys_info['isPlayStoreBuild'])}
  ${sys_info_row('networkTypeName', sys_info.get('networkTypeName', 'None'))}
</table>

<h3>Psiphon Info</h3>
<table>
  % for k, v in sorted(sys_info['PsiphonInfo'].iteritems()):
    ${sys_info_row(k, v)}
  % endfor
</table>


##
## Status History and Diagnostic History
##

<%def name="status_history_row(entry, last_timestamp)">
  <%
    timestamp_diff_secs, timestamp_diff_str = utils.get_timestamp_diff(last_timestamp, entry['timestamp'])

    # These values come from the Java definitions for Log.VERBOSE, etc.
    PRIORITY_CLASSES = {
        2: 'priority-verbose',
        3: 'priority-debug',
        4: 'priority-info',
        5: 'priority-warn',
        6: 'priority-error',
        7: 'priority-assert' }
    priority_class = ''
    if 'priority' in entry and entry['priority'] in PRIORITY_CLASSES:
        priority_class = PRIORITY_CLASSES[entry['priority']]
  %>

  ## Put a separator between entries that are separated in time.
  % if timestamp_diff_secs > 10:
    <hr>
  % endif

  <div class="status-entry">
    <div class="status-first-line">
      <span class="timestamp">${utils.timestamp_display(entry['timestamp'])} [+${timestamp_diff_str}s]</span>

      <span class="status-entry-id ${priority_class}">${entry['id']}</span>

      <span class="format-args">
        % if entry['formatArgs'] and len(entry['formatArgs']) == 1:
          ${entry['formatArgs'][0]}
        % elif entry['formatArgs'] and len(entry['formatArgs']) > 1:
          ${repr(entry['formatArgs'])}
        %endif
        </span>
    </div>

    % if entry.get('throwable'):
      <div class="status-latter-line">
        <pre>${yaml.dump(entry['throwable'], default_flow_style=False)}</pre>
      </div>
    %endif
  </div>
</%def>

<%def name="diagnostic_history_row(entry, last_timestamp)">
  <%
    timestamp_diff_secs, timestamp_diff_str = utils.get_timestamp_diff(last_timestamp, entry['timestamp'])
  %>

  ## Put a separator between entries that are separated in time.
  % if timestamp_diff_secs > 10:
    <hr>
  % endif

  <div class="diagnostic-entry">
    <span class="timestamp">${utils.timestamp_display(entry['timestamp'])} [+${timestamp_diff_str}s]</span>

    <span class="diagnostic-entry-msg">${entry['msg']}</span>

    ## We special-case some of the common diagnostic entries
    % if entry['msg'] == 'ServerResponseCheck':
      <%
        ping_class = 'good'
        ping_value = int(entry['data']['responseTime'])
        ping_str = '%dms' % ping_value
        if not entry['data']['responded'] or ping_value < 0:
          ping_class = 'bad'
          ping_str = 'none'
        elif ping_value > 2000:
          ping_class = 'warn'

        ping_regionCode = utils.coalesce(entry, ('data', 'regionCode'), '')

        remaining_data = entry['data']
        remaining_data.pop('responseTime', None)
        remaining_data.pop('responded', None)
        remaining_data.pop('regionCode', None)
      %>
      <span>${ping_regionCode}</span>
      <span class="intcompare ${ping_class}">${ping_str}</span>
      <span>${repr(remaining_data)}</span>
    % else:
      <span>${repr(entry['data'])}</span>
    % endif
  </div>
</%def>

<h2>Status History</h2>
<%
  last_timestamp = None

  # We want the diagnostic entries to appear inline chronologically with the
  # status entries, so we'll merge the lists and process them together.
  status_diagnostic_history = status_history
  if diagnostic_history:
      status_diagnostic_history += diagnostic_history
  status_diagnostic_history = sorted(status_diagnostic_history,
                                     key=itemgetter('timestamp'))
%>
% for entry in status_diagnostic_history:
  % if 'formatArgs' in entry:
    ${status_history_row(entry, last_timestamp)}
  % else:
    ${diagnostic_history_row(entry, last_timestamp)}
  % endif
  <% last_timestamp = entry['timestamp'] %>
% endfor

## end of diagnostic info
% endif
