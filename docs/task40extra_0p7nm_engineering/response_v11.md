# Task40 V11 执行回应

## 结论

V11 已按 Review §S0–S6 收口。端口平面功率接线在同一份已保存 B0 场上通过独立复核；两个原尺寸局部 p6 块的恢复候选通过局部方程和已知场检查；dot 的 32,060 个 B/D 行分块动作在两个代表面通过独立 checker。主数值里程碑没有完成：Gx560 的四个 q 只完成符号阶段，随后在数值因子化前触发内存准入受控停止；Gx784 条件未满足而未运行。50×25×140 nm、0.7 nm 的完整三维目标仍为 `NO_GO / NOT_QUALIFIED`，这表示本轮没有足够证据证明目标满足资源与精度门槛，不表示数学上不可能。

## 身份、窗口与历史基线

| 项目 | 值 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task40extra_0p7nm_engineering` |
| Review V11 base / 本轮冻结代码 HEAD | `eb6489e95463f22798f0d004fe9e74e78cbc3937` / `223f602b84761eb99631e7a61a784c3d6c857c04` |
| 固定 V11 窗口 SHA-256 | `1014f9ff536344d0829c1e58f1a1f25373be7b18f11bddd132e15a23558a0bd1` |
| 固定截止 / 收口预留 | `2026-10-07T01:17:35.732545140Z` / 600 s |
| 预算观察 | seq 8089 是历史快照：累计 charge `24167.947039851726 s`、推导余额 `61632.05296014827 s`。主控随后记录交付观察 seq 8090（`2026-10-06T09:14:00.836725318Z`）：累计 policy charge `28609.104986536724 s`、推导 numerical remaining `57190.895013463276 s`；窗口未刷新，`final_settlement=false`，Git/测试收尾成本仍由主控写入同一账本 |
| 源码状态 | 当前 HEAD 是收口源码，不替代每次运行的 source SHA；执行者不操作 Git，由主控集中审查后提交/推送；未经最终批准与用户授权不合并 master。最终预算观察由主控单一写入者完成 |

S0 保留 V10 B0 的正、负两类结果。B0 是 80 cells、p6、y 方向四个周期 q 分支的真实三维两单元缺口问题。p6 求解的显式 true residual 为 `1.6089774391665316e-8`，释放后 native witness 为 `1.6089791915820923e-8`，均低于 `1e-6`；原始能量闭合 `6.581916436299018e-5` 高于 `1e-5`，旧记录仍保留为历史负结果。p4 控制的 2048 步、KSP reason `-3`、A6 residual `0.966131083707469` 也继续保留，不重跑、不用于成功速度对照。

B0 原始 candidate summary 在因子销毁前记录四个 q 因子同时存活。下表的 MUMPS 内存是各因子自身的 INFOG 记录，不是进程树 RSS 或 cgroup 峰值；INFOG(29) 是因子项数，不是字节数。

| q | 因子行数 | 输入矩阵 NNZ | INFOG16/17 符号估计 (MB, max/sum) | INFOG19/22 分配/使用 (MB) | INFOG29 因子项 |
|---|---:|---:|---:|---:|---:|
| 0 | 4,324 | 2,270,108 | 123 / 123 | 123 / 110 | 3,625,232 |
| 1 | 4,400 | 2,327,293 | 125 / 125 | 125 / 112 | 3,676,320 |
| 2 | 4,400 | 2,304,310 | 124 / 124 | 124 / 111 | 3,655,050 |
| 3 | 4,400 | 2,325,342 | 125 / 125 | 125 / 112 | 3,674,096 |

## S1：B0 保存场的端口功率复核

这一步对已保存 p6 解做输出恢复；恢复过程可以重建必要的 mesh/space/operator 准备，但本次未重解 PDE、未新建数值因子/KSP。在线求解输出与保存场恢复均使用 gauge-aware 功率路径；端口平面振幅直接用于物理功率，避免再次乘传播相位。legacy global-z 默认行为保持不变，boundary-plane 行为显式 opt-in。科学 E/H/curl/模式数据与可选 PyVista 可视化分开保存，可选绘图依赖不会决定科学输出是否写出。独立 checker 核对了全部 532 个端口模式、top 入射只扣除一次、bottom 无入射扣除、逐模态叉乘功率、分组功率和体吸收。

| 指标 | 新保存场复核值 | Gate / 状态 |
|---|---:|---|
| R / T | `0.9842736080926772 / 0.014240518143988908` | 独立逐模态与分组功率一致 |
| A_balance / A_volume | `0.001485873763333926 / 0.00148587384621333` | absorption consistency `8.287940407754324e-11` |
| 能量闭合绝对差 | `8.287925901129256e-11` | `<1e-5`，通过 |
| sum-factorized residual / native full-A6 witness | `1.6089774391665316e-8 / 1.6089791915820923e-8` | 均 `<1e-6`，通过 |
| 保存场后处理成本 | wall `11.256015081 s`；树 RSS 峰 `716091392 B`；swap `0 B` | saved-field-only |

结果分类为 `SAVED_FIELD_PHYSICS_REVALIDATED`。这是原 B0 已保存解的物理输出复核，不是新的 PDE 运行；V10 的旧 energy-fail 记录没有被覆盖。

## S2：原尺寸局部 p6 恢复

两个已保存局部块（top / bottom）的已知场恢复相对误差分别为 `5.3524732442130614e-14` / `5.143310794873929e-14`，低于 `1e-11`；原始局部方程相对误差为 `4.771522785641244e-16` / `6.413893640082291e-16`，低于 `1e-10`。重算的端口方程也通过。分类是 `DERIVED_LOCAL_RECOVERY_REPAIR_CANDIDATE_WITH_RECOMPUTED_PORT_EQUATIONS`：它支持这两个保存局部块，不等于完整原尺寸边界链资格。全 q60 行重检为 `NOT_RUN`（保留既有 witness），全目标体积 MPC 为 `NOT_RUN_AUTHORITY_LIMITED`。

S2 用时 wall `33.1747834029 s`、CPU `36.778499242 s`、单个 Python 进程 `ru_maxrss=634454016 B`。这是单进程峰值，不是进程树或 cgroup 峰值。

## S3：B0 可选直接参考

状态为 `NOT_RUN_AUTHORITY_LIMITED_OPTIONAL_REFERENCE`。现有 direct 链绑定 G0 的 map/witness，与 B0 boundary-plane operator、RHS 和输出合同不匹配；缺少 B0 专用的整图 witness 与预算绑定，安全适配会跨越 witness loader、direct assembly/native action 和 saved-output 比较。本轮因此保留 authority limitation。它不是硬件容量失败、ABI 失败，也不是用户授权缺失。

## S4：Gx560 与 Gx784

Gx560 实际 attempt 使用 source `9977284c47c8028751de4dbecd12b95d1912a580`、run id `task40extra_0p7nm_nonseparable_gx560_p6_y_orbit_v11_v1`、input SHA-256 `7f20aa9719c91c6be4d6a4b4cd00ec8b7a7610fdf53c889f88a42ece03f17d1f`，网格为 10×4×14、560 cells、p6、340 modes。四 q 的行维数沿用已审阅的 sector/block shape 合同；final admission receipt 没有保留各 q 的独立 matrix NNZ 或单独符号阶段时长，因此这两项记为 `unknown`。

| q | 行数（case/sector shape 合同） | 矩阵 NNZ | INFOG16/17 (MB) | INFOG20（符号因子项估计） |
|---|---:|---|---:|---:|
| 0 | 28,508 | unknown | 1,157 / 1,157 | 41,320,088 |
| 1 | 28,508 | unknown | 1,150 / 1,150 | 41,253,248 |
| 2 | 28,576 | unknown | 1,169 / 1,169 | 41,789,336 |
| 3 | 28,508 | unknown | 1,165 / 1,165 | 41,269,544 |

四 q 的 INFOG16/17 是 MUMPS 符号分析给出的内存估计，INFOG20 是假设满秩时的因子项估计；它们不是已经构造的数值因子库存。MUMPS 对 INFOG16/17/20 的定义见 [MUMPS 5.8.2 Users’ Guide](https://mumps-solver.org/doc/userguide_5.8.2.pdf)。

最终 Gate `all_q_symbolic_before_any_numeric` 的资源数据如下。两种 cap 来自不同边界：13.462 GB 是本任务 finite cap；3.167 GB 是停止时的动态物理可用内存预算。

| 指标 | 值 | 口径 |
|---|---:|---|
| Gate 时 process-tree RSS | `10,295,283,712 B` | 当时同时树采样 |
| 加入四 q 符号估计后的 projected RSS | `15,205,944,640 B` | 准入投影，不是实测峰值 |
| effective finite cap | `13,462,286,336 B` | all-object finite cap |
| 停止时可用物理内存 / 动态 launch cap | `3,301,220,352 / 3,167,002,624 B` | 各扣留 `134,217,728 B` 证据写入余量 |
| 四 q native symbolic estimate | `4,776,443,200 B` | MUMPS 符号阶段估计 |
| watchdog process-tree RSS peak | `10,418,892,800 B` | 全程采样同时树峰值 |
| dedicated cgroup memory peak / limit | `10,930,950,144 / 17,179,869,184 B` | cgroup 高水位 / 限值；不是 tree RSS |
| task/cgroup swap | `0 / 0 B` | 受控 Gate 通过 |

因此分类为 `RESOURCE_CONTROLLED_STOP_BEFORE_NUMERIC`。numeric allocated/used/fill、KSP、场、official R/T/A 均为 `null / NOT_RUN`；INFOG 符号项数不能当成 numeric factor inventory。leader exit code 4，进程身份覆盖完整、状态可读、后代已清理。运行 watchdog monotonic elapsed 为 `2041.652704 s`，service workflow monotonic 为 `2041.826505 s`；保守 UTC policy 计费 `2244.797416 s`，两钟差 `203.143 s`。原始 `shared_budget.remaining_numerical_seconds_at_worker_entry` 为 `73181.66253952701 s`；watchdog `time_reference_seconds=73182.01969292195 s` 是父级入口参考，两者各按来源保留，不混作 worker 实测耗时。

另有一次早期启动 guard 因缺少既有受监督 service 而停止，没有进入数值阶段；109-byte console 收据 SHA-256 `80fcf085a1177e7700e68c7f25309d083c52b88e5e093eb55832c02705d64d1c`，该次耗时/成本 `unknown`。实际 Gx560 service 随后按固定窗口运行。由于 Gx560 未通过数值资格，条件 Gx784 状态为 `NOT_RUN_CONDITION_NOT_MET`。

## S5：dot 的 882 行组件结果

这是完整 B/D 分块动作在两个代表面的规模测试，不是全边界、全域 MPC、全算子范数或 PDE。每面均保留完整 882 个 native rows，按 16 模态一批、64 点一块、q60 的 961 个采样点处理；未构造 32,060² 矩阵，也未保留 mode×882 全量映射。

| 面 | 模态数 | 全 inventory Bα 相对误差 | 全 inventory Dx 相对误差 | checker |
|---|---:|---:|---:|---|
| top | 16,030 | `1.1308675126224078e-13` | `3.861920061984271e-14` | PASS |
| bottom | 16,030 | `1.0414255157250765e-14` | `3.908206118402893e-15` | PASS |

84 行仅用于局部表面 trace adapter 的抽取/散射一致性诊断；它不替代 882 行 B/D。84 行压缩替代尚未资格化，本轮主线未重跑压缩。

四个阶段共用一个 systemd service，依次运行。该 service wall `15.182 s`、CPU `11.481 s`、共享 cgroup memory peak `546459648 B`、swap 0、PSS null；这是四阶段共用的 cgroup 高水位，不是每阶段峰值。各阶段独立 process-tree RSS 峰值为 `455847936 / 495640576 / 457056256 / 381509632 B`，不得相加。局部 helper 自有数组上界为 `7313968 B`。

S5 的三个工程重试错误均保留：`ModuleNotFoundError: No module named benchmarks`（启动前，未数值执行）、`NameError: construction is not defined`（trace extract/scatter 后、Bα/Dx helper 输出前；tree RSS `453398528 B`、swap 0、后代清理）、以及旧 campaign 参数触发 `ValueError: Task40 V10 campaign time must be enforced`（启动前）。早期 service 的状态读数仅保存为约 `1.2M` 的舍入显示；先前 `1258291 B` 是换算值，不是精确 bytes 实测，精确峰值 unknown。修复后的 action、独立 checker、full inventory action 与 checker 四阶段均通过。

## S6：可推广性、测试和下一步

小模型上的四 q p6 参考逆把规则背景按周期相位分块，再用它给保留真实三维缺口的目标系统提供迭代修正；Gx560 显示，完成符号分析仍不足以证明数值因子化可安全准入。S5 只验证两个面上的 B/D 分块，S2 只验证两个局部块，均不能补成原尺寸完整映射或 2 TB/48 h 资格。当前没有充分证据承诺原尺寸完整流程的内存或时间。

| 下一项 | 状态 / 决策 |
|---|---|
| 全部 S0–S6 结果与人工审阅 | 交由主控依据本回应、综合报告和五份 V11 compact records 审阅 |
| Gx784、全尺寸 direct、原尺寸 global MPC、工作站运行 | 本轮 `NOT_RUN`；需后续独立授权、输入身份与资源准入，不从本轮推定通过 |
| S5 helper / gauge-aware 输出 | 可按显式 opt-in、独立 review 复用；ordinary default 保持不变 |
| Gx560 p6 全 q 参考路线 | 保留为 resource-controlled research result；不升为 production default，不原样重复资源失败运行 |
| 提交、推送、合并 master | 本执行者均未进行；等待主控处理 |

Gx560 后续唯一优先项是查明数值阶段前 `10,295,283,712 B` live process-tree RSS 工作集的对象所有权与生命周期。其来源类别仍 unknown；不能归因给 Python heap、有限元装配或 numeric factors（数值因子尚未建立），也不应先新增预条件器实验。相同资源状态不原样重跑。各阶段时间和嵌套口径见[综合工程报告](outcomes/review_v11_engineering.md)。

测试按源码身份分别记录：S2 定向测试 `26 passed` 的执行父 HEAD 为 `9977284c47c8028751de4dbecd12b95d1912a580`，当时源码文件 SHA-256 为 `3c8bd3bef250a590e433247ac287cc43b9e134dfa48d7a09183cc98ad90b4ff6`、测试文件 SHA-256 为 `be4575083a17df3af6f1bd51e35e49ba0d70be4eaf8a0ab44641a89c9baeb21e`；随后实现冻结在 `a1c5c6040cc3674418bbebd877790b1882ac010f`，不把测试误称为在该冻结提交上运行。S5 helper 定向测试 `5 passed`（HEAD `223f602b…`）；artifact-local runner `py_compile` 通过。最终文档合同测试见 [test summary](outcomes/test_summary.md)。全仓 pytest、MPI4、Ruff 和 CI 均 `NOT_RUN`。

完整 S0–S6 证据索引、成本分层和移交边界见 [综合工程报告](outcomes/review_v11_engineering.md)、[结果总览](outcomes/summary.md)、[V11 manifest](outcomes/records/review_v11_manifest.json) 及 [run index](outcomes/records/run_index.json)。
