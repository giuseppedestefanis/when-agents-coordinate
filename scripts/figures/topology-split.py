#!/usr/bin/env python3
"""Regenerate the paper's team-structure x split success figure from data/."""
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def cp_interval(k, n):
    lo = stats.beta.ppf(0.025, k, n-k+1) if k > 0 else 0.0
    hi = stats.beta.ppf(0.975, k+1, n-k) if k < n else 1.0
    return lo, hi

r1 = pd.read_csv(os.path.join(ROOT, 'data', 'family-1-full', 'master', 'runs.csv'))
r2 = pd.read_csv(os.path.join(ROOT, 'data', 'family-2-full', 'master', 'runs.csv'))
splits = ['clean', 'overlapping', 'conflicting']

def rates(df, task, n, topos):
    out = []
    for s in splits:
        d = df[(df.instance == f'{task}/{s}') & (df.agent_count == n)
               & (df.artefact_policy == 'allowed') & (df.topology.isin(topos))]
        k, m = int(d.success.sum()), len(d)
        lo, hi = cp_interval(k, m)
        out.append((k/m, lo, hi))
    return out

fig, axes = plt.subplots(2, 2, figsize=(9.2, 6.4), sharey=True)
panels = [(r1, 'process_orders', 4,  'Experiment 1 (distributed), $n=4$'),
          (r1, 'process_orders', 8,  'Experiment 1 (distributed), $n=8$'),
          (r2, 'summarise_transactions', 4, 'Experiment 2 (chained), $n=4$'),
          (r2, 'summarise_transactions', 8, 'Experiment 2 (chained), $n=8$')]
x = np.arange(3)
for ax, (df, task, n, title) in zip(axes.flat, panels):
    for topos, dx, color, marker, label in [
            (['solo', 'peer'], -0.08, '#2b6cb8', 'o', 'flat, both sessions ($N{=}20$)'),
            (['orchestrator'], +0.08, '#b07547', 's', 'orchestrator ($N{=}10$)')]:
        se = rates(df, task, n, topos)
        ys = [s[0] for s in se]
        ax.errorbar(x+dx, ys, yerr=[[s[0]-s[1] for s in se], [s[2]-s[0] for s in se]],
                    fmt=marker, color=color, markersize=7, markeredgecolor='black',
                    markeredgewidth=0.6, capsize=3, lw=1.3, label=label)
        ax.plot(x+dx, ys, color=color, lw=1.0, alpha=0.55)
    ax.set_title(title, fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels(splits, fontsize=9)
    ax.set_ylim(-0.05, 1.09); ax.grid(axis='y', alpha=0.25)
    ax.spines[['top', 'right']].set_visible(False)
for ax in axes[:, 0]: ax.set_ylabel('verifier success rate', fontsize=9.5)
axes[0, 0].legend(fontsize=8.5, loc='lower left', frameon=True)
fig.tight_layout()
out = os.path.join(ROOT, 'figures', 'topology-split.png')
fig.savefig(out, dpi=200)
print('wrote', out)
