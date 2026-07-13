# 测试总结

## Response V4 最终实现提交验证

验证提交：`da05077fc010f658f2fe01ef65a00f0723cee88c`。

| 检查 | 环境 | 结果 |
|---|---|---|
| tracked source status | host Git，忽略 untracked | clean |
| benchmark checker `--no-write` | host | 148/148 passed |
| benchmark contract | host | 5/5 passed |
| documentation contract | host | 11/11 passed |
| preset/parser contract | `myfenics-stage4:task28` | 8/8 passed |
| Ruff check/format | host | pass |
| `git diff --check` | host | pass |

Case002/003 canonical JSON 未被覆盖；h2 direct/iterative、h1.5 和新参数扫描均未运行。

## Response V3 最终验证

| 检查 | 环境 | 结果 |
|---|---|---|
| `compileall` | `myfenics-stage4:task28` | pass |
| Ruff check/format | host Ruff 0.12.0 | pass |
| full `src/test` | complex DOLFINx container | 115 passed，10 skipped |
| focused MPI4 | 同一容器 | 4 ranks，各 14 passed |
| documentation contract | host + container | 11 passed |
| preset/parser contract | container | 17 presets 全部接受 |
| benchmark checker | host + container | 143/143 passed |
| Markdown local links | test26 | pass |
| `git diff --check` | host | pass |

## 2D Canonical Runs

| case | residual | 核心 Gate | 结果 |
|---|---:|---|---|
| Case002 explicit | 2.168e-15 | lossless closure、matrix stats | pass |
| Case002 auxiliary | 1.867e-15 | field/RTA 对 explicit | pass |
| Case003 TM | 3.323e-14 | nonnegative、A balance、aux/trace | pass |
| Case003 TE | 1.486e-15 | nonnegative、A balance、closure | pass |

## Lossless/Lossy Regression

| 回归 | 证据 |
|---|---|
| zero contrast `R≈0,T≈1` | Case002 + existing Level1 record |
| lossless flat interface `R+T≈1` | `test_03_fresnel_coefficients` |
| below-cutoff order has no power | `test_20_2d_lossy_port_modes` |
| lossy propagating order carries positive real power | `test_20_2d_lossy_port_modes` |

## Documentation Contract

自动检查 15 篇核心 Quick Start 的 16 节结构与最低深度、11 篇核心 Walkthrough 的源码/shape/ownership/公式/调用/Gate/限制、13 个 case-contained contract、Case002/003 record 字段、技术错误防回归、demo/target 名称、MPI4 PyCharm 配置和全部本地链接。

## Benchmark Gate

143 项包括 13 个 case contract、7 个 SHA reference、全部 record metadata/commit、Case002 双解、Case003 lossy、lossless、3D direct/iterative、三残差、coarse、physical model、RSS、RTA、environment 和 ordinary default。

## 未重跑

没有运行 h2 ordinary direct、h2 iterative、h1.5 或新参数扫描。3D 数值只读取既有已审查 records；本轮计算负担集中在 2D lightweight canonical 与软件测试。
