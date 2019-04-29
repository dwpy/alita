import logging
import asyncio
import websockets
from datetime import datetime
from urllib.parse import unquote
from alita.serve.utils import get_local_addr, get_remote_addr, is_ssl


class Server:
    closing = False

    def register(self, ws):
        pass

    def unregister(self, ws):
        pass


class WebSocketProtocol(websockets.WebSocketServerProtocol):
    def __init__(self, app, config, server_state):
        self.app = app
        self.config = config
        self.server_state = server_state
        self.loop = config.loop
        self.logger = config.logger
        self.root_path = config.root_path
        self.access_log = config.access_log and (self.logger.level <= logging.INFO)

        # Shared server state
        self.connections = server_state.connections
        self.tasks = server_state.tasks
        self.default_headers = server_state.default_headers + config.default_headers

        # Connection state
        self.transport = None
        self.server = None
        self.client = None
        self.scheme = None

        # Connection events
        self.environ = None
        self.handshake_started_event = asyncio.Event()
        self.handshake_completed_event = asyncio.Event()
        self.closed_event = asyncio.Event()
        self.initial_response = None
        self.connect_sent = False
        self.accepted_subprotocol = None

        server = Server()

        super().__init__(ws_handler=self.ws_handler, ws_server=server)

    def connection_made(self, transport):
        self.connections.add(self)
        self.transport = transport
        self.server = get_local_addr(transport)
        self.client = get_remote_addr(transport)
        self.scheme = "wss" if is_ssl(transport) else "ws"
        super().connection_made(transport)

    def connection_lost(self, exc):
        self.connections.remove(self)
        self.handshake_completed_event.set()
        super().connection_lost(exc)

    def shutdown(self):
        self.transport.close()

    def on_task_complete(self, task):
        self.tasks.discard(task)

    async def process_request(self, path, headers):
        """
        This hook is called to determine if the websocket should return
        an HTTP response and close.

        Our behavior here is to start the ASGI application, and then wait
        for either `accept` or `close` in order to determine if we should
        close the connection.
        """
        path_portion, _, query_string = path.partition("?")

        websockets.handshake.check_request(headers)

        subprotocols = []
        for header in headers.get_all("Sec-WebSocket-Protocol"):
            subprotocols.extend([token.strip() for token in header.split(",")])

        headers = [
            (name.encode("ascii"), value.encode("ascii"))
            for name, value in headers.raw_items()
        ]

        self.environ = {
            "type": "websocket",
            "scheme": self.scheme,
            "server": self.server,
            "client": self.client,
            "method": "GET",
            "host": self.server[0],
            "port": int(self.server[1]),
            "root_path": self.root_path,
            "path": unquote(path_portion),
            "query_string": query_string.encode(),
            "headers": headers,
            "subprotocols": subprotocols,
            "default_headers": self.default_headers,
            "protocol": self,
            "transport": self.transport,
        }
        task = self.loop.create_task(self.run_ws())
        task.add_done_callback(self.on_task_complete)
        self.tasks.add(task)

    def process_subprotocol(self, headers, available_subprotocols):
        """
        We override the standard 'process_subprotocol' behavior here so that
        we return whatever subprotocol is sent in the 'accept' message.
        """
        return self.accepted_subprotocol

    def send_500_response(self):
        msg = b"Internal Server Error"
        content = [
            b"HTTP/1.1 500 Internal Server Error\r\n"
            b"content-type: text/plain; charset=utf-8\r\n",
            b"content-length: " + str(len(msg)).encode("ascii") + b"\r\n",
            b"connection: close\r\n",
            b"\r\n",
            msg,
        ]
        self.transport.write(b"".join(content))

    async def ws_handler(self, protocol, path):
        """
        This is the main handler function for the 'websockets' implementation
        to call into. We just wait for close then return, and instead allow
        'send' and 'receive' events to drive the flow.
        """
        self.handshake_completed_event.set()
        await self.closed_event.wait()

    async def run_ws(self):
        try:
            result = await self.app(self.environ, None)
        except BaseException as exc:
            self.closed_event.set()
            msg = "Exception in ws application\n"
            self.logger.error(msg, exc_info=exc)
            if not self.handshake_started_event.is_set():
                self.send_500_response()
            else:
                await self.handshake_completed_event.wait()
            self.transport.close()
        else:
            self.closed_event.set()
            if not self.handshake_started_event.is_set():
                msg = "Ws callable returned without sending handshake."
                self.logger.error(msg)
                self.send_500_response()
                self.transport.close()
            elif result is not None:
                msg = "Ws callable should return None, but returned '%s'."
                self.logger.error(msg, result)
                await self.handshake_completed_event.wait()
                self.transport.close()

    async def on_response(self, response):
        # Callback for pipelined HTTP requests to be started.
        self.server_state.total_requests += 1
        response.set_protocol(self)
        self.transport.write(b"%b" % response.body)
        self.log_response(response)

        if not self.transport.is_closing():
            self.transport.close()
            self.transport = None

    def log_response(self, response):
        if self.access_log:
            self.logger.info('[access] %s - - [%s] "%s %s" %s -',
                             self.environ['host'],
                             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             self.environ['method'],
                             self.environ['path'],
                             response.status)
