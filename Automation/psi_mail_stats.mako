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

  .better {
    background-color: #EFE;
  }

  .worse {
    background-color: #FEE;
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

<h1>Psiphon 3 Stats</h1>

<h2> Connections Stats </h2>
## Iterate through the tables
% for key, connections_data in data['connections']['platform'].iteritems():
  % for platform_key, platform_data in connections_data.iteritems():
    <h3>${platform_key}</h3>
    <table>
      <thead>
        <tr>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Region</th>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Yesterday</th>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">One Week Ago</th>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Past Week</th>
        </tr>
      </thead>
      <tbody>
        % for row_index, row_data in enumerate(platform_data['region']['buckets']):
          <tr class="row-${'odd' if row_index%2 else 'even'}">
            ## First column is the region
            <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">${row_data['key']}</th>

            <%
              change = ''
              target_value = row_data['time_range']['buckets'][2]['doc_count']
              compartor = row_data['time_range']['buckets'][0]['doc_count']
              change = 'better' if target_value > compartor else 'worse'
            %>
            ## Data
            <td class="numcompare ${change}">
              ${'{:,}'.format(row_data['time_range']['buckets'][2]['doc_count'])}
            </td>
            <td>
              ${'{:,}'.format(row_data['time_range']['buckets'][0]['doc_count'])}
            </td>
            <td>
              ${'{:,}'.format(row_data['time_range']['buckets'][1]['doc_count'])}
            </td>
          </tr>
        % endfor

        <tr class="row-${'odd' if row_index%2 else 'even'}">
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Total</th>
          <%
            yesterday_total = data['connections_total']['platform']['buckets'][platform_key]['time_range']['buckets'][2]['doc_count']
            week_ago_total = data['connections_total']['platform']['buckets'][platform_key]['time_range']['buckets'][0]['doc_count']
            past_week_total = data['connections_total']['platform']['buckets'][platform_key]['time_range']['buckets'][1]['doc_count']
          %>
          <%
            change = ''
            target_value = yesterday_total
            compartor = week_ago_total
            change = 'better' if target_value > compartor else 'worse'
          %>
          <td class="numcompare ${change}">
            ${'{:,}'.format(yesterday_total)}
          </td>
          <td>
            ${'{:,}'.format(week_ago_total)}
          </td>
          <td>
            ${'{:,}'.format(past_week_total)}
          </td>
        </tr>
      </tbody>
    </table>
  %endfor
% endfor

<h2> Unique Users Stats </h2>
## Iterate through the tables
% for key, connections_data in data['unique_users']['platform'].iteritems():
  % for platform_key, platform_data in connections_data.iteritems():
    <h3>${platform_key}</h3>
    <table>
      <thead>
        <tr>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Region</th>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Yesterday</th>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">One Week Ago</th>
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Past Week</th>
        </tr>
      </thead>
      <tbody>
        % for row_index, row_data in enumerate(platform_data['region']['buckets']):
          <tr class="row-${'odd' if row_index%2 else 'even'}">
            ## First column is the region
            <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">${row_data['key']}</th>

            <%
              change = ''
              target_value = row_data['time_range']['buckets'][2]['unique_daily']['value']
              compartor = row_data['time_range']['buckets'][0]['unique_daily']['value']
              change = 'better' if target_value > compartor else 'worse'
            %>
            ## Data
            <td class="numcompare ${change}">
              ${'{:,}'.format(int(row_data['time_range']['buckets'][2]['unique_daily']['value']))}
            </td>
            <td>
              ${'{:,}'.format(int(row_data['time_range']['buckets'][0]['unique_daily']['value']))}
            </td>
            <td>
              ${'{:,}'.format(int(row_data['time_range']['buckets'][1]['unique_weekly']['value']))}
            </td>
          </tr>
        % endfor

        <tr class="row-${'odd' if row_index%2 else 'even'}">
          <th style="font-size: 1em; border: 1px solid #CCC; margin: 0; padding: 0.5em 1em; font-weight: bold; background-color: #F0F0F0">Total</th>
          <%
          yesterday_total = data['unique_users_total']['platform']['buckets'][platform_key]['time_range']['buckets'][2]['unique_daily']['value']
          week_ago_total = data['unique_users_total']['platform']['buckets'][platform_key]['time_range']['buckets'][0]['unique_daily']['value']
          past_week_total = data['unique_users_total']['platform']['buckets'][platform_key]['time_range']['buckets'][1]['unique_weekly']['value']
          %>
          <%
            change = ''
            target_value = yesterday_total
            compartor = week_ago_total
            change = 'better' if target_value > compartor else 'worse'
          %>
          <td class="numcompare ${change}">
            ${'{:,}'.format(int(yesterday_total))}
          </td>
          <td>
            ${'{:,}'.format(int(week_ago_total))}
          </td>
          <td>
            ${'{:,}'.format(int(past_week_total))}
          </td>
        </tr>
      </tbody>
    </table>
  %endfor
% endfor
