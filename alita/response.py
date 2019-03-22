import os
import mimetypes
from functools import partial
from urllib.parse import quote_plus
from alita.base import BaseResponse
from aiofiles import open as open_async

try:
    from ujson import dumps as json_dumps
except:
    from json import dumps
    json_dumps = dumps


class HTTPResponse(BaseResponse):
    pass


class RawResponse(HTTPResponse):
    """
    Returns response object without encoding the body.
    """
    def __init__(self, body, status=200, headers=None, content_type="application/octet-stream"):
        super().__init__(body, status, headers, content_type)


class HtmlResponse(HTTPResponse):
    """
    Returns response object with body in html format.
    """
    def __init__(self, body, status=200, headers=None, content_type="text/html; charset=utf-8"):
        super().__init__(body, status, headers, content_type)


class TextResponse(HTTPResponse):
    """
    Returns response object with body in text format.
    """
    def __init__(self, body, status=200, headers=None, content_type="text/plain; charset=utf-8"):
        super().__init__(body, status, headers, content_type)


class JsonResponse(HTTPResponse):
    """
    Returns response object with body in json format.
    """
    def __init__(self, body, status=200, headers=None, content_type="application/json"):
        if isinstance(body, dict):
            body = json_dumps(body)
        super().__init__(body, status, headers, content_type)


class RedirectResponse(HTTPResponse):
    """
    Returns response object with body in json format.
    """
    def __init__(self, to, status=200, headers=None, content_type="text/html; charset=utf-8"):
        headers = headers or {}
        safe_to = quote_plus(to, safe=":/%#?&=@[]!$&'()*+,;")
        headers["Location"] = safe_to
        super().__init__(None, status, headers, content_type)


class StreamHTTPResponse(BaseResponse):
    def __init__(self, stream_fn, status=200, headers=None, content_type="text/plain"):
        self.stream_fn = stream_fn
        super().__init__('', status, headers, content_type)

    async def write(self, data):
        data = self._encode_body(data)
        self._protocol.push_data(b"%x\r\n%b\r\n" % (len(data), data))
        await self._protocol.drain()

    async def output(self, version="1.1", keep_alive=False, keep_alive_timeout=None):
        if not self.has_protocol():
            raise RuntimeError("Http protocol not set, "
                               "stream response can not execute.")
        self.headers["Transfer-Encoding"] = "chunked"
        self.headers.pop("Content-Length", None)
        headers = super().output(version, keep_alive, keep_alive_timeout)
        self._protocol.push_data(headers)
        await self._protocol.drain()
        await self.stream_fn(self)
        self._protocol.push_data(b"0\r\n\r\n")


class FileResponse(HTTPResponse):
    """
    Returns response object with output file.
    """
    def __init__(self, location, mime_type=None, filename=None,
                 _range=None, status=200, headers=None):
        headers = headers or {}
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        self._range = _range
        self.location = location
        self.filename = filename or os.path.split(self.location)[-1]
        self.mime_type = mime_type or mimetypes.guess_type(self.filename)[0] or "text/plain"
        super().__init__('', status, headers, self.mime_type)

    async def output(self, version="1.1", keep_alive=False, keep_alive_timeout=None):
        async with open_async(self.location, mode="rb") as _file:
            if self._range:
                await _file.seek(self._range.start)
                out_stream = await _file.read(self._range.size)
                self.headers["Content-Range"] = "bytes %s-%s/%s" % (
                    self._range.start,
                    self._range.end,
                    self._range.total,
                )
                self.status = 206
            else:
                out_stream = await _file.read()
        self.body = self._encode_body(out_stream)
        return await super().output(version, keep_alive, keep_alive_timeout)


class StreamResponse(StreamHTTPResponse):
    """
    Returns response object with output stream.
    """
    def __init__(self, location, mime_type=None, filename=None,
                 _range=None, status=200, headers=None, chunk_size=4096):
        headers = headers or {}
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        self._range = _range
        self.location = location
        self.chunk_size = chunk_size
        self.filename = filename or os.path.split(self.location)[-1]
        self.mime_type = mime_type or mimetypes.guess_type(self.filename)[0] or "text/plain"
        super().__init__(None, status, headers, self.mime_type)

    async def output(self, version="1.1", keep_alive=False, keep_alive_timeout=None):
        _file = await open_async(self.location, mode="rb")

        async def _stream_fn(response):
            nonlocal _file
            try:
                if self._range:
                    chunk_size = min((self._range.size, self.chunk_size))
                    await _file.seek(self._range.start)
                    to_send = self._range.size
                    while to_send > 0:
                        content = await _file.read(chunk_size)
                        if len(content) < 1:
                            break
                        to_send -= len(content)
                        await response.write(content)
                else:
                    while True:
                        content = await _file.read(self.chunk_size)
                        if len(content) < 1:
                            break
                        await response.write(content)
            finally:
                await _file.close()
        self.stream_fn = _stream_fn
        return await super().output(version, keep_alive, keep_alive_timeout)
