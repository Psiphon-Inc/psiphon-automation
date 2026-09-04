## Copyright (c) 2026, Psiphon Inc.
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
  import utils
%>

<%
  ## `Metadata` and `Feedback` are normalized by utils.normalize_lowercase_envelope;
  ## the remaining blocks stay in the lowercase shape the client sent.
  metadata = data['Metadata']
  feedback_info = data.get('Feedback', {})
  system = data.get('system', {})
  app = data.get('app', {})
  logs = data.get('logs', [])
  diagnostics = data.get('diagnostics', {})

  device = system.get('device', {})
  os_info = system.get('os', {})
  tunnel_core = app.get('tunnelCore', {})

  def join_present(obj, keys):
    ## brand and manufacturer often differ only in case, as with Google and
    ## google on Pixel hardware. The first spelling wins, so pass it first.
    parts, seen = [], set()
    for k in keys:
      value = obj.get(k)
      if value in (None, '') or str(value).lower() in seen:
        continue
      seen.add(str(value).lower())
      parts.append(str(value))
    return ' '.join(parts)

  date = metadata.get('date')

  summary = [
    ('Feedback ID', metadata.get('id')),
    ('Date', utils.timestamp_display(date) if hasattr(date, 'year') else date),
    ('Platform', metadata.get('platform')),
    ('App ID', app.get('appId')),
    ('Version', join_present(app, ('version', 'buildNumber'))),
    ('Build mode', app.get('buildMode')),
    ('Internal test', app.get('internalTest')),
    ('Git describe', app.get('gitDescribe')),
    ('Sponsor', app.get('sponsorId')),
    ('Propagation channel', app.get('propagationChannelId')),
    ('App locale', app.get('locale')),
    ('Device locale', system.get('locale')),
    ('Device', join_present(device, ('manufacturer', 'brand', 'model'))),
    ('OS', join_present(os_info, ('name', 'version', 'sdkInt'))),
    ('Network', system.get('networkType')),
  ]

  ## Root and jailbreak detection are deliberately not one shared key: they are
  ## different mechanisms. Only one of them is ever present.
  if 'rootDetected' in system:
    summary.append(('Root detected', system['rootDetected']))
  elif 'jailbreakDetected' in system:
    summary.append(('Jailbreak detected', system['jailbreakDetected']))
%>

<style>
  th {
    text-align: right;
    padding-right: 0.3em;
    vertical-align: top;
  }

  td {
    vertical-align: top;
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

  .log-entry-data {
    font-family: monospace;
    font-weight: normal;
  }

  hr {
    width: 80%;
    border: 0;
    background-color: lightGray;
    height: 1px;
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
    % if no_translation:
      <div class="smaller">Auto-translate failed: ${message['text_lang_name']}</div>
    % endif

    <div class="original_message ${direction}">${msg_text}</div>

    <div class="smaller">
      <a href="${gtranslate_url}">Google Translate.</a>
    </div>
  % endif
% endif

% if feedback_info.get('email'):
  <p>Reply address: ${feedback_info['email']}</p>
% endif

<h2>Summary</h2>
<table>
  % for label, value in summary:
    % if value is not None and value != '':
      <tr><th>${label}</th><td>${value}</td></tr>
    % endif
  % endfor
</table>

##
## The schema leaves these blocks opaque, because that is where the platforms
## diverge or a third party owns the contents. Dump them rather than modelling
## their keys.
##

% if device or os_info:
  <h2>System</h2>
  <pre>
${yaml.dump(system, default_flow_style=False, allow_unicode=True)}
  </pre>
% endif

% if tunnel_core:
  <h2>Tunnel Core</h2>
  <pre>
${yaml.dump(tunnel_core, default_flow_style=False, allow_unicode=True)}
  </pre>
% endif

% if diagnostics:
  <h2>Diagnostics</h2>
  <pre>
${yaml.dump(diagnostics, default_flow_style=False, allow_unicode=True)}
  </pre>
% endif

% if metadata:
  <h2>Metadata</h2>
  <pre>
${yaml.dump(metadata, default_flow_style=False, allow_unicode=True)}
  </pre>
% endif

##
## Logs
##

<%def name="log_row(entry, last_timestamp)">
  <%
    ## A tunnel-core line carries no level or message; its payload is a notice
    ## nested under data. Every other line has a level, a message, and a tag.
    category = entry.get('category', '')
    entry_data = entry.get('data') or {}

    if category == 'tunnel-core':
      headline = entry_data.get('noticeType') or '(no noticeType)'
      payload = entry_data.get('data') or {}
    else:
      headline = entry.get('message', '')
      payload = entry_data

    level = entry.get('level')
    log_level_class = level.lower() if level else 'none'

    ## A timestamp that failed to parse keeps its `!!timestamp` key and stays a
    ## string, so there may be no datetime to diff against.
    timestamp = entry.get('timestamp')
    if hasattr(timestamp, 'year'):
      timestamp_diff_secs, timestamp_diff_str = utils.get_timestamp_diff(last_timestamp, timestamp)
      timestamp_display = '%s [+%ss]' % (utils.timestamp_display(timestamp), timestamp_diff_str)
    else:
      timestamp_diff_secs = 0
      timestamp_display = str(entry.get('timestamp!!timestamp') or '(no timestamp)')
  %>

  ## Put a separator between entries that are separated in time.
  % if timestamp_diff_secs > 10:
    <hr>
  % endif

  <div class="log-entry">
    <span class="timestamp">${timestamp_display}</span>

    <span class="log-entry-message log-level-${log_level_class}">
      ${category}
      % if level:
        [${level}]:
      % endif
      ${headline}
      % if payload:
        <span class="log-entry-data">${repr(payload)}</span>
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
  <%
    if hasattr(entry.get('timestamp'), 'year'):
      last_timestamp = entry['timestamp']
  %>
% endfor
