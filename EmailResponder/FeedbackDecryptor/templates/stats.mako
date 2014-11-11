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
  import operator
  import functools
  import collections
  import utils
%>


<style>
  .timestamp {
    font-size: 0.8em;
    font-family: monospace;
  }

  .smaller {
    font-size: 0.8em;
  }

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

  table tr td[align="right"] {
    text-align: right;
  }

  table tr td[align="left"] {
    text-align: left;
  }

  table tr td[align="center"] {
    text-align: center;
  }
</style>

<h1>Feedback Decryptor Stats</h1>

<h2>New Diagnostic Data Records</h2>

<p>
  New Android records: ${data['new_android_records']}
  <br>
  New Windows records: ${data['new_windows_records']}
</p>

<h2>Response Times</h2>

<%
# Like: ORDER BY sponsor_record_count, sponsor_id, propagation_channel_id, platform
data['stats'] = sorted(data['stats'], key=operator.itemgetter('platform'))
data['stats'] = sorted(data['stats'], key=operator.itemgetter('propagation_channel_id'))
data['stats'] = sorted(data['stats'], key=operator.itemgetter('sponsor_id'))
data['stats'] = sorted(data['stats'],
                       key=lambda item: sum([d['record_count']
                                             for d in data['stats']
                                             if d['sponsor_id'] == item['sponsor_id']]),
                       reverse=True)

prev_sponsor_id = None
prev_propagation_channel_id = None

def ff(f):
  if f is None:
    return 'N/A'
  return '{:.2f}'.format(f)
%>

<%def name="output_survey_results(item)">
  <%
  survey = item.get('survey_results', {})
  vals = survey.values()
  res = dict(functools.reduce(operator.add, map(collections.Counter, vals)))
  %>
  ## If there are few responses, then the data isn't useful. Pick an arbitrary cut-off.
  % if sum(res.values()) > 20:
    <img src="https://chart.googleapis.com/chart?cht=bvg:nda&amp;chs=45x40&amp;chds=a&amp;chco=BEFFC1|FFBEBE&amp;chbh=20,0,1&amp;chm=r,FFFFFF,0,-0.01,0.01,1|R,FFFFFF,0,-0.01,0.01,1&amp;chd=t:${res.get(0, 0)},${res.get(1, 0)}" alt="Happy/Sad chart" title="${res.get(0, 0)},${res.get(1, 0)}">
  % endif
</%def>


<table>
  <thead>
    <tr>
      <th>Sponsor</th><th>Prop.Ch.</th><th>Platform</th><th>#</th>
      <th>Response (ms)</th><th>Failrate</th>
      <th>Happy/Sad</th>
    </tr>
  </thead>
  <tbody>
    % for r in data['stats']:
      <tr>
        <td>${r['sponsor_id'] if r['sponsor_id'] != prev_sponsor_id else ''}</td>
        <td>${r['propagation_channel_id'] if r['propagation_channel_id'] != prev_propagation_channel_id else ''}</td>
        <td>${r['platform']}</td>
        <td class="numcompare-left">
          ${r['record_count']} (${r['response_sample_count']})
        </td>
        <td>
          ## Pick an arbitrary minimum number of samples before we show the plot.
          % if r['response_sample_count'] > 50 and r['quartiles']:
            <img src="https://chart.googleapis.com/chart?chs=75x75&amp;cht=bhs&amp;chd=t0:${ff(r['quartiles'][0])}|${ff(r['quartiles'][1])}|${ff(r['quartiles'][3])}|${ff(r['quartiles'][4])}|${ff(r['quartiles'][2])}&amp;chm=F,000000,0,1,10|H,000000,0,1,1:10|H,000000,3,1,1:10|H,000000,4,1,1:10&amp;chxt=x&amp;chxr=0,0,2000&amp;chds=0,2000" alt="Show images for box plot">
          % endif
        </td>
        <td class="numcompare">${ff(r['failrate'])}</td>
        <td>
          % if r.get('survey_results'):
            ${output_survey_results(r)}
          % endif
        </td>
      </tr>

        <%
          prev_sponsor_id = r['sponsor_id']
          prev_propagation_channel_id = r['propagation_channel_id']
        %>
    % endfor
  </tbody>
</table>

<h2>New Errors</h2>

<% error_count = 0 %>
% for err in data['new_errors']:
  <p>
    <div class="timestamp">${err['datetime']}</div>
    <div>${repr(err['error'])}</div>
  </p>

  <% error_count += 1 %>
  ## The number of errors is unbounded, so we need to limit the count that we
  ## output here.
  % if error_count > 100:
    <div><strong>ERROR LIST TRUNCATED</strong></div>
    <% break %>
  % endif
% endfor

% if error_count > 0:
  <p>None</p>
% endif

<br>
<p>
  Stats time: <span class="timestamp">${utils.timestamp_display(data['now_timestamp'])}</span>
  <br>
  Last stats time: <span class="timestamp">${utils.timestamp_display(data['since_timestamp'])}</span>
</p>
