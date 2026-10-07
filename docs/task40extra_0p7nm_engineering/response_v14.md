# Task40extra Response V14：Gx560 完成四 q 因子与参考检查，物理作用身份门未通过

V14 延续原固定窗口，在冻结源码 6ac8cf7fd4697e575a4bf47a862c560ae290076b 上完成 Gx560 的四个 p6 参考因子、增广参考检查和物理 RHS 检查。四个因子的严格真残差、时间门与内存门均通过；但物理 RHS 的独立算子作用身份差为 1.6834572689277185e-11，高于不可放宽的 1e-11 门槛，因此 worker 在 Full3D target solve 前以 exit 4 停止。Gx560 没有官方 R/T/A，Gx784 未运行，原尺寸目标仍未资格化。没有发现可据以重放的新实现 bug，也没有放宽门槛；仅对已保存数组做有界离线核查，未新增 FE 或扩大数值诊断。

## E0：接续状态与固定窗口

V14 审阅开始时远端没有归档 Response V13；本地证据显示 V13 B0 已有合格的完整结果，而 V13 Gx560 在数值因子前因资源门受控停止。本报告直接记录这些实际状态，不补造 Response V13。B0 复用原已归档结果，不重跑、不改写旧 worker 状态；此前 Gx560 资源负结果仍保留。

本轮固定窗口沿用 V13 原窗口，T0 为 2026-10-06T23:21:33.326800586Z，deadline 为 2026-10-07T23:21:33.326800586Z，没有刷新。V14 attempt 1 在 1.735083 秒内因 NameError: is_v13 未定义而于数值计算前退出；修复后冻结源码为 6ac8cf7。Attempt 2 的完整 workflow monotonic 时间为 2220.8270128549775 秒，策略保守 realtime charge 为 2420.165726454603 秒。二者是不同计时口径；不从差值推算 solver 阶段时间。后续文档、测试和主控 Git 收口仍计入同一窗口，最终结算由主控负责。

## E1–E4：里程碑与实际结果

| 里程碑 | 模型与方法 | 实际结果 | 状态 |
|---|---|---|---|
| E1 路由与装配策略 | 共用 allowlist、CLI/dispatcher/worker 路由与 witness 覆盖检查 | 46 passed；这是 5ac NameError 修复前的 source-ready 收据，不归因于后续修复 | PASS；独立早期收据 |
| E1 is_v13 NameError 修复 | 修复 worker-local predicate，冻结 source 6ac8cf7 | 另有 4 个 focused tests passed in 0.40 s，compileall 与 diff check 通过 | PASS；单独记录，不与 46 项合并 |
| E2 B0 | 80 cells、p6、532 modes、四 q | 复用 archived pass：R=0.9842736080926642，T=0.014240518143990319，A=0.0014858737633455053，A_volume=0.0014858738462134112；能量闭合绝对差 8.286793473644138e-11；释放后真残差 1.6089762312332008e-8 | REUSED_ARCHIVED_PASS；不是 V14 fresh run |
| E3 Gx560 | 10×4×14、560 cells、p6、340 modes、四 q；MPI1，complex128，int32 | 四 q 真残差依次为 3.986719346e-11、1.591872870e-12、8.624700464e-13、2.813498243e-12，均低于 1e-10。物理 RHS 独立 action identity 为 1.6834572689277185e-11，超过 1e-11 限值。Full3D solve 与 R/T/A 未运行 | NUMERICAL_GATE_FAILED；不是资源或时间停止 |
| E4 Gx784 | 14×4×14、784 cells、p6 | 没有运行目录或新测量 | NOT_RUN；因 Gx560 数值门未通过，不满足启动条件 |

Gx560 q 增广矩阵行数为 28,508、28,508、28,576、28,508，NNZ 为 15,451,743、15,479,361、15,581,290、15,479,361，总计 61,991,755。每个 q 的 native CSR 内容身份、MUMPS INFOG 实际字段与保守 allocated/used 上界列于 [formal results](outcomes/records/review_v14_formal_results.json)。四个因子同时存活；上界合计 allocated 4,645,000,000 B、used 4,080,000,000 B。INFOG9 原值保留，但没有从它推断因子填充项数或字节数。

### 参考见证与阻断诊断

参考逆是用四个 q 因子解一个已知的参考问题，再检查结果能否满足原方程；修正步骤把一次完整残差再送回同一组因子。它只改善参考解，不改变真实 target 方程。各见证结果如下：

| 见证 | V14 状态 | 实际证据 |
|---|---|---|
| 通用完整独立 RHS | 修正后严格通过 | 原完整方程相对残差 3.966049298e-12，最大 q 真残差 5.476337243e-11 |
| 全部 252,000 个内部行 | 修正后在已授权的有界不精确范围内通过 | complete_augmented_FE 相对残差 4.431933190549465e-12；原 full_regular 残差 4.431934540620194e-12；local combined 1.557941415e-11。q0 真残差 1.883671536e-10，高于严格 1e-10 但低于有界 1e-8。保留 raw_packet_passed=false，不改写为严格通过 |
| 非零全模式端口 RHS | 初始严格通过 | 完整方程 2.823850968e-12，最大 q 真残差 3.546290897e-11 |
| 物理 regular incident RHS | 结构身份门失败；未应用修正 | 独立 sector/native action 差 1.6834572689277185e-11，限值 1e-11；动作差范数 4.13049706226925e-11，分母 2.4535799859655354 |

主控随后对既存 NPZ 做了有界离线核查，不只核对数组归属：独立重算 action 差范数 4.13049706226925e-11、原 operation 分母 2.4535799859655354 和原比值 1.6834572689277185e-11，确认仍高于 1e-11 门槛。它只使用保存数组，没有新增 FE、factor、reference 或 PDE，也没有扩大数值诊断。

因此，V14 的具体阻断是物理 RHS 的参考作用身份核验失败，不能归类为“仅残差略高”或把它当成一般求解器失败。没有证据支持静默放宽结构门、增加 floor、跳过 q、再重放或推断单一根因。

## 装配选择、时间与资源

预分配 CSR 是提前为稀疏矩阵的存储位置排好空间；它在 B0 的完整四 q 组件比较中节省 6.370516 秒，但那项比较没有构造 MUMPS 因子，也没有证明 Gx 的整体 setup 或暂存峰值更低，256 MiB 暂存上限亦未资格化。因此 V14 依据 review 授权选择经过验证的旧 CSR 累加路径，保持参考 PC 不变。

| Gx560 阶段或口径 | 数值 | 解释 |
|---|---:|---|
| q=[0,2] 扇区装配 | 252.601001339 s | 父阶段；局部贡献生成、投影与稀疏累加包含在内 |
| q=[1,3] 扇区装配 | 192.365708545 s | 第二个父阶段；与上一行均包含在完整 workflow 中 |
| 四 q 因子 setup | 30.428798860 s | 子阶段，不与完整 workflow 相加 |
| 四 q numeric 时间合计 | 18.483240675 s | 子阶段，不与 setup 或完整 workflow 重复相加 |
| 两次参考修正 | 8 次额外 q MatSolve；完整 raw augmented inverse 回调 16.055923939 s | 计数为 4 个初始 startup witness callback 加 2 个 correction callback；target PC 为 0 / NOT_RUN；纯 MatSolve 秒数未知 |
| 完整 workflow monotonic | 2220.827012855 s | 全工作流计时 |
| campaign policy charge | 2420.165726455 s | 保守 realtime 记账，和 monotonic 分列 |
| 进程树 RSS 峰 / cgroup 峰 | 10,168,500,224 / 11,207,577,600 B | 不同内存口径，不相加；PSS 按 profile 未采样 |
| 任务 swap / watchdog 样本 | 0 B / 8,615 | 身份覆盖完整，子进程已清理；时间和内存门通过 |

Full3D target KSP、场恢复、输出和独立 checker 的阶段成本是 NOT_RUN，不从完整 workflow 与子计时的差额推算。

## E5：原尺寸桥接与下一唯一候选

[工程到目标桥接包](outcomes/v14_engineering_to_target.md)复用了原有 0.7 nm 模式清单和资源账，没有生成原尺寸网格、矩阵、因子或 PDE。原尺寸候选 272×4×14=15,232 cells 是计数推导；32,060 个 AUTO 传播模式是已测模式清单。p6 行数、74 个 Krylov 向量、保留 scratch 和单个稠密 H 的数字均不是同时 RSS。实际目标 NNZ、CSR indptr、四 q 填充、y/z 精度、目标时间与 2 TB / 48 h 资格仍未知。不得只凭 int32 行数宣称目标索引安全。

下一单一电尺寸点是同波长 0.7 nm 的 E1 q1.25：现有输入 SHA256 5c0aa01d1bb327f1331b69cfe359c6f775961398d316c2f88d3aeaff978af8fd，计划轴计数 10×4×19、760 cells。它保持 HELD、未运行；实际生成网格、传播模式数和资源成本未知。当前 V13 case allowlist 没有 E1 的端到端 reference-PC 路由，V14 不扩充 allowlist，也不启动该 case。E1 还依赖 Gx560 物理 action identity 门后续获得可审查闭环。

## 选择性合并建议与测试边界

| 依赖组 | V14 建议 | 测试 / 新鲜数值证据 |
|---|---|---|
| production numerical/core | 不升为默认；V14 未证明 Gx560 完整 target 解 | 有参考 q 因子与失败的物理 action 门；没有 target solve |
| reusable runner/watchdog | 保留通用监督、身份、资源门与已审查输入路由 | 46 项 E1 定向测试及 validate-only；不代表新数值算法资格 |
| checker/benchmark | 保留原字段与保存见证独立复算入口 | 四见证按原始字段区分严格通过、有界通过和结构失败 |
| compact evidence/docs | 合入本响应、summary、target bridge、run index 与紧凑 records | 文档合同测试结果登记在 test summary |
| research-only | legacy CSR 选择、V13 参考修正候选及 Gx560 四 q 实测库存 | 没有 Gx560 完整 target pass；保持研究状态 |
| do-not-merge / do-not-claim | 不放宽 identity gate、不扩大 E1 allowlist、不宣称 Gx784或目标资格 | Gx784、官方 Gx560 R/T/A、原尺寸 PDE、MPI4、全仓 pytest、Ruff、CI 均未运行 |

本轮不改 ordinary default、dot、workstation 或 master；执行者不 commit/push。主控统一审核并处理 Git 收口。

## 证据索引

- [Review V14](review_report_v14.md)
- [执行接续记录](outcomes/records/review_v14_execution_handoff.json)
- [参考与装配记录](outcomes/records/review_v14_reference_and_assembly.json)
- [正式结果记录](outcomes/records/review_v14_formal_results.json)
- [成本与修复 compact ledger](outcomes/records/review_v14_cost_and_repairs.json)
- [原尺寸桥接说明](outcomes/v14_engineering_to_target.md) 与 [结构化桥接记录](outcomes/v14_engineering_to_target.json)
- [run index](outcomes/records/run_index.json)、[summary](outcomes/summary.md)、[test summary](outcomes/test_summary.md)
- 原始完整运行材料位于 ignored run directory results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_gx560_p6_reference_v13__full3d_iterative__mpi1__Mna/20261007T044200.351370Z；以 compact records 中的 artifact hashes 核对。

最终状态：CLOSEOUT_READY。轻量文档合同检查为 24 passed、134 subtests passed。该状态仅表示获准工作与证据收口可供主控审阅，不表示 Gx560 完整 PDE、原尺寸模型或 2 TB / 48 h 目标已通过。
