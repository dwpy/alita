import os
import sys
import importlib
from alita.base import BaseFactory


def prepare_import(path):
    """
    Given a filename this will try to calculate the python path, add it
    to the search path and return the actual module name that is expected.
    """
    path = os.path.realpath(path)

    if os.path.splitext(path)[1] == '.py':
        path = os.path.splitext(path)[0]

    if os.path.basename(path) == '__init__':
        path = os.path.dirname(path)

    module_name = []

    # move up until outside package structure (no __init__.py)
    while True:
        path, name = os.path.split(path)
        module_name.append(name)

        if not os.path.exists(os.path.join(path, '__init__.py')):
            break

    if sys.path[0] != path:
        sys.path.insert(0, path)

    return '.'.join(module_name[::-1])


class CliFactory:
    def load_app(self, app_file=None):
        try:
            if not app_file:
                app_file = os.environ.get('ALITA_APP') or "app.py"
            import_name = prepare_import(app_file)
            app_module = importlib.import_module(import_name)
            return getattr(app_module, 'app')
        except SyntaxError as e:
            message = (
                          'Unable to import your app.py file:\n\n'
                          'File "%s", line %s\n'
                          '  %s\n'
                          'SyntaxError: %s'
                      ) % (getattr(e, 'filename'), e.lineno, e.text, e.msg)
            raise RuntimeError(message)


class AppFactory(BaseFactory):
    def __init__(self, app=None):
        self.app = app

    def create_request_object(self, environ):
        from alita.request import Request
        return Request(self.app, environ)

    def create_base_response_class(self):
        from alita.response import HTTPResponse
        return HTTPResponse

    def create_base_exception_class(self):
        from alita.exceptions import HTTPException
        return HTTPException

    def create_exception_handler_object(self):
        from alita.handler import ExceptionHandler
        return ExceptionHandler(self.app)

    def create_router_object(self):
        from alita.routing import Router
        return Router(self.app)

    def create_static_handler(self):
        from alita.handler import StaticHandler
        return StaticHandler(self.app)

    def create_jinja_loader(self):
        from alita.templating import DispatchingJinjaLoader
        return DispatchingJinjaLoader(self.app)
