import logging
import os
import socket


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', int(port))) == 0


def kill_process(port):
    command_0 = "lsof -ti:" + str(port) + " | xargs kill"
    command = "kill -9 $(lsof -t -i:" + str(port) + " -sTCP:LISTEN)"
    os.system(command)


def release_port(port):
    if is_port_in_use(port):
        logging.info(f"Releasing port: {port}")
        kill_process(port)


def wait_for_socket(host, port):
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result_of_check = s.connect_ex((host, port))
        if result_of_check == 0:
            break
