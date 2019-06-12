# -*- coding: utf-8 -*-
import asyncio
from jinja2 import FileSystemLoader
from alita.base import BaseBlueprint
from alita.helpers import cached_property


class Blueprint(BaseBlueprint):
    _has_registered = False

    def __init__(self, name, url_prefix=None, template_folder=None):
        self.name = name
        self.url_prefix = url_prefix or '/' + self.name
        self.deferred_functions = []
        self.app = None
        self.template_folder = template_folder

    @property
    def registered(self):
        return self._has_registered

    def record(self, func):
        if self._has_registered:
            from warnings import warn
            warn('The blueprint was already registered once '
                 'but is getting modified now.  These changes '
                 'will not show up.')
        self.deferred_functions.append(func)
    
    def register(self, app, **options):
        self.app = app
        for option in options:
            if hasattr(self, option):
                setattr(self, option, options[option])
        self._has_registered = True
        for deferred in self.deferred_functions:
            deferred(self)

    def route(self, rule, **options):
        def decorator(f):
            self.add_url_rule(rule, f, **options)
            return f
        return decorator

    def add_app_url_rule(self, rule, view_func, **options):
        is_websocket = options.pop('is_websocket', False)
        endpoint = options.get('endpoint')
        url_prefix = options.pop('url_prefix', None)
        if url_prefix is None:
            url_prefix = self.url_prefix
        elif not url_prefix.lstrip('/'):
            raise RuntimeError("Register blueprint url prefix not support empty value.")
        if url_prefix is not None:
            if rule:
                rule = '/'.join((
                    url_prefix.rstrip('/'), rule.lstrip('/')))
            else:
                rule = url_prefix
        if endpoint is None:
            endpoint = self.app.get_endpoint_from_view_func(view_func)
        options['endpoint'] = '%s.%s' % (self.name, endpoint)
        url_handler = self.app.add_websocket_handler \
            if is_websocket else self.app.add_url_rule
        url_handler(view_func, rule, **options)

    def add_url_rule(self, rule, view_func, **options):
        endpoint = options.get('endpoint')
        if endpoint:
            assert '.' not in endpoint, "Blueprint endpoints should not contain dots"
        if view_func and hasattr(view_func, '__name__'):
            assert '.' not in view_func.__name__, "Blueprint view function name should not contain dots"
        self.record(lambda s: s.add_app_url_rule(rule, view_func, **options))

    def endpoint(self, endpoint):
        def decorator(f):
            def register_endpoint():
                self.app.view_functions[endpoint] = f
            self.record(register_endpoint)
            return f
        return decorator

    def request_middleware(self, f):
        self.record(lambda s: s.app.before_request_funcs.setdefault(self.name, []).append(f))
        return f

    def response_middleware(self, f):
        self.record(lambda s: s.app.after_request_funcs.setdefault(self.name, []).append(f))
        return f

    def context_processor(self, f):
        assert asyncio.iscoroutinefunction(f)
        self.record(lambda s: s.app.template_context_processors.setdefault(self.name, []).append(f))
        return f

    def view_handler(self, f):
        self.record(lambda s: s.app.view_functions_handlers.setdefault(self.name, []).append(f))
        return f

    def url_for(self, endpoint, **path_params):
        return self.app.url_for(endpoint, **path_params)

    def error_handler(self, code_or_exception):
        def decorator(func):
            self.register_error_handler(code_or_exception, func)
            return func
        return decorator

    def register_error_handler(self, code_or_exception, func):
        self.record(lambda s: s.app.register_error_handler(code_or_exception, func))

    def add_websocket_handler(self, rule, handler, **options):
        self.add_url_rule(rule, handler, is_websocket=True, **options)

    def websocket(self, rule, **options):
        def decorator(f):
            self.add_url_rule(rule, f, is_websocket=True, **options)
            return f
        return decorator

    @cached_property
    def jinja_loader(self):
        if self.template_folder is not None:
            return FileSystemLoader(self.template_folder)
