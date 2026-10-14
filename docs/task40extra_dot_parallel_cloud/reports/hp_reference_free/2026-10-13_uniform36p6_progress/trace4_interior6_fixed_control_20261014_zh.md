# trace4_interior6_fixed_control_20261014

日期：2026-10-14（UTC）。两次 fixed 诊断均已终态失败并完成独立复核。本报告保留原始失败与完整成本，不将压力资格失败混称为 same6656 实际 PC 结果。

## 1. 已确认的第一次固定诊断结果

同一 native 108 单元、fine p6，粗空间 trace-p4 + 全部 48,600 个 fine-p6 泡函数；场 FE 58,824，Schur 10,304（含原 80 端口）。新 K 的 fresh symbolic 和数值分解成功，H3 setup 完成，但独立完整 native Qᴴ 精度门在第二个任意 RHS 探测失败，因此 same6656 完整 PC 对比未到达。

第一次用时 137.203601282 s，542 个资源采样，采样进程树峰值 3,088,789,504 B。子进程 exit 1；原监督器清理通过，无剩余进程。2,705 次准入及原资源限制全部通过，系统/进程 swap 与换入换出增量为零。

## 2. 失败位置，不能被较小 Schur 残差覆盖

- 第一个纯 interior RHS：独立 full/native Qᴴ 相对残差 2.0075311355985018e-13，端口闭合 4.981899313712429e-13，均通过。
- 第二个 mixed full RHS：原始 RHS 单位归一化，interior 部分范数 0.8149493550626877；独立 full/native Qᴴ 残差 2.3045817425193467e-10，超过未变更的 1e-10 门槛 2.30458 倍。
- 该 mixed 探测的 reduced Schur 残差经过原内部修正，由 1.4198348165838251e-10 降至 5.059937502301175e-13；端口闭合 2.1379993648775107e-16。两者通过不能覆盖 full/native Qᴴ 的失败。
- 第三个非零 80-port RHS 探测、完整 BAL_H eps1/eps2 账目和 same6656 原始入口/实际首 Arnoldi PC 对比未达到。

标量证据表明仅按已很小的 Schur 残差修正不足以满足 recovered full/native 精度门；尚不能从这些标量定位具体舍入误差来源，也不能归因为旧 108 单元 BAL_H 平台的原因。

## 3. 实际完成的工作与成本

fresh MUMPS JOB1 一次、数值分解一次，数值阶段 6.326022231 s，INFOG(1)=0，ICNTL(23) 读回 1,675 MB；同因子线性 solve 三次。H3 setup 做了 20 次 power-matrix 乘法，但没有完整 H3 smoother/完整 BAL_H 调用。CG 和 outer 迭代均为零。

数值前 VmSize 3,049,758,720 B，命名 numeric+future 增量 2,931,985,088 B，6 GiB AS 门后余量 460,707,136 B。数值后 VmSize 快照 4,089,118,720 B，不能作为全过程峰值。预计整树 6,416,665,344 B，属于 tree 口径，不是 AS 数值。

原两次 symbolic 实际耗时合计 173.448107106 s，加本次失败尝试后，三次已完成阶段合计 310.651708388 s。第二次 fixed 尝试 202.155973311 s，两次 fixed 合计 339.359574593 s；连同前两次 symbolic，本 trace4 路线四次实际阶段合计 512.807681699 s，不代表更早项目全部成本；准备、复核和等待未测量，不记零。两次 factor 秒数已包含各次阶段墙钟，不再次相加。分时内存峰值不相加。

更广范围的 v69 执行账本记录：已知终态阶段累计 20,722.26267112211 s；含中断记录的累计下界为 28,636.254953965094 s。这些不是精确总墙钟；另列辅助只读核验未并入科学阶段和，准备/复核/等待亦不能遗漏或记零。

保留 hwloc/UCX sysfs 环境告警与真正的 native Qᴴ 失败 traceback；不能把日志说成无异常。数值因子及已知所有者清理成功、原进程树终态验证通过，不声称每个 helper 隐藏的部分 native 句柄都有单独释放收据。

## 4. fixed_control_v2 的修正规则与不变门槛

冻结命令 SHA-256：a70bd276b35ae71f70e20b1f34c9eb3f1356894482555e485fcdc14acc5388f7。窄范围独立源码复核及 75 项 stdlib 测试通过；这不代表实际数值通过。

对固定原始 (r,g)，用独立 native A6 对恢复后的全场求物理缺陷 d = r − A6u − B Hp⁻¹g，再以同一 fresh factor 调用未变更的 raw(d,0)，累加 field 与 port 解。每次逻辑粗解最多两次完整 RHS 修正、三次缺陷评估；原 raw 内的 Schur 修正保留。

full/native Qᴴ 检查始终使用原始分母 max(‖Qᴴr_original‖,1e-30) 与 1e-10 门槛，不能改用更大的 operation norm 或 correction norm。每次累加后仍按原非零 g 检查 g+Du−Hpα 和原端口尺度；raw(d,0) 不保证主动消除既存端口缺陷，不能用齐次 correction 端口测试冒充通过。

保持矩阵、P 系数、共轭伴随、物理 A6、H3、same6656 原始/单位输入身份、严格比较门和旧 p4 基线标签不变。原诊断余量 128 MiB 保留，额外加 32 MiB scratch（合计 160 MiB），其余 6 GiB AS / 8 GiB tree / host 1 GiB / 零 swap / 600 s / disk 4 GiB / 总输出 128 MiB 均不变。

源码总工作上界为九次逻辑粗解、最多 81 次同因子 solve、postfactor native A6 最多 49 次，独立 volume/DtN 各最多 27 次；这些是上界，不是实际已发生计数。零 outer/CG。

## 5. 第二次实际终态

第二次 fixed 运行已按原门槛失败并结束：202.155973311 s、800 个资源采样、采样树峰值 3,090,669,568 B、child exit 1、监督器确认清理且无剩余进程。独立复核已验证全部 800 个资源采样、2,708 次准入、37 个源码 pin、已知所有者清理与原进程树终态。

- 纯 interior RHS 无需完整缺陷修正即通过。
- mixed full RHS 使用一次完整缺陷修正；wrapper Qᴴ 相对残差由 2.3045817465743055e-10 降到 6.061535615934218e-11，外层独立 arbitrary 核验值为 6.061535632364496e-11，均按原 1e-10 门槛通过。
- 第三个非零原 80-port RHS 在 wrapper 中按固定两次完整缺陷修正执行，Qᴴ 相对残差依次为 3.354523134926728e-8、9.301511207087944e-9、7.869231993711079e-9，最终仍为原门槛的约 78.69 倍，正确停止。
- 该失败 case 的原端口闭合最终为 1.3034403188518079e-15，端口过门不能覆盖 field Qᴴ 失败。第三个 case 的外层 arbitrary 完成核验未到达；same6656 PC、完整 BAL_H 及 outer 仍未到达。

失败 case 的原 Qᴴ 分母固定为 0.9413373512388138；最后绝对 Qᴴ 残差 7.407602001243717e-9，其中 bubble 为 7.3395607807634836e-9，projected trace 为 1.0017060218988391e-9。最后一次 raw Schur 残差已降至 2.304262268997483e-13，仍不能代替完整门。

对应 u 范数 57,138.891042385716；未抵消的 native component operation scale 为 157,688.6104451894；独立 native volume/DtN 范数分别为 36,602.56098023802 / 50,524.90476923584。这些尺度与 bubble 主导的失败提供后续诊断线索，但不能据此断言具体舍入根因，不能改用该 operation scale 稀释原 Qᴴ 门槛。Q 范围外的完整 fine 残差不要求为零。

这是资格压力载荷，不是 same6656 的真实残差：‖field RHS‖≈1、‖g‖=1，却有 ‖BHp⁻¹g‖=70,560.14469571556。固定绝对 Qᴴ 门为 9.413373512388138e-11。bubble 占最后 Qᴴ 误差平方约 98.17%，但 projected-trace 单独也为 1.0017060218988391e-9，已高于绝对门；仅消除 bubble 仍不保证通过。

已存 local LU scaled identity defect 最大 9.814813149023267e-19 只是缩放逆一致性，不是 condition/rcond 估计。逐格 Aii·ui、Ait·ut、Bi·α 与 cond/rcond 未保存，因此当前不能确认具体局部舍入根因。

此次原始 FAIL 保留，不追加第三次修正、不修改阈值、不将源定义的工作上界冒充实际计数。实际 MUMPS JOB1、JOB2 各一次，JOB3 共 11 次，JOB−2 销毁一次；三个逻辑粗解的 solve 分别为 1、4、6 次，完整缺陷修正分别为 0、1、2 次。两次逻辑粗解完成，第三次失败。数值分解阶段 5.436239951 s。

六条 wrapper native trial 加两次完成的独立 arbitrary verifier，按冻结调用路径和事件重构 postfactor native A6 回调共 8 次；独立 volume/DtN 各 6 次。不存在最终 result.json 或最终 aggregate 计数，以上是源码/事件重构，不伪装为最终计数器输出。H3 setup power-matrix 乘法 20 次，H3 smoother application、完整 BAL_H、same6656 full-PC、CG 和 outer 均为零。

A2 数值前 VmSize 3,050,872,832 B，命名增量 2,965,539,520 B，6 GiB AS 余量 426,038,592 B；数值后 VmSize 快照 4,090,232,832 B。tree 计入 ELF 后准入增量 3,840,887,552 B，预计整树 6,452,103,936 B。原限额不变，全部通过且零 swap；三次新增 32 MiB scratch 准入符合源码。两个快照及当次余量不能当作全过程峰值或新运行许可。

13 个已知所有者清理回调均正常返回，数值因子已销毁，原始失败保留且无次生清理异常；仍不声称每个隐藏的部分 native 句柄显式释放。独审 SHA-256：18072bd040eb4e7831e66d5ede0197120a915e1ce3125c8b3ec809c29f4f3b2e。

## 6. 实际 PC 输入范围与发布边界

已核对冻结源码：core_v5 的 apply 调用 solve_full_array(source.array_r)，未传 port_rhs，按默认值 g=0 处理。原 retained 输入中的端口 RHS 由 explicit_lift 先消去，再由 explicit_restrict 按原式恢复，不能把单独 g=1 的资格载荷当作实际 BAL_H 粗调用。

既有 old-p4 same6656 标量记录中，单位 retained 输入范数为 1.000000000000002，lifted expansion 输入范数为 1.0000000000000038；精确 q_port 和 forcing 范数未保存。没有证据可将本次压力资格结论直接转写为真实 same6656 PC 的成败，也不声称旧 p4 已通过相同 g=1 压力测试。

只发布本中文报告及有界 JSON；不上传源码、矩阵、向量、张量、因子或大日志。当前止点是非零原端口压力资格失败，真实 same6656 PC 尚未测。后续仅从已有数据/源码为实际 g=0 的受限诊断做源码准备；没有科学执行准入，不追加修正，也不写成已经通过。两个原始失败均保留；不得宣称 same6656 PC 改善、108 单元收敛或 hp 收敛。

## 7. 证据索引

以下为 hp_resume_20261013 中原始证据的相对名称、字节与 SHA-256；本提交只含报告，不表示这些原始文件已经上传。

- `phase4_trace4_interior6_fixed_attempt01_terminal_review.json`（27687 B）：`964e19329423e1afa6f6c4469706ca3a9b8f49aefd18fc756b8e4eaa9126ab23`
- `phase4_trace4_interior6_fixed_control_v1_source_review.json`（36484 B）：`2c1591d5926254c17a149dd5258d6571788cf966bce08eff4b3b3fb1d81463a2`
- `phase4_trace4_interior6_fixed_control_v1_source_review_execution_timeline.json`（1951 B）：`13ddc38a7418ad6eae5c0b9962eec436b5d613136f8c0ff1416fd7d651d7c754`
- `phase4_trace4_interior6_fixed_control_v2_source_review.json`（27321 B）：`26fb2b6b85ccff7c10a1d45efb1535da81d6450fd93399a2a8c988721f011b1c`
- `phase4_trace4_interior6_candidate/fixed_control_v2/data_source_memory_plan.md`（7438 B）：`1353e65667d9709a93dc71b3793e239606935a430971d62aa8dccf292708492d`
- `phase4_trace4_interior6_candidate/fixed_control_v2/data_source_memory_plan.json`（7536 B）：`b2e7b33eb7d0a6dc0f4e0e80c19a181acce13300012915b79a1fdea24e3a1601`
- `phase4_trace4_interior6_candidate/fixed_control_v2/launch/source_qualification.md`（3691 B）：`013303f012f1ad838fd763b9184c45ed29c8f102cf5f2c3b97f275803f4d561c`
- `phase4_trace4_interior6_candidate/fixed_control_v2/launch/fixed_only.command.json`（163357 B）：`a70bd276b35ae71f70e20b1f34c9eb3f1356894482555e485fcdc14acc5388f7`
- `phase4_trace4_interior6_fixed_attempt02/summary.json`（1184 B）：`8ac2ceaced9a0210d9ac6403df5ddce5f4c388d550355aea812d0ffaeb57dab7`
- `phase4_trace4_interior6_fixed_attempt02/failure.json`（391 B）：`5f59d0c8db65249fc3a15efd46201f4ea6d730d75042c7c6e3af68c0e7b4228f`
- `phase4_trace4_interior6_fixed_attempt02/events.000.jsonl`（1612517 B）：`d5a5cb1ec448f22e329405534765669f6e4e7bbc399bc3d7a2743697ec313256`
- `phase4_execution_ledger_v69.json`（44094 B）：`5475c84eb18d3856f2e4ef47db410bf1e2d82aac7a9af6726569b70949819d64`
- `phase4_trace4_interior6_fixed_attempt02_terminal_review.json`（46750 B）：`18072bd040eb4e7831e66d5ede0197120a915e1ce3125c8b3ec809c29f4f3b2e`
- `phase4_trace4_interior6_candidate/core_v5/trace_bubble_coarse.py`（18188 B）：`e9d4aae6180fcc90e88ed34d36b23feace213983e077ee0e9b885ded4bf3dbbb`
- `phase4_balh_complete_action_oracle_candidate/source/complete_action_oracle.py`（13355 B）：`2e23626a5865cfba90c2e3b196f833637da15de9980f02901ffb5fa164735377`
- `phase4_balh_complete_action_oracle_attempt01/paused6656_native_true_residual_result.json`（11282 B）：`a4fa942f242a68c89aef3fe53924536198dcb79ca2bb3d5da772e7c1d7a8be90`
