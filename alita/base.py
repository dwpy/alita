import os
import sys
import json
import http.cookies
from urllib import parse
from multidict import CIMultiDict
from alita.serve import STATUS_TEXT
from alita.helpers import get_request_url
from alita.helpers import cached_property, to_unicode, \
    has_message_body, remove_entity_headers, parse_options_header


class JSONSerializer:
    """
    Simple wrapper around json to be used in signing.dumps and
    signing.loads.
    """
    def dumps(self, obj):
        return json.dumps(obj, separators=(',', ':'))

    def loads(self, data):
        return json.loads(data)


class BaseFactory:

    def create_request_object(self, environ):
        raise NotImplementedError

    def create_base_response_class(self):
        raise NotImplementedError

    def create_base_exception_class(self):
        raise NotImplementedError

    def create_exception_handler_object(self):
        raise NotImplementedError

    def create_router_object(self):
        raise NotImplementedError


class BaseRequest(object):
    charset = 'utf-8'
    encoding_errors = 'replace'

    def __init__(self, app, environ, headers=None):
        # Request state
        self.app = app
        self.environ = environ
        self.headers = CIMultiDict(headers or {})

        # Response state
        self._cookies = None
        self._cached_data = None
        self._parsed_content_type = None
        self.disconnected = False
        self.response_complete = False
        self.match_headers()

    @property
    def META(self):
        return dict(self.headers, **self.environ)

    def match_headers(self):
        for value in self.environ["headers"]:
            self.headers[value[0]] = value[1]

    @property
    def content_type(self):
        """Like :attr:`content_type`, but without parameters (eg, without
        charset, type etc.) and always lowercase.  For example if the content
        type is ``text/HTML; charset=utf-8`` the mimetype would be
        ``'text/html'``.
        """
        if self.headers.get('content-type'):
            self._parsed_content_type = parse_options_header(self.headers['content-type'])
        else:
            self._parsed_content_type = parse_options_header(self.headers.get('accept', ''))
        return self._parsed_content_type[0].lower()

    @cached_property
    def cookies(self):
        if self._cookies is None:
            cookies = {}
            cookie_header = self.headers.get("cookie")
            if cookie_header:
                cookie = http.cookies.SimpleCookie()
                cookie.load(cookie_header)
                for key, morsel in cookie.items():
                    cookies[key] = morsel.value
            self._cookies = cookies
        return self._cookies

    def get_host(self):
        if self.headers.get(self.app.config['FORWARDED_FOR_HEADER']):
            rv = self.headers[self.app.config['FORWARDED_FOR_HEADER']].split(',', 1)[0].strip()
        elif self.headers.get(self.app.config['HTTP_HOST']):
            rv = self.headers[self.app.config['HTTP_HOST']]
        elif self.headers.get('host'):
            rv = self.headers['host'].split(':', 1)[0].strip()
        else:
            rv = self.environ.get('host')
        return rv

    @cached_property
    def version(self):
        """
        The http request version.
        """
        return self.environ.get("http_version", "1.1")

    @cached_property
    def path(self):
        """
        Requested path as unicode.  This works a bit like the regular path
        info in the WSGI environment but will always include a leading slash,
        even if the URL root is accessed.
        """
        raw_path = self.environ.get('path') or ''
        return '/' + raw_path.lstrip('/')

    @property
    def url_charset(self):
        """
        The charset that is assumed for URLs.  Defaults to the value
        of :attr:`charset`.

        .. versionadded:: 0.6
        """
        return self.charset

    @cached_property
    def full_path(self):
        """
        Requested path as unicode, including the query string.
        """
        return self.path + u'?' + to_unicode(self.query_string, self.url_charset)

    @cached_property
    def body(self):
        """
        The reconstructed current URL as IRI.
        """
        return self.environ.get("body")

    @cached_property
    def data(self):
        return self.get_data()

    @cached_property
    def form(self):
        return self.get_data(parse_form_data=True)

    @cached_property
    def url(self):
        """
        The reconstructed current URL as IRI.
        """
        return self.environ.get("url")

    @cached_property
    def base_url(self):
        """
        Like :attr:`url` but without the querystring
        """
        return get_request_url(self, strip_querystring=True)

    @cached_property
    def root_url(self):
        """
        The full URL root (with hostname), this is the application
        root as IRI.
        """
        return get_request_url(self, root_only=True)

    @cached_property
    def ip(self):
        """
        Just the host including the ip if available.
        """
        return self.environ.get("ip")

    @cached_property
    def host(self):
        """
        Just the host including the host if available.
        """
        return self.get_host()

    @cached_property
    def port(self):
        """
        Just the host including the port if available.
        """
        return self.environ.get("port")

    @cached_property
    def query_string(self):
        """
        Just the request query string.
        """
        return self.environ.get("query_string")

    @cached_property
    def args(self):
        """
        Just the request query string.
        """
        return dict(parse.parse_qsl(parse.urlsplit(self.full_path).query))

    @cached_property
    def method(self):
        """
        Just the request method string.
        """
        return self.environ.get("method")

    @cached_property
    def scheme(self):
        """
        Just the request scheme string.
        """
        return self.environ.get("scheme")

    @cached_property
    def server(self):
        """
        Just the request server string.
        """
        return self.environ.get("server")

    @cached_property
    def client(self):
        """
        Just the request client string.
        """
        return self.environ.get("client")

    @cached_property
    def remote_addr(self):
        return self.headers.get(self.app.config['REAL_IP_HEADER']) \
               or self.headers.get(self.app.config['FORWARDED_FOR_HEADER']) \
               or self.headers.get(self.app.config['REMOTE_ADDR'])

    @cached_property
    def root_path(self):
        """
        Just the request root_path string.
        """
        return self.environ.get("root_path")

    @cached_property
    def transport(self):
        """
        Just the request transport string.
        """
        return self.environ.get("transport")

    def get_data(self, cache=True, as_text=False, parse_form_data=False):
        rv = getattr(self, '_cached_data', None)
        if rv is None:
            rv = self.body
            if cache:
                self._cached_data = rv
        if as_text:
            rv = rv.decode(self.charset, self.encoding_errors)
        return rv


class BaseResponse:
    __slots__ = ("body", "status", "content_type", "headers", "_cookies", "_protocol")

    charset = 'utf-8'
    max_cookie_size = 4093

    def __init__(self, body=None, status=200, headers=None, content_type="text/plain"):
        self.content_type = content_type
        self.body = self._encode_body(body)
        self.status = status
        self.headers = CIMultiDict(headers or {})
        self._cookies = None
        self._protocol = None

    def set_protocol(self, protocol):
        self._protocol = protocol

    def has_protocol(self):
        return self._protocol is not None

    @staticmethod
    def _encode_body(data):
        try:
            if not isinstance(data, bytes):
                return data.encode()
            return data
        except AttributeError:
            return str(data or "").encode()

    def _parse_headers(self):
        headers = b""
        for name, value in self.headers.items():
            try:
                headers += b"%b: %b\r\n" % (
                    name.encode(),
                    value.encode(self.charset),
                )
            except AttributeError:
                headers += b"%b: %b\r\n" % (
                    str(name).encode(),
                    str(value).encode(self.charset),
                )
        return headers

    def set_cookie(self, key, value="", max_age=None, expires=None, path="/",
                   domain=None, secure=False, httponly=False, samesite=None):
        cookie = http.cookies.SimpleCookie()
        cookie[key] = value
        if max_age is not None:
            cookie[key]["max-age"] = max_age  # type: ignore
        if expires is not None:
            cookie[key]["expires"] = expires  # type: ignore
        if path is not None:
            cookie[key]["path"] = path
        if domain is not None:
            cookie[key]["domain"] = domain
        if secure:
            cookie[key]["secure"] = True
        if httponly:
            cookie[key]["httponly"] = True
        if samesite:
            cookie[key]["samesite"] = samesite
        cookie_val = cookie.output(header="").strip()
        self.headers.add('Set-Cookie', cookie_val)

    def delete_cookie(self, key, path="/", domain=None):
        self.set_cookie(key, expires=0, max_age=0, path=path, domain=domain)

    def get_headers(self, version="1.1", keep_alive=False, keep_alive_timeout=None):
        timeout_header = b""
        if keep_alive and keep_alive_timeout is not None:
            timeout_header = b"Keep-Alive: %d\r\n" % keep_alive_timeout
        self.headers["Content-Type"] = self.headers.get(
            "Content-Type", self.content_type
        )
        if self.status in (304, 412):
            self.headers = remove_entity_headers(self.headers)
        headers = self._parse_headers()
        if self.status is 200:
            description = b"OK"
        else:
            description = STATUS_TEXT.get(self.status, b"UNKNOWN RESPONSE")

        return (
            b"HTTP/%b %d %b\r\n" b"Connection: %b\r\n" b"%b" b"%b\r\n"
        ) % (
            version.encode(),
            self.status,
            description,
            b"keep-alive" if keep_alive else b"close",
            timeout_header,
            headers
        )

    async def output(self, version="1.1", keep_alive=False, keep_alive_timeout=None):
        if has_message_body(self.status):
            body = self.body
            self.headers["Content-Length"] = self.headers.get(
                "Content-Length", len(self.body)
            )
        else:
            body = b""
        return self.get_headers(
            version,
            keep_alive,
            keep_alive_timeout
        ) + b"%b" % body


class BaseHTTPException(Exception):
    """
    Baseclass for all HTTP exceptions.  This exception can be called as WSGI
    application to render a default error page or you can catch the subclasses
    of it independently and render nicer error messages.
    """

    code = None
    description = None

    def __init__(self, description=None, response=None, code=None):
        super().__init__(self)
        if code is not None:
            self.code = code
        if description is not None:
            self.description = description
        self.response = response

    @classmethod
    def wrap(cls, exception, name=None):
        """
        This method returns a new subclass of the exception provided that
        also is a subclass of `BadRequest`.
        """
        class newcls(cls, exception):

            def __init__(self, arg=None, *args, **kwargs):
                cls.__init__(self, *args, **kwargs)
                exception.__init__(self, arg)
        newcls.__module__ = sys._getframe(1).f_globals.get('__name__')
        newcls.__name__ = name or cls.__name__ + exception.__name__
        return newcls

    @property
    def name(self):
        """
        The status name.
        """
        return STATUS_TEXT.get(self.code, 'Unknown Error')

    def __call__(self, environ, start_response):
        """
        Call the exception as WSGI application.

        :param environ: the WSGI environment.
        :param start_response: the response callable provided by the WSGI
                               server.
        """
        response = self.get_response(environ)
        return response(environ, start_response)

    def __str__(self):
        code = self.code if self.code is not None else '???'
        return '%s %s: %s' % (code, self.name, self.description)

    def __repr__(self):
        code = self.code if self.code is not None else '???'
        return "<%s '%s: %s'>" % (self.__class__.__name__, code, self.name)

    def get_description(self, environ=None):
        raise NotImplementedError

    def get_body(self, environ=None):
        raise NotImplementedError

    def get_response(self, environ=None):
        raise NotImplementedError

    def get_headers(self, environ=None):
        raise NotImplementedError


class BaseMiddleware:
    def __init__(self, app):
        self.app = app

    async def process_request(self, request):
        pass

    async def process_response(self, request, response):
        return response


class BaseExceptionHandler:
    def __init__(self, app=None):
        self.app = app

    def process_exception(self, request, exc):
        raise NotImplementedError


class BaseBlueprint:
    def register(self, app, **options):
        raise NotImplementedError

    def add_url_rule(self, rule, view_func, **options):
        raise NotImplementedError

    def before_request(self, f):
        pass

    def after_request(self, f):
        pass


class BaseRoute:
    def match(self, request):
        raise NotImplementedError()

    def url_path_for(self, endpoint, **path_params):
        raise NotImplementedError()


class BaseRouter:
    def match(self, request):
        raise NotImplementedError()

    def add_route(self, path, endpoint, view_func, methods=None):
        raise NotImplementedError()

    def url_path_for(self, endpoint, **path_params):
        raise NotImplementedError()


class BaseConverter:
    regex = ""

    def convert(self, value):
        raise NotImplementedError()

    def to_string(self, value):
        raise NotImplementedError()


class BaseStaticHandler:
    def __init__(self, app):
        self.app = app
        self.static_folder = self.app.static_folder
        self.static_url_path = self.app.static_url_path
        self.send_file_max_age = self.app.send_file_max_age
        if self.static_folder:
            self.app.add_url_rule(
                self.send_static_file,
                self.get_static_url_path() + '/<file_name:path>',
                endpoint='static'
            )

    @property
    def has_static_folder(self):
        return self.static_folder is not None

    def get_static_url_path(self):
        if self.static_url_path is not None:
            return self.static_url_path

        if self.static_folder is not None:
            return '/' + os.path.basename(self.static_folder)

    async def send_static_file(self, request, file_name):
        raise NotImplementedError()
