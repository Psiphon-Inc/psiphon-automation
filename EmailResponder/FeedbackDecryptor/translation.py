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

'''
We're creating our own Google Translate interface for two reasons:
- The lesser reason: The Google API Python lib sends requests that are too
  long (and so get a response error), so we'd have to wrap it anyway.
- The greater reason: Requests to the API timeout *a lot*. We need to have
  some failover between IP addresses. We'll be using `/etc/hosts` to help us.

We have found that `www.googleapis.com` resolves to different IPs from
different geographical regions, and that when one IP is failing, the other
IP(s) is often still working. So we'll leverage those multiple IPs to make our
requests more robust.

Note that `/etc/hosts` has to have entries for every `apiServers` alias. The
aliases must be of the form `[a-z0-9]+.googleapis.com`, because the SSL
certificate will only match `*.googleapis.com`.

If you don't want any failover, just leave `apiServers` empty or None.
'''

# The actual errors we've had from the Google API servers:
# socket.error: [Errno 110] Connection timed out
# socket.error: [Errno 101] Network is unreachable

import requests

import logger
import utils


# See https://developers.google.com/translate/v2/using_rest
# Experimentation suggests that the POST size can be much larger than claimed.
_MAX_GET_REQUEST_SIZE = 2000
_MAX_POST_REQUEST_SIZE = 15000

_USE_POST_REQUEST = True

_TARGET_LANGUAGE = 'en'

# This will be a dict of 'lang-code': 'full-lang-name'
_languages = {}


def translate(apiServers, apiKey, msg):
    '''
    Translates msg to English. Returns a tuple of:
      (original-language-code, original-language-fullname, translated-msg)

    Special values: `original-language-code` may have the values:
      - "[INDETERMINATE]": If the language of `msg` can't be determined.
      - "[TRANSLATION_FAIL]": If the translation process threw an exception.
        In this case, `original-language-fullname` will have the exception
        message.
    '''

    try:
        if not _languages:
            _load_languages(apiServers, apiKey)

        # Detect the language. We won't use the entire string, since we pay per
        # character, and the #characters-to-accuracy curve is probably logarithmic.
        # Note that truncating the request means we don't have to worry about the
        # max request size yet.
        detected = _make_request(apiServers, apiKey,
                                 'detect', {'q': msg[:200]})
        from_lang = detected['data']['detections'][0][0]['language']

        # 'zh-CN' will be returned as a detected language, but it is not in the
        # _languages set. So we might need to massage the detected language.
        if from_lang not in _languages:
            from_lang = from_lang.split('-')[0]
            if from_lang not in _languages:
                # This probably means that the detection failed
                return ('[INDETERMINATE]',
                        'Language could not be determined',
                        None)

        if from_lang == _TARGET_LANGUAGE:
            # msg is already in the target language
            return (from_lang, _languages[from_lang], msg)

        msg_translated = _translate_request_helper(apiServers, apiKey,
                                                   from_lang, msg)

        return (from_lang, _languages[from_lang], msg_translated)
    except Exception as e:
        return ('[TRANSLATION_FAIL]', utils.safe_str(e), None)


def _load_languages(apiServers, apiKey):
    global _languages

    resp = _make_request(apiServers, apiKey, 'languages')
    _languages = dict((lang['language'], lang['name'])
                      for lang
                      in resp['data']['languages'])


def _translate_request_helper(apiServers, apiKey, from_lang, msg):
    '''
    Because requests to the API have a maximum allowed size, we might need to
    break up our request and recombine the results. This help encapsulates
    that.
    Returns translated `msg`.
    Will throw and exception on error.
    '''

    # This is a bit tricky. A unicode string of a particular length will
    # encode to different length UTF-8 strings depending on what characters
    # are in the unicode string (one to four bytes per character). This
    # also means that a UTF-8 string can't be split just anywhere -- you might
    # be splitting a byte sequence, resulting in invalid UTF-8.
    # In addition, the length of a UTF-8 string will be multiplied by 3 to
    # account for URL encoding ('\xe6' -> '%E6').
    # If we wanted to do this naively/simply, we could do:
    # 5000 - {a little bit for other params} - {unicode length * 4 * 3}
    # And... that's how we're going to do it. It will result in about twice
    # as many requests as needed, but a) we're not in a huge hurry, b) we pay
    # per character, not per request, and c) it's much less complex and less
    # prone to bugs.
    # Another downside to smaller requests: Breaking the text up into smaller
    # pieces surely impacts the quality of the translation.
    # TESTING NOTE: When using POST, I can't actually get the size limit to
    # trigger (before hitting "userRateLimitExceed"). So maybe breaking up
    # this request is a waste of time...?

    max_size = _MAX_POST_REQUEST_SIZE if _USE_POST_REQUEST else _MAX_GET_REQUEST_SIZE
    msg_size_limit = (max_size - 200) / (4 * 3)
    result_accumulator = u''
    start_index = 0
    while True:
        msg_fragment = msg[start_index:start_index + msg_size_limit]
        if not msg_fragment:
            break
        start_index += msg_size_limit

        resp = _make_request(apiServers, apiKey,
                             'translate',
                             {'source': from_lang, 'q': msg_fragment})

        result_accumulator += resp['data']['translations'][0]['translatedText']

    return result_accumulator


_lastGoodApiServer = None


def _make_request(apiServers, apiKey, action, params=None):
    '''
    Make the specified request, employing server failover if necessary.
    `action` must be one of ['languages', 'detect', 'translate'].
    `params` must be None or a dict of query parameters.
    Throws exception on error.
    '''

    global _lastGoodApiServer

    assert(action in ('languages', 'detect', 'translate'))

    original_action = action
    if action == 'translate':
        # 'translate' is the API's default action.
        action = ''
    else:
        action = '/' + action

    if not params:
        params = {}

    params['key'] = apiKey
    params['target'] = _TARGET_LANGUAGE

    # Without this, the input is assumed to be HTML and newlines get stripped.
    params['format'] = 'text'

    # If `apiServers` is empty, we not doing failover.
    if not apiServers:
        apiServers = ['www.googleapis.com']

    # If we have a _lastGoodApiServer, then move it to the front of the
    # failover list.
    if _lastGoodApiServer in apiServers:
        apiServers.remove(_lastGoodApiServer)
        apiServers.insert(0, _lastGoodApiServer)

    # We have to set the Host header so that Google will accept requests to
    # "server1.googleapis.com", etc.
    headers = {'Host': 'www.googleapis.com'}

    # This header is required to make a POST request.
    # See https://developers.google.com/translate/v2/using_rest
    if _USE_POST_REQUEST:
        headers['X-HTTP-Method-Override'] = 'GET'

    ex = None

    # Fail over between available servers
    for apiServer in apiServers:
        success = True

        url = 'https://%s/language/translate/v2%s' % (apiServer, action)

        try:
            if _USE_POST_REQUEST:
                req = requests.post(url, headers=headers, data=params)
            else:
                req = requests.get(url, headers=headers, params=params)

            extra_fail = _extra_fail_check(original_action, params, req)

            if extra_fail != False:
                success = False
                err = 'translate request not ok; failing over: %s; %d; %s' \
                        % (apiServer, req.status_code, extra_fail)
                # logger.error(err)  # don't log -- not useful
                ex = Exception(err)
            elif req.ok:
                _lastGoodApiServer = apiServer
                break
            else:
                success = False
                err = 'translate request not ok; failing over: %s; %d; %s; %s' \
                        % (apiServer, req.status_code, req.reason, req.text)
                # logger.error(err)  # don't log -- not useful
                ex = Exception(err)

        # These exceptions are the ones we've seen when the API server is
        # being flaky.
        except (requests.ConnectionError, requests.Timeout) as ex:
            success = False
            # logger.error('%s.py: API error; failing over: %s' % (__name__, utils.safe_str(ex)))  # don't log -- not useful
        except Exception as ex:
            # Unexpected error. Not going to fail over.
            logger.error('%s.py: request error: %s' % (__name__, utils.safe_str(ex)))
            raise

    if not success:
        # We failed over through all our servers with no luck. Re-raise the
        # last exception.
        raise ex if ex else Exception('translation fail')

    return req.json()


def _extra_fail_check(action, params, req):
    '''
    This encapsulates a cheap hack: Sometimes Google Translate fails silently
    by returning the same string back as the translation. We need to fail over
    when this happens.
    Returns False if no fail, otherwise an error string.
    '''

    if req.ok and action == 'translate':
        msg = params['q']
        msg_translated = req.json()['data']['translations'][0]['translatedText']
        if msg == msg_translated:
            return 'Google Translate returned same string'

    return False
