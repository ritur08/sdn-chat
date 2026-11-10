#!/usr/bin/env python3
# PERSON2: new file. Bigger Mininet topology (3 switches, 6 clients).
# topology.py is NOT modified.
#
#                 h1 (chat server 10.0.0.1)
#                  |
# NAT 10.0.0.254 -- s1 (core)
#                 /    \
#               s2      s3
#          h2 h3 h4    h5 h6 h7    (clients 10.0.0.2 ...)
#
# Usage: sudo python3 topology_big.py [--clients 6] [--bw 10]
#   --bw  optional speed limit in Mbit/s on the server link
#         (the shared bottleneck, used later for the VIP experiment)
import argparse
import os
import time

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))


def build(n_clients=6, bw=None):
    net = Mininet(controller=None, switch=OVSKernelSwitch, link=TCLink,
                  autoSetMacs=True)
    net.addController("c0", controller=RemoteController,
                      ip="127.0.0.1", port=6653)
    s1 = net.addSwitch("s1", protocols="OpenFlow13")  # core
    s2 = net.addSwitch("s2", protocols="OpenFlow13")  # edge, left
    s3 = net.addSwitch("s3", protocols="OpenFlow13")  # edge, right

    server = net.addHost("h1", ip="10.0.0.1/24")
    link_opts = {"bw": bw} if bw else {}
    net.addLink(server, s1, **link_opts)
    net.addLink(s1, s2)
    net.addLink(s1, s3)

    half = (n_clients + 1) // 2
    for i in range(n_clients):
        host = net.addHost(f"h{i + 2}", ip=f"10.0.0.{i + 2}/24")
        net.addLink(host, s2 if i < half else s3)

    # NAT is added last so every host gets a route to the controller
    net.addNAT(ip="10.0.0.254/24", connect=s1)
    return net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients", type=int, default=6)
    ap.add_argument("--bw", type=float, default=None)
    args = ap.parse_args()

    setLogLevel("info")
    net = build(args.clients, args.bw)
    net.start()
    time.sleep(3)  # let the switches connect to the controller
    names = ["h1"] + [f"h{i + 2}" for i in range(args.clients)]
    net.ping([net.get(n) for n in names])

    net.get("h1").cmd(f"python3 {HERE}/server.py > /tmp/server.log 2>&1 &")
    print("\nChat server running on h1 (10.0.0.1:5000)")
    for n in names[1:]:
        h = net.get(n)
        print(f"{n} ({h.IP()}) pid: {h.pid}")
    print("Server log: /tmp/server.log\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    main()
