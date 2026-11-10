# PERSON3 - runs the scaling test in Mininet (NEW file). Run with sudo.
# Start the controller FIRST in another terminal:
#   baseline: ryu-manager ryu.app.simple_switch_13
#   sdn:      ryu-manager controller.py
# Then:  sudo python3 run_scaling.py --mode baseline   (and later --mode sdn)
import argparse, time
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import SingleSwitchTopo
from mininet.log import setLogLevel
import config as C

def run(mode, n):
    hosts = C.CLIENT_HOSTS
    net = Mininet(topo=SingleSwitchTopo(hosts + 1), controller=None, switch=OVSSwitch)
    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
    net.addNAT()  # PERSON3
    net.start()
    nat = net.get("nat0"); ifn = nat.defaultIntf().name  # PERSON3
    nat.cmd(f"ip addr flush dev {ifn}; ip addr add 10.0.0.254/24 dev {ifn}; ip link set {ifn} up")  # PERSON3
    time.sleep(3)
    srv = net.get("h1").popen("python3 server.py")   # TODO: change if the server starts differently
    time.sleep(2)
    per = [n // hosts + (1 if i < n % hosts else 0) for i in range(hosts)]
    procs = []
    for i, k in enumerate(per):
        if k:
            h = net.get(f"h{i + 2}")
            procs.append(h.popen(f"python3 load_clients.py --mode {mode} --total {n} --clients {k} --tag {h.name}"))
    for p in procs:
        p.wait()
    srv.terminate()
    net.stop()

if __name__ == "__main__":
    setLogLevel("warning")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["baseline", "sdn"])
    a = ap.parse_args()
    for n in C.CLIENT_COUNTS:
        print(f"== {a.mode}: {n} clients ==")
        run(a.mode, n)
