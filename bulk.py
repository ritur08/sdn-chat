#!/usr/bin/env python3
# PERSON2: new file. Bulk sender: one user sends big chat messages at a steady
# rate and measures how much of it actually reaches the server.
# Usage: python3 bulk.py <user> <room> [kb_per_msg=20] [msgs_per_sec=10] [seconds=15] [server_ip=10.0.0.1]
# Keep msgs_per_sec below 20, or Ritu's flood detection will block the user.
import socket
import sys
import threading
import time

if len(sys.argv) < 3:
    sys.exit("usage: python3 bulk.py <user> <room> [kb_per_msg] [msgs_per_sec] [seconds] [server_ip]")
user, room = sys.argv[1], sys.argv[2]
kb = float(sys.argv[3]) if len(sys.argv) > 3 else 20
rate = float(sys.argv[4]) if len(sys.argv) > 4 else 10
duration = float(sys.argv[5]) if len(sys.argv) > 5 else 15
host = sys.argv[6] if len(sys.argv) > 6 else "10.0.0.1"

line = ("MSG " + "x" * int(kb * 1000) + "\n").encode()
echo_prefix = f"[{room}] {user}: "
got = {"bytes": 0, "msgs": 0, "counting": False}


def reader(sock):
    """The server echoes our own MSG back to us. Counting those echoes tells us
    how much of what we sent really got through to the server."""
    for raw in sock.makefile("r", encoding="utf-8"):
        if got["counting"] and raw.startswith(echo_prefix):
            got["bytes"] += len(raw)
            got["msgs"] += 1


sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)  # small buffer: no big backlog
sock.connect((host, 5000))
threading.Thread(target=reader, args=(sock,), daemon=True).start()
sock.sendall(f"REGISTER {user}\nJOIN {room}\n".encode())
print("registered, waiting 3 s for the controller to apply the policy ...")
time.sleep(3)

offered = rate * len(line) * 8 / 1000
print(f"sending {kb:g} KB messages at {rate:g}/s for {duration:g} s "
      f"(offered load {offered:.0f} kbps) as user {user} in room {room}")
got["counting"] = True
t0 = time.time()
sent = 0
while time.time() - t0 < duration:
    t = time.time()
    sock.sendall(line)
    sent += 1
    time.sleep(max(0, 1.0 / rate - (time.time() - t)))
elapsed = time.time() - t0
delivered_bytes, delivered_msgs = got["bytes"], got["msgs"]
got["counting"] = False

print("---- RESULT ----")
print(f"offered load:       {offered:.0f} kbps")
print(f"messages sent:      {sent}")
print(f"messages delivered: {delivered_msgs}")
print(f"delivered rate:     {delivered_bytes * 8 / 1000 / elapsed:.0f} kbps")
time.sleep(3)
try:
    sock.sendall(b"QUIT\n")
except OSError:
    pass
sock.close()
