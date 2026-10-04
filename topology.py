#!/usr/bin/env python3
"""Mininet topology: 1 switch, 1 chat server host (h1), N client hosts."""
import os
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))


def build(n_clients=2):
    net = Mininet(controller=None, switch=OVSKernelSwitch, autoSetMacs=True)
    net.addController("c0", controller=RemoteController,
                      ip="127.0.0.1", port=6653)
    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    server = net.addHost("h1", ip="10.0.0.1/24")
    net.addLink(server, s1)
    for i in range(n_clients):
        client = net.addHost(f"h{i + 2}", ip=f"10.0.0.{i + 2}/24")
        net.addLink(client, s1)
    return net


def main():
    setLogLevel("info")
    net = build(n_clients=2)
    net.start()
    net.pingAll()
    h1 = net.get("h1")
    h1.cmd(f"python3 {HERE}/server.py > /tmp/server.log 2>&1 &")
    print("\nChat server running on h1 (10.0.0.1:5000)")
    for name in ("h2", "h3"):
        print(f"{name} pid: {net.get(name).pid}")
    print("Server log: /tmp/server.log\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    main()
