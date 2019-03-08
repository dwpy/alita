from functools import partial
from urllib.parse import quote_plus
from alita.base import BaseResponse

try:
    from ujson import dumps as json_dumps
except:
    from json import dumps
    json_dumps = partial(dumps, separators=(",", ":"))


class HTTPResponse(BaseResponse):
    pass


class RawResponse(HTTPResponse):
    """
    Returns response object without encoding the body.
    """
    def __init__(self, body, status=200, headers=None, content_type="application/octet-stream"):
        super(RawResponse, self).__init__(body, status, headers, content_type)


class HtmlResponse(HTTPResponse):
    """
    Returns response object with body in html format.
    """
    def __init__(self, body, status=200, headers=None, content_type="text/html; charset=utf-8"):
        super(HtmlResponse, self).__init__(body, status, headers, content_type)


class TextResponse(HTTPResponse):
    """
    Returns response object with body in text format.
    """
    def __init__(self, body, status=200, headers=None, content_type="text/plain; charset=utf-8"):
        super(TextResponse, self).__init__(body, status, headers, content_type)


class JsonResponse(HTTPResponse):
    """
    Returns response object with body in json format.
    """
    def __init__(self, body, status=200, headers=None, content_type="application/json"):
        super(JsonResponse, self).__init__(body, status, headers, content_type)


class RedirectResponse(HTTPResponse):
    """
    Returns response object with body in json format.
    """
    def __init__(self, to, status=200, headers=None, content_type="text/html; charset=utf-8"):
        headers = headers or {}
        safe_to = quote_plus(to, safe=":/%#?&=@[]!$&'()*+,;")
        headers["Location"] = safe_to
        super(RedirectResponse, self).__init__(None, status, headers, content_type)
