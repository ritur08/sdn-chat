## Person 2: QoS, VIP rooms and experiment

**Topology:** `topology_big.py` builds a 3-switch tree (core s1, edge s2 and s3),
the chat server on h1, six clients, and an optional bandwidth limit on the
server link (`--bw`).

**QoS policy (`controller_qos.py`):** extends the chat controller without
modifying it. Every registered user is NORMAL: their chat traffic passes through
a per-user OpenFlow meter (500 kbps, drop band). A user inside the `vip` room is
exempt. The policy changes live: when the chat server reports a REGISTER, JOIN
or DISCONNECT event, the controller recomputes the user's class and re-installs
that user's flows with or without the meter.

**Experiment (`vip_experiment.py`, `vip_probe.py`, `bulk.py`):** 2 Mbit/s server
link, 3 heavy NORMAL users each offering 1.6 Mbit/s, plus a VIP probe and a
NORMAL probe sending 20 KB messages every 2 s. Run once with the plain
controller and once with `controller_qos.py`.

| | Baseline | QoS |
|---|---|---|
| VIP probe, avg delay | 24,677 ms | 412 ms |
| NORMAL probe, avg delay | 24,873 ms | 387 ms |
| Heavy users, delivered each | 600-620 kbps | 436-444 kbps |
| Meter drops (s2, meter 102) | n/a | 336 packets |

Heavy-user traffic is capped by the meters, which keeps the server link from
saturating, so chat delay falls by about 60x. VIP users are exempt from the
cap: in a separate test the same heavy sender delivered 1595 kbps as a VIP and
407 kbps as a NORMAL user.

**How to reproduce:** start the controller (`controller.py` for the baseline,
`controller_qos.py` for QoS) with
`ryu-manager --ofp-tcp-listen-port 6653 <controller>`, then in another terminal
run `sudo python3 vip_experiment.py --label baseline` (or `--label qos`).
Results are appended to `vip_results.csv`. Run `sudo mn -c` between runs.

**Limitations:** one run per case. Under QoS the VIP and NORMAL probes see
similar delay, because the delay came from the heavy users, and the meters fix
that for everyone. The meters attach to flows created when chat traffic reaches
the controller, so learned L2 flows can hide the traffic from it. The
experiment clears them before it starts.
