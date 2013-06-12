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

## Expected input data format:
##  {
##    lang_id: language ID -- might not be valid/support,
##    response_id: response ID,
##    responses: {lang_id: {response_id: value, ...}, ...},
##    format_dict: the dict to pass to the format call for the response bodies
##  }


<%!
import collections
%>


<style>

  hr {
    width: 80%;
    border: 0;
    background-color: lightGray;
    height: 1px;
  }

</style>


<%
# The order that we show the languages in the response is dependent on a number of factors...
responses = collections.OrderedDict()

# Firstly, the target language
if data['lang_id'] in data['responses']:
  responses[data['lang_id']] = data['responses'][data['lang_id']]

# Secondarily, the priority languages
for priority_lang in ('en', 'fa', 'ar', 'zh'):
  if priority_lang in data['responses']:
    responses[priority_lang] = data['responses'][priority_lang]

# Tertiarily, the rest of the languages
responses.update(data['responses'])

response_id = data['response_id']
%>

% for response in responses.values():
  ## Disable escaping, since we're output HTML
  ${response[response_id] % data['format_dict'] | n}
  <hr>
% endfor
