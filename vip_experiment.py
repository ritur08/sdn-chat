#!/usr/bin/env python3
# PERSON2: new file. VIP experiment (Step 4). Runs by itself, no clicking.
#
#   1. builds the 3-switch topology (topology_big.build) with a slow server link
#   2. starts the chat server and 3 heavy NORMAL users (background load)
#   3. a VIP probe user (h5) and a NORMAL probe user (h6) measure their chat delay
#   4. appends the results to vip_results.csv
#
# The controller is NOT started here. Start it yourself first, in another terminal:
#   baseline:  ryu-manager --ofp-tcp-listen-port 6653 controller.py
#   QoS:       ryu-manager --ofp-tcp-listen-port 6653 controller_qos.py
# Then:   sudo python3 vip_experiment.py --label baseline    (or --label qos)
import argparse
import csv
import os
import re
import time

from mininet.log import setLogLevel

from topology_big import build   # PERSON2: reuse the topology file

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_IP = "10.0.0.1"
RESULTS = os.path.join(HERE, "vip_results.csv")
FIELDS = ["label", "bw_mbps", "size_kb", "role", "user", "sent", "received",
          "loss_pct", "avg_ms", "p95_ms", "max_ms", "delivered_kbps"]

# background load: 3 heavy NORMAL users, each alone in its own room
HEAVY = [("h2", "heavyA", "roomA"), ("h3", "heavyB", "roomB"),
         ("h4", "heavyC", "roomC")]
# probes: one VIP user (room "vip") and one NORMAL user (room "lab")
PROBES = [("h5", "vipprobe", "vip", "vip_probe"),
          ("h6", "normprobe", "lab", "normal_probe")]


def log_path(user):
    return "/tmp/exp_%s.log" % user


def read_log(user):
    try:
        with open(log_path(user)) as f:
            return f.read()
    except OSError:
        return ""


def wait_for(users, marker, deadline):
    """Wait until every user's log contains marker (or the deadline passes)."""
    while time.time() < deadline:
        if all(marker in read_log(u) for u in users):
            return True
        time.sleep(1)
    return False


def parse_probe(text):
    m = re.search(r"PROBE_RESULT user=(\S+) room=(\S+) sent=(\d+) received=(\d+) "
                  r"loss_pct=([-\d.]+) avg_ms=([-\d.]+) p95_ms=([-\d.]+) "
                  r"max_ms=([-\d.]+)", text)
    if not m:
        return None
    return dict(sent=int(m.group(3)), received=int(m.group(4)),
                loss_pct=float(m.group(5)), avg_ms=float(m.group(6)),
                p95_ms=float(m.group(7)), max_ms=float(m.group(8)))


def parse_heavy(text):
    m = re.search(r"delivered rate:\s+(\d+) kbps", text)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="baseline or qos")
    ap.add_argument("--bw", type=float, default=2, help="server link, Mbit/s")
    ap.add_argument("--duration", type=float, default=40, help="probe seconds")
    ap.add_argument("--size-kb", type=float, default=20, help="probe message size")
    args = ap.parse_args()

    for _, user, _ in HEAVY:
        open(log_path(user), "w").close()
    for _, user, _, _ in PROBES:
        open(log_path(user), "w").close()

    setLogLevel("warning")
    net = build(6, args.bw)
    net.start()
    rows = []
    try:
        time.sleep(3)
        hosts = [net.get("h%d" % i) for i in range(1, 8)]
        loss = net.ping(hosts)
        print("setup ping loss: %s%%" % loss)
        net.get("h1").cmd("python3 %s/server.py > /tmp/server.log 2>&1 &" % HERE)
        time.sleep(2)

        # PERSON2: the setup ping made the controller install learned L2 flows.
        # While they exist they match the chat traffic first, so the controller
        # never sees it and the QoS meters never get attached. Remove them.
        for sw in ("s1", "s2", "s3"):
            for n in range(1, 9):
                net.get(sw).cmd("ovs-ofctl -O OpenFlow13 del-flows %s "
                                "dl_src=00:00:00:00:00:%02x" % (sw, n))

        heavy_secs = int(args.duration + 30)   # load must outlast the probes
        for host, user, room in HEAVY:
            net.get(host).cmd("python3 %s/bulk.py %s %s 20 10 %d %s > %s 2>&1 &"
                              % (HERE, user, room, heavy_secs, SERVER_IP,
                                 log_path(user)))
        print("3 heavy users started, letting the load build up for 10 s ...")
        time.sleep(10)

        for host, user, room, _ in PROBES:
            net.get(host).cmd("python3 %s/vip_probe.py %s %s %g %g 2 %s > %s 2>&1 &"
                              % (HERE, user, room, args.size_kb, args.duration,
                                 SERVER_IP, log_path(user)))
        print("probes running (about %d s) ..." % (args.duration + 25))
        probe_users = [u for _, u, _, _ in PROBES]
        wait_for(probe_users, "PROBE_RESULT", time.time() + args.duration + 60)
        print("waiting for the heavy users to finish ...")
        heavy_users = [u for _, u, _ in HEAVY]
        wait_for(heavy_users, "delivered rate", time.time() + 60)

        print("\nmeter counters on s2 (edge switch, heavy users h2-h4):")
        print(net.get("s2").cmd("ovs-ofctl -O OpenFlow13 meter-stats s2"))

        for _, user, _, role in PROBES:
            r = parse_probe(read_log(user))
            if r:
                rows.append(dict(label=args.label, bw_mbps=args.bw,
                                 size_kb=args.size_kb, role=role, user=user, **r))
            else:
                print("WARNING: no result from %s, see %s" % (user, log_path(user)))
        for _, user, _ in HEAVY:
            kbps = parse_heavy(read_log(user))
            if kbps is not None:
                rows.append(dict(label=args.label, bw_mbps=args.bw,
                                 size_kb=args.size_kb, role="heavy_normal",
                                 user=user, delivered_kbps=kbps))
            else:
                print("WARNING: no result from %s, see %s" % (user, log_path(user)))
    finally:
        h1 = net.get("h1")
        h1.cmd("pkill -f bulk.py; pkill -f vip_probe.py; pkill -f server.py")
        net.stop()

    new_file = not os.path.exists(RESULTS)
    with open(RESULTS, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for row in rows:
            w.writerow(row)

    print("\n==== %s (server link %g Mbit/s, probe message %g KB) ====" %
          (args.label, args.bw, args.size_kb))
    for r in rows:
        if r["role"].endswith("probe"):
            print("%-13s avg %8.1f ms   p95 %8.1f ms   max %8.1f ms   lost %.1f%%"
                  % (r["role"], r["avg_ms"], r["p95_ms"], r["max_ms"], r["loss_pct"]))
        else:
            print("%-13s %-7s delivered %d kbps" %
                  (r["role"], r["user"], r["delivered_kbps"]))
    print("saved to %s" % RESULTS)


if __name__ == "__main__":
    main()
