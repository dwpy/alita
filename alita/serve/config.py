import asyncio
import logging
from alita.serve.server import HttpProtocol
from alita.serve.ws import WebSocketProtocol


def get_logger(log_level):
    logging.basicConfig(format="%(message)s", level=log_level)
    logger = logging.getLogger("uvicorn")
    logger.setLevel(log_level)
    return logger


def init_loop(uvloop=True, create=True):
    if uvloop:
        try:
            import uvloop
            try:
                asyncio.get_event_loop().close()
            except:
                pass
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except ImportError:
            pass
    if create:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return asyncio.get_event_loop()


class ServerConfig:
    DEFAULT_PROTOCOL = HttpProtocol

    def __init__(
        self,
        host="127.0.0.1",
        port=8000,
        uds=None,
        fd=None,
        ssl=None,
        socket=None,
        connections=None,
        loop=None,
        http_protocol=None,
        ws=None,
        log_level=logging.INFO,
        logger=None,
        uvloop=True,
        access_log=True,
        wsgi=False,
        debug=False,
        backlog=100,
        proxy_headers=False,
        root_path="",
        limit_concurrency=None,
        limit_max_requests=None,
        timeout_keep_alive=5,
        timeout_notify=30,
        callback_notify=None,
        reuse_port=False,
        install_signal_handlers=True,
        asyncio_server_kwargs=None,
        graceful_shutdown_timeout=10.0,
        keep_alive_timeout=5,
        default_headers=None,
        run_async=False
    ):
        self.host = host
        self.port = port
        self.uds = uds
        self.fd = fd
        self.ssl = ssl
        self.socket = socket
        self.connections = connections
        self.loop = loop or init_loop(uvloop)
        self.log_level = log_level
        self.logger = logger or get_logger(self.log_level)
        self.access_log = access_log
        self.wsgi = wsgi
        self.debug = debug
        self.run_async = run_async
        self.backlog = backlog
        self.proxy_headers = proxy_headers
        self.root_path = root_path
        self.limit_concurrency = limit_concurrency
        self.limit_max_requests = limit_max_requests
        self.timeout_keep_alive = timeout_keep_alive
        self.timeout_notify = timeout_notify
        self.callback_notify = callback_notify
        self.reuse_port = reuse_port
        self.asyncio_server_kwargs = asyncio_server_kwargs
        self.graceful_shutdown_timeout = graceful_shutdown_timeout
        self.http_protocol = http_protocol or self.DEFAULT_PROTOCOL
        self.ws_protocol = ws or WebSocketProtocol
        self.keep_alive_timeout = keep_alive_timeout
        self.default_headers = default_headers or []


__all__ = [
    "ServerConfig",
    "init_loop",
]
