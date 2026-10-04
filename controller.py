#!/usr/bin/env python3
"""Ryu controller: learning switch + chat traffic classification (D1)."""
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, ether_types

CHAT_PORT = 5000
PRIO_MISS = 0
PRIO_FWD = 10
PRIO_CHAT = 100


class ChatController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.seen_chat_flows = set()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def on_switch_features(self, ev):
        dp = ev.msg.datapath
        ofp, parser = dp.ofproto, dp.ofproto_parser
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                          ofp.OFPCML_NO_BUFFER)]
        self.add_flow(dp, PRIO_MISS, parser.OFPMatch(), actions)
        self.logger.info("switch %s connected, table-miss rule installed",
                         dp.id)

    def add_flow(self, dp, priority, match, actions, idle=0):
        ofp, parser = dp.ofproto, dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS,
                                             actions)]
        dp.send_msg(parser.OFPFlowMod(datapath=dp, priority=priority,
                                      match=match, instructions=inst,
                                      idle_timeout=idle))

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
