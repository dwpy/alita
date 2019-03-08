import os
import six
import sys
import inspect
import logging
import warnings
import itertools
import traceback
import alita.signals as signals
from alita.serve import *
from inspect import isawaitable
from alita.datastructures import ImmutableDict
from alita.config import Config, ConfigAttribute
from alita.factory import AppFactory
from alita.utils import import_string, ImportFromStringError, check_serialize
from alita.base import BaseMiddleware
from alita.response import HtmlResponse, JsonResponse
from alita.exceptions import InternalServerError


class Alita(object):
    config_class = Config
    _default_factory_class = AppFactory
    _view_middleware = []

    app_factory_class = None
    response_class = None
    exception_class = None

    key_prefix = ConfigAttribute('SESSION_KEY_PREFIX')
    session_use_signer = ConfigAttribute('SESSION_USE_SIGNER')
    session_engine = ConfigAttribute('SESSION_ENGINE')
    session_cookie_name = ConfigAttribute('SESSION_COOKIE_NAME')
    session_cookie_path = ConfigAttribute('SESSION_COOKIE_PATH')
    session_cookie_domain = ConfigAttribute('SESSION_COOKIE_DOMAIN')
    session_save_every_request = ConfigAttribute('SESSION_SAVE_EVERY_REQUEST')
    session_cookie_expire = ConfigAttribute('SESSION_COOKIE_EXPIRE')
    session_engine_config = ConfigAttribute('SESSION_ENGINE_CONFIG')
    session_table_name = ConfigAttribute('SESSION_TABLE_NAME')
    send_file_max_age = ConfigAttribute('SEND_FILE_MAX_AGE')

    default_config = ImmutableDict({
        'DEBUG': False,
        'PROPAGATE_EXCEPTIONS': None,
        'PRESERVE_CONTEXT_ON_EXCEPTION': None,
        'SECRET_KEY': None,
        'SESSION_COOKIE_EXPIRE': 30 * 24 * 60 * 60,
        'USE_X_SENDFILE': False,
        'SERVER_NAME': None,
        'APPLICATION_ROOT': '/',
        'SESSION_COOKIE_NAME': 'sessionid',
        'SESSION_COOKIE_DOMAIN': None,
        'SESSION_COOKIE_PATH': None,
        'SESSION_COOKIE_HTTPONLY': True,
        'SESSION_COOKIE_SECURE': False,
        'SESSION_COOKIE_SAMESITE': None,
        'SESSION_KEY_PREFIX': '',
        'SESSION_USE_SIGNER': False,
        'SESSION_REFRESH_EACH_REQUEST': True,
        'MAX_CONTENT_LENGTH': None,
        'SEND_FILE_MAX_AGE': 12 * 60 * 60,
        'TRAP_BAD_REQUEST_ERRORS': None,
        'TRAP_HTTP_EXCEPTIONS': False,
        'EXPLAIN_TEMPLATE_LOADING': False,
        'PREFERRED_URL_SCHEME': 'http',
        'JSON_AS_ASCII': True,
        'JSON_SORT_KEYS': True,
        'JSONIFY_PRETTYPRINT_REGULAR': False,
        'JSONIFY_MIMETYPE': 'application/json',
        'TEMPLATES_AUTO_RELOAD': None,
        'MAX_COOKIE_SIZE': 4093,
        'SESSION_SAVE_EVERY_REQUEST': False,
        'SESSION_EXPIRE_AT_BROWSER_CLOSE': False,
        'SESSION_MUST_SAVE': True,
        'SESSION_TABLE_NAME': 'session',
        "SESSION_ENGINE": "alita.contrib.sessions.backends.mysql",
        # 'SESSION_ENGINE_CONFIG': {
        #     'db': 'gezi',
        #     'host': '192.168.4.5',
        # },
        'SESSION_ENGINE_CONFIG': {
            'host': '192.168.4.5',
            'port': 3306,
            'username': 'root',
            'password': 'tianfu',
            'database': 'gezi'
        },
        'MIDDLEWARE': [
            "alita.contrib.sessions.middleware.SessionMiddleware"
        ],
    })

    def __init__(self, name=None, subdomain_matching=False, static_folder=None,
                 static_url_path=None):
        self.name = name
        self.view_functions = {}
        self.static_folder = static_folder
        self.static_url_path = static_url_path
        self.subdomain_matching = subdomain_matching
        self.config = None
        self.is_running = False
        self.make_config()

        self.before_request_funcs = {}
        self.after_request_funcs = {}
        self.error_handler_spec = {}
        self.blueprints = {}
        self.logger = logging.getLogger(__name__)
        self.load_middleware()

        self.app_factory_class = import_string(self.config.get(
            "APP_FACTORY_CLASS", self._default_factory_class))
        self.app_factory = self.app_factory_class(self)
        self.exception_handler = None
        self.static_handler = None
        self.router = None
        self.make_factory()

    @property
    def debug(self):
        return self.config['DEBUG']

    def load_middleware(self):
        """
        Populate middleware lists from settings.MIDDLEWARE.

        Must be called after the environment is fixed (see __call__ in subclasses).
        """
        self._view_middleware = []
        for middleware_path in reversed(self.config['MIDDLEWARE']):
            try:
                middleware_class = import_string(middleware_path)
                if not issubclass(middleware_class, BaseMiddleware):
                    raise TypeError('Middleware class must implement by '
                                    'BaseMiddleware: %r', middleware_path)
                self._view_middleware.append(middleware_class(self))
            except ImportFromStringError as exc:
                self.logger.debug('Middleware import error: %r', middleware_path)
                raise exc

    def register_middleware(self, middleware_class):
        if middleware_class in self._view_middleware:
            raise Exception("register middleware repeated!")
        self._view_middleware.append(middleware_class(self))

    async def process_request_middleware(self, request):
        for middleware in self._view_middleware:
            await middleware.process_request(request)

    async def process_response_middleware(self, request, response):
        for middleware in self._view_middleware:
            response = await middleware.process_response(request, response)
        return response

    def before_request(self, f):
        self.before_request_funcs.setdefault(None, []).append(f)
        return f

    def after_request(self, f):
        self.after_request_funcs.setdefault(None, []).append(f)
        return f

    def make_config(self):
        defaults = dict(self.default_config)
        self.config = self.config_class(defaults)

    def config_from_py(self, filename, silent=False):
        self.config.from_pyfile(filename, silent)

    def config_from_json(self, filename, silent=False):
        self.config.from_json(filename, silent)

    def config_from_object(self, filename, silent=False):
        self.config.from_object(filename, silent)

    def make_factory(self):
        self.response_class = self.app_factory.create_base_response_class()
        self.exception_class = self.app_factory.create_base_exception_class()
        self.exception_handler = self.app_factory.create_exception_handler_object()
        self.router = self.app_factory.create_router_object()
        self.static_handler = self.app_factory.create_static_handler()

    def error_handler(self, code_or_exception):
        def decorator(func):
            self.register_error_handler(code_or_exception, func)
            return func
        return decorator

    def register_error_handler(self, code_or_exception, func):
        if isinstance(code_or_exception, int):
            self.exception_handler.add_status_handler(code_or_exception, func)
        elif isinstance(code_or_exception, Exception):
            self.exception_handler.add_exception_handler(code_or_exception, func)
        else:
            raise ValueError("decorator error handler code or exception "
                             "is invalid int or exception type!")

    @staticmethod
    def get_endpoint_from_view_func(view_func):
        return view_func.__name__

    def add_url_rule(self, rule, view_func, endpoint=None, methods=None):
        if endpoint is None:
            endpoint = self.get_endpoint_from_view_func(view_func)
        if methods is None:
            methods = getattr(view_func, 'methods', None) or ('GET',)
        elif isinstance(methods, str):
            methods = [methods]
        assert isinstance(methods, (tuple, list))
        methods = set(item.upper() for item in methods)
        self.router.add_route(rule, endpoint, view_func, methods)
        old_func = self.view_functions.get(endpoint)
        if old_func is not None and old_func != view_func:
            raise AssertionError('View function mapping is overwriting an '
                                 'existing endpoint function: %s' % endpoint)
        if not inspect.iscoroutinefunction(view_func):
            warnings.warn("View function [%s] should be async function" % view_func.__name__)
        self.view_functions[endpoint] = view_func

    def route(self, rule, **options):
        def decorator(f):
            self.add_url_rule(rule, f, **options)
            return f
        return decorator

    def run(self, **kwargs):
        config = ServerConfig(**kwargs)
        server = Server(self, config=config)
        server.run()

    async def preprocess_request(self, request):
        bp = request.blueprint
        funcs = self.before_request_funcs.get(None, [])
        if bp is not None and bp in self.before_request_funcs:
            funcs = itertools.chain(funcs, self.before_request_funcs[bp])
        for func in funcs:
            rv = self.get_awaitable_result(func)
            if rv is not None:
                return rv

    async def dispatch_request(self, request):
        if request.routing_exception is not None:
            raise request.routing_exception
        route_match = request.route_match
        return await self.get_awaitable_result(
            route_match.view_func,
            request, **route_match.path_params
        )

    async def make_response(self, response):
        return response

    async def get_awaitable_result(self, func, *args, **kwargs):
        func_result = func(*args, **kwargs)
        if isawaitable(func_result):
            return await func_result
        else:
            return func_result

    async def process_response(self, request, response):
        bp = request.blueprint
        funcs = self.after_request_funcs.get(None, [])
        if bp is not None and bp in self.after_request_funcs:
            funcs = itertools.chain(funcs, self.after_request_funcs[bp])
        for func in funcs:
            response = self.get_awaitable_result(func)
        return response

    async def finalize_response(self, response):
        if isinstance(response, self.response_class):
            pass
        elif isinstance(response, self.exception_class):
            return response.get_response()
        elif isinstance(response, six.string_types):
            return HtmlResponse(response)
        elif check_serialize(response):
            return JsonResponse(response)
        else:
            raise Exception("Response Object Type invalid!")
        return response

    async def finalize_request(self, request, response, from_error_handler=False):
        response = await self.make_response(response)
        try:
            response = await self.process_response(request, response)
            signals.request_finished.send(self, response=response)
        except Exception as ex:
            if not from_error_handler:
                raise ex
            self.logger.exception('Request finalizing failed with an '
                                  'error while handling an error')
        return response

    async def make_dispatch_request_exception(self, exp):
        self.logger.error(str(exp))
        self.logger.exception(traceback.format_exc())
        return InternalServerError(description=traceback.format_exc())

    async def full_dispatch_request(self, request):
        try:
            signals.request_started.send(self)
            await self.process_request_middleware(request)
            response = await self.preprocess_request(request)
            if response is None:
                response = await self.dispatch_request(request)
            response = await self.finalize_request(request, response)
            response = await self.finalize_response(response)
            return await self.process_response_middleware(request, response)
        except Exception as ex:
            exception = await self.exception_handler.process_exception(request, ex)
            raise exception

    async def create_request(self, environ):
        return self.app_factory.create_request_object(environ)

    async def __call__(self, environ, on_response):
        request, response = None, None
        try:
            request = await self.create_request(environ)
            response = await self.full_dispatch_request(request)
        except Exception as ex:
            exception = await self.exception_handler.process_exception(request, ex)
            if isinstance(exception, self.exception_class):
                response = exception.get_response()
            elif isinstance(exception, self.response_class):
                response = exception
            else:
                response = None
        if response:
            await on_response(response)
        else:
            message = "Caught handled exception, response object empty."
            self.logger.error(message)
            await on_response(self.exception_handler.ruder_error_response(
                request, RuntimeError(message)))

    def log_exception(self, request, exc_info):
        self.logger.error('Exception on %s [%s]' % (
            request.path,
            request.method
        ), exc_info=exc_info)

    def register_blueprint(self, blueprint, **options):
        if blueprint.name in self.blueprints:
            raise RuntimeError("blueprint %s has registered to app. "
                               "not allow repeat register." % blueprint.name)
        else:
            self.blueprints[blueprint.name] = blueprint
        blueprint.register(self, **options)

    def url_for(self, request, endpoint, **path_params):
        url_path = self.router.url_path_for(endpoint, **path_params)
        return url_path.make_url(request=request)
