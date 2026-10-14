# trace4_interior6_actual_only_20261014

日期：2026-10-14（UTC）。实际终态及独立复核已绑定；范围限定为 actual-input-only g=0 诊断。

## 1. 结论及边界

受限 actual-input-only 阶段 exit 0，并完成 same6656 原 first-Arnoldi 入口的 PC 诊断。八次实际 g=0 粗调用均通过原 full/native Qᴴ 与端口门；但 retained 最佳单方向残差比仅从旧 p4 的 0.9999998952548249 变为 0.9999875004448556，仍几乎为 1，改善很弱。

这里的成功是有限输入、有限检查和清洁终态。all_diagnostics_passed_claimed=false；原压力 g=1 FAIL、checkpoint raw MISMATCH、saved/native PC 与 prediction raw FAIL 均保留。没有接受物理解，没有 outer/CG 步，不能称为通用粗逆、平台修复、108 或 hp 收敛。

## 2. 限定实际输入，没有丢掉原端口

保持同一 108 单元 fine p6、trace-p4 + 全部 48,600 个 p6 泡函数、58,824 场自由度、原 80 端口及 10,304 阶 Schur K。P 系数、原物理算子、H3、共轭伴随、消去/恢复和原 1e-10 门槛不变。

v3 actual-only 源码及 84 项 stdlib 测试通过，冻结命令 SHA 为 `36fa15f74b8030ff60fc3ff17fbfc31506d90fd083c632cfbb5a20ce5e7717d6`。入口明确限制粗子解辅助 port RHS 为 g=0；保留两份旧 FAIL 的摘要、错误及独审哈希。第三个 g=1 压力探测不重跑，未被改写成通过。

实际 retained 端口先由原 explicit_lift 消去，最后由原式恢复。本次被动测量：

- retained trace 范数：1.000000000000002
- retained port 范数：5.7780000526830012e-13
- Hp⁻¹ retained-port 范数：1.8499356695780710e-13
- BHp⁻¹ retained-port forcing 范数：3.9890790823751881e-12
- lifted full RHS 范数：1.0000000000000049

因此本次实际输入与旧资格压力 g=1、forcing 约 70,560 的情况不同。辅助 g=0 不代表删除 retained 端口。新增测量只调用一次原 Hp solve 和一次 B action，不参与修正公式、门槛、归一化或物理场。

## 3. 实际执行与有限资格

本次用时 362.962546363 s，1,439 个资源采样，进程树采样峰值 3,204,517,888 B。fresh JOB1/数值分解各一次，factor solve 共 18 次；八次逻辑粗解；postfactor native A6 共 33 次；wrapper 的独立 volume/DtN 各 12 次；H3 apply 三次，另有 H3 setup 的 20 次 power-matrix 乘法。outer KSP 未创建，outer 与 CG 迭代为零。执行 first-Arnoldi 的检查钩子不等于执行一次 outer 迭代。

八次粗解使用完整缺陷修正的次数分别为 0、1、1、0、1、0、1、0；同因子 solve 次数分别为 1、4、4、1、3、1、3、1。最终 Qᴴ 最大相对残差 7.83179254187148e-11；端口最大相对闭合误差 1.9938047826728694e-12，低于原 1e-10 门槛。每次最多两次修正的上界未改变。

随机 balance 探测的原 eps1−eps2 账目通过，closure relative 为 7.861224817561227e-13（原 closure limit 1e-8）。这些结果只覆盖两次 g=0 场探测及本阶段实际调用，不是对任意 RHS/非零辅助端口的证明。

## 4. 同一冻结 6656 输入下的方向仍很弱

新旧 raw hash、unit hash 和 PETSc 原始范数完全一致；原始 native residual 范数为 0.013898680225977397。未修改物理输入或原 checkpoint。

retained 空间可直接对比的最佳单方向残差比：旧 p4/H3 为 0.9999998952548249，新 trace4/interior6/H3 为 0.9999875004448556。新方向的理想单步相对下降仅约 0.00125%；这只是固定方向的最优标量诊断，不是实际 outer 收敛轨迹。

新的完整 native p6 结果单列：最佳单方向相对残差 0.9999875004448089，A6PC/source 范数比 0.6367509532802941。旧实际 full A6PC 没有独立保存，不能将旧 reference full 范数、retained Arnoldi 范数和新 actual full 指标混在一起比较。

同一 full-reference 诊断中，coarse complement 从 2.9978874320107307 降为 1.1849131298691549，smoother surviving complement 从 12.229182177440041 降为 2.652855829366698。这显示局部指标改善，但不能推出平台根因或整体有效收敛；最终方向仍很弱。

## 5. 哪些比较通过，哪些严格失败保留

原组件公式的 full PC 展开、retained dual lift、bridge 及原端口完成比较的差为 0；same6656 原 ledger closure relative 为 8.806663592155179e-12。这些是明确限定的 PC 展开/桥接/闭合比较。

以下没有被上面的 PASS 覆盖：

- 原 checkpoint action raw mismatch：相对差 7.194752879915044e-9，门槛 1e-10，状态 DIAGNOSTIC_CHECKPOINT_RAW_MISMATCH。
- saved/native checkpoint 残差的 raw 相对差 3.5652711475150975e-7。
- saved/native PC action raw 相对差 9.442207777669592e-10；operation-relative 4.721103888894146e-10，也未过门。
- native prediction raw 相对误差 2.7082330670013e-10；saved prediction raw 相对误差 2.7426671867684214e-10。其 operation-scaled 检查通过不覆盖原 raw FAIL。
- coarse initial/complement/complete 的 raw 相对比依次为 3.0069224031635163e-6、0.28230218084969383、1.0123818378780467；raw_passed 均为 false。原 operation-scaled eps1−eps2/closure 门通过，不能把相对于近零 defect 的 raw 比值改写成 PASS。
- 历史 g=1 压力资格最终 Qᴴ 为 7.869231993711079e-9，原 1e-10 门仍失败，nonzero_port_arbitrary_RHS_qualified=false。

沿该方向评估的 native true relative residual 为 0.020167854356936972；这是未接受、未保存的新迭代诊断。原 checkpoint 不变，field_accepted=false、solution_accepted=false、all_diagnostics_passed_claimed=false。

## 6. 资源、清理及所有成本口径

原限制保留：硬 AS 6 GiB、整树 8 GiB、host available 至少 1 GiB、零 swap、600 s、disk 至少 4 GiB、总新输出 128 MiB、MPI1/thread1、单科学子进程。原 128 MiB 诊断余量与额外 32 MiB native-defect 余量保留；被动测量另准入 2,535,744 B scratch，不削减既有余量。

独立终审已核对全部 1,439 个资源采样、2,718 次准入、38 个源码 pin、16 个缓存角色及完整计数，原资源门全部通过且系统/进程零 swap。

数值前 VmSize 为 3,049,799,680 B，命名增量 2,965,539,520 B，6 GiB AS 门后余量 427,111,744 B；数值后 VmSize 快照为 4,089,159,680 B。tree 计入 ELF 后的准入增量为 3,840,887,552 B，预计整树 6,452,427,520 B；此 tree 数值不等于 AS。最终清理前 VmSize 快照为 4,089,311,232 B。

17 个已知所有者清理回调正常返回，MUMPS JOB−2 销毁已观察到，监督器确认无剩余进程。hwloc sysfs 环境警告保留；不声称每个 helper 隐藏的部分 native 句柄都有单独释放收据。RSS 为采样峰值，不代表全过程精确峰值；VmSize 快照也不能代替 AS 峰值。

本次 362.962546363 s；此前两次 fixed 为 339.359574593 s；加前两次 symbolic，trace4 五次实际阶段合计 875.770228062 s。本次数值分解 5.014026389 s 和 symbolic 0.212139317 s 已包含在本次 wall 中，不重复相加。

最终 v71 执行账本记录已知终态阶段累计 21085.225217485116 s，含中断记录的累计下界 28999.2175003281 s；不是精确总墙钟。准备、源码复核和等待未测量，不能记零；辅助只读核验另列；分时内存峰值不相加。

## 7. 本轮止点

本次已完成受限 g=0 的实际 same6656 诊断，仍未解决平台或全部严格一致性问题。下一步仅允许静态检查 trace 空间假设；没有下一轮 outer 或新科学执行准入。

此前失败与成本见同目录 [fixed-control 报告](trace4_interior6_fixed_control_20261014_zh.md)；更早 symbolic 资格见 [symbolic 报告](trace4_interior6_symbolic_20261014_zh.md)。本提交仅两份小报告，不含源码、矩阵、向量、张量、因子或大日志。

## 8. 证据索引

以下是 hp_resume_20261013 中相对证据名、字节和 SHA-256；不表示原始文件已上传。

- `phase4_trace4_interior6_fixed_control_v3_actual_only_source_review.json`（30724 B）：`979fcb0176f022d45505321301703e40d149a28214c3fcafdee4f8d3410c8da3`
- `phase4_trace4_interior6_actual_only_attempt01/summary.json`（1218 B）：`e931ede1c088b8cc615e9c64628014d91a9631b3bdf947bb597a5040a79df955`
- `phase4_trace4_interior6_actual_only_attempt01/result.json`（330641 B）：`860caa25f55557ef2d481208381cc8b88f2930dae8d0464b6338fff73156b3a1`
- `phase4_trace4_interior6_fixed_attempt01_terminal_review.json`（27687 B）：`964e19329423e1afa6f6c4469706ca3a9b8f49aefd18fc756b8e4eaa9126ab23`
- `phase4_trace4_interior6_fixed_attempt02_terminal_review.json`（46750 B）：`18072bd040eb4e7831e66d5ede0197120a915e1ce3125c8b3ec809c29f4f3b2e`
- `phase4_balh_complete_action_oracle_attempt01/paused6656_native_true_residual_result.json`（11282 B）：`a4fa942f242a68c89aef3fe53924536198dcb79ca2bb3d5da772e7c1d7a8be90`
- `phase4_execution_ledger_v71.json`（46268 B）：`274032cf123c60fb09c001d5d185c5c96c75603412f699249852cb4bce3774fa`
- `phase4_trace4_interior6_actual_only_attempt01_terminal_review.json`（53776 B）：`212ce4b58428b38844fbf64e3ae6ddd6db3fddcf346615d84ac866a0032f20da`
