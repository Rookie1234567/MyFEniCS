# Task40 Review V7 执行回应：W0 补充运行收口（待审）

**本次补充执行已按时间与实现失败边界收口，等待审阅；目标未实现。**实际 W0 进入了 p6-only 的 fresh setup，并生成八门 `PASS_COMPONENT_ONLY` same-live 收据；随后 worker 在 tuple/list mode identity guard 处失败，尚未进入完整 p6 component worker 与 raw export。修复版 public validator 在 native 主机上对同一保存 JSON 的 list、tuple 两种身份表示均通过；主线只核验了捕获的 stdout 文件及 SHA。它是离线 JSON/身份检查，不是本地主机重放、worker 重试或 PDE 通过。W1/W2 不在本次收口中自动继续，原尺寸目标仍 **NO-GO**。

用通俗的话说，这个小 W0 检查要确认体单元与端口模式之间的两组耦合项（C/D）及端口作用（H）是否彼此相容。保存的收据是这次实际组件计算留下的数值和身份记录；离线重验只重读该记录。完整验收还需要完整单元恢复和原始数组的独立核验，本次 worker 没有到达这些步骤。

## 实际 W0 范围

| 项目 | 事实 |
|---|---|
| run / source | `w0_20261004T0638Z_4b89d7f`；运行 source `4b89d7f922bda3859048d20714557ac0cf07ffc6`；身份检查修复 commit `5f74e15fae6e01e4361325db162806a7319ba3f4` |
| 输入 | `input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat`；SHA256 `6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e` |
| 实际离散 | 80 cells（4×4×5）、degree set `{6}`、532 ordered modes、φ=5°；这是 p6-only 组件 probe |
| 未执行范围 | 输入文件名/配置中的 `q4` 标签不代表四个 q 已执行；本次没有 p4 空间、四 q 分支、q 因子或完整 p6 component worker |
| Native execution host independent ABI | PETSc 3.25.6 `complex128/int32`；DOLFINx/Basix 0.10.0，MPC 0.10.5，MPICH 5.0.1；MPI 1、数学线程 1 |
| FE 事件 | fresh p6 setup 于 `2026-10-04T06:38:30.344517Z` 开始，`06:38:31.146454Z` 完成；same-live 组件收据随后生成 |

本地主线文档/index pure tests 使用仓库 `scripts/activate_myfenics_wsl.sh` 的 `.venv` 与旧 PETSc 3.19 / Open MPI 4.1.6 栈；它与 native W0 的 PETSc 3.25.6 / MPICH 5.0.1 环境分开，未用于任何 native 数值证明。

已核对 tracked runner `benchmarks/run_fresh_c1_p6_component.py`（SHA256 `7290d392a9ac4c00b1bc1a3f070da947b62414865b29faac8f07814315a3ef36`）：它以 `(6,)` 构造层级，并要求 `spaces == {6}`、`floquets == {6}`；准入记录将 global p6 matrix 标为未创建。实际失败发生在调用 full p6 component worker 前。因此这里只记录 p6 setup/组件收据，不声称构造 p4、完整四 q 或任何全局 q factor。

### 源码链与独立预算合同

reference dot source `077ec9c8386c976da232093779279fb9d1a93033` 是审阅时观察到的参考提交；本次 native W0 没有执行该 source。实际主线代码链为 `6bbc4fb57f7132dd6367ba3173f563fad7d9b025`（native supervised p6 W0 path）→ `74bfcddf52cc97b518e71154dc47d59654fd4a8e`（activation 引号修复）→ `17c0f2b921fd9ed7244c53fad87c5fcb6bc620ad`（通过 repository module 启动 worker/checker）→ `4b89d7f922bda3859048d20714557ac0cf07ffc6`（将资源回调绑定到真实 subreaper PID）→ `5f74e15fae6e01e4361325db162806a7319ba3f4`（修复 JSON-normalized mode identity 校验）。对应的 74/17/4b 运行尝试耗时分别单独列在下表；6bbc shell/activation cache-reference blocker 仍是 unknown。

W0 raw-member cap 独立由 [`fresh_c1_p6_w0_budget.json`](../../benchmarks/fresh_c1_p6_w0_budget.json) 绑定，SHA256 `533930676db07f7a145e0e6b71eacd198288bea92717bf7a8ba91fe9d16a9b81`：磁盘 raw member payload 上限 8 GiB（`8,589,934,592 B`），本 case 的 derived worst-case 上界 `6,900,030,936 B`，余量 `1,689,903,656 B`；另有独立的 process-tree memory cap `3,221,225,472 B`（3 GiB）。这个 manifest 标记为 derived admission，不是实际写出量、RSS 或容量测量。旧 512 MiB cap 的 checker 测试仍保留并拒绝不匹配的 cap 值；本次没有扩大 RAM 限额或改写旧配置。表中的 quadrature 数据是面求积身份元数据：4 个 primary facet records 对应两侧各两个分量（节点相同），8 个 independent identity comparisons；它们不是四种 q 运算。

## 保存的组件收据

native 原路径中的 `same_live_literal532.json` 为 `PASS_COMPONENT_ONLY`，532 modes、8 个命名 gate，报告大小 `2,410,188 B`、SHA256 `858094d19ec9f7ea05eec85c94ecf003fa37ddbbe12cc7f1e62749de2fc6c037`。以下指标来自保存 JSON 的 native 纯校验输出；不是全域 Maxwell residual 或官方物理量。

| 组件检查 | 重算最大 defect/ratio | 限值 | 结果 |
|---|---:|---:|---|
| C/D/H 与 raw action 等价 | `3.5931818134322393e-14` | `1e-10` | PASS |
| 532 模式 full-DOF rank-one 界 | `2.4672054282185927e-13` | `1e-10` | PASS |
| 五状态 action/recovery/output | `3.099637928778201e-14` | `1e-10` | PASS |
| 物理 FE RHS literal defect | `1.7324712509441664e-14` | `1e-10` | PASS |
| 非零端口 mode equation defect | `1.8654147652106162e-14` | `1e-10` | PASS |
| transform gate ratio | `3.4637921787560976e-6` | `1` | PASS |

native public validator recheck 使用 source commit `5f74e15fae6e01e4361325db162806a7319ba3f4`、validator SHA256 `aec3ae90634ce8ef0f18d3490097e331f863dc56cc4d978c0e2244a22af4673d`、qualification SHA256 `fb572d7f1ab6f0e5bc2b94cc14bbb3d9a3bd9d1c6b637aa59a7926121c5ddfdb`。其真实 stdout 由主线捕获在 `/tmp/task40_w0_fix5f74_list_tuple_stdout.json`：`1,951 B`，SHA256 `b563cbce296c0740b707aa48394bc3fd15cb8cdbc5a89dbb6f473db5e01a8c89`。list/tuple 分别 `PASS`，内部耗时 `1.411307457 / 1.404511847 s`，outer wall 均 `1.58 s`，RSS 分别 `46,796 / 47,108 KiB`；输出明确 `FE_or_JIT=NOT_RUN`。校验器在 native 主机执行，主线只验证捕获 stdout 的长度/hash。

## Worker 失败、资源与原始数据边界

worker 在 `2026-10-04T06:41:46.252994Z` exit 1。错误为 `ValueError: same-live receipt ordered mode identity is incomplete or repeated`：live carrier 用 tuple keys，保存 JSON 用等价的 list keys；worker 读取序列化前身份而拒绝等价表示。该失败发生在 full p6 component worker 调用前，属实现身份校验错误，不是截止、资源或数值失败。

| 项目 | 实测 / 状态 | 口径 |
|---|---:|---|
| 当前 worker wall / limit | `196.762108860 / 199.490712881 s` | 退出时距离 worker cutoff 还有 `2.746385813 s`；全部时间 gate false |
| Process-tree RSS peak | `1,408,434,176 B` | 同时进程树约每 `0.25 s` 采样的峰值 |
| PSS | `null` | PSS disabled，未采样 |
| Task swap / host swap | `0 B` / 既有 `21,600 KiB` | 前者是 Task 进程树口径；后者是 native 主机已有用量，不能称整机 zero-swap qualified |
| Resource gate | 未触发 | 不据此推导主机总容量 |
| 8 GiB raw-member 导出预算 | 公式上界 `6,900,030,936 B` | 导出载荷预算，不是 RAM 或 RSS |
| Scientific raw / PDE | raw export `NOT_REACHED`；p6 tensor/FE field 数组未生成；independent tensor/CSR checker `NOT_RUN`；full A6 residual 与 official R/T/A `NOT_REACHED/NOT_RUN` | 原始数组不存在，因为 worker 在导出前失败；不是只有跨窗传输受限 |

支持收据与科学 raw 必须分开看。native 侧 copy/fsync/readback 的 36 份支持文件共 `5,757,491 B`，每份 SHA256 均列于 member manifest；其中有 run log、ABI/resource/test/timeline 收据及 2.41 MB same-live JSON，manifest 明确 `raw_member_count=0`。原 35-member 包 `47,078 B`、SHA256 `d5f934e09e034b1349c2860948e1dc91ec24c9670ba6dd5939a01bc8e6379f62` 也是运行日志/ABI/资源/测试收据包，不是 tensor/场包，主线没有读取其原始包字节。主线本地 `1c65fa…` 小包为 `6,972 B`、SHA256 `1c65fa402ea537cf732871895a7aa29cf5d4f0b56cba770eaa9b1b2665a8dd4b`，只有三份派生 JSON。64 个 native JIT 文件共 `1,220,807,231 B`，留在原路径，未复制。随后支持收据跨窗传输被 auto-review 拒绝，没有改用其他传输渠道；这与科学 raw 未生成是两个独立事实。

## 历史尝试与时间账

| 预 FE 尝试 | 结果 | worker wall | RSS peak | 额外口径 |
|---|---|---:|---:|---|
| `w0_20261004T0629Z_74bfcddf`，source `74bfcdd…` | 缺少 `src`，exit 1 | `2.026239892 s` | `287,481,856 B` | task swap 0；后代清除 |
| `w0_20261004T0635Z_17c0f2b9`，source `17c0f2b…` | allocation gate 缺 live subreaper identity，exit 1 | `2.090595266 s` | `290,197,504 B` | task swap 0；后代清除 |
| `preflight_6bbc` shell/activation cache-reference blocker | worker 未启动 | `null` | `null` | 耗时与收费 unknown，不记 0 |
| 当前 `w0_20261004T0638Z_4b89d7f` | tuple/list guard 失败，exit 1 | `196.762108860 s` | `1,408,434,176 B` | task swap 0；PSS disabled/null |

三次相互独立 worker 的已测 elapsed 小计为 `200.87894401792437 s`；它不含 6bbc shell blocker，也不等于完整准备时长或 W0 总费用。准备起点和 W0 总收费保持 `null/unknown`。四小时 policy cutoff 是 `2026-10-04T06:41:49Z`，属于派生政策窗口，不是实测耗时；当前 worker 在 cutoff 前 `2.746385813 s` 退出。V7 FE 启动 deadline 是另一个时间 `2026-10-04T10:07:14Z`，本次 FE 在该启动 deadline 前开始。现在 policy cutoff 已过，本次不再启动新 FE，也不扩大预算。V6 historical settled debit `5,428.582333962078 s` 原样保留。

## 保留的旧材料与后续边界

5f74 commit 中旧 pre-FE ledger 已逐字节封存：[prefe ledger snapshot](outcomes/records/review_v7_prefe_snapshot_5f74e15.json)，Git blob `7eb0caf575732e9f68e18b48b7fee4379ee074a2`，`10,566 B`，SHA256 `e89103312f52f5717a3219d7ca01f5ea0c1ff41b178321ba43a62c259eae2f20`。旧的完整 response 同样保留：[prefe response snapshot](response_v7_prefe_snapshot_5f74e15.md)，Git blob `883bbf822cb97e9f72714d923802984be1b800d9`，`12,983 B`，SHA256 `922f6efc5e75e63e480025eef60294c70d999d20b0aa96958beaa256244a8bd5`。旧 response 中完整 target/AUTO/W1/H 稠密成本账及历史失败材料都在快照内，未删除或简写覆盖。ledger 快照中的 `5be1210…` PyVista import blocker、当时的 077 source authorization、held/dry-not-run/no-PID 等是早期检查点，不是当前 W0 状态。

W1/W2 本次不自动继续；W1 的原尺寸 AUTO 成本入口/准入条件尚未闭合，W2 还缺 C1c raw 与完整 p6 链。原尺寸 50×25×140 nm 的精度、完整 AUTO、全部 q 因子、完整 p6 恢复和 172,800 s 端到端成本仍未证明，维持 **NO-GO**。32,060-mode manifest 与 272×4×14 候选只沿用历史计数，不重生成，不称已资格化网格。

本轮只整理既有运行事实与证据索引。实际 W0 执行源为 `4b89d7f922bda3859048d20714557ac0cf07ffc6`；后续 `5f74e15fae6e01e4361325db162806a7319ba3f4` 只修复 JSON-normalized mode identity 校验，不改变数值或 ABI gate。主控统一审核后提交、推送，并按 Git 回执报告最终交付 HEAD。
