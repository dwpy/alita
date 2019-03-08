from alita.base import BaseFactory


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
