import http.server
import logging
import socket
import subprocess
import time
import urllib.error
import urllib.request


def get_free_port(host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def get_free_ports(count, host="127.0.0.1"):
    """Get multiple guaranteed-distinct free ports by binding them simultaneously."""
    sockets = []
    ports = []
    try:
        for _ in range(count):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, 0))
            ports.append(s.getsockname()[1])
            sockets.append(s)
    finally:
        while sockets:
            sockets.pop().close()
    return ports


def is_port_in_use(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            return s.connect_ex((host, int(port))) == 0
        except socket.gaierror:
            return False


def release_port(port):
    if is_port_in_use(port):
        logging.info(f"Releasing port: {port}")
        subprocess.run(["killport", str(port)], stdout=subprocess.DEVNULL)


def wait_for_socket(host, port, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, int(port))) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for {host}:{port} after {timeout}s")


class RestartProxy(http.server.BaseHTTPRequestHandler):
    """Reverse proxy that restarts a backend process on every browser refresh.

    The backend command must contain ``{port}`` which will be substituted
    with a free port on each restart.  Example::

        proxy = RestartProxy.create(
            cmd=["node", "server.js", "--port", "{port}"],
            port=8080,
        )
        proxy.serve_forever()  # Ctrl-C to stop
    """

    _process = None
    _backend_port = None
    _cmd = None
    _host = "127.0.0.1"
    _loaded = False

    @classmethod
    def _restart(cls):
        cls._stop_backend()
        cls._backend_port = get_free_port(cls._host)
        full_cmd = [a.format(port=cls._backend_port) for a in cls._cmd]
        cls._process = subprocess.Popen(full_cmd)
        try:
            wait_for_socket(cls._host, cls._backend_port, timeout=5)
        except TimeoutError:
            print("Backend failed to start", flush=True)

    @classmethod
    def _stop_backend(cls):
        if cls._process:
            cls._process.terminate()
            cls._process.wait()
            cls._process = None

    def _proxy(self):
        if self.path == "/" and self._loaded:
            self._restart()
            print(f"Restarted backend on :{self._backend_port}", flush=True)
        type(self)._loaded = True

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else None

        url = f"http://{self._host}:{self._backend_port}{self.path}"
        req = urllib.request.Request(url, data=body, method=self.command)
        for key, val in self.headers.items():
            if key.lower() != "host":
                req.add_header(key, val)

        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            resp = e
        except urllib.error.URLError:
            self.send_error(502, "Backend unavailable")
            return

        self.send_response(resp.status)
        for key, val in resp.getheaders():
            if key.lower() != "transfer-encoding":
                self.send_header(key, val)
        self.end_headers()
        self.wfile.write(resp.read())

    do_GET = _proxy
    do_PUT = _proxy
    do_POST = _proxy
    do_DELETE = _proxy

    def log_message(self, _format, *_args):
        pass

    @classmethod
    def serve(cls, cmd, port=0, host="127.0.0.1"):
        """Start the proxy and block until Ctrl-C.

        :param cmd: Backend command list with ``{port}`` placeholder.
        :param port: Proxy listen port (0 = auto).
        :param host: Bind address.
        """
        cls._cmd = cmd
        cls._host = host
        if not port:
            port = get_free_port(host)
        print(f"http://{host}:{port} (refresh to restart)", flush=True)
        cls._restart()
        server = http.server.HTTPServer((host, port), cls)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            cls._stop_backend()
            server.server_close()
