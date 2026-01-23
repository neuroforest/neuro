import logging
import socket
import subprocess


def get_free_port(host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


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


def wait_for_socket(host, port):
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result_of_check = s.connect_ex((host, int(port)))
        if result_of_check == 0:
            break
