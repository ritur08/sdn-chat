# PERSON3 - table + graph from results_raw.csv (NEW file)
import csv
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as C

agg = defaultdict(lambda: [0, 0, 0.0])   # (mode, n) -> sent, recv, total_ms
with open(C.RESULTS_FILE) as f:
    for mode, n, _, sent, recv, tot in csv.reader(f):
        r = agg[(mode, int(n))]
        r[0] += int(sent); r[1] += int(recv); r[2] += float(tot)

rows = []
for (mode, n), (sent, recv, tot) in sorted(agg.items(), key=lambda x: (x[0][1], x[0][0])):
    avg = tot / recv if recv else float("nan")
    rows.append((n, mode, avg, sent - recv, sent))

print("| clients | controller | avg delay (ms) | lost msgs | sent |")
print("|---|---|---|---|---|")
for n, mode, avg, lost, sent in rows:
    print(f"| {n} | {mode} | {avg:.1f} | {lost} | {sent} |")

fig, ax = plt.subplots(1, 2, figsize=(10, 4))
for mode in ("baseline", "sdn"):
    pts = [(n, avg, 100 * lost / sent) for n, m, avg, lost, sent in rows if m == mode and sent]
    if pts:
        ax[0].plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=mode)
        ax[1].plot([p[0] for p in pts], [p[2] for p in pts], marker="o", label=mode)
ax[0].set(xlabel="clients", ylabel="avg round-trip delay (ms)", title="Delay")
ax[1].set(xlabel="clients", ylabel="lost messages (%)", title="Loss")
for a in ax: a.legend(); a.grid(True)
plt.tight_layout()
plt.savefig("results.png", dpi=150)
print("saved results.png")
