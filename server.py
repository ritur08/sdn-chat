#!/usr/bin/env python3
"""Multi-client TCP chat server. Sends UDP events to the SDN controller."""
import socket
import threading

HOST = "0.0.0.0"
PORT = 5000
CONTROLLER_ADDR = ("10.0.0.254", 9000)  # Ryu controller (via Mininet NAT)

clients = {}    # username -> socket
rooms = {}      # room name -> set of usernames
user_room = {}  # username -> current room
lock = threading.Lock()  # protects the three dicts above

notify_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

HELP = ("Commands: REGISTER <name> | JOIN <room> | MSG <text> | "
        "PM <user> <text> | USERS | LEAVE | QUIT")


def notify(text):
    """Tell the SDN controller about a chat event (fire and forget)."""
    try:
        notify_sock.sendto(text.encode(), CONTROLLER_ADDR)
    except OSError:
        pass


def send(sock, text):
    try:
        sock.sendall((text + "\n").encode())
    except OSError:
        pass


def broadcast(room, text, exclude=None):
    with lock:
        targets = [clients[u] for u in rooms.get(room, set())
                   if u != exclude and u in clients]
    for s in targets:
        send(s, text)


def leave_room(name):
    with lock:
        room = user_room.pop(name, None)
        if room:
            rooms[room].discard(name)
            if not rooms[room]:
                del rooms[room]
    if room:
        broadcast(room, f"* {name} left {room}")
    return room


def handle_client(conn, addr):
    name = None
    send(conn, "Welcome! " + HELP)
    try:
        for line in conn.makefile("r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            cmd = parts[0].upper()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd == "REGISTER":
                if name:
                    send(conn, "ERR already registered")
                elif not arg or " " in arg:
                    send(conn, "ERR usage: REGISTER <name> (no spaces)")
                else:
                    with lock:
                        taken = arg in clients
                        if not taken:
                            clients[arg] = conn
                    if taken:
                        send(conn, "ERR name already taken")
                    else:
                        name = arg
                        send(conn, f"OK registered as {name}")
                        print(f"[server] {name} registered from {addr[0]}")
                        notify(f"REGISTER {name} {addr[0]}")
            elif cmd == "QUIT":
                break
            elif name is None:
                send(conn, "ERR register first: REGISTER <name>")
            elif cmd == "JOIN":
                if not arg or " " in arg:
                    send(conn, "ERR usage: JOIN <room> (no spaces)")
                else:
                    leave_room(name)
                    with lock:
                        rooms.setdefault(arg, set()).add(name)
                        user_room[name] = arg
                    send(conn, f"OK joined {arg}")
                    broadcast(arg, f"* {name} joined {arg}", exclude=name)
                    notify(f"JOIN {name} {arg}")
            elif cmd == "LEAVE":
                if leave_room(name):
                    send(conn, "OK left room")
                else:
                    send(conn, "ERR you are not in a room")
            elif cmd == "MSG":
                room = user_room.get(name)
                if not room:
                    send(conn, "ERR join a room first: JOIN <room>")
                elif not arg:
                    send(conn, "ERR usage: MSG <text>")
                else:
                    broadcast(room, f"[{room}] {name}: {arg}")
            elif cmd == "PM":
                target, _, text = arg.partition(" ")
                with lock:
                    target_sock = clients.get(target)
                if not target or not text:
                    send(conn, "ERR usage: PM <user> <text>")
                elif target_sock is None:
                    send(conn, f"ERR user {target} not found")
                else:
                    send(target_sock, f"[PM from {name}] {text}")
                    send(conn, f"[PM to {target}] {text}")
            elif cmd == "USERS":
                with lock:
                    names = sorted(clients)
                send(conn, "Users: " + ", ".join(names))
            else:
                send(conn, "ERR unknown command. " + HELP)
    except (OSError, UnicodeDecodeError):
        pass
    finally:
        if name:
            leave_room(name)
            with lock:
                clients.pop(name, None)
            print(f"[server] {name} disconnected")
            notify(f"DISCONNECT {name}")
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)
    print(f"[server] listening on {HOST}:{PORT}")
    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr),
                             daemon=True).start()
    except KeyboardInterrupt:
        print("\n[server] shutting down")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
