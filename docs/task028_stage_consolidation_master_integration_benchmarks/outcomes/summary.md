# Response V4 最新结论

Task028 Review V4 的三项轻量加固已在 `da05077fc010f658f2fe01ef65a00f0723cee88c` 关闭：5 份 Case002/003 lightweight canonical record 现在强制 `tracked_source_dirty=false`；两个 candidate runner 必须显式提供真实 `IMAGE_DIGEST`；最终实现提交的 checker 为 `148/148`，documentation contract 为 `11/11`，容器 preset/parser contract 为 `8/8`。未覆盖 canonical record，未重跑 h2，未启动新求解器或 Task29 实现。用户已明确许可完成这些修正后合并 Task28。

# Outcome Summary

## 任务

Task028 Response V3 关闭最终审查提出的 2D canonical 证据、preset 物理身份、PyCharm MPI4、教程/源码导读深度、理论统一、case-contained benchmark 和文档自动契约问题。

## 分支

| 项目 | 值 |
|---|---|
| branch | `codex/20260712-task28-stage-consolidation` |
| review | `review_report_v3.md` |
| 2D evidence source | `e89fb632bb4318a739afd1ee702be3a17d109d7c` |
| 原项目 worktree | 已恢复为唯一 Git worktree |
| master merge | 未执行，等待用户许可 |

## Changed Files

主要新增/修改：2D canonical runner 与 records、13 个 case contract、17 preset metadata、benchmark checker、lossy/lossless 与文档 tests、15 篇核心 Quick Start、11 篇核心 Walkthrough、Theory 统一表，以及本任务 response/outcomes。完整清单见 `changed_files.md`。

## Run Commands

```text
python -m benchmarks.run_2d_canonical --case 002 ...
python -m benchmarks.run_2d_canonical --case 003 --variant tm ...
python -m benchmarks.run_2d_canonical --case 003 --variant te ...
python -m unittest discover -s src/test -p "test_*.py"
mpiexec -n 4 python -m unittest src.test.test_22_condensed_dtn src.test.test_23_physical_slab_two_level
python benchmarks/check_benchmarks.py --no-write
```

## Physical Model

Case002 为 10 x 10 nm 无损零对比 TM。Case003 TM 为 100 nm EUV 周期多阶 DtN，TE 为 10 x 10 nm 小平层；两者使用同一 complex Si 折射率，但作为独立 frozen variants。

3D target 仍为 50 x 25 x 140 nm、17 x 25 x 120 nm block、13.5 nm、80 度 s polarization。3D canonical 数值本轮只审计，不重跑。

## Numerical Settings

| case | element | h/nm | port |
|---|---|---:|---|
| 002 explicit/auxiliary | N1curl p1 | 2 | TM Fourier-DtN |
| 003 TM | N1curl p2 | 3 | 30 auxiliary modes |
| 003 TE | Lagrange p1 | 2 | scalar explicit zero order |

## Key Results

| case | DoF/rows | residual | R | T | A_volume | closure | RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| 002 explicit | 139/139 | 2.168e-15 | 4.7765e-4 | 0.9995223 | 0 | 4.44e-16 | lightweight |
| 002 auxiliary | 139+2/141 | 1.867e-15 | 4.7765e-4 | 0.9995223 | 0 | 1.67e-15 | lightweight |
| 003 TM | 14,452+30/14,482 | 3.323e-14 | 3.663e-6 | 0.8821725 | 0.1178239 | -3.33e-15 | 365.30 MB |
| 003 TE | 56/56 | 1.486e-15 | 8.746e-5 | 0.9903458 | 0.0095668 | 5.83e-16 | 287.48 MB |

Case002 field relative difference `2.771e-15`，最大 R/T/A 差 `1.221e-15`。TM auxiliary/trace 最大差同为 `1.221e-15`。

## Energy Check

有损功率只使用实际端口平面 coefficient；phase-normalized report amplitude 不进入 T。TM/TE 的 `A_balance-A_volume` 分别为约 `-3.33e-15/5.83e-16`。probe closure 保留为 diagnostic，不覆盖 official。

## Mesh / DoF / Solver Cost

本轮新运行均为轻量 2D。3D 既有记录仍为：h5 44,698 DoF/1.991 GB、h3 198,438/5.082 GB、h2 615,108/13.080 GB；没有重复运行 h2 direct 或 iterative。

## Validation

| 检查 | 结果 |
|---|---|
| compileall | pass |
| Ruff | pass |
| full suite | 115 passed，10 skipped |
| MPI4 | 每 rank 14 passed |
| documentation contract | 11 passed |
| benchmark checker | 143/143 passed |

## Known Issues

Stage2B/2C 精度、h1.5、near-Rayleigh 和参数域鲁棒性仍未资格化；基础 complex MPC image 仍是本机限定。`SmallDenseInverse` 显式 inverse 是非阻断技术债。

## Next Questions for Review

1. P0-1 至 P0-15 是否已全部关闭？
2. Case002/003 的 canonical record 与 Gate 是否足够作为 production regression？
3. 15 篇 Quick Start、11 篇核心 Walkthrough 和 13 个 case README 是否达到可跟随深度？
4. 审查通过后是否由用户许可合并 master？
