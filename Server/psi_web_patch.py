# Copyright (c) 2014, Psiphon Inc.
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

import types
from OpenSSL import SSL


def patch_ssl_adapter(ssl_adapter):
    # Patch pyOpenSSLAdapter to exclude SSLv3 due to POODLE flaw:
    # http://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2014-3566
    ssl_adapter.get_context = types.MethodType(get_context_disallow_SSLv3, ssl_adapter)


# This is a modified copy of get_content() from:
# https://bitbucket.org/cherrypy/cherrypy/src/default/cherrypy/wsgiserver/ssl_pyopenssl.py
# with SSLv3 disabled.

# Copyright (c) 2004-2011, CherryPy Team (team@cherrypy.org)
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without modification, 
# are permitted provided that the following conditions are met:
# 
#     * Redistributions of source code must retain the above copyright notice, 
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice, 
#       this list of conditions and the following disclaimer in the documentation 
#       and/or other materials provided with the distribution.
#     * Neither the name of the CherryPy Team nor the names of its contributors 
#       may be used to endorse or promote products derived from this software 
#       without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND 
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED 
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE 
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE 
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL 
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER 
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, 
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE 
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

def get_context_disallow_SSLv3(self):
    """Return an SSL.Context from self attributes."""
    # See http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/442473
    c = SSL.Context(SSL.SSLv23_METHOD)
    c.set_options(SSL.OP_NO_SSLv2|SSL.OP_NO_SSLv3) # PSIPHON
    c.use_privatekey_file(self.private_key)
    if self.certificate_chain:
        c.load_verify_locations(self.certificate_chain)
    c.use_certificate_file(self.certificate)
    return c
