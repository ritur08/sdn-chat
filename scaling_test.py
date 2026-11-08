
#!/usr/bin/env python3
"""Load generator + latency measurement for the scaling experiment.
Usage: python3 load_clients.py [server_ip] [clients] [msgs_per_sec] [seconds] [label]
Each simulated client registers, joins room1, sends chat messages at
msgs_per_sec, and sends a private message to itself once per second to
measure the round-trip time. A summary line is appended to results.csv."""
import os
import re
import socket
import sys
import threading
import time

host = sys.argv[1] if len(sys.argv) > 1 else "10.0.0.1"
n_clients = int(sys.argv[2]) if len(sys.argv) > 2 else 10
rate = float(sys.argv[3]) if len(sys.argv) > 3 else 2
duration = float(sys.argv[4]) if len(sys.argv) > 4 else 20
label = sys.argv[5] if len(sys.argv) > 5 else "run"

rtts = []          # round-trip times in seconds, from all clients
pings_sent = [0]
lock = threading.Lock()


def run_client(i):
    name = f"u{i}"
    try:
        s = socket.create_connection((host, 5000), timeout=5)
    except OSError:
        return
    pending = {}   # ping number -> time sent

    def reader():
        for line in s.makefile("r", encoding="utf-8"):
            m = re.match(r"\[PM from %s\] ping(\d+)" % name, line)
            if m:
                t = pending.pop(int(m.group(1)), None)
                if t is not None:
                    with lock:
                        rtts.append(time.time() - t)

    threading.Thread(target=reader, daemon=True).start()
    s.sendall(f"REGISTER {name}\nJOIN room1\n".encode())
    time.sleep(1)

    interval = 1.0 / rate if rate > 0 else 1e9
    next_msg = next_ping = time.time()
    seq = 0
    end = time.time() + duration
    while time.time() < end:
        now = time.time()
        if now >= next_msg:
            s.sendall(f"MSG hello from {name}\n".encode())
            next_msg += interval
        if now >= next_ping:
            pending[seq] = time.time()
            s.sendall(f"PM {name} ping{seq}\n".encode())
            with lock:
                pings_sent[0] += 1
            seq += 1
            next_ping += 1.0
        time.sleep(0.005)
    time.sleep(2)   # let late replies arrive
    try:
        s.sendall(b"QUIT\n")
    except OSError:
        pass
    s.close()


print(f"{n_clients} clients, {rate} msg/s each, {duration:.0f}s ({label}) ...")
threads = []
for i in range(n_clients):
    t = threading.Thread(target=run_client, args=(i,))
    t.start()
    threads.append(t)
    time.sleep(0.05)
for t in threads:
    t.join()

got = sorted(rtts)
sent = pings_sent[0]
lost = sent - len(got)
avg = 1000 * sum(got) / len(got) if got else 0
p95 = 1000 * got[min(len(got) - 1, int(0.95 * len(got)))] if got else 0
worst = 1000 * got[-1] if got else 0
print("---- RESULT ----")
print(f"pings sent: {sent}   lost: {lost}")
print(f"avg: {avg:.1f} ms   95th pct: {p95:.1f} ms   max: {worst:.1f} ms")

new_file = not os.path.exists("results.csv")
with open("results.csv", "a") as f:
    if new_file:
        f.write("label,clients,msgs_per_sec,seconds,pings_sent,lost,avg_ms,p95_ms,max_ms\n")
    f.write(f"{label},{n_clients},{rate},{duration:.0f},{sent},{lost},{avg:.1f},{p95:.1f},{worst:.1f}\n")
