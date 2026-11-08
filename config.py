# PERSON3 - shared constants (NEW file)
SERVER_IP = "10.0.0.1"
CLIENT_START_IP = "10.0.0.2"
CONTROLLER_NAT_IP = "10.0.0.254"
CLIENT_COUNTS = [3, 10, 20]
CLIENT_HOSTS = 5          # how many Mininet client hosts to spread clients over

# --- ADAPT THESE 3 LINES to the real chat protocol (copy from probe.py / client code) ---
SERVER_PORT = 5000                    # TODO: real server port
LOGIN_LINE = "REGISTER {name}\n"          # TODO: whatever a client sends to log in
PM_LINE = "PM {name} {text}\n"        # private message to self, e.g. "PM c1 ping1"
# -----------------------------------------------------------------------------------------

DURATION = 30      # seconds per client
RATE = 2           # messages per second per client
TIMEOUT = 2.0      # seconds to wait for a ping to come back; otherwise counted as lost
RESULTS_FILE = "results_raw.csv"
