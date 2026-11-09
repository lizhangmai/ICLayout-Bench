"""Byte-preserving stdio relay to one operator-created MCP connection."""

import os
import socket
import sys
import threading


def main():
    connection = socket.socket(socket.AF_UNIX)
    connection.connect("\0" + sys.argv[1])

    def send():
        try:
            while data := os.read(0, 65536):
                connection.sendall(data)
            connection.shutdown(socket.SHUT_WR)
        except OSError:
            pass

    threading.Thread(target=send, daemon=True).start()
    with connection:
        while data := connection.recv(65536):
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
