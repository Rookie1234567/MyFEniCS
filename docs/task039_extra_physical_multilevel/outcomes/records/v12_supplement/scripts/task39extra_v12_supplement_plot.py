"""Plot measured bounded outer histories; no interpolation or extrapolation."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument('history', type=Path)
parser.add_argument('outer_audit', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
history = json.loads(args.history.read_text())
outer = json.loads(args.outer_audit.read_text())
assert not history['errors'] and not outer['errors']
fig, axes = plt.subplots(1, 2, figsize=(12.8, 4.8), constrained_layout=True)
colors = ['#475569', '#64748b', '#94a3b8', '#85955b', '#ae8f55']
labels = ['V5 exact p4 (historical)', 'V7 entity I16 (historical)',
          'V7 projected seq2 (historical)', 'V8 GCROT8 (historical)',
          'V9 GCROT8 new16 (historical)']
for case, color, label in zip(history['historical_cases'], colors, labels, strict=True):
    nodes = case['nodes_through_64']
    iteration = [row['iteration'] for row in nodes]
    rho = [row['explicit_true_residual'] for row in nodes]
    seconds = [row['solve_seconds'] for row in nodes]
    axes[0].semilogy(iteration, rho, 'o-', lw=1.3, ms=3, color=color, label=label)
    axes[1].semilogy(seconds, rho, 'o-', lw=1.3, ms=3, color=color, label=label)
for run in outer['runs']:
    restart = run['restart']
    color = '#b91c1c' if restart == 32 else '#0369a1'
    nodes = run['nodes']
    iteration = [row['iteration'] for row in nodes]
    rho = [row['true_residual'] for row in nodes]
    seconds = [row['elapsed_seconds_conservative'] for row in nodes]
    label = f'V12 complete PC, restart {restart}'
    axes[0].semilogy(iteration, rho, 's-', lw=2, ms=4, color=color, label=label)
    axes[1].semilogy(seconds, rho, 's-', lw=2, ms=4, color=color, label=label)
axes[0].set_xlabel('Outer iteration (different PC work per iteration)')
axes[1].set_xlabel('Conservative outer solve seconds (setup excluded)')
for ax in axes:
    ax.set_ylabel('Full explicit original A6 relative residual')
    ax.grid(True, which='both', alpha=.18)
    ax.set_ylim(1e-2, 1.2)
    ax.spines[['top', 'right']].set_visible(False)
axes[0].set_xlim(0, 66)
axes[0].legend(fontsize=7.3, frameon=False, loc='lower left')
fig.suptitle('Same physical model and modes; measured nodes only, bounded at 64 iterations', fontsize=12)
fig.supxlabel('No convergence claim. Time axis excludes setup and separate failed/stopped attempts; diagnostic frequency differs across historical runs.', fontsize=8)
args.output.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(args.output.with_suffix('.png'), dpi=180)
fig.savefig(args.output.with_suffix('.svg'))
print(args.output.with_suffix('.png'))
