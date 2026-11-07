#!/usr/bin/env python3
"""Flooder: registers as a user and spams chat messages (flooding scenario).
Usage: python3 flooder.py [server_ip] [msgs_per_sec] [duration_sec]"""
import socket
import sys
import threading
import time

host = sys.argv[1] if len(sys.argv) > 1 else "10.0.0.1"
rate = float(sys.argv[2]) if len(sys.argv) > 2 else 100
duration = float(sys.argv[3]) if len(sys.argv) > 3 else 10


def drain(sock):
    """Read and discard what the server sends back, so buffers don't fill."""
    try:
        while sock.recv(4096):
            pass
    except OSError:
        pass


sock = socket.create_connection((host, 5000))
threading.Thread(target=drain, args=(sock,), daemon=True).start()
sock.sendall(b"REGISTER flooder\nJOIN room1\n")
time.sleep(1)

sent = 0
end = time.time() + duration
print(f"flooding {host} at {rate:.0f} msgs/s for {duration:.0f}s ...")
try:
    while time.time() < end:
        sock.sendall(f"MSG spam {sent}\n".encode())
        sent += 1
        time.sleep(1.0 / rate)
except OSError as e:
    print("connection error:", e)
print(f"done, sent {sent} messages")
try:
    sock.sendall(b"QUIT\n")
except OSError:
    pass
sock.close()
