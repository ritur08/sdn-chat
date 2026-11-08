import csv, sys
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

path = sys.argv[1] if len(sys.argv) > 1 else "results.csv"
rows = defaultdict(list)
with open(path) as f:
    for r in csv.DictReader(f):
        rows[(r["label"], int(r["clients"]))].append(r)

labels = ["baseline", "sdn"]
clients = sorted({c for (_, c) in rows})

def stat(label, c, col, fn):
    vals = [float(r[col]) for r in rows.get((label, c), [])]
    return fn(vals) if vals else 0.0

mean = lambda v: sum(v) / len(v)

print("%-9s %7s %5s %9s %9s %9s %6s" % ("label", "clients", "runs", "avg_ms", "p95_ms", "max_ms", "lost"))
for lab in labels:
    for c in clients:
        rs = rows.get((lab, c), [])
        lost = sum(int(r["lost"]) for r in rs)
        print("%-9s %7d %5d %9.2f %9.2f %9.1f %6d" % (
            lab, c, len(rs), stat(lab, c, "avg_ms", mean),
            stat(lab, c, "p95_ms", mean), stat(lab, c, "max_ms", max), lost))

fig, axes = plt.subplots(1, 2, figsize=(10, 4))
w = 0.35
x = list(range(len(clients)))
for ax, col, title in [(axes[0], "avg_ms", "Average round-trip time"),
                       (axes[1], "p95_ms", "95th percentile round-trip time")]:
    for i, lab in enumerate(labels):
        ys = [stat(lab, c, col, mean) for c in clients]
        ax.bar([p + i * w for p in x], ys, w, label=lab)
    ax.set_xticks([p + w / 2 for p in x])
    ax.set_xticklabels([str(c) for c in clients])
    ax.set_xlabel("Number of clients")
    ax.set_ylabel("ms (mean of runs)")
    ax.set_title(title)
    ax.legend()
plt.tight_layout()
plt.savefig("scaling.png", dpi=150)
print("saved scaling.png")
