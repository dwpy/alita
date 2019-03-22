import os
import inspect
import logging
import warnings
import itertools
import alita.signals as signals
from alita.serve import *
from inspect import isawaitable
from alita.datastructures import ImmutableDict
from alita.config import Config, ConfigAttribute
from alita.factory import AppFactory
from alita.helpers import import_string, cached_property, method_dispatch
from alita.response import TextResponse, JsonResponse
from alita.exceptions import ServerError
from collections import UserDict
from alita.templating import Environment
from jinja2 import FileSystemLoader


class Alita(object):
    config_class = Config
    _default_factory_class = AppFactory
    _view_middleware = []
    jinja_environment = Environment

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
    max_content_length = ConfigAttribute('MAX_CONTENT_LENGTH')

    default_config = ImmutableDict({
        'DEBUG': False,
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
        'TEMPLATES_AUTO_RELOAD': False,
        'MAX_COOKIE_SIZE': 4093,
        'SESSION_SAVE_EVERY_REQUEST': False,
        'SESSION_EXPIRE_AT_BROWSER_CLOSE': False,
        'SESSION_MUST_SAVE': True,
        'SESSION_TABLE_NAME': 'session',
        "SESSION_ENGINE": None,
        'SESSION_ENGINE_CONFIG': None,
    })

    def __init__(self, name=None, subdomain_matching=False, static_folder=None,
                 static_url_path=None, template_folder='templates'):
        self.name = name
        self.view_functions = {}
        self.static_folder = static_folder
        self.static_url_path = static_url_path
        self.template_folder = template_folder
        self.subdomain_matching = subdomain_matching
        self.config = None
        self.is_running = False
        self.make_config()

        self.before_request_funcs = {}
        self.after_request_funcs = {}
        self.error_handler_spec = {}
        self.blueprints = {}
        self._blueprint_order = []
        self.extensions = UserDict()
        self.logger = logging.getLogger(__name__)

        self.template_context_processors = {
            None: [self._default_template_ctx_processor]
        }
        self.app_factory_class = import_string(self.config.get(
            "APP_FACTORY_CLASS", self._default_factory_class))
        self.app_factory = self.app_factory_class(self)
        self.exception_handler = None
        self.static_handler = None
        self.router = None
        self.make_factory()

    def _get_debug(self):
        return self.config['DEBUG']

    def _set_debug(self, value):
        self.config['DEBUG'] = value
        self.jinja_env.auto_reload = self.templates_auto_reload()

    debug = property(_get_debug, _set_debug)
    del _get_debug, _set_debug

    def request_middleware(self, f):
        self.before_request_funcs.setdefault(None, []).append(f)
        return f

    def response_middleware(self, f):
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

    def add_url_rule(self, view_func, rule, endpoint=None, methods=None):
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
            self.add_url_rule(f, rule,  **options)
            return f
        return decorator

    def run(self, extra_files=None, auto_reload=None, reload_interval=1, **kwargs):
        def inner(loop=None):
            server = Server(self, config=ServerConfig(loop=loop, **kwargs))
            server.run()

        def _log(type, message, *args, **kwargs):
            getattr(self.logger, type)(message.rstrip(), *args, **kwargs)

        if auto_reload and os.environ.get("SERVER_RUN_MAIN") != "true":
            run_auto_reload(extra_files, reload_interval, _log)
        else:
            inner()

    async def preprocess_request(self, request):
        bp = request.blueprint
        funcs = self.before_request_funcs.get(None, [])
        if bp is not None and bp in self.before_request_funcs:
            funcs = itertools.chain(funcs, self.before_request_funcs[bp])
        for func in funcs:
            rv = await self.get_awaitable_result(func, request)
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

    @method_dispatch
    async def make_response(self, response):
        if isinstance(response, self.response_class):
            pass
        elif isinstance(response, self.exception_class):
            return response.get_response()
        else:
            raise ServerError("Response Object Type invalid!")
        return response

    @make_response.register(str)
    async def _(self, text):
        return TextResponse(text)

    @make_response.register(dict)
    async def _(self, json_value):
        return JsonResponse(json_value)

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
            response = await self.get_awaitable_result(func, request, response)
        return response

    async def finalize_response(self, response):
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

    async def full_dispatch_request(self, request):
        try:
            signals.request_started.send(self)
            response = await self.preprocess_request(request)
            if response is None:
                response = await self.dispatch_request(request)
            response = await self.finalize_request(request, response)
            return await self.finalize_response(response)
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
            self._blueprint_order.append(blueprint)
        blueprint.register(self, **options)

    def iter_blueprints(self):
        return iter(self._blueprint_order)

    def url_for(self, request, endpoint, **path_params):
        url_path = self.router.url_path_for(endpoint, **path_params)
        return url_path.make_url(request=request)

    def templates_auto_reload(self):
        r = self.config['TEMPLATES_AUTO_RELOAD']
        return r if r is not None else self.debug

    def create_jinja_environment(self):

        def select_jinja_autoescape(filename):
            if filename is None:
                return True
            return filename.endswith(('.html', '.htm', '.xml', '.xhtml'))

        options = dict(
            extensions=['jinja2.ext.autoescape', 'jinja2.ext.with_'],
            autoescape=select_jinja_autoescape,
            auto_reload=self.templates_auto_reload()
        )
        rv = self.jinja_environment(self, **options)
        rv.globals.update(
            url_for=self.url_for,
            config=self.config,
        )
        return rv

    @cached_property
    def jinja_env(self):
        return self.create_jinja_environment()

    @cached_property
    def jinja_loader(self):
        if self.template_folder is not None:
            return FileSystemLoader(self.template_folder)

    def create_global_jinja_loader(self):
        return self.app_factory.create_jinja_loader()

    def add_template_filter(self, f, name=None):
        self.jinja_env.filters[name or f.__name__] = f

    def add_template_global(self, f, name=None):
        self.jinja_env.globals[name or f.__name__] = f

    def _default_template_ctx_processor(self, request):
        return dict(request=request)

    def context_processor(self, f):
        self.template_context_processors[None].append(f)
        return f
