# Task036 test summary

## 1. 当前状态

本文件先以 `IN_PROGRESS_PENDING_FINAL_TRACEBACK` 状态推送，现已用同一个未中断
的 full-repository pytest 最终输出收口。该运行在数值源码 `bb0e5e3...` 上得到：

```text
803 passed, 41 skipped, 3 failed in 2935.37 s
```

三个 failure 均不是数值 PDE assertion：一个是 B08 后未更新的旧 telemetry 文案
断言，一个是临时 clean worktree 未链接项目 `.venv` 造成的路径误判，一个是
numerical-blob checker 漏登记 Task036 已实测的 QEP helper。前者和后者由最小
测试/治理合同提交 `5231282...` 修正；中间一项用正确的 checkout-local `.venv`
链接复核。最终在主 checkout 与 clean worktree 均得到 `59 passed`，Ruff 和
compileall 通过，临时链接随后删除，两个 worktree 均恢复干净。

没有第二次运行耗时 48 分 55 秒的 full suite：收口提交没有改变数值 kernel，
三个原失败点均由定向测试覆盖，且最慢的 p1–p6 测试在原 full suite 已通过。
因此本文不把结果写成“最终 full suite 0 failure”，而使用更准确的口径：
**完整执行为 803/41/3，三项非数值收口在最终提交上定向通过。**

| 项目 | 值 |
|---|---|
| 最终数值源码 | `bb0e5e3e385586e137d861cf0a53a142e4fe0fe0` |
| full-test 收口提交 | `5231282f21e799c62b3a10ac1ccb1a8226935dc6` |
| 起始 `origin/master` | `007298261681014efbe6508ac91c6c3ae9a6a44a` |
| 分支 | `codex/20260730-task36-forward-solver-bugfix-hardening` |
| full-suite worktree | `/tmp/myfenics-task036-p6phi45` |
| full-suite source identity | `bb0e5e3e385586e137d861cf0a53a142e4fe0fe0` |
| post-full targeted source | `5231282f21e799c62b3a10ac1ccb1a8226935dc6` |
| full-suite过滤 | 无 deselect；不是缩减版 suite |
| ordinary default | unchanged |

## 2. 环境和 ABI

所有正式 Python、MPI、PETSc、DOLFINx 和 PDE 命令均在
`/home/Projects/MyFEniCS` 的资格化 WSL activation 中执行。最终 preflight 为：

| 检查 | 结果 |
|---|---|
| Python | 仓库 `.venv` |
| `PETSc.ScalarType` | `complex128` |
| `PETSc.IntType` | `int32` |
| MPI | Open MPI `4.1.6` |
| activation marker | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Windows Python/Git/MPI 污染 | 未发现 |

## 3. 已完成测试

### 3.1 Task036 focused regression

| source | suite | 结果 |
|---|---|---:|
| `9de46581...` | 最终 focused Task036 组合 | `60 passed`，`23.68 s` |
| `bb0e5e3...` | `test_181` + `test_196` incidence/traction Gate | `16 passed`，`1.80 s` |
| `bb0e5e3...` | partial-missing exact traction fail-closed 回归 | `8 passed`，`1.64 s` |
| `bb0e5e3...` | DtN/Floquet/Task036 组 | `49 passed, 4 skipped` |
| `bb0e5e3...` | mode/Hybrid/static 组 | `55 passed` |
| `bb0e5e3...` | 其余 high-order/docs 组 | `63 passed, 1 deselected` |
| `5231282...` | 三个 full-suite failure 及 B08/Task036 相关回归 | `59 passed`，主 checkout `1.87 s`，clean worktree `1.88 s` |

最后一行的临时 deselect 仅发生在分组审计阶段：旧的 30 分钟边界曾中止一个已知
长测试。随后已按 Task036 的 90 分钟单项边界启动无 deselect 的 full suite；最终
结论只以该运行结果为准。

### 3.2 Full-repository pytest

完整命令为：

```bash
cd /tmp/myfenics-task036-p6phi45
source /home/Projects/MyFEniCS/scripts/activate_myfenics_wsl.sh
TMPDIR=/tmp/myfenics-task036-fullrepo-bb0e5e3 \
TMP=/tmp/myfenics-task036-fullrepo-bb0e5e3 \
TEMP=/tmp/myfenics-task036-fullrepo-bb0e5e3 \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -m pytest -q --durations=20
```

| 项目 | 结果 |
|---|---|
| 完整计数 | `803 passed, 41 skipped, 3 failed` |
| error | `0` |
| 总时间 | `2935.37 s`（48:55） |
| 最慢测试 | `test_53` p1–p6，`1738.74 s`，pass |
| 数值 PDE assertion failure | `0` |

三个 failure 的处置为：

| failure | 根因 | 最终处置 |
|---|---|---|
| `test_28_direct_memory_telemetry.py:70` | 旧测试仍要求 `not inferred MUMPS`，与 B08 只对负 `INFOG(9)` 使用文档化 million-entry correction 的新合同冲突 | 改为检查 `factor_nnz_source`、storage source 和 PETSc fallback；B08 专测继续通过 |
| `test_73_task034_hardening.py:160` | clean worktree 没有 `.venv`，却从主 checkout activation，实际 complex ABI 全通过但 ROOT-relative path Gate 失败 | 不放宽 probe；验证时建立指向同一项目 `.venv` 的临时 checkout-local 链接，测试通过后删除 |
| `test_73_task034_hardening.py:185` | `src/modes/quadratic_beta_eigenproblem.py` 的显式 residual helper 已用于 Task036 reciprocal 路径，但 checker 漏登记 | 增加 `requires PDE rerun` 分类；已有 QEP/Hybrid/PDE anchors 支撑，checker 定向通过 |

pytest 的 PTY 输出文件在运行期是已删除的临时 FD，结束后没有可绑定的持久日志；
本文只记录 Codex 捕获的最终计数和 traceback，不伪造日志路径。

### 3.3 MPI 小型回归

| MPI | 结果 |
|---|---|
| MPI1 | `4 passed`，`1.58 s` |
| MPI2 rank 0 | `4 passed`，`1.46 s` |
| MPI2 rank 1 | `4 passed`，`1.45 s` |

这些测试用于检查串并行语义和 ABI；正式数值 PDE 证据仍以用户要求的 MPI8 为主。

### 3.4 静态与文档检查

| 检查 | 结果 |
|---|---|
| tracked JSON parse | `928` 个文件通过 |
| Ruff | pass |
| `compileall`（`src/`、`benchmarks/`） | pass |
| `git diff --check` | pass |

主工作树中的一次文档扫描曾看到 ignored 的
`benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/__pycache__/`，
使一个“case 目录必须属于 001–097”测试失败。干净 worktree 中不存在 Case098，
该测试通过；这属于本地 ignored 历史缓存污染，不是 tracked source failure。
Task036 没有删除历史 evidence，也没有为迎合测试而放宽目录合同。

### 3.5 并发 pytest 的环境负信号

一次将三个会导入 `mpi4py` 的 pytest collection 进程同时启动时：

- DtN/Floquet 组正常得到 `49 passed, 4 skipped`；
- 另外两个 collection 进程在 OpenMPI singleton 初始化阶段退出 `139`；
- 三组改为顺序运行后均通过。

该现象分类为本机 OpenMPI singleton/shared-TMP 的 orchestration controlled
negative，不是代码 assertion failure。正式 MPI8 PDE 每个 run 使用独立 output、
TMP/TEMP 与 MUMPS scratch，未混用结果目录。

## 4. 正式 PDE 回归摘要

### 4.1 Full3D 与 Ny alias

| 模型 | 结果 |
|---|---|
| p2/h5 S standard | pass；true residual `1.225e-11`；direct projection `9.47e-14`；同步峰值 `3.012 GiB` |
| p4/h10 P static | pass；同步峰值 `4.535 GiB` |
| p6/h10 S static | pass；同步峰值 `15.567 GiB` |
| Ny3 y-invariant control | actual MPC overlap `0.9171201301 > 1e-8`；solve 前受控拒绝 |
| Ny4 refinement control | pass；overlap `4.357371e-16`；非零 n power `7.11637e-25`；zero swap |

Ny3 是新增 preflight 正确捕获旧 alias 根因的 controlled negative；不得写成 solver
失败。Ny4 证明细化后的 trace identity 与物理结果恢复。

### 4.2 Hybrid representative points

| 模型 | 结果 |
|---|---|
| F1 M120 S standard/static | reciprocal、direct projection、exact traction dual 和正式数值 Gate 通过 |
| F2/F5 M120 P static | `hybrid_modal_rank_insufficient`；Hybrid-P 保持 fail closed |
| F1 M40 S | bounded repair 后 row norm `1.049407943e-6 > 1e-6`；solve 前受控停止 |
| conical S ordinary | independent positive/negative QEP 通过；ordinary default 未改变 |

### 4.3 p6/h10、10° grazing（theta=80°）、phi=45°

Full3D static MPI8 在最终源码上通过：

- true residual：`1.681162353460025e-11`；
- energy closure：`2.0112800314109336e-12`；
- direct projection 最大差：`7.493344841658936e-13`；
- 同步 process-tree 峰值：`15.400711059570312 GiB`；
- PSS / USS：`13803.7998 / 13165.0078 MiB`；
- swap：`0`。

对应 Hybrid M120 是最终 controlled negative：

- scalar-stage4 reciprocal basis 是显式 `research_only` opt-in；
- 一次有界 repair 将 row norm 从 `2.207345253e-6` 降至
  `1.033365679e-6`，cross norm 从 `1.629344379e-6` 降至
  `6.962868665e-7`；
- 新 worst groups 转到 `[96,97] / [98,99]`；
- repair budget 已耗尽，Hybrid solve 未进入；
- disposition 为 `bounded_repair_exhausted`，分类
  `DEFERRED_ARCHITECTURE_REQUIRED`。

这条结果证明 Task036 能确定性检测并限制局部修复，但没有把通用 near-degenerate
continuation 冒充已解决。

## 5. 当前测试判定

| Gate | 当前状态 |
|---|---|
| ABI | pass |
| targeted regressions | pass |
| MPI small regressions | pass |
| Ruff / compileall / JSON / diff-check | pass |
| MPI8 PDE evidence | pass 或按合同保存为 controlled negative |
| full repository pytest | `803 passed, 41 skipped, 3 failed`；三个 failure 均为非数值收口项 |
| post-full targeted closure | `59 passed`，主 checkout 与 clean worktree 均通过 |
| Task036 最终测试闭合 | complete；无数值 failure，未虚称 full suite 零失败 |

## 6. Review V2 启动检查点

Review V2 只新增扫描范围，没有改变已完成 PDE 的数值源码。Round A/B/C/D 的冻结点表
和合同测试属于调度/文档改动，因此未触发旧 PDE 或 48:55 full-suite 重跑。

| 检查 | 状态 |
|---|---|
| V2 review HEAD | `1eab6393525d25ebbf0e7d5068f446c6d5afde1f` |
| frozen configurations | `226` |
| frozen table SHA-256 | `01701c580355b8870c3865a6cb631d4db53f12a1a8fc3a2eaba3da59a26812d4` |
| new PDE at freeze checkpoint | `not_run` |
| numerical source changed | `false` |

## 7. Review V2 首次 PDE 前数值端口 Gate

冻结点表后发现，旧 Hybrid CLI 只允许 Task035c 的固定 p6/S/10°路径，不能诚实执行
V2 的 p5、P、动态方位角和几何。本轮先完成最小 opt-in 接线与 one-shot repair 的
connected-component 修复，没有运行 PDE。

| 检查 | 结果 |
|---|---|
| targeted Python tests | `82 passed`，`22.02 s` |
| Hybrid p5/p6 dynamic CLI round-trip | pass |
| raw Full3D exact source/input identity mutation tests | pass |
| two disjoint + transitive near-degenerate components | pass |
| bounded size/condition fail-closed | pass |
| full `||B-I||_inf` synthetic batch repair | pass |
| Ruff | pass |
| compileall | pass |
| `git diff --check` | pass |
| ordinary default | unchanged |
| new PDE | `not_run` |

该 Gate 只证明执行端口和算法局部合同正确；connected-component 修复仍需原 p6/45°
及其邻域 actual PDE 证明，不能因 unit test 提前写成数值闭环。

## 8. Review V2 首批同源 PDE 与停止判定

### 8.1 最终数值源码前的 focused Gate

V2-B05 static-recovery beta、V2-B06 scalar-CG energy 和 connected-component left-basis
修复在提交 `de60ce3695eefd4fa7c808856fdea0b708d395a1` 上完成；driver dry-run 串行化
提交后，正式 PDE 源码为：

```text
6d5e9781bcb1458ecac7a77af22fa2d420f0cd55
```

运行前回归：

| suite | 结果 |
|---|---:|
| Task036 / Hybrid / propagation targeted serial | `68 passed` |
| cross-section/static focused | `11 passed` |
| MPI8 test179 micro-fixture | 每个 rank `6 passed` |
| Ruff / compileall / diff-check | pass |

MPI8 micro-fixture 同时发现并修复了“rank 数多于 quad cell 时空 partition 仍为一维数组”
的问题；空分区现在保持 `(0,4)` cell shape，不改变非空分区数值。

### 8.2 五个 configuration pair

| point | Full3D | Hybrid M120 | zero swap | Hybrid peak GiB | 最终判定 |
|---|---|---|---|---:|---|
| A001-P p5 | pass | complete return 2 | pass | 7.212 | numerical Gate negative |
| A004-P p5 | pass | complete return 2 | pass | 7.450 | numerical Gate negative |
| A004-S p5 | pass | complete return 2 | pass | 7.464 | numerical Gate negative |
| A049-P p5 | pass | complete return 2 | pass | 7.131 | fixed-channel negative |
| D001-P p6 | pass | complete return 2 | pass | 11.222 | numerical Gate negative |

`return 2` 是正式 fail-closed 状态，不是 crash、timeout 或 memory termination。五个
Hybrid 均通过 true residual、algebraic interface E、exact traction 和完整
biorthogonality row norm，但固定衍射通道没有闭合。详细数字见
`robustness_scan_matrix.md` 和 `hybrid_validity_map.md`。

这五个结果足以识别重复的 trace-complement 架构根因，因此按照 Review V2 停止其余
221 个配置，并没有运行 M240/M480/M492。旧 A049-P M492 controlled negative 继续保留，
不重复 PDE。

### 8.3 并发时间口径

首批 Full3D 五路并发的 outer CPU lease 被 OpenMPI `core/slot` 内层映射覆盖，导致五组
rank 初期共同绑定 CPU0–7。Hybrid 启动后约 15 秒即发现并实时重绑。由此：

- 数值、residual、observable 和同步 process-tree memory 仍有效；
- Full3D wall time 不是正式 authority；
- Hybrid wall time只作参考，不用于宣称速度优势；
- driver 已改为 explicit `hwloc_base_cpu_list` +
  `cpu-list:ordered`；
- 独立 MPI8 probe 已验证 rank 0–7 分别绑定租约中的八个 CPU；
- 数值 kernel 未变，不因调度文档修复重跑 PDE。

### 8.4 full-suite 口径不变

V2 的正式 PDE、driver 和文档收口没有重跑此前 48:55 的 full repository suite。当前
仍诚实保留：

```text
803 passed, 41 skipped, 3 failed
post-full targeted closure = 59 passed
```

三个旧 failure 的非数值性质和最终定向闭合见第 3.2 节。最终收口只重跑本轮 changed
files 的 focused tests、MPI binding probe、Ruff、compileall、文档/JSON 与 diff-check。

### 8.5 最终收口回归

| 检查 | 结果 |
|---|---:|
| mode/QEP/propagation/reconstruction/static/driver/analyzer focused | `74 passed` |
| Task036 docs/B08/hardening/driver/analyzer 组合 | `50 passed, 1 failed` |
| 失败项 | checkout-local ignored Case098 目录；与第 3.4 节已记录的同一非源码污染 |
| 单独 documentation local-link / required-layer tests | `2 passed` |
| MPI8 static-condensation micro-fixture | 每个 rank `6 passed` |
| explicit MPI8 CPU lease probe | rank 0–7 分别绑定 CPU 8–15 |
| Ruff | pass |
| compileall | pass |
| `git diff --check` | pass |

本轮没有删除 Case098 历史目录来换取测试通过，也没有因此修改 documentation contract。

## 9. Review V3 strong trace-subspace 回归

Review V3 数值实现提交为：

```text
5b04a4398fe752083024487ca95eb00a09e646cc
```

实现提交完成：

| 检查 | 结果 |
|---|---:|
| affected serial fixture/gate tests | `40 passed` |
| broad related suite | `159 passed` |
| MPI2 strong-trace micro-fixture | 每个 rank `4 passed` |
| MPI8 strong-trace micro-fixture | 每个 rank `4 passed` |
| Ruff / compileall / diff-check | pass |

A004-S actual PDE 随后暴露齐次 residual partition 的报告分母缺陷。该缺陷只影响
telemetry，不改变矩阵、解、场或物理量；修复提交为：

```text
a5b86a319af3cfc88d5de5801f2e8131f89a9be4
```

最终 targeted 回归：

| 检查 | 结果 |
|---|---:|
| serial `test_199_task036_strong_trace_hybrid.py` | `6 passed` |
| MPI2 | 每个 rank `6 passed` |
| MPI8 | 每个 rank `6 passed` |
| Ruff | pass |
| compileall | pass |
| `git diff --check` | pass |

没有因纯 telemetry 修复重复运行 35 分钟的 broad suite，也没有重跑 A004-S PDE。原始
A004 artifact 仍绑定 `5b04a43...`；离线 residual 修正与新的 fixture 绑定
`a5b86a3...`。A004 最终仍因 energy `1.531666e-5 > 1e-5` 和固定通道 `77/96`
失败，不会因测试通过被写成 production pass。
