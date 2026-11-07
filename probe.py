#!/usr/bin/env python3
"""Probe: measures what a normal user experiences during a flood.
Usage: python3 probe.py [server_ip] [duration_sec]
Sends a private message to itself every 0.2 s and times the round trip,
and counts how many spam messages from the flooder reach it."""
import re
import socket
import sys
import threading
import time

host = sys.argv[1] if len(sys.argv) > 1 else "10.0.0.1"
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 25

sent = {}   # message number -> time sent
rtts = {}   # message number -> round-trip time in seconds
spam = [0]  # spam messages received


def reader(sock):
    for line in sock.makefile("r", encoding="utf-8"):
        now = time.time()
        m = re.match(r"\[PM from probe\] ping(\d+)", line)
        if m:
            n = int(m.group(1))
            if n in sent and n not in rtts:
                rtts[n] = now - sent[n]
        elif "flooder: spam" in line:
            spam[0] += 1


sock = socket.create_connection((host, 5000))
threading.Thread(target=reader, args=(sock,), daemon=True).start()
sock.sendall(b"REGISTER probe\nJOIN room1\n")
time.sleep(1)
print(f"probing for {duration:.0f}s ...")
n = 0
end = time.time() + duration
while time.time() < end:
    sent[n] = time.time()
    sock.sendall(f"PM probe ping{n}\n".encode())
    n += 1
    time.sleep(0.2)
time.sleep(3)  # allow late replies to arrive

got = list(rtts.values())
print("---- RESULT ----")
print(f"pings sent:           {n}")
print(f"replies received:     {len(got)}")
print(f"replies lost:         {n - len(got)}")
if got:
    print(f"avg round trip:       {1000 * sum(got) / len(got):.1f} ms")
    print(f"max round trip:       {1000 * max(got):.1f} ms")
print(f"spam msgs received:   {spam[0]}")
sock.sendall(b"QUIT\n")
sock.close()
