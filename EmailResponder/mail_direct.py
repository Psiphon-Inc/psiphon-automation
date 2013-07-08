# Copyright (c) 2011, Psiphon Inc.
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

import argparse
import email

import mail_process



if __name__ == '__main__':

    # Set up the program arguments
    parser = argparse.ArgumentParser(description='Send email directly to an address, as if in response to a request')
    parser.add_argument('--recip_addr', required=True, action='store', help='the email will appear to be a response to a request to this address')
    parser.add_argument('--responder_addr', required=True, action='store', help='the address the email will be sent to')
    parser.add_argument('--subject', required=True, action='store', help='the subject of the email that will be sent')
    args = parser.parse_args()
    
    # Create a stub email to send to the email processor
    em = email.message.Message()
    em['To'] = args.responder_addr
    em['X-Original-To'] = args.responder_addr
    em['Return-Path'] = args.recip_addr
    em['Subject'] = args.subject.strip('Re:').strip('re:').strip()
    
    if not mail_process.process_input(em.as_string()):
        print 'FAILED: check log for details'
    else:
        print 'SUCCESS'
