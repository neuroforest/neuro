import socket


def wait_for_socket(host, port):
    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result_of_check = s.connect_ex((host, port))
        if result_of_check == 0:
            break
