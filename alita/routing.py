import re
import attr
from enum import Enum
from alita.base import BaseRoute, BaseRouter
from alita.converters import CONVERTER_TYPES
from urllib.parse import urljoin
from alita.helpers import get_request_url, set_query_parameter
from alita.exceptions import NotFound, BadRequest


class NoMatchFound(NotFound):
    pass


class Match(Enum):
    NONE = 0
    PARTIAL = 1
    FULL = 2


def replace_params(path, param_converters, path_params):
    for key, value in list(path_params.items()):
        if "{" + key + "}" in path:
            converter = param_converters[key]
            value = converter.to_string(value)
            path = path.replace("{" + key + "}", value)
            path_params.pop(key)
    for key, value in path_params.items():
        path = set_query_parameter(path, key, value)
    return path


# Match parameters in URL paths, eg. '<param_name:int/float/str/path>'
PARAM_REGEX = re.compile("<([a-zA-Z_][a-zA-Z0-9_]*)(:[a-zA-Z_][a-zA-Z0-9_]*)?>")


def compile_path(path):
    path_regex = "^"
    path_format = ""

    idx = 0
    param_converters = {}
    for match in PARAM_REGEX.finditer(path):
        param_name, converter_type = match.groups("str")
        converter_type = converter_type.lstrip(":")
        if converter_type not in CONVERTER_TYPES:
            raise RuntimeError(f"Unknown path converter '{converter_type}'")
        converter = CONVERTER_TYPES[converter_type]
        path_regex += path[idx: match.start()]
        path_regex += f"(?P<{param_name}>{converter.regex})"
        path_format += path[idx: match.start()]
        path_format += "{%s}" % param_name
        param_converters[param_name] = converter
        idx = match.end()

    path_regex += path[idx:] + "$"
    path_format += path[idx:]
    return re.compile(path_regex), path_format, param_converters


class URLPath:
    def __init__(self, path, protocol="http", host="", params=None):
        self.path = path
        self.protocol = protocol
        self.host = host
        self.params = params or {}
        assert protocol in ("http", "websocket")

    def make_url(self, base_url='/', request=None):
        if request is not None:
            assert not base_url, 'Cannot set both "base_url" and "request".'
            return get_request_url(request)
        elif base_url:
            assert not request, 'Cannot set both "request" and "**components".'
            return urljoin(base_url, self.path)
        else:
            raise ValueError('base_url or request need supply one.')


@attr.s
class RouteMatch:
    status = attr.ib(validator=attr.validators.instance_of(Match))
    endpoint = attr.ib(validator=attr.validators.instance_of(str))
    view_func = attr.ib()
    path_params = attr.ib(validator=attr.validators.instance_of(dict))


class Route(BaseRoute):
    def __init__(self, path, endpoint, view_func, methods=None):
        assert path.startswith("/"), "Routed paths must start with '/'"
        self.path = path
        self.endpoint = endpoint
        self.view_func = view_func
        methods = methods or getattr(view_func, 'methods', None) or ('GET',)
        self.methods = set([method.upper() for method in methods])
        if "GET" in self.methods:
            self.methods |= set(["HEAD"])

        self.path_regex, self.path_format, self.param_converters = compile_path(path)

    def match(self, request):
        if request.scheme in ("http", "https", "wss", "ws"):
            match = self.path_regex.match(request.path)
            if not match:
                raise NoMatchFound()
            matched_params = match.groupdict()
            for key, value in matched_params.items():
                matched_params[key] = self.param_converters[key].convert(value)
            if self.methods and request.method not in self.methods:
                status = Match.PARTIAL
            else:
                status = Match.FULL
            return RouteMatch(
                status,
                self.endpoint,
                self.view_func,
                matched_params,
            )
        else:
            raise NoMatchFound()

    def url_path_for(self, endpoint, **path_params):
        seen_keys = set(path_params.keys())
        expected_keys = set(self.param_converters.keys())
        if endpoint != self.endpoint:
            raise NoMatchFound()
        if expected_keys and not seen_keys.issuperset(expected_keys):
            raise NoMatchFound()
        path = replace_params(self.path_format, self.param_converters, path_params)
        return URLPath(path=path, protocol="http", params=path_params)

    def __eq__(self, other):
        return (
            isinstance(other, Route)
            and self.path == other.path
            and self.endpoint == other.endpoint
            and self.methods == other.methods
        )


class Router(BaseRouter):
    def __init__(self, app, routes=None):
        self.app = app
        self.routes = routes or []

    def add_route(self, path, endpoint, view_func, methods=None):
        route = Route(
            path,
            endpoint=endpoint,
            view_func=view_func,
            methods=methods,
        )
        self.routes.append(route)

    def match(self, request):
        for route in self.routes:
            try:
                route_math = route.match(request)
                if route_math.status == Match.PARTIAL:
                    raise BadRequest()
                return route_math
            except NoMatchFound:
                pass
        raise NoMatchFound()

    def url_path_for(self, endpoint, **path_params):
        for route in self.routes:
            try:
                return route.url_path_for(endpoint, **path_params)
            except NoMatchFound:
                pass
        raise NoMatchFound()
