# Task037b Review V2 response v3：单侧 block-PC screen 研究结项

## 结论先行

本轮只问一个窄问题：已经通过代数审计的固定 DtN Woodbury action，作为完整 Hybrid
block-LDU 的近似局部逆，是否在冻结配置下提供有限步容量。答案是单侧不一致：
bottom approximate 通过 20-step screen，top approximate 严格失败。因此最终分类为
TOP_APPROXIMATE_SIDE_NEGATIVE，按 Review V2 §6.3 关闭本轮，不启动 double。

这不是 Hybrid 模型、exact matrix-free block operator、exact block-LDU 或 Woodbury 公式
失败。它只说明冻结的 top approximate one-sided capacity 未达到 0.35 screen Gate；
未经 review 的其他算法家族也没有被本轮否定。

## R0–V2 状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| R0 | pass | source、authority、qualified ABI 与 ordinary default 边界 |
| R1 | pass | F/C/D/H action decomposition |
| R2 | complete controlled negative | 六-slab F-only 未资格化 |
| R3 | complete controlled negative | whole-endcap ILU(0) 的 F-only 与 complete-A 未资格化 |
| R4 | pass | exact F inverse Woodbury 与 exact A 一致 |
| R5 | numerical negative | 21/21 nonzero capacity 未通过 |
| V2-B | pass | bottom approximate / top exact，final true=0.26797784324787316 |
| V2-T | negative | top approximate / bottom exact，final true=0.3518371324843258，严格高于 0.35 |
| V2 double 20/100/200 | not_run | 一正一负触发 one-sided stop |

V2-T 的 formal_record_pass=true 表示 source、launch、resource authority、安全清理和完整
raw record 均完成；worker_numerical_pass=false 表示 screen 数值 Gate 未通过。两者不是
矛盾字段，不能把 formal record completion 写成 numerical pass。

## 冻结身份与实现边界

| 项目 | 值 |
|---|---|
| source | 5b94060eae3a2ce02dd87e8a8c2075b635711346 |
| branch | codex/20260807-task37b-hybrid-iterative-development |
| physics | p6/h10、modal p6/h10、13.5 nm、M120/candidate240、external modes/endcap=40、MPI8、10/110 nm、10° S |
| assembly/models | static-condensed、full3d_uniform_cg、scalar_cg_discrete_derivative |
| callback | FixedAction wrapper 每次精确调用一次 HybridLocalDtnWoodburyOracle.apply |
| inner solver | 不调用 LocalInverse.solve，不创建 nested local FGMRES/KSP、fallback 或 adaptive path |
| ordinary defaults | unchanged |

733a1cb 的首次 V2-B 只在 worker/PDE 启动前因 scoped Case090 evidence wiring 停止，
不是数值运行；5b94060 的单行 scoped exemption 修复后，才完成唯一正式 V2-B 与 V2-T。
旧 artifact 保留，但不计为第三次数值 screen。

Task37-extra 只作为继承的冻结负证据：remote ref e637b11d93baae920cb019f26fd0dcbd94802af6，
reviewed source 30e179799b8eb6dee1be1bb976002550424bb40d，payload 3128209352 B =
2.9133719876408577 GiB，约 trace ILU 25.636x；1V rho 为 5.61e6/3.47e6/6.17e7，
2V rho 为 4.89e15/1.65e15/1.41e16，G2_FAIL、G3 prohibited；LOR transfer/algebra = pass only。LOR、AMS/HX、p2/p4、
p-multigrid、full-space ILU 继续冻结，未重开。

V2 依赖顺序与边界如下；六个实现提交均为 research-only，ordinary defaults unchanged：

| SHA | 作用 |
|---|---|
| a42938eb912c2d24acc15e64a668649dfafc7dbe | fixed one-apply R5 action |
| 25d5a211b8df5a59784bfa0e60a8324f890eeed8 | same-action modal Schur/block-LDU |
| e75ce90256d53cc12c295eb0b2fbd5d4b4dc4343 | bounded outer screen core |
| 3baa695c0c8e1933d2c36923f8d4f96dffde8e82 | bounded block screen runner with frozen V2 flags |
| 733a1cb0ee533639e29b3a5ce60becf6a29162ec | V2 explicit watchdog implementation |
| 5b94060eae3a2ce02dd87e8a8c2075b635711346 | final scoped launch wiring fix and numerical source |

## V2 数值与资源

V2-B callback identity=0、linearity error=1.9458251250889472e-15、determinism=0、
repeat hash 一致、K rank=40/condition=3.033166890369435；modal Schur 为 240×240、
rank=240、condition=831.7366055154229。factor bottom direct/ILU=0/1、top=1/0，
online increments=40/40。

V2-T callback identity=0、linearity error=1.9498727881145686e-15、determinism=0、
repeat hash 一致、K rank=40/condition=4.162687539173754；modal Schur 为 240×240、
rank=240、condition=638.1064857343471。factor bottom direct/ILU=1/0、top=0/1，
online increments=40/40。

| 运行 | process-tree RSS | worker RSS/PSS/USS sum | wall | swap |
|---|---:|---:|---:|---:|
| V2-B | 8164.375 MiB = 7.9730224609375 GiB | 8149.71875 / 7027.908203125 / 6841.94921875 MiB | 390.9353968849173 s | 0 |
| V2-T | 8736.828125 MiB = 8.532058715820312 GiB | 8722.1796875 / 7609.48046875 / 7424.91015625 MiB | 389.2415761810262 s | 0 |

process-tree RSS 是权威峰值；PSS/USS 是 timeline smaps_rollup 的 8-rank simultaneous
sum，均取独立最大值，不是对象体积。两次均未触发 10/14 GiB watchdog 安全阈值，均无
orphan，但都高于 6 GiB standalone resource-positive 线，因此没有 resource-qualified
candidate。T 的峰值含一个 exact bottom direct factor，不能预测 double。

## Official 与后续边界

official_record、Hybrid field、R/T/A、A_volume、external diffraction、12+12 和 Full3D
physical comparison 全部 not_run。H6–H10 不运行；double 20/100/200 不运行。不得因为
本轮负结果调参、重跑、做 full solve，或自行重开 LOR/AMS/HX/p2/p4/p-multigrid/新
Schwarz/shift/overlap/ILU sweep。master merge not authorized；所有当前 V2 source、
runner、watchdog 和 candidate 仍为 research-only。

## 证据索引

| 证据 | 位置 |
|---|---|
| compact V2 record | [Case101 V2 record](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v2_block_pc_screen_v1.json) |
| 单侧结果与残差表 | [one-sided boundary](outcomes/one_sided_replacement.md) |
| double stop | [double funnel boundary](outcomes/double_iterative_funnel.md) |
| 资源账本 | [resource ledger](outcomes/resource_ledger.md) |
| 测试账本 | [test summary](outcomes/test_summary.md) |
| source/选择性边界 | [changed files](outcomes/changed_files.md) |

本 response 不修改 response_v1、response_v2、原 H5b/R5 raw 数值或 review/task 文件。
本轮 code-free closeout 不运行 full pytest、CI、PDE 或 double MPI。
