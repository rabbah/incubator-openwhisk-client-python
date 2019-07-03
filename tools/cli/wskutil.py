#
# Copyright 2015-2016 IBM Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import print_function
import sys
import os
import json
import httplib
import ssl
import base64
import collections
from urlparse import urlparse

try:
    raw_input          # Python 2
except NameError:
    raw_input = input  # Python 3

# global configurations, can control whether to allow untrusted certificates on
# HTTPS connections
httpRequestProps = {'secure': True}


def supportsColor():
    return bool((sys.platform != 'win32' or 'ANSICON' in os.environ) and
                sys.stdout.isatty())


def hilite(status, bold=False):
    if supportsColor():
        attr = []
        if status == 'up':
            attr.append('32')  # green
        elif status == 'down':
            attr.append('31')  # red
        if bold:
            attr.append('1')
        return '\x1b[%sm%s\x1b[0m' % (';'.join(attr), status)
    else:
        return status


def bold(string):
    return hilite(string, True)


def addAuthenticatedCommand(subcmd, props):
    auth = props.get('AUTH')
    subcmd.add_argument('-u', '--auth', help='authorization key', default=auth,
                        required=bool(auth is None))


def request(method, urlString, body='', headers=None, auth=None, verbose=False,
            https_proxy=os.getenv('https_proxy', None)):
    headers = headers or {}
    url = urlparse(urlString)
    if url.scheme == 'http':
        conn = httplib.HTTPConnection(url.netloc)
    else:
        if (httpRequestProps['secure'] or
                not hasattr(ssl, '_create_unverified_context')):
            conn = httplib.HTTPSConnection(https_proxy or url.netloc)
        else:
            conn = httplib.HTTPSConnection(https_proxy or url.netloc,
                            context=ssl._create_unverified_context())  # noqa
        if https_proxy:
            conn.set_tunnel(url.netloc)

    if auth is not None:
        auth = base64.encodestring(auth).replace('\n', '')
        headers['Authorization'] = 'Basic %s' % auth

    if verbose:
        print('========')
        print('REQUEST:')
        print('%s %s' % (method, urlString))
        print('Headers sent:')
        print(getPrettyJson(headers))
        if body:
            print('Body sent:')
            print(body)

    try:
        conn.request(method, urlString, body, headers)
        res = conn.getresponse()
        body = ''
        try:
            body = res.read()
        except httplib.IncompleteRead as e:
            body = e.partial

        # patch the read to return just the body since the normal read
        # can only be done once
        res.read = lambda: body

        if verbose:
            print('--------')
            print('RESPONSE:')
            print('Got response with code %s' % res.status)
            print('Body received:')
            print(res.read())
            print('========')
        return res
    except Exception as e:
        res = dict2obj({'status': 500, 'error': str(e)})
        return res


def responseError(res, prefix='error:', flatten=True):
    if prefix:
        print(prefix, end=' ', file=sys.stderr)
    response = None
    try:
        response = res.read()
        result = json.loads(response)
        if 'error' in result and 'code' in result:
            print('%s (code %s)' % (result['error'], result['code']),
                  file=sys.stderr)
        elif 'error' in result and flatten:
            print(result['error'], file=sys.stderr)
        else:
            print(getPrettyJson(result), file=sys.stderr)
    except:
        if res.status == 502:
            print('connection failed or timed out', file=sys.stderr)
        elif isinstance(res, collections.Iterable):
            if 'read' in res:
                print(res.read(), file=sys.stderr)
            elif 'error' in res:
                print(res['error'], file=sys.stderr)
            else:
                print('unrecognized failure', file=sys.stderr)
        elif response is not None:
            print(response, file=sys.stderr)
        else:
            print('unrecognized failure', file=sys.stderr)
    return res.status


# creates [ { key: "key name", value: "the value" }* ] from annotations.
def getAnnotations(args):
    annotations = []
    if args.annotation:
        for annotation in args.annotation:
            annotations.append(getParam(annotation[0], annotation[1]))
    return annotations


# creates [ { key: "key name", value: "the value" } ] from arguments
# to conform to Action schema for parameters and annotations
def getParams(args):
    return getParameters(args.param, False)

# creates [ { key: "key name", value: "the value", init: True } ] from arguments
# to conform to Action schema for init-time parameters
def getEnvVars(args):
    return getParameters(args.envvar, True)

def getParameters(args, asEnvVar):
    params = []
    if args:
        for param in args:
            p = getParam(param[0], param[1])
            p['init'] = asEnvVar
            params.append(p)
    return params

# creates a parameter { key: "key name", value: "the value" }
def getParam(key, value):
    p = {}
    p['key'] = key
    try:
        p['value'] = json.loads(value)
    except ValueError:
        p['value'] = value
    return p


# creates JSON object from parameters
def getActivationArgument(args):
    params = {}
    if args.param:
        for p in args.param:
            try:
                params[p[0]] = json.loads(p[1])
            except:
                params[p[0]] = p[1]
    return params


def chooseFromArray(array):
    count = 1
    for value in array:
        print('{0:3d}. {1}'.format(count, value))
        count += 1
    print('{0:>3}. {1}'.format('x', 'abort and exit'))

    chosen = None
    while True:
        try:
            keypress = raw_input('Choice: ')
            if keypress == 'x':
                return -1
            chosen = int(keypress)
        except ValueError:
            chosen = 0
        if chosen > 0 and chosen < count:
            break
        else:
            print('Please choose one of the given options')
    return array[chosen - 1]


# class to convert dictionary to objects
class dict2obj(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        else:
            raise AttributeError('object has no attribute "%s"' % name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        if name in self:
            del self[name]
        else:
            raise AttributeError('object has no attribute "%s"' % name)


def getPrettyJson(obj):
    return json.dumps(obj, sort_keys=True, indent=4, separators=(',', ': '))


# Return description string from annotations.
def getDescriptionFromAnnotations(annotations):
    description = ''
    for a in annotations:
        if a['key'] == 'description':
            description = a['value']
    return description


# Return list of parameters names from annotations.
def getParameterNamesFromAnnotations(annotations):
    names = []
    for a in annotations:
        if a['key'] == 'parameters':
            for p in a['value']:
                names.append(p['name'])
    return names


#
# Resolve namespace, either to default namespace or
# from properties extracted from file if defined
#
def resolveNamespace(props, key='namespace'):
    ns = props.get(key, '_').strip()
    return ns if ns != '' else '_'


def getPathDelimiter():
    return '/'


#
# Parse a (possibly fully qualified) resource name into
# namespace and name components. If the given qualified
# name isNone, then this is a default qualified name
# and it is resolved from properties. If the namespace
# is missing from the qualified name, the namespace is also
# resolved from the property file.
#
# Return a (namespace, package+name) tuple.
#
# Examples:
#      foo => (_, foo)
#      pkg/foo => (_, pkg/foo)
#      /ns/foo => (ns, foo)
#      /ns/pkg/foo => (ns, pkg/foo)
#
def parseQName(qname, props):
    parsed = collections.namedtuple('QName', ['namespace', 'name'])
    delimiter = getPathDelimiter()
    if qname is not None and len(qname) > 0 and qname[0] == delimiter:
        parts = qname.split(delimiter)
        namespace = parts[1]
        name = delimiter.join(parts[2:]) if len(parts) > 2 else ''
    else:
        namespace = resolveNamespace(props)
        name = qname
    r = parsed(namespace, name)
    return r


# Return a fully qualified name given a (possibly fully qualified) resource
# name and optional namespace.
#
# Examples:
#      (foo, None) => /_/foo
#      (pkg/foo, None) => /_/pkg/foo
#      (foo, ns) => /ns/foo
#      (ns, pkg/foo) => /ns/pkg/foo
#      (/ns/pkg/foo, None) => /ns/pkg/foo
#      (/ns/pkg/foo, otherns) => /ns/pkg/foo
def getQName(qname, namespace=None):
    delimiter = getPathDelimiter()
    if qname[0] == delimiter:
        return qname
    elif namespace is not None and namespace[0] == delimiter:
        return '%s%s%s' % (namespace, delimiter, qname)
    else:
        namespace = namespace if namespace else resolveNamespace({})
        return '%s%s%s%s' % (delimiter, namespace, delimiter, qname)


def hostBase(props):
    host = props['apihost']
    url = urlparse(host)
    if url.scheme is '':
        return 'https://%s' % host
    else:
        return host


def apiBase(props):
    host = hostBase(props)
    version = props['apiversion']
    return '%s/api/%s' % (host, version)
