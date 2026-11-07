#!/usr/bin/env python3
"""Ryu controller: learning switch + chat traffic classification +
reaction to chat events sent by the chat server over UDP.
D2 step 1: per-user traffic monitoring using OpenFlow flow statistics."""
import os
import socket
import time

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, ether_types

# ---------- configuration (tune values here) ----------
CHAT_PORT = 5000
EVENT_PORT = 9000      # the chat server sends UDP events here
STATS_INTERVAL = 3     # seconds between flow-statistics polls
FLOOD_MSGS = int(os.environ.get("FLOOD_MSGS", 20))         # chat msgs/sec (reported by the server) that counts as flooding
BLOCK_SECONDS = 30     # how long a flooding user stays blocked

PRIO_MISS = 0
PRIO_FWD = 10
PRIO_CHAT = 100
PRIO_USER = 150
PRIO_BLOCK = 200       # drop rule, beats every other rule


class ChatController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.seen_chat_flows = set()
        self.dp = None
        self.users = {}       # username -> ip
        self.rooms = {}       # room -> set of usernames
        self.user_room = {}   # username -> room
        self.prev_stats = {}  # ip -> (packets, bytes, timestamp)
        self.user_rates = {}  # ip -> (packets/sec, bytes/sec)
        self.blocked = {}     # ip -> time when its block expires
        hub.spawn(self.listen_for_events)
        hub.spawn(self.monitor_loop)

    # ---------- events from the chat server ----------
    def listen_for_events(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", EVENT_PORT))
        self.logger.info("listening for chat events on UDP %d", EVENT_PORT)
        while True:
            data, _ = sock.recvfrom(1024)
            try:
                self.handle_event(data.decode().strip())
            except Exception as e:
                self.logger.warning("bad event %r: %s", data, e)

    def handle_event(self, line):
        parts = line.split()
        kind = parts[0]
        if kind == "REGISTER":
            name, ip = parts[1], parts[2]
            self.users[name] = ip
            self.install_user_flow(ip)
            self.logger.info("EVENT register: %s at %s -> priority %d "
                             "rule installed", name, ip, PRIO_USER)
        elif kind == "JOIN":
            name, room = parts[1], parts[2]
            old = self.user_room.get(name)
            if old in self.rooms:
                self.rooms[old].discard(name)
            self.user_room[name] = room
            self.rooms.setdefault(room, set()).add(name)
            self.logger.info("EVENT join: %s joined %s (members: %s)",
                             name, room, sorted(self.rooms[room]))
        elif kind == "DISCONNECT":
            name = parts[1]
            ip = self.users.pop(name, None)
            room = self.user_room.pop(name, None)
            if room in self.rooms:
                self.rooms[room].discard(name)
            if ip and ip not in self.users.values():
                self.remove_user_flow(ip)
                self.prev_stats.pop(ip, None)
                self.user_rates.pop(ip, None)
            self.logger.info("EVENT disconnect: %s (rule removed)", name)
        elif kind == "RATE":
            name, rate = parts[1], float(parts[2])
            ip = self.users.get(name)
            if rate >= 5:
                self.logger.info("RATE %s: %.1f msg/s", name, rate)
            if ip and rate > FLOOD_MSGS and ip not in self.blocked:
                self.block_user(ip, rate)
        else:
            self.logger.warning("unknown event: %s", line)

    def user_match(self, ip):
        parser = self.dp.ofproto_parser
        return parser.OFPMatch(eth_type=0x0800, ip_proto=6,
                               ipv4_src=ip, tcp_dst=CHAT_PORT)

    def install_user_flow(self, ip):
        if self.dp is None:
            self.logger.warning("no switch connected yet")
            return
        parser = self.dp.ofproto_parser
        actions = [parser.OFPActionOutput(self.dp.ofproto.OFPP_NORMAL)]
        self.add_flow(self.dp, PRIO_USER, self.user_match(ip), actions)

    def remove_user_flow(self, ip):
        if self.dp is None:
            return
        ofp, parser = self.dp.ofproto, self.dp.ofproto_parser
        self.dp.send_msg(parser.OFPFlowMod(
            datapath=self.dp, command=ofp.OFPFC_DELETE_STRICT,
            priority=PRIO_USER, match=self.user_match(ip),
            out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY))

    # ---------- monitoring (D2 step 1) ----------
    def monitor_loop(self):
        """Every STATS_INTERVAL seconds, ask the switch for its flow stats."""
        while True:
            hub.sleep(STATS_INTERVAL)
            self.check_unblock()
            if self.dp is not None:
                parser = self.dp.ofproto_parser
                self.dp.send_msg(parser.OFPFlowStatsRequest(self.dp))

    def block_user(self, ip, rate):
        """Install a high-priority drop rule for a flooding user."""
        if self.dp is None:
            return
        self.add_flow(self.dp, PRIO_BLOCK, self.user_match(ip), [],
                      hard=BLOCK_SECONDS)
        self.blocked[ip] = time.time() + BLOCK_SECONDS
        self.logger.warning(
            "FLOOD DETECTED: %s (%s) sent %.1f msg/s (limit %d) -> "
            "BLOCKED for %d s (priority %d drop rule)",
            self.name_for_ip(ip), ip, rate, FLOOD_MSGS,
            BLOCK_SECONDS, PRIO_BLOCK)

    def check_unblock(self):
        """The switch removes the drop rule by itself; log when it expires."""
        now = time.time()
        for ip, until in list(self.blocked.items()):
            if now >= until:
                del self.blocked[ip]
                self.prev_stats.pop(ip, None)
                self.logger.info("UNBLOCKED: %s (%s) - block expired, "
                                 "access restored", self.name_for_ip(ip), ip)

    def name_for_ip(self, ip):
        for name, user_ip in self.users.items():
            if user_ip == ip:
                return name
        return "?"

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def on_flow_stats(self, ev):
        """Turn the switch's per-rule counters into per-user rates."""
        now = time.time()
        for stat in ev.msg.body:
            if stat.priority != PRIO_USER:
                continue
            ip = stat.match.get("ipv4_src")
            if ip is None:
                continue
            pkts, byts = stat.packet_count, stat.byte_count
            prev = self.prev_stats.get(ip)
            self.prev_stats[ip] = (pkts, byts, now)
            if prev is None or pkts < prev[0]:
                continue   # first sample, or the rule was re-installed
            dt = now - prev[2]
            if dt <= 0:
                continue
            pps = (pkts - prev[0]) / dt
            bps = (byts - prev[1]) / dt
            self.user_rates[ip] = (pps, bps)
            if pkts > prev[0]:   # only log users that were active
                self.logger.info(
                    "STATS %s (%s): %.1f pkt/s, %.0f B/s "
                    "(total %d pkts, %d bytes)",
                    self.name_for_ip(ip), ip, pps, bps, pkts, byts)

    # ---------- switch handling ----------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch_features(self, ev):
        dp = ev.msg.datapath
        self.dp = dp
        ofp, parser = dp.ofproto, dp.ofproto_parser
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                          ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, PRIO_MISS, parser.OFPMatch(), actions)
        self.logger.info("switch %s connected, table-miss rule installed",
                         dp.id)

    def add_flow(self, dp, priority, match, actions, idle=0, hard=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,
                                             actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority,
                                      match=match, instructions=inst,
                                      idle_timeout=idle,
                                      hard_timeout=hard))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def on_packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dp.id, {})
        self.mac_to_port[dp.id][eth.src] = in_port
        out_port = self.mac_to_port[dp.id].get(eth.dst, ofp.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        ip = pkt.get_protocol(ipv4.ipv4)
        seg = pkt.get_protocol(tcp.tcp)
        is_chat = bool(ip and seg and
                       CHAT_PORT in (seg.src_port, seg.dst_port))

        if out_port != ofp.OFPP_FLOOD:
            if is_chat:
                match = parser.OFPMatch(
                    in_port=in_port, eth_type=0x0800, ip_proto=6,
                    ipv4_src=ip.src, ipv4_dst=ip.dst,
                    tcp_src=seg.src_port, tcp_dst=seg.dst_port)
                self.add_flow(dp, PRIO_CHAT, match, actions, idle=60)
                key = (ip.src, seg.src_port, ip.dst, seg.dst_port)
                if key not in self.seen_chat_flows:
                    self.seen_chat_flows.add(key)
                    self.logger.info("CHAT flow: %s:%s -> %s:%s (prio %d)",
                                     ip.src, seg.src_port,
                                     ip.dst, seg.dst_port, PRIO_CHAT)
            else:
                match = parser.OFPMatch(in_port=in_port, eth_dst=eth.dst,
                                        eth_src=eth.src)
                self.add_flow(dp, PRIO_FWD, match, actions, idle=60)

        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        dp.send_msg(parser.OFPPacketOut(datapath=dp,
                                        buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions,
                                        data=data))
