# Multi-Client Chat Network via SDN (Mininet + Ryu)

A concurrent, multi-user TCP chat application deployed over a virtual **Software-Defined Network (SDN)**. Unlike a standard static network, this project uses **cross-layer communication**: the chat server monitors application-level events (users registering, joining rooms) and sends them to an SDN controller, which uses that information to dynamically classify, shape and prioritize network traffic with OpenFlow rules.

![Python](https://img.shields.io/badge/Python-3-blue)
![OpenFlow](https://img.shields.io/badge/OpenFlow-1.3-green)
![Mininet](https://img.shields.io/badge/Mininet-Emulation-orange)
![Ryu](https://img.shields.io/badge/Controller-Ryu-red)

---

## Table of Contents

- [Architecture](#architecture)
- [Core Components](#core-components)
- [OpenFlow Priority Levels](#openflow-priority-levels)
- [Installation & Execution](#installation--execution)
- [Supported Chat Commands](#supported-chat-commands)
- [Current Limitations](#current-limitations)
- [Roadmap (Deliverable 2)](#roadmap-deliverable-2)

---

## Architecture

The environment is built with **Mininet** (virtual topology), **Open vSwitch (OVS)**, and **Ryu** (OpenFlow 1.3 controller).

```text
                         +----------------------+
                         |   Ryu Controller     |
                         |   OpenFlow 1.3       |
                         |  - Chat detection    |
                         |  - Flow management   |
                         +----------^-----------+
                                    | UDP :9000 (Chat events)
+----------------+        +---------+----------+
| Client h2      |        |                    |
| TCP :5000      |--------|     OVS s1         |
+----------------+        |   OpenFlow 1.3     |
                          |                    |
+----------------+        |                    |
| Client h3      |--------|                    |
| TCP :5000      |        +---------+----------+
+----------------+                  | TCP :5000
                          +---------+----------+
                          | Chat Server h1     |
                          | UDP events -> NAT  |
                          +--------------------+
```

### Data Flow

The workflow is a strict event-driven loop:

1. A user runs a command (e.g. `REGISTER alice`). The client sends it over **TCP** to the chat server.
2. The server processes the command and simultaneously fires a **UDP** notification (e.g. `REGISTER alice 10.0.0.2`) to the Ryu controller.
3. The controller dynamically installs a high-priority flow rule on the OVS switch to optimize that specific user's chat traffic.

---

## Core Components

| File | Description |
|------|-------------|
| `server.py` | TCP chat server on host **h1** (`10.0.0.1:5000`). Spawns a new thread per client and uses a threading lock to safely manage connected sockets, chat rooms, and user locations. Handles broadcasting, private messaging, and sends UDP event triggers to the controller. |
| `client.py` | Lightweight TCP client. A daemon thread asynchronously receives and prints incoming messages while the main thread waits for user input. |
| `topology.py` | Mininet topology: chat server (h1), clients (h2, h3), a single Open vSwitch (s1), and a NAT node (`10.0.0.254`) bridging the internal network to the external Ryu controller. |
| `controller.py` | Ryu controller. Listens on **UDP port 9000** for server events (`REGISTER`, `JOIN`, `DISCONNECT`), handles Packet-In for unknown packets, and enforces four OpenFlow priority levels. |

---

## OpenFlow Priority Levels

| Priority | Rule | Description |
|----------|------|-------------|
| **150** | User Rule | Highest priority. Installed dynamically on user registration, matching the user's IP and TCP port 5000 for fast forwarding. |
| **100** | Chat Rule | Installed when the controller detects general TCP traffic on port 5000, classifying it as chat traffic (60-second idle timeout). |
| **10** | Normal Forwarding | Standard learned-MAC forwarding for non-chat packets. |
| **0** | Table Miss | Catches unmatched packets and sends them to the controller for inspection. |

---

## Installation & Execution

### Prerequisites

A Linux environment with:

- Python 3
- Mininet
- Open vSwitch
- Ryu

### Steps

**1. Start the controller**

In a terminal, activate your Ryu environment and run:

```bash
ryu-manager controller.py
```

It will indicate that it is listening on UDP 9000.

**2. Launch the network**

In a separate terminal:

```bash
sudo python3 topology.py
```

This builds the topology, automatically starts the server on h1, and drops you into the Mininet CLI.

**3. Verify connectivity**

Inside the Mininet CLI:

```text
mininet> pingall
```

You should see **0% dropped**.

**4. Connect clients**

Open terminals for the hosts:

```text
mininet> xterm h2 h3
```

or run directly from the CLI:

```text
mininet> h2 python3 client.py 10.0.0.1 5000
```

**5. Verify flow installation (optional)**

```text
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

---

## Supported Chat Commands

| Command | Description | Expected SDN Behavior |
|---------|-------------|-----------------------|
| `REGISTER <name>` | Registers your session. | Ryu logs the registration and installs a **Priority 150** flow rule. |
| `JOIN <room>` | Enters a chat room. | Ryu updates its internal room membership state. |
| `MSG <text>` | Broadcasts a message to the current room. | — |
| `PM <user> <text>` | Sends a private direct message. | — |
| `USERS` | Lists active users. | — |
| `LEAVE` | Leaves the current room. | — |
| `QUIT` | Disconnects from the server. | Triggers a UDP `DISCONNECT` event; Ryu removes the user's Priority 150 flow rule from the switch. |

---

## Current Limitations

The D1 prototype demonstrates application-to-network integration, but has these limitations:

- Single switch (`s1`) with a hardcoded controller datapath, so multi-switch routing is not supported.
- Plain-text TCP communication (port 5000) with no username authentication or encryption.
- UDP event notifications have no retry mechanism if packets are dropped.

---

## Roadmap (Deliverable 2)

- **Complex topologies:** expand to multi-switch topologies to test advanced routing.
- **Performance evaluation:** measure latency, throughput, and controller response time under stress.
- **Failure testing:** observe network recovery when links break or the controller goes offline.
- **Traffic management:** finer policies, such as specific bandwidth rules for VIP chat rooms.
