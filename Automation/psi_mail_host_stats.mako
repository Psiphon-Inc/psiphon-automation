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

<h1>Psiphon 3 Host Stats</h1>

## Iterate through the tables
% for tablename, tableinfo in data.iteritems():
  <h2>${tablename}</h2>

  <table>

    <thead>
      <tr>
        % for header in tableinfo['headers']:
          <th>${header}</th>
        % endfor
      </tr>
    </thead>

    <tbody>
      % for row_index, row in enumerate(tableinfo['data']):
        <tr class="row-${'odd' if row_index%2 else 'even'}">
          <%
            # A row is of the form: ('Key', defaultdict(int, {'Past Week': 46400L, 'Yesterday': 0L, '1 week ago': 6406L}))
            row_head, row_vals = row
          %>


          ## First column is the region (or Total)
          <th>${row_head}</th>

          ## The headers indicate the order we need to output the data
          % for col_index, col_name in enumerate(tableinfo['headers'][1:]):
            <%
              change = ''
              # Note that this loop starts at tableinfo['headers'][1], so col_index == 0 is tableinfo['headers'][1]
              if col_index == 0:
                target_value = row_vals[tableinfo['headers'][1]]
                compartor = row_vals[tableinfo['headers'][2]]
                #change = 'better' if target_value > compartor else 'worse'
                change = 'better' if target_value > 0 else 'worse'
            %>
            <td class="numcompare ${change}">
              ${'{:,}'.format(row_vals[col_name] or 0)}
            </td>
          % endfor
        </tr>
      % endfor
    </tbody>

  </table>
% endfor
