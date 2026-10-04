# Task40extra Review V8执行回应（W0组件检查通过；W1固定窗口内持续推进）

**当前结论：W0组件和独立保存数据检查通过；PDE及官方R/T/A未产生。W1固定7200 s窗口已冻结（T0 2026-10-04T15:24:35.195396Z；deadline 2026-10-04T17:24:35.195396Z），接线、定向测试、源码提交准备/主控源码审查和唯一数值探针均在同一窗口计时，不刷新或排除准备。按既有授权连续推进，无需新的范围批准；数值探针使用主控审查提交的clean source。W2、dot仍HELD，原尺寸仍NO-GO。

## Review V8 后续 W0：独立组件核验与原始数据持久性闭合

W0 的这次 checker-only 复核只读取 attempt4 已生成的 worker report 与 1,602 个 raw 成员；没有重新运行 worker、生成网格或解 PDE。独立 checker 对 80 个单元、29 个唯一局部修正类和 955 个重算指标完成检查，复核了 3,287 个保存成员角色。制造一致状态的原始 native 方程相对残差为 `1.077949573325129e-15`，门限 `1e-10`；最差恢复相对误差为 `1.4966004617481827e-12`，门限 `1e-11`。这些是组件/制造态闭合指标，不是正式 Maxwell 求解残差。

| 核验阶段 | 实测结果 | 解释与边界 |
|---|---|---|
| attempt4 component worker | 80 cells、p6、532 modes；监督耗时 `797.628623222 s`；同时进程树 RSS 峰 `2,204,782,592 B`；进程树 swap 峰 `0 B` | worker 组件控制通过；没有完成生产 Maxwell PDE、官方后处理或 R/T/A |
| 独立 checker（成功重试） | 955 metrics、80 cells、29 classes、1,602 members / 3,287 roles；`18.994373507 s`；RSS 峰 `478,863,360 B`；tree swap 峰 `0 B` | 从保存数组重算组件方程与恢复闭合；checker `independent_component_pass=true` |
| native 方程 / recovery | `1.077949573325129e-15 <= 1e-10`；最差恢复 `1.4966004617481827e-12 <= 1e-11` | 制造态与局部恢复检查通过；不构成 full A6、场精度或官方输出门 |
| raw durability / array hash | `1,602 / 604,158,016 B`；1,602/1,602 fsync 后 reopened SHA、1,602/1,602 array SHA 均通过；未复制 raw | manifest SHA `000c9bb5cbfa531077d0535dccc6cbf0ca8f8984f444f2e22d97b057d9d7e1e4`；字节绑定 SHA `4046536acb6afbae8a642702cf47d23296998f779781187d30d54c96b4742e79`；`durable_archive_verified=false` 保持原值 |
| 文件描述符处理 | 首次 checker-only 在 carrier port 210 因 `OSError: [Errno 24] Too many open files` 失败，监督耗时 `6.205292497 s`、RSS 峰 `351,285,248 B`；只在重试 systemd service 限定 `LimitNOFILE=4096` | 24-array mmap fixture 直接读到 soft/hard=4096；按 1,602 files 与 512 FD allowance 的 projected use 为 2,118，余量 1,978。checker leaf `/proc` RLIMIT **NOT_SAMPLED**，不声称有直接 leaf 读数；全局 FD limit 未改 |
| swap 与清理 | 各监督树 VmSwap 峰 `0 B`；有采样的 global `pswpin/out` 区间增量均为 `0`；checker/readback 基线及末值仍为 `783/3167` 页 | 宿主已有 swap 基线保留，不能写成整机 swap 为零。监督后代清空；没有残留 Task40 checker service、FD fixture 临时文件或第二份 raw 目录 |

固定 W0 T0/deadline 仍为 `2026-10-04T13:04:57Z` / `2026-10-04T17:04:57Z`，未刷新；到 checker gate 完成时按 UTC 端点推导 elapsed `7515 s`、remaining `6885 s`，这不是 monotonic 总耗时或费用。完整准备、无监督空档与本窗口总 charge 均保持 `UNKNOWN_NOT_SETTLED`；既有 `200.87894401792437 s` worker 小计、`6bbc` 准备成本 unknown 和 V6 settled debit `5428.582333962078 s` 均未改写。首次 FD 失败仍在追加事件账中保留。

紧凑指标及 artifact hashes 见 [W0 closeout record](outcomes/records/review_v8_w0_component_closeout_v1.json)、[增量费用账](outcomes/records/review_v8_w0_incremental_workflow_ledger.json) 和 [run index](outcomes/records/run_index.json)。ignored artifact 的 [closeout receipt](../../benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/continuation_attempt4_checker_only_fd4096_20261004T150320Z/w0_component_closeout_receipt.json) 绑定完整 checker/raw receipts。`PDE_solved=false`、`official_results=false`、`R/T/A=NOT_GENERATED`；这只关闭 W0 组件与保存数据核验门。

## 首轮 W0 正式 worker identity-gate 停止（历史分类保留）

本次使用 Task40 README 指定的本机登记 worktree、分支 `task40extra_0p7nm_engineering` 和明确获准的独立 WSL2 ABI。数学输入仍是 80 cells、p6-only、532 个模式、φ=5°、MPI1/单线程；输入 SHA256 为 `6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e`，源身份清单 SHA256 为 `2609f67bf22cd4d00385c4d4806226498b42d22d8ed653c3debf5a80cfa7ee84`。数值源 HEAD 为 `8553a22b73ba8605888d0b27930144470ff5a84d`。

| W0 检查 | 观测 | 解释 |
|---|---:|---|
| 固定窗口 | T0 `2026-10-04T08:55:26.395534Z`；固定截止 `2026-10-04T12:55:26.395534Z`；截至 `2026-10-04T11:33:35.805415Z` | UTC 推导已过 `9489.409881 s`、剩余 `4910.590119 s`；不是 monotonic 耗时或费用，整窗准备与 W0 费用仍 `UNKNOWN_NOT_SETTLED` |
| 正式 worker | 新窗口第 1 次启动；停止记录 `2026-10-04T10:41:11.771267Z`；worker phase `1.5594090659869835 s` | 在 `build_dynamic_mode_inventory` 后、`fresh_p6_cold_setup_begin` 前触发有序身份断言 |
| 运行身份/入口 | `run_id=w0_formal_local_20261004T1038Z`；目录 basename 即 run ID；旧索引键 `local_w0_formal_20261004T1038Z_8553a22` 保留为 alias | run summary SHA256 `dc0dd382c03c7d4ffdb80f6ad0fd38ad624111fc5512cdfc071eb4d5168eb0bc`；worker PID/start_ticks `1733184/70682370`。formal service PID、start_ticks、unit name 未记录，未拿 control-smoke PID `1733083`代替。入口按保存的 precheck/ABI receipt 与 tracked wrapper 契约重建；字面 argv 未持久化。systemd unit `task40freshc1_local_wsl2_authorized_20261004T103856Z_1733139` 已由启动工具观测；服务 PID/start_ticks 未记录，unit 后缀不当作 supervisor PID |
| 精确错误 | `ValueError: fresh C1 requires the independently regenerated ordered literal532 physical inventory` | 冻结条件为 532 个有序模式且规范化清单 SHA256 等于 `4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951`。正式失败收据中的实际 count/hash 为 `null`；后续 no-FE 诊断见 W1 记录，不冒充 worker 原字段 |
| 进程资源 | 同时进程树 RSS 峰 `200,359,936 B`；任务树 swap `0 B`；global `pswpin/out` 增量均 `0`；后代已清空 | 采样 RSS，不是整机容量或 cgroup 硬峰；资源 Gate 未触发 |
| 失败边界 | FE/JIT/矩阵/因子/PDE 均未到达；checker `NOT_RUN`；raw 文件 `0`；official results `false` | 属于身份/实现 Gate 停止，不是 Maxwell 数值失败、收敛失败或资源失败 |

新独立前缀的纯模式诊断得到 532 行、规范化清单 SHA256 `afc439d8969463d3c3d46076382ec30c7a8fe3c9b1150955dc2d228a483e7f6b`，与冻结值不同。旧仓库 `.venv` 仅用于诊断，纠正入口路径判定后生成 532 行，哈希为 `ce7cb6670fb9c7b2dde457c13238bfd9bca99faab98fbb5c3f738a8902478f4d`，也不匹配；该环境 Open MPI 4.1.6/PETSc 3.19.6，不能代替 W0 的 MPICH 5.0.1/PETSc 3.25.6 前缀。旧证据包未交付冻结的 532 行原件，因此当前不能逐字段归因差异，也不修改门槛或源码。两次均未运行 FE/JIT/PDE。在 Task40 自有 artifacts 的边界文件名/大小核对中，也没有找到旧冻结 532 行 gold；唯一既存的其他 mode manifest 是 direct-reference 的 80-mode 文件（SHA256 `c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a`），不能作为 532 gold。目录中两个 532 行规范化清单都是本轮 no-FE 诊断生成且均不匹配冻结值。因此 W0 身份仍阻塞，不能用新摘要替换权威哈希或删除 guard。

## W1：核实原有 32,060 通道清单身份

这里的“流式核验”是逐块计算文件 SHA256，再逐行读取 JSON 数组来重算 key 摘要；不调用生成器，不保存完整的 32,060 行清单。原件与 repair 副本分别核验，结果完全相同：

| 核验项 | 实测 | 冻结记录 | 结果 |
|---|---:|---:|---|
| 文件大小 | 各 `36,244,923 B` | `36,244,923 B` | 一致 |
| 完整文件 SHA256 | 各 `52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d` | 同值 | 通过，两个文件字节身份相同 |
| `[side,m,n,polarization]` 有序 key 摘要 | 各 `03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec` | 同值 | 通过，按生产测试的 JSON 编码重算 |
| 顺序和覆盖 | `mode_index=0…32059` 连续；top/bottom 各 16,030；s/p 各 16,030；全部 propagating；最大 `(|m|,|n|)=(142,35)` | 原 inventory 为 32,060 个有序通道 | 通过 |
| 目标物理身份 | canonical identity SHA256 `a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f`；组合 inventory identity SHA256 `39b457c3f0b9d8db5f85a8f1482734513d48670c017d4c8060cae734bdcd0c12` | 原件与 repair ledger 保存同值 | 通过 |

目标身份是原尺寸 λ=0.7 nm、θ=89°、φ=0°、双端口 AUTO 模式；主线 Si 折射率为 `0.9998851703688496 + 4.3236152269189515e-6 i`，上端空气 `n=1`。ledger 中另有 Gx784 缩小输入物理模型 SHA `2d9fa71c8781d96a75e07d0ef1636bbba05e38e50891cd0bcb6661e4059555d8`；那是缩小源输入身份，不能与原尺寸目标身份混用。

这项通过只证明两个**已有文件**与库存中的完整文件、key 顺序及目标身份摘要一致；它不表示 32,060 模态的 W1 边界作用、目标网格精度或 FE 已通过。

## Task042 最小代码移交与适用边界

只读对象固定为 Task042 commit `f3bf7942f62e725057c3ae44820bc1ca1794ee59`。后续最小候选是 `src/solvers/directional_boundary.py` 与 `src/solvers/native_boundary_adapter.py`：前者把平面上的多项式基与傅里叶相位积分写成共享的一维积分收缩，减少通道重复遍历面片；后者按 native 单元方向、完整实体归属和 MPC 主从关系建立稀疏抽取矩阵 `E`，并用共轭转置 `Eᴴ` 把边界力散回体积自由度。它们是边界组件，不能替代体积求解器。

| 最小依赖组 | 可借鉴部分 | 接入前仍需处理 |
|---|---|---|
| 边界核 | NumPy/Basix 上的 exact-q Fourier/Legendre 方向收缩；原实现不含体积行号 | 按主线自己的材料、模式、参考面、相位和实际表面重建身份并测试 |
| native adapter | 由真实单元变换、完整实体 owner 与 MPC 展开构建 `E`；`Eᴴ` 完成 dual scatter | 全目标 native 行号未构造；Task042 witness 不是主线全模型映射。`independent_trace_port_terms` 惰性依赖 Task042 的 `P6DirectTracePortTerms`，需以主线 API 替换或隔离 |
| 独立证据参考 | pinned commit 含 `test_boundary_structure.py`、`test_native_integration.py`、`check_boundary_structure.py`、`check_native_integration.py` 和 V38/V39 checker 记录 | 这些只证明各自 fixture，不是主线 fresh FE/独立残差通过；`task042_full_input_checker.py` 是另一条 full-input/direction checker，不属于边界最小依赖 |

不能继承 Task042 的数值资格：它使用的 Si 为 `0.999885140474 + 4.32477054e-6 i`，与主线不同；Task042 每侧有 73×36 面片，而主线 272×4×14 仍只是单元数候选。若主线 y 向仅 4 段，最高 `|n|=35` 的相位跨度约 `54.98 rad`，而 36 段约 `6.11 rad`；这是提示积分风险的几何推导，不是误差测量。`q30` 是求积 degree，不是 30 个面片块。本轮新面片 q30/q60 结构对照 **NOT_RUN**：先决 W0 未完整通过，不能借用 Task042 的 q30 结果补门。

Task042 V38 边界组件在其材料和表面身份下覆盖 32,060 输出及上下共 378,432 紧凑行，q30/q60 最差逐通道差约 `1.6066e-12`；旧 q15 失败和 native q60 存储停止仍保留。V39 的四类 native mapping witness 最大差约 `1.3623e-12`，但真实体积尝试运行 `912.591881 s` 后，因为把 660 个 MPC slave 行误当独立 trace 而失败。修复要求使用 `owned_active_original_dofs`；修复后没有完整 FE 重放。V39 消费演示的 volume callback 是 synthetic zero callback；非零 native 内部 RHS 的完整仿射恢复仍未资格化，不能称为通过的体积引擎。

变量约定不能凭相似名称拼接。Task042 增广块为 `[V,B; -D,I]`，其中 `D` 已除 projection denominator；未消元的 `Hp=I` 是隐式单位块。消去内部自由度后 `Hhat=I+Di Vii⁻¹ Bi`，端口 RHS 含 `Di Vii⁻¹ fi`，内部恢复为 `xi=Vii⁻¹(fi−Vit xt−Bi α)`。projection denominator、`Hp` 与 `Hhat` 不同；Task042 记录的 native C 内部项最大 `1.3012535225e−11`，不得直接裁零。

## 首轮阶段、费用和证据快照（历史；上文为当前续作状态）

| 阶段 | 当前状态 | 具体边界 |
|---|---|---|
| W0 | `INCOMPLETE` | 当前 V8 窗口 worker 启动 1/最多 4 次；身份 Gate 前停止，非 FE/PDE/资源结果 |
| W1 清单身份 | `PASS_READ_ONLY_IDENTITY` | 原件与 repair 逐块/逐行核验通过 |
| W1 FE/边界作用 | `HELD / NOT_RUN` | 必须先完整通过 W0；本轮没有建网格或生成边界 action |
| W2 | `HELD / NOT_RUN` | 没有 C1c raw、完整 p6 链或对应条件 |
| dot | `HELD` | dot 许可与预算独立，未因本次身份审计改变 |

旧三次 worker 已知 elapsed 小计 `200.87894401792437 s` 保持不变；旧 `6bbc` 准备/阻断费用仍 `unknown/null`；历史 V6 settled debit `5428.582333962078 s` 保持不变。新 worker phase 实测 `1.5594090659869835 s`，但从本轮 T0 起的全部准备、诊断和总结费用尚未完整结算，**W0 总费用仍 unknown/null，不按 worker 秒数冒充整窗成本**。政策额度最多 4 次 worker 启动、最多 3 轮工程修复；保留 event 15 的 `NOT_INFERRED` 快照，本次有限审计后保守记为已用 2/3：`4b780d8` 修复固定 deadline 传递并补共享 no-FE 控制入口；`8553a22` 是用户另行授权的 local WSL2 profile 资格化，虽属运行 profile/source 变更、非数学修复，仍保守计作第 2 轮。其后的新前缀/旧 `.venv` 身份清单与 preflight 诊断没有源修改，不计修复轮。

详细身份与 Task042 blob 见[机器可读审计记录](outcomes/records/review_v8_w1_identity_audit_v1.json)；正式 worker 原始失败/资源收据及 no-FE 诊断位于 ignored artifact 目录 `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w0_wsl/w0_formal_local_20261004T1038Z/`。本机事件账只追加，窗口原件未改写。主线 summary、run index 和费用账本已补当前状态；这份进度证据由主控审核并提交到同一执行分支；它不代表 W0 数值资格通过，也不取消本轮尚未到期的授权。
