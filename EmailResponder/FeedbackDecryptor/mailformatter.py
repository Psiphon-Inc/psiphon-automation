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
    platform = 'windows' if data['Metadata']['platform'] == 'windows' else 'android'
    version = int(data['Metadata']['version'])

    template_filename = 'templates/template_%s_%d.mako' % (platform, version)

    if template_filename not in _cached_templates:
        template_lookup = TemplateLookup(directories=['.'])

        # SECURITY IMPORTANT: `'h'` in the `default_filters` list causes HTML
        # escaping to be applied to all expression tags (${...}) in this
        # template. Because we're output untrusted user-supplied data, this is
        # essential.
        _cached_templates[template_filename] = Template(filename=template_filename,
                                                        default_filters=['unicode', 'h'],
                                                        lookup=template_lookup)

    try:
        rendered = _cached_templates[template_filename].render(data=data)
    except:
        raise Exception(exceptions.text_error_template().render())

    # CSS in email HTML must be inline
    rendered = pynliner.fromString(rendered)

    return rendered
