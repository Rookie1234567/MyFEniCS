# Task037-extra Review Report V1：G2 LOR-HX 最终审阅

## 0. 审阅身份与最终决定

| 项目 | 审阅结论 |
|---|---|
| 执行分支 | `codex/20260806-task37-iterative-extra-development` |
| raw 运行源码 | `30e179799b8eb6dee1be1bb976002550424bb40d` |
| 被审证据 HEAD | `175a743251c4ba439d562fade07644f0bc76cfca` |
| 被审 response | `docs/task37_extra_development/response_v5.md` |
| D3c 实现与测试 | `ACCEPTED` |
| raw 与紧凑证据闭环 | `ACCEPTED` |
| G2 数值判定 | `G2_FAIL` |
| G3 | `not_started_and_prohibited_by_G2_FAIL` |
| production promotion | 不批准 |
| merge to master | 不授权；任务书本身规定 `permanently_not_planned` |

本审阅没有发现需要返工的代码或证据问题。这里的“审阅通过”只表示实现、测试、原始记录、
派生计算和负结果分类可信；它不表示 LOR-HX 达到了预条件器性能目标。任务书规定 minimum
contraction 失败即为 `G2_FAIL`，本轮正式数据已经触发该 hard stop。

## 1. 代码审阅结论

### 1.1 架构与范围

本轮 contraction 核心位于 `src/solvers/`，watchdog 只负责参数传播、生命周期和 raw
记录，checker 从 raw 独立重算结论。没有把新的数值算法堆进 benchmark runner，也没有
新增第二套 solver 实现。

正式比较的四种方法为 current trace ILU、B4 GMRES(4)、LOR-HX 1V 和 LOR-HX 2V。
三个 source 的 correction 后残差均调用 exact shifted full-space slab Schur action；记录明确
给出 `proxy_self_score=false` 与 `global_matrix_materialized=false`。1V/2V 没有被替换成
更多 local Krylov steps，也没有通过 sweep 调参。

### 1.2 防御性代码检查

没有发现以下不应出现的扩张：

- 自动重试、静默 fallback 或失败后更换算法；
- 为单一正式 case 建立通用配置框架或 registry；
- 大量类型兼容层、重复 schema 适配或无需求的异常吞噬；
- 根据正式结果自动调 shift、cycle 数或 smoother 参数；
- checker 重新实现 solver，或只相信 raw 中已有的 `status`。

新增的边界检查集中在 MPI/类型身份、有限值、重复 action 和 raw 合同上，直接服务于数值证据
真实性，范围与风险相称，不构成过度防御性开发。

### 1.3 独立测试核对

在正式运行源码 `30e179799b8eb6dee1be1bb976002550424bb40d` 上，审阅方独立执行：

| 检查 | 结果 |
|---|---|
| `test_219_task037_external_solver_runtime.py` | 纳入 targeted suite，通过 |
| `test_223_task037_f3_watchdog_screen.py` | 纳入 targeted suite，通过 |
| `test_270_task037_extra_lor_hx_contraction.py` | 纳入 targeted suite，通过 |
| targeted suite 合计 | `49 passed in 5.01s` |
| 相关 `compileall` | 通过 |
| `git diff --check` | 通过 |
| Ruff | 当前资格化环境不可用；未宣称通过 |

测试中特别覆盖了一个必要边界：raw measurement 可以完整、自洽并通过 qualification，
同时 performance minimum 可以为 false。该边界防止 watchdog 把“证据可用”误报为“算法通过”。

## 2. 正式运行与证据审阅

### 2.1 运行身份

| 字段 | 正式值 |
|---|---|
| source SHA | `30e179799b8eb6dee1be1bb976002550424bb40d` |
| case | p6/h10/S、MPI1、primary slab14、screen20 |
| partition | M3a overlap0.125 |
| materialization | M2c never-materialized |
| watchdog status | `task037_extra_g2_slab14_lor_hx_contraction_measurement_qualified` |
| watchdog return / failures | `0 / []` |
| solver stop | 20 steps，`DIVERGED_MAX_IT(-3)` |
| true / reported residual | `0.04474243612765 / 0.04474243612765121` |
| official field / official RTA | `false / false` |

固定 20 步的 `DIVERGED_MAX_IT(-3)` 是 screen 边界，不是一次收敛求解。watchdog status
只证明 raw 字段、重复 action、hash 和派生关系可审计。response 和 outcome 均正确保留了这条
边界，没有生成 official R/T/A。

### 2.2 contraction Gate

`rho` 表示应用局部 correction 后，exact shifted full-space Schur 残差相对输入残差的
范数比。小于 1 才表示该方向被缩小；本轮 LOR-HX 在三个 source 上均出现数量级很大的放大。

| source | current trace ILU | B4 GMRES(4) | LOR-HX 1V | LOR-HX 2V | best LOR-HX |
|---|---:|---:|---:|---:|---:|
| real M3a iter0 | 2.422027189163481 | 0.9440411915945912 | 5611759.4667701805 | 4885392465721929.0 | 5611759.4667701805 |
| real M3a iter20 | 1.2604899530937386 | 0.755818683406265 | 3465823.613309288 | 1651097278181490.5 | 3465823.613309288 |
| manufactured mixed/high | 4.455510654442446 | 0.8584226047142137 | 61738549.74675689 | 1.4084260534619966e16 | 61738549.74675689 |

| Gate | 正式结果 |
|---|---|
| minimum：iter20、mixed/high 相对 B4 | `false / false` |
| strong：iter0、iter20 相对 trace ILU | `false / false` |
| apply-time：iter0 / iter20 / mixed | `true / false / true`，overall `false` |
| deterministic / finite / apply count | 通过 |

本轮没有单独测量 B4 i200/long-tail raw；iter0 和 iter20 是 M3a screen 的真实 residual。
这项缺失已经在记录和 response 中显式标为 `b4_long_tail_raw_measured=false`，不能把 M3a
residual 改称 B4 long-tail。

但任务书的 minimum 要求是 B4 long-tail 与 mixed/high 两项都通过。已测的 required
mixed/high source 上，best LOR-HX 为 `61738549.74675689`，而阈值只有
`(2/3) * 0.8584226047142137`。该必要条件单独就已明确失败，因此 conjunction 不可能通过；
无需、也不得为了改变 hard-stop 分类补跑 B4 long-tail。

### 2.3 存储与资源 Gate

| 指标 | 正式值 |
|---|---:|
| LOR transfer payload | `18735740 B` |
| D2c hierarchy payload | `3109473612 B` |
| total retained hierarchy payload | `3128209352 B` |
| one-slab trace-ILU baseline | `122023588 B` |
| 0.60 memory threshold | `73214152.8 B` |
| HX / trace baseline | `25.63610366874313` |
| retained-payload memory Gate | `FAIL` |
| transfer / HX build | `51.72637021099217 / 607.4379243750591 s` |
| whole-run process-tree authority | `8333.12890625 MB = 8.137821197509766 GiB` |
| worker RSS / PSS / USS | `8319.29296875 / 8267.7822265625 / 8223.19140625 MB` |
| swap | `0` |

`7924.58984375 MB` 的 HX-ready interval 还覆盖了后续既有 trace-factor setup，文档正确
没有把它称为纯 HX build peak。`13279.546875 MB` 是 historical cgroup peak，也没有被
冒充成本轮 authority。

## 3. Raw 与紧凑记录一致性

审阅方没有只读取 compact record 的 `status`。对 record 中三类 source、四种 method 的
source norm/hash、rho、post norm、first/repeat apply time、correction hash 和重复 hash
逐项回查 raw，结果一致。资源字段、Gate 布尔值和以下 raw SHA256 也已重新计算并匹配：

| raw 文件 | SHA256 |
|---|---|
| `watchdog_summary.json` | `b52125f40f946da4bbf792174224beb4a1526c1d20eab04e3b3bc748da95b2f4` |
| `run_summary.json` | `a6e53c655f896ddb26de3ef86fd39e147da3b74bfda558fd4998870e9ec32f65` |
| `task037_f3_core_audit.json` | `a87537cc899d3ae6df8068a8f797fbd5da4061e32e7400c32d20f33e3595f9e4` |
| `progress_3d.jsonl` | `db8c0f2e8de7f6924dc953b65026f74abfc304c1f0eda8d43fb0c49f2664227d` |
| `task037_f3_residual_history.jsonl` | `75f0bc3ebec3648b60fdfc55daa9afd036b81cf6d5fe0ef1f7051a83e0f24940` |
| `memory_timeline.csv` | `ca7ff04921b5be4e8b1cb31f356f7baff9eda1203479f0ca666fe9b193759dad` |
| `parent_launch_descriptor.json` | `19854ce17d27bfe2fde1e6dfb4de280249fc4f49ddad4605c29542094c756b57` |
| `worker_stdout.txt` / `solver_log.txt` | `a6a3509af15b95064729acfd1ba0c1904b44fb14826d4a4b6c9e6663b50a5dde` |
| `NO_OFFICIAL_FIELD_OUTPUT.txt` | `e11465d92e416af3e4321c581b7291b7d4df5c932b425541f9b0114e259d3f38` |

证据提交 `175a743251c4ba439d562fade07644f0bc76cfca` 的父提交正是正式运行源码
`30e179799b8eb6dee1be1bb976002550424bb40d`。该提交恰好包含 7 个约定的 case、record、
outcome 和 response 文件，没有代码或 ignored raw artifact；本地与 upstream 为 0/0，
提交后工作树干净。

## 4. 最终裁决与停止边界

最终裁决如下：

1. D3c contraction 实现、外层传播、checker、targeted tests 和证据固化通过审阅。
2. G2.4 只保留 `pass_transfer_build_and_algebra_only`。
3. G2.5 只保留 `pass_build_only`，存储信号失败。
4. G2.6 只保留 `measurement_qualified`，minimum、strong、apply-time overall 均失败。
5. G2 overall 必须是 `G2_FAIL`，不是 `G2_PARTIAL`。
6. `G2_FAIL` 没有 rooted local repair 额度；不得 sweep，不得启动 G3。
7. 不批准 production promotion，不授权合并到 `master`。

Task037-extra 在任务书规定的科学 hard stop 处真实收口。负结果应保留在当前执行分支，
不再要求 Codex 为获得“正结果”增加防御代码、参数扫描或新的重型运行。
