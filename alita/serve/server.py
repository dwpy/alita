import os
import logging
import httptools
import signal
import asyncio
import functools
import traceback
from datetime import datetime
from alita.serve.utils import *
from urllib.parse import unquote
from websockets import handshake, InvalidHandshake, WebSocketCommonProtocol

HIGH_WATER_LIMIT = 65536


class ServiceUnavailable:
    def __init__(self, body=None, status=503, headers=None, content_type="text/plain"):
        self.content_type = content_type
        self.body = self._encode_body(body)
        self.status = status
        self._cookies = None
        self.headers = headers or {}

    def _encode_body(self, data):
        try:
            return data.encode()
        except AttributeError:
            return str(data or "").encode()

    async def __call__(self, environ, on_response):
        on_response(self)

    def output(self, version="1.1", keep_alive=False, keep_alive_timeout=None):
        # This is all returned in a kind-of funky way
        # We tried to make this as fast as possible in pure python
        body, timeout_header = b"", b""
        if keep_alive and keep_alive_timeout is not None:
            timeout_header = b"Keep-Alive: %d\r\n" % keep_alive_timeout
        self.headers["Content-Type"] = self.headers.get(
            "Content-Type", self.content_type
        )
        headers = self._parse_headers()
        description = b'Service Unavailable'

        return (
            b"HTTP/%b %d %b\r\n" b"Connection: %b\r\n" b"%b" b"%b\r\n" b"%b"
        ) % (
            version.encode(),
            self.status,
            description,
            b"keep-alive" if keep_alive else b"close",
            timeout_header,
            headers,
            body,
        )

    def _parse_headers(self):
        headers = b""
        for name, value in self.headers.items():
            try:
                headers += b"%b: %b\r\n" % (
                    name.encode(),
                    value.encode("utf-8"),
                )
            except AttributeError:
                headers += b"%b: %b\r\n" % (
                    str(name).encode(),
                    str(value).encode("utf-8"),
                )
        return headers


class HttpProtocol(asyncio.Protocol):
    DEFAULT_TYPE = "http"
    DEFAULT_VERSION = "1.1"

    def __init__(self, app, config, server_state):
        self.app = app
        self.config = config
        self.loop = config.loop
        self.logger = config.logger
        self.access_log = config.access_log and (self.logger.level <= logging.INFO)
        self.protocol = config.protocol
        self.root_path = config.root_path
        self.limit_concurrency = config.limit_concurrency
        self.keep_alive_timeout = config.keep_alive_timeout
        self.debug = config.debug

        # Timeouts
        self._request_timeout_handler = None
        self._response_timeout_handler = None
        self.timeout_keep_alive_task = None
        self.timeout_keep_alive = config.timeout_keep_alive

        # Global state
        self.server_state = server_state
        self.connections = server_state.connections
        self.tasks = server_state.tasks
        self.default_headers = server_state.default_headers + config.default_headers

        # Per-connection state
        self.transport = None
        self.server = None
        self.client = None
        self.scheme = None
        self.parser = None
        self.websocket = None
        self.pipeline = []

        # Per-request state
        self.url = None
        self.environ = None
        self.body = b""
        self.more_body = True
        self.headers = []
        self.expect_100_continue = False
        self.message_event = asyncio.Event()
        self.message_event.set()

    # Protocol interface
    def connection_made(self, transport):
        self.connections.add(self)
        self.transport = transport
        self.server = get_local_addr(transport)
        self.client = get_remote_addr(transport)
        self.scheme = "https" if is_ssl(transport) else "http"

        if self.logger.level <= logging.DEBUG:
            self.logger.debug("%s - Connected", self.client)

        self._request_timeout_handler = self.loop.call_later(
            self.config.request_timeout, self.request_timeout_callback
        )

    def connection_lost(self, exc):
        self.connections.discard(self)
        if self.logger.level <= logging.DEBUG:
            self.logger.debug("%s - Disconnected", self.client)
        self.message_event.set()

    def request_timeout_callback(self):
        self.shutdown()

    def response_timeout_callback(self):
        self.shutdown()

    def cancel_timeout_keep_alive_task(self):
        if self.timeout_keep_alive_task is not None:
            self.timeout_keep_alive_task.cancel()
            self.timeout_keep_alive_task = None
        if self._request_timeout_handler is not None:
            self._request_timeout_handler.cancel()
            self._request_timeout_handler = None
        if self._response_timeout_handler is not None:
            self._response_timeout_handler.cancel()
            self._response_timeout_handler = None

    def data_received(self, data):
        self.cancel_timeout_keep_alive_task()
        try:
            if self.parser is None:
                self.headers = []
                self.parser = httptools.HttpRequestParser(self)
            self.parser.feed_data(data)
        except httptools.parser.errors.HttpParserError as exc:
            msg = "Invalid HTTP request received."
            if self.debug:
                msg += "\n" + traceback.format_exc()
            self.logger.error(msg)
            self.on_response(msg)
        except httptools.HttpParserUpgrade as exc:
            #self.handle_upgrade()
            pass

    def handle_upgrade(self):
        upgrade_value = None
        for name, value in self.headers:
            if name == b"upgrade":
                upgrade_value = value.lower()

        if upgrade_value != b"websocket" or self.protocol is None:
            msg = "Unsupported upgrade request."
            self.logger.warning(msg)
            content = [STATUS_TEXT[400]]
            for name, value in self.default_headers:
                content.extend([name, b": ", value, b"\r\n"])
            content.extend(
                [
                    b"content-type: text/plain; charset=utf-8\r\n",
                    b"content-length: " + str(len(msg)).encode("ascii") + b"\r\n",
                    b"connection: close\r\n",
                    b"\r\n",
                    msg.encode("ascii"),
                ]
            )
            self.transport.write(b"".join(content))
            self.transport.close()
            return

        self.connections.discard(self)
        method = self.environ["method"].encode()
        output = [method, b" ", self.url, b" HTTP/1.1\r\n"]
        for name, value in self.environ["headers"]:
            output += [name, b": ", value, b"\r\n"]
        output.append(b"\r\n")
        protocol = self.protocol(
            app=self.app,
            config=self.config,
            server_state=self.server_state
        )
        protocol.connection_made(self.transport)
        protocol.data_received(b"".join(output))
        self.transport.set_protocol(protocol)

    # Parser callbacks
    def on_url(self, url):
        parsed_url = httptools.parse_url(url)
        path = parsed_url.path.decode("ascii")
        if "%" in path:
            path = unquote(path)
        self.url = url
        self.expect_100_continue = False
        self.environ = {
            "url": url.decode(),
            "parsed_url": parsed_url,
            "type": self.DEFAULT_TYPE,
            "http_version": self.DEFAULT_VERSION,
            "server": self.server,
            "client": self.client,
            "scheme": self.scheme,
            "ip": self.server[0],
            "port": int(self.server[1]),
            "path": path,
            "query_string": (parsed_url.query if parsed_url.query else b"").decode(),
        }

    def on_header(self, name: bytes, value: bytes):
        name = name.lower()
        if name == b"expect" and value.lower() == b"100-continue":
            self.expect_100_continue = True
        self.headers.append((name.decode("ascii"), value.decode("ascii")))

    def on_headers_complete(self):
        http_version = self.parser.get_http_version()
        if http_version != self.DEFAULT_VERSION:
            self.environ["http_version"] = http_version
        self.environ.update(
            protocol=self,
            method=self.parser.get_method().decode("ascii"),
            transport=self.transport,
            logger=self.logger,
            root_path=self.root_path,
            access_log=self.access_log,
            expect_100_continue=self.expect_100_continue,
            keep_alive=http_version != "1.0",
            keep_alive_timeout=self.keep_alive_timeout,
            headers=self.headers,
            default_headers=self.default_headers,
        )
    
    def on_body(self, body: bytes):
        self.body += body
        if len(self.body) > HIGH_WATER_LIMIT:
            self.transport.pause_reading()
        self.message_event.set()

    def on_message_complete(self):
        self.more_body = False
        self.message_event.set()
        self.cancel_timeout_keep_alive_task()
        self.environ.update(body=self.body.decode())
        self.process_request()

    def log_response(self, response):
        if self.access_log:
            self.logger.info('[access] %s - - [%s] "%s %s" %s -',
                             self.environ['host'],
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             self.environ['method'],
                             self.environ['path'],
                             response.status)

    def process_request(self):
        # Standard case - start processing the request.
        # Handle 503 responses when 'limit_concurrency' is exceeded.
        self._response_timeout_handler = self.loop.call_later(
            self.config.response_timeout, self.response_timeout_callback
        )
        if self.limit_concurrency is not None and (
                len(self.connections) >= self.limit_concurrency
                or len(self.tasks) >= self.limit_concurrency
        ):
            app = ServiceUnavailable()
            message = "Exceeded concurrency limit."
            self.logger.warning(message)
        else:
            app = self.app
        task = self.loop.create_task(app(self.environ, self.on_response))
        task.add_done_callback(self.tasks.discard)
        self.tasks.add(task)

    async def on_response(self, response):
        # Callback for pipelined HTTP requests to be started.
        self.server_state.total_requests += 1
        if isinstance(response, str):
            output_content = response
        else:
            response.set_protocol(self)
            output_content = await response.output(
                self.environ["http_version"],
                self.environ["keep_alive"],
                self.environ["keep_alive_timeout"]
            )
        self.transport.write(output_content)
        self.log_response(response)
        self.cancel_timeout_keep_alive_task()
        if not self.transport.is_closing():
            self.transport.close()
            self.transport = None
        else:
            # Set a short Keep-Alive timeout.
            self.timeout_keep_alive_task = self.loop.call_later(
                self.timeout_keep_alive, self.timeout_keep_alive_handler
            )

    def shutdown(self):
        """
        Called by the server to commence a graceful shutdown.
        """
        if not self.transport.is_closing():
            self.transport.close()

    def pause_writing(self):
        """
        Called by the transport when the write buffer exceeds the high water mark.
        """
        self.message_event.clear()

    def resume_writing(self):
        """
        Called by the transport when the write buffer drops below the low water mark.
        """
        self.message_event.set()

    async def drain(self):
        await self.message_event.wait()

    def timeout_keep_alive_handler(self):
        """
        Called on a keep-alive connection if no new data is received after a short delay.
        """
        self.shutdown()

    def push_data(self, data):
        self.transport.write(data)

    def close(self):
        """
        Force close the connection.
        """
        if self.transport is not None:
            self.transport.close()
            self.transport = None


class WebSocketProtocol(HttpProtocol):
    def request_timeout_callback(self):
        if self.websocket is None:
            super().request_timeout_callback()

    def response_timeout_callback(self):
        if self.websocket is None:
            super().response_timeout_callback()

    def timeout_keep_alive_handler(self):
        if self.websocket is None:
            super().timeout_keep_alive_handler()

    def connection_lost(self, exc):
        if self.websocket is not None:
            self.websocket.connection_lost(exc)
        super().connection_lost(exc)

    def data_received(self, data):
        if self.websocket is not None:
            self.websocket.data_received(data)
        else:
            try:
                super().data_received(data)
            except httptools.HttpParserUpgrade:
                pass

    def write_response(self, response):
        if self.websocket is not None:
            self.transport.close()
        else:
            super().on_response(response)

    async def websocket_handshake(self, request, subprotocols=None):
        headers = {}

        try:
            key = handshake.check_request(request.headers)
            handshake.build_response(headers, key)
        except InvalidHandshake:
            msg = "Invalid websocket request received."
            if self.debug:
                msg += "\n" + traceback.format_exc()
            self.logger.error(msg)
            self.on_response(msg)
            raise RuntimeError(msg)

        subprotocol = None
        if subprotocols and "Sec-Websocket-Protocol" in request.headers:
            # select a subprotocol
            client_subprotocols = [
                p.strip()
                for p in request.headers["Sec-Websocket-Protocol"].split(",")
            ]
            for p in client_subprotocols:
                if p in subprotocols:
                    subprotocol = p
                    headers["Sec-Websocket-Protocol"] = subprotocol
                    break

        # write the 101 response back to the client
        rv = b"HTTP/1.1 101 Switching Protocols\r\n"
        for k, v in headers.items():
            rv += k.encode("utf-8") + b": " + v.encode("utf-8") + b"\r\n"
        rv += b"\r\n"
        request.transport.write(rv)

        # hook up the websocket protocol
        self.websocket = WebSocketCommonProtocol(
            timeout=self.config.ws_timeout,
            max_size=self.config.ws_max_size,
            max_queue=self.config.ws_max_queue,
            read_limit=self.config.ws_read_limit,
            write_limit=self.config.ws_write_limit,
        )
        self.websocket.subprotocol = subprotocol
        self.websocket.connection_made(request.transport)
        self.websocket.connection_open()
        return self.websocket


class ServerState:
    """
    Shared servers state that is available between all protocol instances.
    """

    def __init__(self, total_requests=0, connections=None, tasks=None, default_headers=None):
        self.total_requests = total_requests
        self.connections = connections or set()
        self.tasks = tasks or set()
        self.default_headers = default_headers or []


class Server(object):
    def __init__(self, app, config, server_state=None):
        self.app = app
        self.config = config
        self.started = False
        self.loop = config.loop
        self.logger = config.logger
        self.socket = config.socket
        self.servers = []
        self.server_state = server_state or ServerState()

        if self.config.debug:
            self.loop.set_debug(True)

    def install_signal_handlers(self):
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                self.loop.add_signal_handler(sig, self.loop.stop)
        except NotImplementedError:
            self.logger.warning("loop.add_signal_handler not implemented on this platform.")

    def run(self):
        protocol = self.config.protocol
        if protocol is None:
            protocol = WebSocketProtocol if self.app.is_websocket else HttpProtocol
        server = functools.partial(
            protocol,
            app=self.app,
            config=self.config,
            server_state=self.server_state
        )
        asyncio_server_kwargs = (
            self.config.asyncio_server_kwargs if self.config.asyncio_server_kwargs else {}
        )
        server_coroutine = self.loop.create_server(
            server,
            self.config.host,
            self.config.port,
            ssl=self.config.ssl,
            reuse_port=self.config.reuse_port,
            sock=self.socket,
            backlog=self.config.backlog,
            **asyncio_server_kwargs
        )

        if self.config.run_async:
            return server_coroutine

        try:
            http_server = self.loop.run_until_complete(server_coroutine)
        except BaseException:
            self.logger.exception("Unable to start server")
            return
        self.install_signal_handlers()
        pid = os.getpid()
        try:
            self.started = True
            self.servers = [server]
            self.logger.info("Starting worker [%s]", pid)
            message = "Server running on http://%s:%d (Press CTRL+C to quit)"
            self.logger.info(message % (self.config.host, self.config.port))
            self.loop.run_forever()
        finally:
            self.logger.info("Stopping worker [%s]", pid)
            # Wait for event loop to finish and all connections to drain
            http_server.close()
            self.loop.run_until_complete(http_server.wait_closed())

            # Complete all tasks on the loop
            for connection in self.server_state.connections:
                connection.shutdown()

            # Gracefully shutdown timeout.
            # We should provide graceful_shutdown_timeout,
            # instead of letting connection hangs forever.
            # Let's roughly calcucate time.
            start_shutdown = 0
            while self.server_state.connections and (
                    start_shutdown < self.config.graceful_shutdown_timeout):
                self.loop.run_until_complete(asyncio.sleep(0.1))
                start_shutdown = start_shutdown + 0.1

            # Force close non-idle connection after waiting for
            # graceful_shutdown_timeout
            coros = []
            for conn in self.server_state.connections:
                if hasattr(conn, "websocket") and conn.websocket:
                    coros.append(conn.websocket.close_connection())
                else:
                    conn.close()

            _shutdown = asyncio.gather(*coros, loop=self.loop)
            self.loop.run_until_complete(_shutdown)
            self.loop.close()


__all__ = [
    "HttpProtocol",
    "Server",
    "ServerState"
]
