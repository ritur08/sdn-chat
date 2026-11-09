#!/usr/bin/env python3
# PERSON2: new file. QoS (per-user meters + VIP rooms) on top of Ritu's controller.
# It SUBCLASSES her ChatController, so controller.py is NOT modified.
# Run with:  ryu-manager --ofp-tcp-listen-port 6653 controller_qos.py
# Everything Ritu's controller does (events, stats, flood block) still works.
#
# Policy:
#   - every registered user is NORMAL: their chat traffic goes through a meter
#     (rate limiter) of NORMAL_LIMIT_KBPS, one meter per user
#   - a user who is inside a VIP room (VIP_ROOMS) is exempt: no meter
#   - the JOIN / REGISTER / DISCONNECT events from the chat server change the
#     policy while the system is running
import os
import sys

# PERSON2: make "from controller import ..." work however ryu-manager is started
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3

from controller import ChatController, PRIO_CHAT

# ---------- PERSON2 settings (tune here) ----------
VIP_ROOMS = {"vip"}        # users inside these rooms are NOT rate limited
NORMAL_LIMIT_KBPS = 500    # every other user is limited to this rate (each)
BURST_KBIT = 100           # burst allowance of each meter
METER_BASE = 100           # per-user meter id = METER_BASE + last octet of the IP
COOKIE_QOS = 0x51          # tags the flows we manage, so we only ever remove ours
COOKIE_MASK = 0xFFFFFFFFFFFFFFFF


class QoSChatController(ChatController):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.switches = {}         # PERSON2: dpid -> datapath (ALL switches)
        self.meters_made = set()   # PERSON2: meter ids already created on every switch

    # PERSON2: runs in addition to Ritu's on_switch_features
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def qos_on_switch_features(self, ev):
        dp = ev.msg.datapath
        self.switches[dp.id] = dp
        self.logger.info("QOS: switch %s registered", dp.id)

    # ---------- reacting to chat events ----------
    def handle_event(self, line):
        """Ritu's handler runs first, unchanged; then we apply the QoS policy."""
        parts = line.split()
        kind = parts[0] if parts else ""
        ip = None
        if kind == "DISCONNECT" and len(parts) > 1:
            ip = self.users.get(parts[1])   # her code forgets the user, so read it first
        super().handle_event(line)
        if kind in ("REGISTER", "JOIN") and len(parts) > 1:
            ip = self.users.get(parts[1])
        if ip and kind in ("REGISTER", "JOIN", "DISCONNECT"):
            self.apply_policy(ip, kind.lower())

    def is_vip(self, ip):
        return any(self.user_room.get(name) in VIP_ROOMS
                   for name, u_ip in self.users.items() if u_ip == ip)

    def meter_for_ip(self, ip):
        """Meter id for this host, or None (VIP users, unknown hosts, the server)."""
        if ip not in self.users.values() or self.is_vip(ip):
            return None
        return METER_BASE + int(ip.split(".")[-1])

    def apply_policy(self, ip, why):
        meter_id = self.meter_for_ip(ip)
        if meter_id is not None:
            self.ensure_meter(meter_id)
        # Remove this host's chat flows on every switch. The next packet is a
        # table miss, so Ritu's packet-in code re-installs the flow, and our
        # add_flow below attaches the meter (or not) for the new policy.
        self.remove_tagged_flows(ip)
        if ip not in self.users.values():
            state = "no users left, limits cleared"
        elif meter_id is None:
            state = "VIP, no rate limit"
        else:
            state = "NORMAL, meter %d = %d kbps" % (meter_id, NORMAL_LIMIT_KBPS)
        self.logger.info("QOS: %s (%s) after %s -> %s",
                         self.name_for_ip(ip), ip, why, state)

    # ---------- meters and flows ----------
    def ensure_meter(self, meter_id):
        if meter_id in self.meters_made:
            return
        for dp in self.switches.values():
            self.add_meter(dp, meter_id, NORMAL_LIMIT_KBPS, BURST_KBIT)
        self.meters_made.add(meter_id)

    def add_meter(self, dp, meter_id, rate_kbps, burst_kbit):
        """Create a drop meter: packets above rate_kbps are dropped."""
        ofp, parser = dp.ofproto, dp.ofproto_parser
        band = parser.OFPMeterBandDrop(rate=rate_kbps, burst_size=burst_kbit)
        flags = ofp.OFPMF_KBPS | ofp.OFPMF_BURST | ofp.OFPMF_STATS
        dp.send_msg(parser.OFPMeterMod(datapath=dp, command=ofp.OFPMC_ADD,
                                       flags=flags, meter_id=meter_id,
                                       bands=[band]))

    # PERSON2: replaces Ritu's add_flow for chat flows only (priority 100).
    # Every other flow goes to her original add_flow untouched.
    def add_flow(self, dp, priority, match, actions, idle=0, hard=0):
        if priority != PRIO_CHAT:
            return super().add_flow(dp, priority, match, actions, idle, hard)
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = []
        meter_id = self.meter_for_ip(match.get("ipv4_src"))
        if meter_id is not None:
            self.ensure_meter(meter_id)
            inst.append(parser.OFPInstructionMeter(meter_id))
        inst.append(parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,
                                                 actions))
        dp.send_msg(parser.OFPFlowMod(datapath=dp, cookie=COOKIE_QOS,
                                      priority=priority, match=match,
                                      instructions=inst, idle_timeout=idle,
                                      hard_timeout=hard))

    def remove_tagged_flows(self, ip):
        """Delete only the flows WE tagged (cookie) for this source IP."""
        for dp in self.switches.values():
            ofp, parser = dp.ofproto, dp.ofproto_parser
            match = parser.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=ip)
            dp.send_msg(parser.OFPFlowMod(
                datapath=dp, command=ofp.OFPFC_DELETE, cookie=COOKIE_QOS,
                cookie_mask=COOKIE_MASK, out_port=ofp.OFPP_ANY,
                out_group=ofp.OFPG_ANY, match=match))
