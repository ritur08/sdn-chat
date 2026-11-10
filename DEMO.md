# D2 Demo Script (about 8 to 10 minutes)

Step-by-step script for the live demo of the Multi-Client Chat Network. Setup is in the [README](README.md#setup). The scaling write-up by Person 3 is in [SCALING_PERSON3.md](SCALING_PERSON3.md).

Commands use `~/sdn-chat` as the repo folder. If you cloned to a different folder, use that folder name everywhere. Inside Mininet host shells `~` means `/root`, so use the full path (`/home/<your-user>/sdn-chat`).

## Before the demo

- Only the `sdn-vm` virtual machine is running in UTM. The Mac is plugged in. Terminal font is large.
- Six Mac Terminal tabs are open, each logged in with `ssh ritured@192.168.64.5`. If it times out, the IP changed: run `ip a` in the UTM console and look under `enp0s1`.
- Never run `ssh` from inside the VM. The prompt in each tab should read `ritured@sdn-vm`.
- Do not run `sudo mn -c` once the demo has started: it kills the controller and the topology.

## Steps

### Step 1. Clean start and controller (Tab 1)

```bash
sudo mn -c
cd ~/sdn-chat && ryu-manager --ofp-tcp-listen-port 6653 controller_qos.py
```

Wait for `listening for chat events on UDP 9000`.

Say: this is the Ryu controller with QoS on top of our monitoring and flood blocking. It listens for events from the chat server on UDP 9000.

### Step 2. Topology and connectivity (Tab 2)

```bash
cd ~/sdn-chat && sudo python3 topology.py
```

At the `mininet>` prompt:

```text
pingall
h2 echo $$
h3 echo $$
```

Write the two numbers down. `pingall` should show `0% dropped (12/12 received)`. Tab 1 shows `switch 1 connected` and `QOS: switch 1 registered`.

Say: one OpenFlow 1.3 switch, three hosts and a NAT node, so the chat server can reach the controller.

### Step 3. Flow table before any chat (Tab 3)

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

Say: only the table-miss rule (priority 0) and priority-10 forwarding rules from the pings. There are no user rules yet.

### Step 4. alice (Tab 4)

```bash
sudo mnexec -a <h2 number> bash
cd /home/ritured/sdn-chat && python3 client.py 10.0.0.1
```

Type:

```text
REGISTER alice
JOIN room1
```

### Step 5. bob (Tab 5)

```bash
sudo mnexec -a <h3 number> bash
cd /home/ritured/sdn-chat && python3 client.py 10.0.0.1
```

Type:

```text
REGISTER bob
JOIN room1
MSG hello
PM alice hi
```

Show alice's tab: `[room1] bob: hello` and `[PM from bob] hi`. Names are lowercase and case-sensitive.

### Step 6. The network reacts to the application (Tab 1, then Tab 3)

Tab 1 shows `EVENT register`, `EVENT join`, `QOS:` and `STATS` lines. Then in Tab 3:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep priority=150
```

Say: the chat server sent UDP events, and the controller installed one priority-150 rule per registered user, dynamically. The `STATS` lines come from reading those rules every 3 seconds.

### Step 7. Flood scenario (Tabs 6, 1, 3)

Tab 6:

```bash
sudo mnexec -a <h3 number> bash
cd /home/ritured/sdn-chat && python3 flooder.py 10.0.0.1 100 20
```

Tab 1 shows `RATE flooder ...` and `FLOOD DETECTED ... BLOCKED for 30 s`. Within 10 seconds, in Tab 3:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep priority=200
```

Say: the server counts real messages per second and reports the rate. Above 20 messages per second, the controller installs a DROP rule at priority 200 for that host's IP, with a 30-second timeout. Alice's tab shows the spam stopping.

Say: blocking is per host IP, and bob shares h3 with the flooder, so he is blocked too. This is a known limitation (see the README).

After about 35 seconds, run the same `grep` again: it prints nothing, and Tab 1 shows `UNBLOCKED`. Say: the rule expired on its own.

### Step 8. Results (Tab 3, then the README on GitHub)

```bash
cd ~/sdn-chat && python3 plot_scaling.py
```

Say: baseline (Ryu `simple_switch_13`) against our controller at 3, 10 and 20 clients: no lost messages, about 1 ms or less, so no measurable overhead. Show in the README:

- the scaling graph
- the blocking on/off table: about 94% less spam reached other users (102 messages with blocking, 1702 without)
- the QoS table from the 3-switch experiment

### Step 9 (optional, Person 2 explains). Meters (Tab 3)

```bash
sudo ovs-ofctl -O OpenFlow13 dump-meters s1
```

Say: one 500 kbps meter per user, created from the chat events. The delay improvement is measured in the 3-switch experiment (see the README). In this single-switch demo the meters exist but client uploads match the priority-150 rule, which has no meter, so they are not throttled here.

### Step 10. Clean up

1. Tab 4 (alice): type `QUIT`.
2. Tab 3: run `sudo ovs-ofctl -O OpenFlow13 dump-flows s1 | grep priority=150`. Alice's rule is gone, and Tab 1 shows `EVENT disconnect ... rule removed`.
3. Tab 5 (bob): type `QUIT`.
4. Type `exit` in each host shell (Tabs 4, 5 and 6).
5. Tab 2: at `mininet>`, type `exit`.
6. Tab 1: press Ctrl+C, then run `sudo mn -c`.

## If something goes wrong

| Problem | Fix |
|---|---|
| `mnexec` says no such process | The number is stale. Run `h2 echo $$` and `h3 echo $$` again at `mininet>`. |
| Controller says address already in use | `pkill -f ryu-manager`, then `sudo mn -c`, then restart from Step 1. |
| Flooder says the name is taken | The old flooder is still connected. Wait a few seconds or `exit` its tab. |
| `pingall` shows packet loss | Check Tab 1 for `switch 1 connected`. If it is missing, restart from Step 1. |
| Spam does not stop | Check Tab 1 for `FLOOD DETECTED`. The limit is 20 messages per second. |

## Questions each team member should be able to answer

- Why TCP for chat and UDP for controller events?
- What do the five priority levels do (0, 10, 100, 150, 200)?
- Why block at the switch, and why with a `hard_timeout`?
- Why does the server count messages instead of the controller counting packets?
- Why does the server need a lock, and why one thread per client?
- What does the table-miss rule do, and why is there a NAT node?
- What happens when a UDP event is lost?
- What did D2 add, and what are the limitations?
