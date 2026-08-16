#!/usr/bin/env python3
"""Regenerate every data-derived figure in the paper into figures/."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)
# topology-density.py reads data/derived/topology-scaling.csv; regenerate it first.
print("== precompute_topology_scaling.py")
subprocess.run([sys.executable,
                os.path.join(SCRIPTS_DIR, "precompute_topology_scaling.py")],
               check=True)
SCRIPTS = ["agent-scaling.py", "handshake-arrival.py", "topology-density.py",
           "coordination-degree.py", "cost-analysis.py", "channel-linearisation.py",
           "reliability-scatter.py", "topology-split.py"]
for s in SCRIPTS:
    print(f"== {s}")
    subprocess.run([sys.executable, os.path.join(HERE, s)], check=True)
print("all figures regenerated into figures/")
