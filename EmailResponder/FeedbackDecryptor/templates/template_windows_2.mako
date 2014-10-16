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
  diagnostic_info = data.get('DiagnosticInfo')
  sys_info = diagnostic_info.get('SystemInformation') if diagnostic_info else None
  status_history = diagnostic_info.get('StatusHistory') if diagnostic_info else []
  diagnostic_history = diagnostic_info.get('DiagnosticHistory') if diagnostic_info else []
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

  .timestamp {
    font-size: 0.8em;
    font-family: monospace;
  }

  .status-entry-message, .diagnostic-entry-msg {
    font-weight: bold;
  }

  .status-entry .debug {
    color: gray;
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


<h1>Windows</h1>

## Survey and feedback message, original and translation

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


## Start of diagnostic info
% if diagnostic_info:

## Display more human-friendly field names
<%def name="sys_info_key_map(key)">
  <%
  map = {
          'CLIENT_VERSION': 'Client Version',
          'PROPAGATION_CHANNEL_ID': 'Prop. Channel',
          'SPONSOR_ID': 'Sponsor',
          'language': '<a href="http://msdn.microsoft.com/en-ca/goglobal/bb964664.aspx">language</a>',
          'locale': '<a href="http://msdn.microsoft.com/en-ca/goglobal/bb964664.aspx">locale</a>',
          'codeSet': '<a href="http://msdn.microsoft.com/en-us/library/windows/desktop/dd317756%28v=vs.85%29.aspx">codeSet</a>',
          'productState': '<a href="http://neophob.com/2010/03/wmi-query-windows-securitycenter2/">productState</a>',
          'flags': '<a href="http://msdn.microsoft.com/en-us/library/windows/desktop/aa385145%28v=vs.85%29.aspx">flags</a>',
          'countryCode': '<a href="http://en.wikipedia.org/wiki/List_of_country_calling_codes">countryCode</a>',
        }
  %>
  % if key in map:
    ## Disabling filtering/escaping for our overrides.
    ${map[key] | n}
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


##
## Brief System Info
##

<h2>System Brief</h2>

<table>

  ${sys_info_row('OS', sys_info['OSInfo']['name'])}
  ${sys_info_row('User is', ', '.join([k for (k,v) in sys_info['UserInfo'].iteritems() if v]))}
  ${sys_info_row('AV', ', '.join([av['displayName'] for av in sys_info['SecurityInfo']['AntiVirusInfo'] if av[av['version']]['enabled']]))}
  ${sys_info_row('Uses proxy', 'yes' if [proxy for proxy in sys_info['NetworkInfo']['Original']['Proxy'] if proxy['flags'] != 'PROXY_TYPE_DIRECT'] else 'no')}
  ${sys_info_row('~Country', ', '.join([c['display'] for c in utils.coalesce(sys_info, ['OSInfo', 'CountryCodeInfo'], [])]))}
  ${sys_info_row('~Locale', utils.coalesce(sys_info, ['OSInfo', 'LocaleInfo', 'display'], ''))}
</table>

<a class="smaller" href="#sys_info_${metadata['id']}">See full System Info</a>


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
        ping_str = '%dms' % entry['data']['responseTime']
        if not entry['data']['responded'] or entry['data']['responseTime'] < 0:
          ping_class = 'bad'
          ping_str = 'none'
        elif entry['data']['responseTime'] > 2000:
          ping_class = 'warn'
      %>
      <span class="intcompare ${ping_class}">${ping_str}</span>
      <span>${entry['data']['ipAddress']}</span>
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
  status_diagnostic_history = sorted(status_history + diagnostic_history,
                                     key=itemgetter('timestamp'))
%>
% for entry in status_diagnostic_history:
  ## The presence of a 'debug' field indicates a status entry
  % if 'debug' in entry:
    ## ...but we're not actually printing out debug entries.
    % if not entry['debug']:
      ${status_history_row(entry, last_timestamp)}
      <% last_timestamp = entry['timestamp'] %>
    % endif
  % else:
    ${diagnostic_history_row(entry, last_timestamp)}
    <% last_timestamp = entry['timestamp'] %>
  % endif
% endfor


##
## System Info
##

<a name="sys_info_${metadata['id']}"></a>
<h2>System Info</h2>

## OS Info

<h3>OS Info</h3>
<table>
  % for k, v in sorted(sys_info['OSInfo'].items()):
    ${sys_info_row(k, v)}
  % endfor
</table>

## Network Info

<h3>Network Info</h3>

<h4>Original Proxy</h4>
% for connection in sys_info['NetworkInfo']['Original']['Proxy']:
  <table>
    % for k, v in sorted(connection.items()):
      <% if k == 'connectionName' and not v: v = '[default]' %>
      ${sys_info_row(k, v)}
    % endfor
  </table>
% endfor

<h4>Original Internet</h4>
<table>
  % for k, v in sorted(sys_info['NetworkInfo']['Original']['Internet'].items()):
    ${sys_info_row(k, v)}
  % endfor
</table>

<h4>Current Internet</h4>
<table>
  % for k, v in sorted(sys_info['NetworkInfo']['Current']['Internet'].items()):
    ${sys_info_row(k, v)}
  % endfor
</table>

## Security Info

<h3>Security Info</h3>
<h4>Anti-Virus</h4>
% for item in sys_info['SecurityInfo']['AntiVirusInfo']:
  <table>
    ${sys_info_row('', item['displayName'])}
    % for k, v in sorted(item[item['version']].items()):
        % if k == 'productState' and v:
          ${sys_info_row(k, hex(v))}
        % else:
          ${sys_info_row(k, v)}
        % endif
    % endfor
  </table>
% endfor

## The anti-spyware info seems to often be identical to the anti-virus info,
## in which case we won't output it.
% if sys_info['SecurityInfo']['AntiSpywareInfo'] != sys_info['SecurityInfo']['AntiVirusInfo']:
  <h4>Anti-Spyware</h4>
  % for item in sys_info['SecurityInfo']['AntiSpywareInfo']:
    <table>
      ${sys_info_row('', item['displayName'])}
      % for k, v in sorted(item[item['version']].items()):
        % if k == 'productState' and v:
          ${sys_info_row(k, hex(v))}
        % else:
          ${sys_info_row(k, v)}
        % endif
      % endfor
    </table>
  % endfor
% endif

% if sys_info['SecurityInfo']['FirewallInfo']:
  <h4>Firewall</h4>
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

<h3>Psiphon Info</h3>
<table>
  % for k, v in sorted(sys_info['PsiphonInfo'].items()):
    ${sys_info_row(k, v)}
  % endfor
</table>

## end of diagnostic info
% endif
