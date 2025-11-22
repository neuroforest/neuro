import logging
import socket
import subprocess


def is_port_in_use(port, url="localhost"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((url, int(port))) == 0


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
