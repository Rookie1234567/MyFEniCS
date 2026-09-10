# Task39extra V10：physical macro inverse M4 收口

本文件是 Review V10 的中心结果。V10 的 M0 ABI/输入注册和 M1 macro 局部构建已经留下可审阅证据，但 M1 在冻结的局部常驻预审策略处停止；因此本轮没有合法的 M1 controls 完成，也没有进入 M2、M3 或 official physical output。机器可读的紧凑记录见 [V10 compact](records/physical_macro_inverse_v10.json)。

## 1. 身份、范围和最终状态

| 项目 | 结果 | 数据身份 / 边界 |
|---|---|---|
| 代码身份 | source `b0df7457c0c4b33c66abda16862926da3426bb7d`，branch `task39extra`；formal launch 时工作树 clean，交付阶段有未提交 M4 文档改动 | measured source state；本地提交尚未能用 HTTPS 凭据推送 |
| 物理输入 | 13.5 nm、p6/h10、Full3D、MPI1、80 DtN modes、`complex128`；80 modes 是冻结输入合同，不是完整新 macro identity 的证明；input SHA `f6a3bc446fa7ce34a446e6a52f07be4a3841df649272fae6164f1ecfaca3dd66` | hash-bound identity；physical model SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| M1 candidate | 42 个 macro blocks，local rows cap 2600，local resident policy cap 2 GiB，temporary reserve 1 GiB | frozen contract；不因本次停止而放宽 |
| 第一次 M1 | source `99428016a73fdbb29f6531974ed1ee4756d96bbc`；native DtN 已构建，在代表块选择处抛出 `ValueError`；I4/B4=`0/0` | `REPRESENTATIVE_SELECTOR_FAILURE_BEFORE_LOCAL_FACTORIZATION`；raw negative evidence 保留 |
| 第二次 M1 | source `b0df7457c0c4b33c66abda16862926da3426bb7d`；完成局部类、代表块登记和 block 0–7 的矩阵/数值分解阶段，在 block 7 后触发 resident policy | measured partial build + controlled resource-policy stop |
| M1 总状态 | `PARTIAL_WITH_CONTROLLED_NEGATIVES`；子分类 `LOCAL_INVERSE_UNQUALIFIED`、`RESOURCE_BLOCKED` | 不是 solver PASS、不是 physics PASS、不是系统 OOM |
| M2/M3 | `not_run` | M1 前置 Gate 未通过；不补跑、不外推 |

第一次尝试的选择错误已经在当前代码中以活动 DtN 行和实际材料标签修正；第二次尝试没有继续更改数值路线。两次运行分别保留于 `benchmarks/artifacts/task39extra/v10_m1/99428016a73fdbb29f6531974ed1ee4756d96bbc/m1` 和 `benchmarks/artifacts/task39extra/v10_m1/b0df7457c0c4b33c66abda16862926da3426bb7d/m1`。

## 2. 四条证据轴

| 证据轴 | 实际结果 | 可推出的判断 | 不能推出的判断 |
|---|---|---|---|
| 内部质量轴 | block 0–7 已进入矩阵/数值阶段；保存的 block 0–6 有 14 次 MUMPS 回代，最大相对残差 `2.0002787934351233e-15`；两个代表块共 6 次 native witness，最大 `8.243915633632588e-16`。但 p4 true error/residual 未测，`build_w_transfer`、cached action、cached/native A4 bridge 未完成 | 保存子集的局部稀疏矩阵、分解和回代数值自洽 | block 7 的回代残差没有落盘；局部 witness 不等于完整 macro inverse、A4 operator 或 p4 true error/场误差通过 |
| 框架耦合轴 | `verify_recursive_map`、6 个 g 校准、BAL_H/ONE_C 框架控制均未运行 | 框架比较状态为 `FRAMEWORK_COMPARISON_LIMITED` | 不能比较第二次粗反馈、不能判断 BAL_H 或 ONE_C 优劣 |
| restart 轴 | M2 未启动，restart32/restart64 均未运行 | `RESTART_DIAGNOSIS_LIMITED` | 不能把旧 ENTITY16/g1 数据解释为本轮 restart 证据 |
| 总成本轴 | 两次 M1 终态收费分别为 `245.63548373799006 s` 和 `134.64191316702528 s`；preparation envelope `1281.5 s` 的取样截止为 `2026-09-10T12:14:07.163Z`；账本已记录 `1661.7773969050152 s` | 可以审计 preparation、两次实际终态和已记录账本的组成 | 12:14 之后的 repair、测试和 M4 文档成本未完整纳入，完整 total cost=`UNKNOWN`；nominal remaining 不是本轮最终可用预算 |

特别地，`m1_summary.maps` 中的 p4/p6 map SHA 是加载的参考 map 身份；本次 `macro_stack_identity=null`。它们不能被写成“完整新 macro stack 的 native/cached identity 对照已经通过”。

## 3. M1 局部资源 Gate：保守分配预审，不是实测常驻

局部缓存构建完成时记录的去重 retained cache 为 `45,710,148 B`。在 block 7 numeric factor 之前，`_resident_bytes()` 已计入当前 block 7 的矩阵以及全部 blocks 的 indices/support，记录为 `1,982,365,908 B`。block 7 的 MUMPS allocated padded factor 为 `261,000,000 B`，所以按既有策略重算：

`1,982,365,908 + 261,000,000 = 2,243,365,908 B`。

这超过 `2,147,483,648 B` 的 2 GiB policy cap `95,882,260 B`。这里不能再次加 block 7 matrix 或 indices/support；它们已经包含在 `resident_before_factor` 中。

| 量 | 数值 | 口径 |
|---|---:|---|
| blocks 0–7 matrix raw storage 合计 | `107,655,760 B` | derived from matrix CSR allocation |
| blocks 0–7 matrix policy budget 合计 | `349,529,248 B` | derived policy budget，非 RSS |
| blocks 0–7 estimated factor padded 合计 | `234,000,000 B` | pre-numeric estimate，非实测常驻 |
| blocks 0–7 allocated padded 合计 | `2,090,000,000 B` | 根据 MUMPS factorization allocation audit 的保守累计量 |
| blocks 0–7 effectively used padded 合计 | `212,000,000 B` | INFOG21/22 语义；不能替代 allocated policy |
| block 7 policy 重算值 | `2,243,365,908 B` | derived conservative cumulative policy |
| policy cap / excess | `2,147,483,648 / 95,882,260 B` | hard pre-audit stop |
| 同期 process-tree RSS 峰 | `1,107,648,512 B` | measured simultaneous RSS；不是 policy 值 |
| 同期 job swap 峰 | `0 B` | measured process-tree VmSwap；descendants 已清场 |

MUMPS 的 INFOG18/19 表示分解期间 allocated internal data，INFOG21/22 表示分解期间 effectively used data；它们都不是分解后 factor-only 常驻查询。因此本次准确表述是“现实现以 allocated 量构造的保守累计预审超过 2 GiB”，而不是“实际 RAM 不够”或“实测常驻超过 2 GiB”。没有理由改用 used 值、放宽 cap、减少 block、改变 MPI、改 MUMPS 参数或切换 ILU；这些都会改变已冻结的 M1 候选合同。

MUMPS 字段含义按其 [MUMPS user guide](https://mumps-solver.org/doc/userguide_5.9.1.pdf#page=112) 记录；本节的 factor-entry 计数仍只是 raw backend observable，不是分解后常驻测量。

### M1 已观测的 partial stage 量

下表从第二次尝试的 `stages.jsonl` 中现有 `p1_symbolic_complete` / `p1_numeric_complete` facts 汇总，只描述 block 0–7 已观测阶段，不把它们扩写成完整 M1 成本。

| partial observable | blocks 0–7 合计 | 口径 / 未完成项 |
|---|---:|---|
| symbolic stage | `0.13301346899970667 s` | per-block recorded stage sum |
| numeric stage | `0.8125463649976155 s` | block 7 numeric fact 已写入 stages，但 block 7 success record 未落盘 |
| matrix NNZ | `5,379,856` | raw CSR `nnz` sum |
| factor entries | `5,796,240` | raw `INFOG(3)=INFOG(9)` sum；不是 factor-only residency |
| local backsolve elapsed / warm-cache load | `UNKNOWN` / `UNKNOWN` | 没有独立时钟字段 |
| global coarse / Krylov / postprocess | `not_run` | 未进入 M2/M3 或 official output |

## 4. 成本与账本

| 费用项 | 实际值 | 口径 |
|---|---:|---|
| 第一次 M1 尝试 | `245.63548373799006 s` | 保守 parent/workflow charge；工程失败，measurement 未提交 |
| 第二次 M1 尝试 | `134.64191316702528 s` | 保守 realtime charge；policy stop，measurement 未提交 |
| 准备 envelope | `1281.5 s`，截止 `2026-09-10T12:14:07.163Z` | conservative preparation envelope；不是完整准备实测，不冒作 PDE 完成时间 |
| V10 ledger 已记录 | `1661.7773969050152 s` | preparation `1281.5 s`（截至上述时间）+ 两次 M1 终态 `380.27739690501534 s`；不包含 12:14 之后全部 repair、测试和 M4 文档成本 |
| nominal ledger 剩余 | `3738.222603094985 s` | 见 `benchmarks/artifacts/task39extra/v10_m1/v10_m1_budget.json`；只是已记录账本的名义余量，不是最终可用预算 |
| 完整 total cost | `UNKNOWN` | 后续成本没有完整、独立、可审计地并入该快照 |

资源 watchdog 的 monotonic interval 为 `122.92740438799956 s`，UTC conservative charge 为 `134.64191316702528 s`；两者差异已保留在 raw watchdog record，不能静默改成单一“实测 wall”。

## 5. 未运行项与正式物理边界

以下项目均为 `not_run`，不是通过、不是失败的物理量，也没有 official output：

- cached/native A4 bridge、recursive map verification、6 个 g calibration；
- BAL_H 与 ONE_C 的三组真实难误差控制；
- restart32 与 restart64 对照；
- original outer、conditional notch、recovery；
- E/H、near-field、`R00_s`、`R00_p`、`R00_total`、`Rtotal`、`Ttotal`、`A`、`A_volume` 和重要衍射级。

旧 ENTITY16/g1 数据只作为历史复用基准，属于不同候选/不同阶段；本轮没有把它们当作 V10 的 restart、BAL/ONE 或完整物理证据。

## 6. 测试、证据和停止决定

| 检查 | 结果 | 边界 |
|---|---|---|
| macro-focused suite | `9 passed in 0.52 s` | 局部实现/fixture 合同；不等于 M1 controls 通过 |
| task-focused regression | `55 passed in 1.81 s` | test361/test379/test410；不等于 PDE 通过 |
| Ruff / py_compile | passed | 静态检查；不等于数值资格 |
| 可审阅测试日志 | `v10_m4_test_run.log`，SHA `f484c96d8231de6b56052f162457010d8a2bba8d1af6b3992dfc8d950090cc97` | 手工编译的执行摘录，不是 raw stdout；绑定 source `b0df7457c0c4b33c66abda16862926da3426bb7d`；只含轻量 task-focused/static 检查 |
| full repository pytest | `not_run` | 本轮没有为文档收口重复全库测试 |
| CI | `not_run` | 没有 GitHub Actions 通过声明 |

### 当前决策表

| 决策项 | 当前结论 | 影响 |
|---|---|---|
| 唯一主要缺口 | 完整的新局部逆尚未跨过 allocation 预审；M1 在 block 7 policy stop，未形成完整 macro stack | p4 质量、框架耦合和 restart 结果都不能归因到一个已资格化的新局部逆 |
| 仅提出的一项后续设计 | 如需重开，先由新 review 审核可核验的分解后常驻记账与 factor 生命周期隔离方案，重新检查 allocation 预审模型 | 只是 review 候选；本轮不改参数、不改 cap/blocks/MPI/MUMPS、不重跑 |
| 负结果边界 | 当前 conservative allocation negative 不能推出局部物理逆无效，也不能推出 actual RAM 不足 | 实测 RSS 与 policy envelope 继续分开报告；ordinary default 不变 |

本轮 M4 决定是停止 V10 这个 macro candidate，并把局部正证据与资源负证据一起交给审阅。任何新的 local-inverse 设计都需要新的 review、source/input/ABI identity 和预算；不能在本轮追加另一个 shift、PML、粗空间、restart 扫描或 workstation heavy case。

证据入口：

- [V10 compact](records/physical_macro_inverse_v10.json)
- [M1 budget ledger](../../../benchmarks/artifacts/task39extra/v10_m1/v10_m1_budget.json)
- [第二次 run summary](../../../benchmarks/artifacts/task39extra/v10_m1/b0df7457c0c4b33c66abda16862926da3426bb7d/m1/run_summary.json)
- [第二次 watchdog summary](../../../benchmarks/artifacts/task39extra/v10_m1/b0df7457c0c4b33c66abda16862926da3426bb7d/m1/watchdog/summary.json)
- [第二次 worker log](../../../benchmarks/artifacts/task39extra/v10_m1/b0df7457c0c4b33c66abda16862926da3426bb7d/m1/watchdog/worker.log)
