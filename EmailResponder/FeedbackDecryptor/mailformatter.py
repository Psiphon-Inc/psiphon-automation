# Copyright (c) 2013, Psiphon Inc.
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
from mako.lookup import TemplateLookup
from mako import exceptions
import pynliner


_cached_templates = {}


def format(data):
    '''
    Will throw exception if data does not match expected structure (that is,
    if the template rendering fails).
    '''

    # The values in `data` come directly from the user, so we shouldn't trust
    # them enough to put them directly in to a filename.

    if data['Metadata']['appName'] == 'ryve':
        app_name = 'ryve'
    elif data['Metadata']['appName'] == 'conduit':
        app_name = 'conduit'
    elif data['Metadata']['appName'] == 'psiphon4':
        app_name = 'psiphon4'
    else:
        app_name = 'psiphon'

    if data['Metadata']['platform'] == 'windows':
        platform = 'windows'
    elif data['Metadata']['platform'] == 'ios': # legacy catch all
        platform = 'ios'
    elif data['Metadata']['platform'] == 'ios-browser':
        platform = 'ios'
    elif data['Metadata']['platform'] == 'ios-vpn':
        platform = 'ios'
    elif data['Metadata']['platform'] in ['ios-vpn-on-mac', 'ios-app-on-mac']:
        platform = 'ios-app-on-mac'
    else:
        platform = 'android'

    version = int(data['Metadata']['version'])

    template_filenames = (
        'templates/template_%s_%s_%d.mako' % (app_name, platform, version),
        'templates/template_%s_%d.mako' % (app_name, version),
    )

    for template_filename in template_filenames:
        if template_filename not in _cached_templates:
            template_lookup = TemplateLookup(directories=['.'])

            # SECURITY IMPORTANT: `'h'` in the `default_filters` list causes HTML
            # escaping to be applied to all expression tags (${...}) in this
            # template. Because we're outputting untrusted user-supplied data, this is
            # essential.
            try:
                _cached_templates[template_filename] = Template(filename=template_filename,
                                                                default_filters=['str', 'h'],
                                                                lookup=template_lookup)
            except FileNotFoundError:
                # This template doesn't exist; try the next one
                continue

        # We found our template
        break

    if template_filename not in _cached_templates:
        raise Exception('No suitable template found for %s' % data['Metadata'])

    try:
        rendered = _cached_templates[template_filename].render(data=data)
    except:
        raise Exception(exceptions.text_error_template().render())

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    return rendered
