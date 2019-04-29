import os
import sys
import time
import logging
from alita.base import BaseExceptionHandler, BaseStaticHandler
from alita.exceptions import default_exceptions, NotFound, BadRequest,\
    InternalServerError, WebSocketConnectionClosed
from alita.response import FileResponse

IGNORE_EXCEPTIONS = (WebSocketConnectionClosed, )


class ExceptionHandler(BaseExceptionHandler):
    _status_handlers = None
    _exception_handlers = None

    def __init__(self, app=None, logger=None):
        super().__init__(app)
        self._status_handlers = {}
        self._exception_handlers = {}
        self.logger = logger or logging.getLogger(__name__)

    def add_status_handler(self, code, handler):
        assert isinstance(code, int)
        self._status_handlers[code] = handler

    def add_exception_handler(self, exception_class, handler):
        assert issubclass(exception_class, Exception)
        self._exception_handlers[exception_class] = handler

    def _lookup_exception_handler(self, exc):
        for cls in type(exc).__mro__:
            if cls in self._exception_handlers:
                return self._exception_handlers[cls]
        return None

    def ruder_error_response(self, request, exc):
        exc_type, exc_value, tb = sys.exc_info()
        self.app.log_exception(request, (exc_type, exc_value, tb))
        # TODO: 此处可以渲染一个默认的500报错页面，当然也可以通过注册500的handler函数来定义渲染
        error_content = str(exc)
        return InternalServerError()

    def default_handler(self, request, exc):
        try:
            exc_class = type(exc)
            if issubclass(exc_class, int):
                return default_exceptions[exc]()
            elif issubclass(exc_class, self.app.exception_class):
                return exc
            else:
                assert issubclass(exc_class, Exception)
                raise exc
        except Exception as ex:
            try:
                return self.ruder_error_response(request, ex)
            except Exception as exc:
                return InternalServerError(str(exc))

    async def process_exception(self, request, exc):
        handler = None
        try:
            if isinstance(exc, IGNORE_EXCEPTIONS):
                raise exc
            if isinstance(exc, self.app.exception_class):
                handler = self._status_handlers.get(exc.code)
            if handler is None:
                handler = self._lookup_exception_handler(exc)
            if handler is None:
                handler = self.default_handler
            return await self.app.get_awaitable_result(handler, request, exc)
        except IGNORE_EXCEPTIONS as ex:
            raise ex
        except Exception as ex:
            return await self.process_exception(request, ex)


class StaticHandler(BaseStaticHandler):
    async def send_static_file(self, request, file_name):
        if not self.has_static_folder:
            raise RuntimeError('No static folder for this object')
        file_max_age = self.send_file_max_age
        filename = os.path.join(self.static_folder, file_name)
        try:
            if not os.path.isfile(filename):
                raise NotFound()
        except (TypeError, ValueError):
            raise BadRequest()
        headers = {}
        if file_max_age is not None:
            headers['Cache-Control'] = 'max-age=%s' % file_max_age
            headers['Expires'] = time.time() + file_max_age
        return FileResponse(filename, headers=headers)
