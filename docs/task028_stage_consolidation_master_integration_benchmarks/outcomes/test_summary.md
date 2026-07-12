# 测试总结

## 最终自动验证

| 检查 | 环境 | 结果 |
|---|---|---|
| `compileall` | `myfenics-stage4:task28` | 通过 |
| Ruff check / format | host Ruff 0.12.0 | 16 个改动 Python 文件通过 |
| 完整 `src/test` | 同上 | 105 通过，10 跳过 |
| focused MPI4 | 同上 | 4 个 rank 各 14 通过 |
| documentation contract | host + container | Quick Start、Walkthrough、Theory、13 cases、相对链接通过 |
| main preset contract | 同上 | 15 个 preset 唯一且全部被真实 runner parser 接受 |
| benchmark checker | host + container | 87/87 通过，失败具有非零退出码 |
| `git diff --check` | host | 通过 |

10 项跳过均为环境或可选后端的既有条件跳过，不是失败。

## Response V2 真实 smoke

| 案例 | 网格/DoF | residual | 主要结果 | RSS |
|---|---|---:|---|---:|
| 默认 3D Stage1 | 48 cells / 98 DoF | 1.4355e-16 | E error 0.02482，H error 0.03724，方向余弦 1 | 274.4 MB |
| 2D TM complex absorption | 14,452 FE + 30 aux | 3.3225e-14 | R=3.6625e-6，T=0.88217245，A=0.11782389，closure=3.33e-15 | 轻量 |
| 2D TE complex absorption | 56 DoF | 1.4856e-15 | R=8.7456e-5，T=0.99034578，A=0.00956676，closure=-5.50e-16 | 轻量 |

TM official auxiliary、boundary trace 与 A_volume 闭合一致到 `3.33e-15`。TM probe closure 约 `2.13e-2`、TE probe closure 约 `-7.51e-2`，因此仍标记为 diagnostic_only。

## Canonical record Gate

| Gate | h5 | h3 | h2 |
|---|---:|---:|---:|
| `ksp_reason > 0` | pass | pass | pass |
| full true residual | 9.8395e-7 | 9.9326e-7 | 9.9974e-7 |
| coarse condition | 900.96 | 606.76 | 734.32 |
| energy closure | -2.55e-9 | 6.18e-10 | 6.58e-9 |
| total peak RSS | 1.991 GB | 5.082 GB | 13.080 GB |
| physical model/provenance | pass | pass | pass |

## 未重跑项目

h=2 ordinary direct 未重复运行；其已审查 reference 约需 20.533 GB，超过当前 14 GB 配额。h=2 iterative 也没有因为纯文档重构重复运行；checker 只审计既有 canonical record、真实来源、物理模型和 qualification。

## 最终命令

```text
docker run ... myfenics-stage4:task28 sh -lc '
  python -m compileall -q src benchmarks &&
  python -m unittest discover -s src/test -p "test_*.py" &&
  mpiexec -n 4 python -m unittest \
    src.test.test_22_condensed_dtn \
    src.test.test_23_physical_slab_two_level &&
  python benchmarks/check_benchmarks.py --no-write'
```
