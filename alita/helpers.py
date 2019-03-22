import os
import re
import sys
import json
import pkgutil
import importlib
from functools import singledispatch, update_wrapper
from urllib.parse import urlencode, parse_qs, urlsplit,\
    urlunsplit, unquote_to_bytes

_ENTITY_HEADERS = frozenset(
    [
        "allow",
        "content-encoding",
        "content-language",
        "content-length",
        "content-location",
        "content-md5",
        "content-range",
        "content-type",
        "expires",
        "last-modified",
        "extension-header",
    ]
)
_etag_re = re.compile(r'([Ww]/)?(?:"(.*?)"|(.*?))(?:\s*,\s*|$)')
_unsafe_header_chars = set('()<>@,;:\"/[]?={} \t')
_option_header_piece_re = re.compile(r'''
    ;\s*
    (?P<key>
        "[^"\\]*(?:\\.[^"\\]*)*"  # quoted string
    |
        [^\s;,=*]+  # token
    )
    \s*
    (?:  # optionally followed by =value
        (?:  # equals sign, possibly with encoding
            \*\s*=\s*  # * indicates extended notation
            (?P<encoding>[^\s]+?)
            '(?P<language>[^\s]*?)'
        |
            =\s*  # basic notation
        )
        (?P<value>
            "[^"\\]*(?:\\.[^"\\]*)*"  # quoted string
        |
            [^;,]+  # token
        )?
    )?
    \s*
''', flags=re.VERBOSE)
_option_header_start_mime_type = re.compile(r',\s*([^;,\s]+)([;,]\s*.+)?')


def escape(s, quote=None):
    """Replace special characters "&", "<", ">" and (") to HTML-safe sequences.

    There is a special handling for `None` which escapes to an empty string.

    .. versionchanged:: 0.9
       `quote` is now implicitly on.

    :param s: the string to escape.
    :param quote: ignored.
    """
    if s is None:
        return ''
    elif hasattr(s, '__html__'):
        return str(s.__html__())
    elif not isinstance(s, str):
        s = str(s)
    if quote is not None:
        from warnings import warn
        warn(DeprecationWarning('quote parameter is implicit now'), stacklevel=2)
    s = s.replace('&', '&amp;').replace('<', '&lt;') \
        .replace('>', '&gt;').replace('"', "&quot;")
    return s


def to_unicode(x, charset=sys.getdefaultencoding(), errors='strict',
               allow_none_charset=False):
    if x is None:
        return None
    if not isinstance(x, bytes):
        return str(x)
    if charset is None and allow_none_charset:
        return x
    return x.decode(charset, errors)


class cached_property(object):
    """Cached property descriptor.

    Caches the return value of the get method on first call.

    Examples:
        .. code-block:: python

            @cached_property
            def connection(self):
                return Connection()

            @connection.setter  # Prepares stored value
            def connection(self, value):
                if value is None:
                    raise TypeError('Connection must be a connection')
                return value

            @connection.deleter
            def connection(self, value):
                # Additional action to do at del(self.attr)
                if value is not None:
                    print('Connection {0!r} deleted'.format(value)
    """

    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        self.__get = fget
        self.__set = fset
        self.__del = fdel
        self.__doc__ = doc or fget.__doc__
        self.__name__ = fget.__name__
        self.__module__ = fget.__module__

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        try:
            return obj.__dict__[self.__name__]
        except KeyError:
            value = obj.__dict__[self.__name__] = self.__get(obj)
            return value

    def __set__(self, obj, value):
        if obj is None:
            return self
        if self.__set is not None:
            value = self.__set(obj, value)
        obj.__dict__[self.__name__] = value

    def __delete__(self, obj, _sentinel=object()):
        if obj is None:
            return self
        value = obj.__dict__.pop(self.__name__, _sentinel)
        if self.__del is not None and value is not _sentinel:
            self.__del(obj, value)

    def setter(self, fset):
        return self.__class__(self.__get, fset, self.__del)

    def deleter(self, fdel):
        return self.__class__(self.__get, self.__set, fdel)


class ImportFromStringError(Exception):
    pass


def import_string(dotted_path):
    """
    Import a dotted module path and return the attribute/class designated by the
    last name in the path. Raise ImportError if the import failed.
    """
    try:
        if not isinstance(dotted_path, str):
            return dotted_path
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError as err:
        raise ImportError("%s doesn't look like a module path" % dotted_path) from err

    module = importlib.import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as err:
        raise ImportError('Module "%s" does not define a "%s" attribute/class' % (
            module_path, class_name)
        ) from err


def import_from_string(import_str):
    if not isinstance(import_str, str):
        return import_str

    module_str, _, attrs_str = import_str.partition(":")
    if not module_str or not attrs_str:
        message = (
            'Import string "{import_str}" must be in format "<module>:<attribute>".'
        )
        raise ImportFromStringError(message.format(import_str=import_str))

    try:
        module = importlib.import_module(module_str)
    except ImportError as exc:
        if exc.name != module_str:
            raise exc from None
        message = 'Could not import module "{module_str}".'
        raise ImportFromStringError(message.format(module_str=module_str))

    instance = module
    try:
        for attr_str in attrs_str.split("."):
            instance = getattr(instance, attr_str)
    except AttributeError as exc:
        message = 'Attribute "{attrs_str}" not found in module "{module_str}".'
        raise ImportFromStringError(
            message.format(attrs_str=attrs_str, module_str=module_str)
        )

    return instance


def get_root_path(import_name):
    """Returns the path to a package or cwd if that cannot be found.  This
    returns the path of a package or the folder that contains a module.

    Not to be confused with the package path returned by :func:`find_package`.
    """
    # Module already imported and has a file attribute.  Use that first.
    mod = sys.modules.get(import_name)
    if mod is not None and hasattr(mod, '__file__'):
        return os.path.dirname(os.path.abspath(mod.__file__))

    # Next attempt: check the loader.
    loader = pkgutil.get_loader(import_name)

    # Loader does not exist or we're referring to an unloaded main module
    # or a main module without path (interactive sessions), go with the
    # current working directory.
    if loader is None or import_name == '__main__':
        return os.getcwd()

    # For .egg, zipimporter does not have get_filename until Python 2.7.
    # Some other loaders might exhibit the same behavior.
    if hasattr(loader, 'get_filename'):
        filepath = loader.get_filename(import_name)
    else:
        # Fall back to imports.
        __import__(import_name)
        mod = sys.modules[import_name]
        filepath = getattr(mod, '__file__', None)

        # If we don't have a filepath it might be because we are a
        # namespace package.  In this case we pick the root path from the
        # first module that is contained in our package.
        if filepath is None:
            raise RuntimeError('No root path can be found for the provided '
                               'module "%s".  This can happen because the '
                               'module came from an import hook that does '
                               'not provide file name information or because '
                               'it\'s a namespace package.  In this case '
                               'the root path needs to be explicitly '
                               'provided.' % import_name)

    # filepath is import_name.py for a module, or __init__.py for a package.
    return os.path.dirname(os.path.abspath(filepath))


def check_serialize(data):
    try:
        json.dumps(data)
        return True
    except:
        return False


def has_message_body(status):
    """
    According to the following RFC message body and length SHOULD NOT
    be included in responses status 1XX, 204 and 304.
    https://tools.ietf.org/html/rfc2616#section-4.4
    https://tools.ietf.org/html/rfc2616#section-4.3
    """
    return status not in (204, 304) and not (100 <= status < 200)


def is_entity_header(header):
    """Checks if the given header is an Entity Header"""
    return header.lower() in _ENTITY_HEADERS


def remove_entity_headers(headers, allowed=("content-location", "expires")):
    """
    Removes all the entity headers present in the headers given.
    According to RFC 2616 Section 10.3.5,
    Content-Location and Expires are allowed as for the
    "strong cache validator".
    https://tools.ietf.org/html/rfc2616#section-10.3.5

    returns the headers without the entity headers
    """
    allowed = set([h.lower() for h in allowed])
    headers = {
        header: value
        for header, value in headers.items()
        if not is_entity_header(header) or header.lower() in allowed
    }
    return headers


def set_query_parameter(url, param_name, param_value):
    scheme, netloc, path, query_string, fragment = urlsplit(url)
    query_params = parse_qs(query_string)

    query_params[param_name] = [param_value]
    new_query_string = urlencode(query_params, doseq=True)

    return urlunsplit((scheme, netloc, path, new_query_string, fragment))


def get_request_url(request, root_only=False, strip_querystring=False):
    scheme = request.scheme
    path = request.root_path + request.path
    query_string = request.query_string
    host_header = None
    if root_only:
        path, query_string = '/', ''
    for key, value in request.headers.items():
        if key == 'host':
            host_header = value
            break

    if host_header:
        url = f"{scheme}://{host_header}{path}"
    else:
        host, port = request.server
        default_port = {"http": 80, "https": 443, "ws": 80, "wss": 443}[scheme]
        if port == default_port:
            url = f"{scheme}://{host}{path}"
        else:
            url = f"{scheme}://{host}:{port}{path}"
    if query_string and not strip_querystring:
        url += "?" + query_string
    return url


def parse_options_header(value, multiple=False):
    if not value:
        return '', {}
    result = []
    value = "," + value.replace("\n", ",")

    def unquote_header_value(val, is_filename=False):
        if val and val[0] == val[-1] == '"':
            val = val[1:-1]
            if not is_filename or val[:2] != '\\\\':
                return val.replace('\\\\', '\\').replace('\\"', '"')
        return val

    while value:
        match = _option_header_start_mime_type.match(value)
        if not match:
            break
        result.append(match.group(1))  # mimetype
        options = {}
        # Parse options
        rest = match.group(2)
        while rest:
            optmatch = _option_header_piece_re.match(rest)
            if not optmatch:
                break
            option, encoding, _, option_value = optmatch.groups()
            option = unquote_header_value(option)
            if option_value is not None:
                option_value = unquote_header_value(
                    option_value,
                    option == 'filename')
                if encoding is not None:
                    option_value = unquote_to_bytes(option_value).decode(encoding)
            options[option] = option_value
            rest = rest[optmatch.end():]
        result.append(options)
        if multiple is False:
            return tuple(result)
        value = rest

    return tuple(result) if result else ('', {})


def method_dispatch(func):
    dispatcher = singledispatch(func)

    def wrapper(*args, **kw):
        return dispatcher.dispatch(args[1].__class__)(*args, **kw)
    wrapper.register = dispatcher.register
    update_wrapper(wrapper, func)
    return wrapper


def _dump_loader_info(loader):
    yield 'class: %s.%s' % (type(loader).__module__, type(loader).__name__)
    for key, value in sorted(loader.__dict__.items()):
        if key.startswith('_'):
            continue
        if isinstance(value, (tuple, list)):
            if not all(isinstance(x, str) for x in value):
                continue
            yield '%s:' % key
            for item in value:
                yield '  - %s' % item
            continue
        elif not isinstance(value, (str, int, float, bool)):
            continue
        yield '%s: %r' % (key, value)


def explain_template_loading_attempts(app, template, attempts):
    """This should help developers understand what failed"""
    info = ['Locating template "%s":' % template]
    total_found = 0
    blueprint = None
    reqctx = _request_ctx_stack.top
    if reqctx is not None and reqctx.request.blueprint is not None:
        blueprint = reqctx.request.blueprint

    for idx, (loader, srcobj, triple) in enumerate(attempts):
        if isinstance(srcobj, Flask):
            src_info = 'application "%s"' % srcobj.import_name
        elif isinstance(srcobj, Blueprint):
            src_info = 'blueprint "%s" (%s)' % (srcobj.name,
                                                srcobj.import_name)
        else:
            src_info = repr(srcobj)

        info.append('% 5d: trying loader of %s' % (
            idx + 1, src_info))

        for line in _dump_loader_info(loader):
            info.append('       %s' % line)

        if triple is None:
            detail = 'no match'
        else:
            detail = 'found (%r)' % (triple[1] or '<string>')
            total_found += 1
        info.append('       -> %s' % detail)

    seems_fishy = False
    if total_found == 0:
        info.append('Error: the template could not be found.')
        seems_fishy = True
    elif total_found > 1:
        info.append('Warning: multiple loaders returned a match for the template.')
        seems_fishy = True

    if blueprint is not None and seems_fishy:
        info.append('  The template was looked up from an endpoint that '
                    'belongs to the blueprint "%s".' % blueprint)
        info.append('  Maybe you did not place a template in the right folder?')
        info.append('  See http://flask.pocoo.org/docs/blueprints/#templates')

    app.logger.info('\n'.join(info))
