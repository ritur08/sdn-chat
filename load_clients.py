# PERSON3 - load generator with round-trip delay + loss measurement (NEW file)
# Each client logs in, then repeatedly sends a PM to itself and times the echo.
import argparse, socket, threading, time
import config as C

def open_conn(name):
    s = socket.create_connection((C.SERVER_IP, C.SERVER_PORT), timeout=C.TIMEOUT)
    s.sendall(C.LOGIN_LINE.format(name=name).encode())
    return s

def send_pm(s, name, text):
    s.sendall(C.PM_LINE.format(name=name, text=text).encode())

def wait_for(s, buf, text):
    """Read until `text` shows up in the incoming data. False on timeout/closed."""
    end = time.time() + C.TIMEOUT
    while True:
        if text in buf[0]:
            buf[0] = buf[0].split(text, 1)[1]
            return True
        left = end - time.time()
        if left <= 0:
            return False
        s.settimeout(left)
        try:
            data = s.recv(4096)
        except (socket.timeout, OSError):
            return False
        if not data:
            return False
        buf[0] += data.decode(errors="ignore")

def client(name, a, rows):
    sent = recv = 0
    total_ms = 0.0
    try:
        s = open_conn(name)
    except OSError as e:
        print(f"{name}: cannot connect: {e}")
        rows.append((name, 0, 0, 0.0))
        return
    buf = [""]
    end = time.time() + a.duration
    seq = 0
    while time.time() < end:
        seq += 1
        text = f"ping{seq}"
        t0 = time.time()
        try:
            send_pm(s, name, text)
        except OSError:
            break
        sent += 1
        if wait_for(s, buf, text):
            recv += 1
            total_ms += (time.time() - t0) * 1000
        time.sleep(max(0, 1.0 / a.rate - (time.time() - t0)))
    s.close()
    rows.append((name, sent, recv, total_ms))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", required=True, help="baseline or sdn")
    p.add_argument("--total", type=int, required=True, help="total clients in this experiment (label)")
    p.add_argument("--clients", type=int, help="clients to run on THIS host (default: total)")
    p.add_argument("--tag", default="h", help="unique per host, used in client names")
    p.add_argument("--duration", type=int, default=C.DURATION)
    p.add_argument("--rate", type=float, default=C.RATE)
    a = p.parse_args()
    k = a.clients or a.total
    rows = []
    ts = [threading.Thread(target=client, args=(f"{a.tag}u{i}", a, rows)) for i in range(k)]
    for t in ts: t.start()
    for t in ts: t.join()
    with open(C.RESULTS_FILE, "a") as f:
        for name, sent, recv, tot in rows:
            f.write(f"{a.mode},{a.total},{name},{sent},{recv},{tot:.2f}\n")
    sent = sum(r[1] for r in rows); recv = sum(r[2] for r in rows)
    print(f"{a.tag}: sent={sent} received={recv} lost={sent-recv}")

if __name__ == "__main__":
    main()
