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
  logs = data.get('Logs', [])
  feedback_info = data.get('Feedback', {})
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

  .log-entry {
    margin-bottom: 0.3em;
  }

  .timestamp {
    font-size: 0.8em;
    font-family: monospace;
  }

  .log-entry-message {
    font-weight: bold;
  }

  .log-entry .log-level-debug {
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


<h1>Psiphon 4</h1>

% if feedback_info and feedback_info.get('Message') and feedback_info['Message'].get('text'):
<%
  message = feedback_info['Message']
  msg_text = message['text']

  # Through experimentation, we have found that the maximum number of urlencoded
  # UTF-8 characters that can successfully be put into a Google Translate URL
  # is about 600. So if there are more characters than that, we'll just link
  # to the blank form.
  gtranslate_url = 'https://translate.google.com/#auto/en/'
  urlencoded_msg = utils.urlencode(msg_text)
  if len(urlencoded_msg) < 600:
    gtranslate_url += urlencoded_msg

  lang_code = message.get('text_lang_code')
  translated = message.get('text_translated')

  # There are some special values that text_lang_code might have that indicate
  # a problem during translation.
  no_translation = lang_code in ('[INDETERMINATE]', '[TRANSLATION_FAIL]')

  direction = 'rtl' if lang_code in ('fa', 'ar', 'iw', 'yi') else ''
%>

  <h2>Feedback</h2>

  % if lang_code and not no_translation:
    <div class="english_message">${translated}</div>

    % if msg_text != translated:
      <div class="smaller">
        Auto-translated from ${message['text_lang_name']}.
      </div>
      <br>

      <div class="original_message ${direction}">${msg_text}</div>

      <div class="smaller">
        <a href="${gtranslate_url}">Google Translate.</a>
      </div>
    % endif
  % else:
    ## Either translation failed/was indeterminate, or this feedback predates
    ## translation being enabled. Show the original message directly (readable,
    ## rather than the unicode-escaped YAML dump) with a translate link.
    % if no_translation:
      <div class="smaller">Auto-translate failed: ${message['text_lang_name']}</div>
    % endif

    <div class="original_message ${direction}">${msg_text}</div>

    <div class="smaller">
      <a href="${gtranslate_url}">Google Translate.</a>
    </div>
  % endif
% endif

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
## Logs
##

<%def name="log_row(entry, last_timestamp)">
  <%
    timestamp_diff_secs, timestamp_diff_str = utils.get_timestamp_diff(last_timestamp, entry['timestamp'])

    log_level_class = entry['level'].lower() if entry.get('level') else 'none'
  %>

  ## Put a separator between entries that are separated in time.
  % if timestamp_diff_secs > 10:
    <hr>
  % endif

  <div class="log-entry">
    <span class="timestamp">${utils.timestamp_display(entry['timestamp'])} [+${timestamp_diff_str}s]</span>

    <span class="log-entry-message log-level-${log_level_class}">
      ${entry['category']}
      % if entry.get('level'):
        [${entry['level']}]:
      % endif
      % if entry.get('message'):
        ${entry['message']}
      % endif
      % if entry.get('data'):
        ${repr(entry['data'])}
      % endif
    </span>
  </div>
</%def>

<h2>Logs</h2>
<%
  last_timestamp = None
%>
% for entry in logs:
  ## level may be absent or null
  % if entry.get('level') and entry['level'].lower() in ('trace', 'debug'):
    ## info is the minimum we'll print
    <% continue %>
  % endif

  ${log_row(entry, last_timestamp)}
  <% last_timestamp = entry['timestamp'] %>
% endfor
