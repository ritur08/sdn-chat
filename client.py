#!/usr/bin/env python3
"""Simple TCP chat client. Usage: python3 client.py [server_ip] [port]"""
import os
import socket
import sys
import threading

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 5000


def receive(sock):
    for line in sock.makefile("r", encoding="utf-8"):
        print(line.rstrip())
    print("Disconnected from server.")
    os._exit(0)


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except OSError as e:
        print(f"Could not connect to {host}:{port} - {e}")
        return
    threading.Thread(target=receive, args=(sock,), daemon=True).start()
    try:
        while True:
            line = input()
            sock.sendall((line + "\n").encode())
            if line.strip().upper() == "QUIT":
                break
    except (EOFError, KeyboardInterrupt, OSError):
        pass
    sock.close()


if __name__ == "__main__":
    main()
