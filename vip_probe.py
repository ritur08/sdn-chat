#!/usr/bin/env python3
# PERSON2: new file. Chat-delay probe for the VIP experiment.
# The user sends a private message (PM) to ITSELF every `interval` seconds and
# times how long it takes to come back from the server. That round trip goes
# through the whole network (edge switch, core switch, server link, server).
# Usage: python3 vip_probe.py <user> <room> [size_kb=20] [seconds=30] [interval=2] [server_ip=10.0.0.1]
# Keep the message rate below 20/s, or Ritu's flood detection will block the user.
import re
import socket
import sys
import threading
import time

if len(sys.argv) < 3:
    sys.exit("usage: python3 vip_probe.py <user> <room> [size_kb] [seconds] [interval] [server_ip]")
user, room = sys.argv[1], sys.argv[2]
size_kb = float(sys.argv[3]) if len(sys.argv) > 3 else 20
duration = float(sys.argv[4]) if len(sys.argv) > 4 else 30
interval = float(sys.argv[5]) if len(sys.argv) > 5 else 2
host = sys.argv[6] if len(sys.argv) > 6 else "10.0.0.1"

pad = "x" * int(size_kb * 1000)
pattern = re.compile(r"^\[%s\] %s: ping(\d+)\b" % (re.escape(room), re.escape(user)))
sent_at = {}   # message number -> time it was sent
rtts = {}      # message number -> round-trip time in seconds


def reader(sock):
    for raw in sock.makefile("r", encoding="utf-8"):
        now = time.time()
        m = pattern.match(raw)
        if m:
            n = int(m.group(1))
            if n in sent_at and n not in rtts:
                rtts[n] = now - sent_at[n]


sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.connect((host, 5000))
threading.Thread(target=reader, args=(sock,), daemon=True).start()
sock.sendall(f"REGISTER {user}\nJOIN {room}\n".encode())
print(f"{user} in room {room}: waiting 3 s for the controller policy ...")
time.sleep(3)

print(f"probing: {size_kb:g} KB message every {interval:g} s for {duration:g} s")
n = 0
t0 = time.time()
while time.time() - t0 < duration:
    t = time.time()
    sent_at[n] = t
    sock.sendall(f"MSG ping{n} {pad}\n".encode())
    n += 1
    time.sleep(max(0, interval - (time.time() - t)))

# slow networks deliver late: wait up to 20 s for the replies still on their way
deadline = time.time() + 20
while len(rtts) < n and time.time() < deadline:
    time.sleep(0.2)

got = sorted(rtts.values())
if got:
    avg = 1000 * sum(got) / len(got)
    p95 = 1000 * got[min(len(got) - 1, int(0.95 * len(got)))]
    worst = 1000 * got[-1]
else:
    avg = p95 = worst = -1
loss = 100.0 * (n - len(got)) / n if n else 0.0
print(f"PROBE_RESULT user={user} room={room} sent={n} received={len(got)} "
      f"loss_pct={loss:.1f} avg_ms={avg:.1f} p95_ms={p95:.1f} max_ms={worst:.1f}")
try:
    sock.sendall(b"QUIT\n")
except OSError:
    pass
sock.close()
