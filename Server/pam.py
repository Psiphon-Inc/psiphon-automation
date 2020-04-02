# (c) 2007 Chris AtLee <chris@atlee.ca>
# (c) 2010 Grzegorz Nosek <root@localdomain.pl>
# Licensed under the MIT license:
# http://www.opensource.org/licenses/mit-license.php
"""
PAM module for python

Provides an authenticate function that will allow the caller to authenticate
a user against the Pluggable Authentication Modules (PAM) on the system.

Implemented using ctypes, so no compilation is necessary.
"""
__all__ = ['PamException', 'Error', 'authenticate', 'open_session', 'close_session']

from ctypes import CDLL, POINTER, Structure, CFUNCTYPE, cast, pointer, sizeof
from ctypes import c_void_p, c_uint, c_char_p, c_char, c_int
from ctypes.util import find_library
import os
import sys

LIBPAM = CDLL(find_library("pam"))
LIBC = CDLL(find_library("c"))

CALLOC = LIBC.calloc
CALLOC.restype = c_void_p
CALLOC.argtypes = [c_uint, c_uint]

STRDUP = LIBC.strdup
STRDUP.argstypes = [c_char_p]
STRDUP.restype = POINTER(c_char) # NOT c_char_p !!!!

# Various constants
PAM_PROMPT_ECHO_OFF = 1
PAM_PROMPT_ECHO_ON = 2
PAM_ERROR_MSG = 3
PAM_TEXT_INFO = 4

# Possible error codes
class Error(object):
      PAM_SUCCESS = 0
      PAM_OPEN_ERR = 1
      PAM_SYMBOL_ERR = 2
      PAM_SERVICE_ERR = 3
      PAM_SYSTEM_ERR = 4
      PAM_BUF_ERR = 5
      PAM_CONV_ERR = 6
      PAM_PERM_DENIED = 7
      PAM_MAXTRIES = 8
      PAM_AUTH_ERR = 9
      PAM_NEW_AUTHTOK_REQD = 10
      PAM_CRED_INSUFFICIENT = 11
      PAM_AUTHINFO_UNAVAIL = 12
      PAM_USER_UNKNOWN = 13
      PAM_CRED_UNAVAIL = 14
      PAM_CRED_EXPIRED = 15
      PAM_CRED_ERR = 16
      PAM_ACCT_EXPIRED = 17
      PAM_AUTHTOK_EXPIRED = 18
      PAM_SESSION_ERR = 19
      PAM_AUTHTOK_ERR = 20
      PAM_AUTHTOK_RECOVERY_ERR = 21
      PAM_AUTHTOK_LOCK_BUSY = 22
      PAM_AUTHTOK_DISABLE_AGING = 23
      PAM_NO_MODULE_DATA = 24
      PAM_IGNORE = 25
      PAM_ABORT = 26
      PAM_TRY_AGAIN = 27
      PAM_MODULE_UNKNOWN = 28
      PAM_DOMAIN_UNKNOWN = 29

class PamHandle(Structure):
    """wrapper class for pam_handle_t"""
    _fields_ = [
            ("handle", c_void_p)
            ]

    def __init__(self):
        Structure.__init__(self)
        self.handle = 0

PAM_STRERROR = LIBPAM.pam_strerror
PAM_STRERROR.restype = c_char_p
PAM_STRERROR.argtypes = [PamHandle, c_int]

class PamException(Exception):
    def __init__(self, handle, errno):
        self.errno = errno
        self.message = PAM_STRERROR(handle, errno)

    def __repr__(self):
        return "<PamException %i '%s'>" % (self.errno, self.message)

class PamMessage(Structure):
    """wrapper class for pam_message structure"""
    _fields_ = [
            ("msg_style", c_int),
            ("msg", POINTER(c_char)),
            ]

    def __repr__(self):
        return "<PamMessage %i '%s'>" % (self.msg_style, self.msg)

class PamResponse(Structure):
    """wrapper class for pam_response structure"""
    _fields_ = [
            ("resp", POINTER(c_char)),
            ("resp_retcode", c_int),
            ]

    def __repr__(self):
        return "<PamResponse %i '%s'>" % (self.resp_retcode, self.resp)

CONV_FUNC = CFUNCTYPE(c_int,
        c_int, POINTER(POINTER(PamMessage)),
               POINTER(POINTER(PamResponse)), c_void_p)

class PamConv(Structure):
    """wrapper class for pam_conv structure"""
    _fields_ = [
            ("conv", CONV_FUNC),
            ("appdata_ptr", c_void_p)
            ]

PAM_START = LIBPAM.pam_start
PAM_START.restype = c_int
PAM_START.argtypes = [c_char_p, c_char_p, POINTER(PamConv),
        POINTER(PamHandle)]

PAM_END = LIBPAM.pam_end
PAM_END.restpe = c_int
PAM_END.argtypes = [PamHandle, c_int]

PAM_AUTHENTICATE = LIBPAM.pam_authenticate
PAM_AUTHENTICATE.restype = c_int
PAM_AUTHENTICATE.argtypes = [PamHandle, c_int]

PAM_OPEN_SESSION = LIBPAM.pam_open_session
PAM_OPEN_SESSION.restype = c_int
PAM_OPEN_SESSION.argtypes = [PamHandle, c_int]

PAM_CLOSE_SESSION = LIBPAM.pam_close_session
PAM_CLOSE_SESSION.restype = c_int
PAM_CLOSE_SESSION.argtypes = [PamHandle, c_int]

PAM_ACCT_MGMT = LIBPAM.pam_acct_mgmt
PAM_ACCT_MGMT.restype = c_int
PAM_ACCT_MGMT.argtypes = [PamHandle, c_int]

PAM_CHAUTHTOK = LIBPAM.pam_chauthtok
PAM_CHAUTHTOK.restype = c_int
PAM_CHAUTHTOK.argtypes = [PamHandle, c_int]

@CONV_FUNC
def default_conv(n_messages, messages, p_response, app_data):
    addr = CALLOC(n_messages, sizeof(PamResponse))
    p_response[0] = cast(addr, POINTER(PamResponse))
    if not os.isatty(sys.stdin.fileno()):
        return 0
    for i in range(n_messages):
        msg = messages[i].contents
        style = msg.msg_style
        msg_string = cast(msg.msg, c_char_p).value
        if style == PAM_TEXT_INFO or style == PAM_ERROR_MSG:
            # back from POINTER(c_char) to c_char_p
            print msg_string
        elif style == PAM_PROMPT_ECHO_ON:
            print msg_string,
            sys.stdout.flush()
            pw_copy = STRDUP(sys.stdin.readline())
            p_response.contents[i].resp = pw_copy
            p_response.contents[i].resp_retcode = 0
        elif style == PAM_PROMPT_ECHO_OFF:
            pw_copy = STRDUP(str(getpass.getpass(msg_string)))
            p_response.contents[i].resp = pw_copy
            p_response.contents[i].resp_retcode = 0
        else:
            print repr(messages[i].contents)
    return 0

def pam_start(service, username, conv_func=default_conv):
    handle = PamHandle()
    conv = pointer(PamConv(conv_func, 0))
    retval = PAM_START(service, username, conv, pointer(handle))

    if retval != 0:
        PAM_END(handle, retval)
        raise PamException(handle, retval)

    return handle

def pam_end(handle, retval):
    e = PAM_END(handle, retval)
    if retval == 0 and e == 0:
        return
    if retval == 0:
        retval = e
    raise PamException(handle, retval)

def authenticate(username, password=None, service='login'):
    """Returns True if the given username and password authenticate for the
    given service.  Returns False otherwise
    
    ``username``: the username to authenticate
    
    ``password``: the password in plain text
                  Defaults to None to use PAM's conversation interface
    
    ``service``: the PAM service to authenticate against.
                 Defaults to 'login'"""

    if password is None:
        handle = pam_start(service, username)
    else:
        @CONV_FUNC
        def my_conv(n_messages, messages, p_response, app_data):
            """Simple conversation function that responds to any
            prompt where the echo is off with the supplied password"""
            # Create an array of n_messages response objects
            addr = CALLOC(n_messages, sizeof(PamResponse))
            p_response[0] = cast(addr, POINTER(PamResponse))
            for i in range(n_messages):
                if messages[i].contents.msg_style == PAM_PROMPT_ECHO_OFF:
                    pw_copy = STRDUP(str(password))
                    p_response.contents[i].resp = pw_copy
                    p_response.contents[i].resp_retcode = 0
            return 0

        handle = pam_start(service, username, my_conv)
    return pam_end(handle, PAM_AUTHENTICATE(handle, 0))

def open_session(username, service='login'):
    handle = pam_start(service, username)
    return pam_end(handle, PAM_OPEN_SESSION(handle, 0))

def close_session(username, service='login'):
    handle = pam_start(service, username)
    return pam_end(handle, PAM_CLOSE_SESSION(handle, 0))

def check_account(username, service='login'):
    handle = pam_start(service, username)
    return pam_end(handle, PAM_ACCT_MGMT(handle, 0))

def change_password(username, service='login'):
    handle = pam_start(service, username)
    return pam_end(handle, PAM_CHAUTHTOK(handle, 0))

if __name__ == "__main__":
    import getpass
    import optparse

    usage = "usage: %prog [options] [username]"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-a', '--authenticate', dest='authenticate',
        action='store_true', help='authenticate user')
    parser.add_option('-o', '--open-session', dest='open_session',
        action='store_true', help='open session')
    parser.add_option('-c', '--close-session', dest='close_session',
        action='store_true', help='close session')
    parser.add_option('-v', '--validate-account', dest='validate_account',
        action='store_true', help='check account validity')
    parser.add_option('-p', '--change-password', dest='change_password',
        action='store_true', help='change password')
    parser.add_option('-s', '--service', dest='service',
        action='store', default='login',
        help='PAM service to use [default: %default]')
    parser.add_option('-P', '--ask-password', dest='ask_password',
        action='store_true', help="own password prompt instead of PAM's")

    (o, a) = parser.parse_args()

    if not (o.authenticate or \
        o.open_session or \
        o.close_session or \
        o.validate_account or \
        o.change_password):
        parser.error("One of -a, -o, -c, -v or -p is mandatory")

    try:
        user = a[0]
    except IndexError:
        user = getpass.getuser()

    if o.authenticate:
        if o.ask_password:
            password = getpass.getpass()
        else:
            password = None

        try:
            authenticate(user, password, o.service)
        except PamException, e:
            print repr(e)

    if o.open_session:
        try:
            open_session(user, o.service)
        except PamException, e:
            print repr(e)

    if o.close_session:
        try:
            close_session(user, o.service)
        except PamException, e:
            print repr(e)

    if o.validate_account:
        try:
            check_account(user, o.service)
        except PamException, e:
            print repr(e)

    if o.change_password:
        try:
            change_password(user, o.service)
        except PamException, e:
            print repr(e)

