# -*- coding: utf-8 -*-
import asyncio
from alita.base import BaseBlueprint


class Blueprint(BaseBlueprint):
    _has_registered = False

    def __init__(self, name, url_prefix=None):
        self.name = name
        self.url_prefix = url_prefix or '/' + self.name
        self.deferred_functions = []
        self.app = None

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
        endpoint = options.get('endpoint')
        url_prefix = options.get('url_prefix')
        if url_prefix is None:
            options['url_prefix'] = self.url_prefix
        elif not url_prefix.lstrip('/'):
            raise RuntimeError("Register blueprint url prefix not support empty value.")
        if self.url_prefix is not None:
            if rule:
                rule = '/'.join((
                    self.url_prefix.rstrip('/'), rule.lstrip('/')))
            else:
                rule = self.url_prefix
        if endpoint is None:
            endpoint = self.app.get_endpoint_from_view_func(view_func)
        options['endpoint'] = '%s.%s' % (self.name, endpoint)
        self.app.add_url_rule(view_func, rule, **options)

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

    def add_websocket_handler(self, rule, handler, **options):
        self.record(lambda s: s.app.add_websocket_handler(rule, handler, **options))

    def websocket(self, rule, **options):
        def decorator(f):
            self.add_websocket_handler(rule, f, **options)
            return f
        return decorator
