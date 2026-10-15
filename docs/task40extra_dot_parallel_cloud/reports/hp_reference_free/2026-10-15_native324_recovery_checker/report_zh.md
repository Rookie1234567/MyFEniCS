# 324-cell 恢复检查器调查：已证实内部自消盲点，完整解仍未资格化

日期：2026-10-15。模型：18×2×9＝324 cells，z 分层 2/5/2，完整 p6、ordinary p4，BAL_H，FGMRES restart=32、正交化 refine_always。此报告只归档本轮已保存证据；不替代原始失败记录，也不改变任何验收阈值。

## 1. 当前结论

已在当前 324-cell 保存的第 8 步、实际 cell164 和普通对照 cell8 上复现一个具体诊断缺口：旧检查器利用同一套恢复/LU 表示相减，内部残差得到严格零；改用同一离散原始块直接作用，残差非零。这说明旧内部指标会漏掉恢复方程的误差。独立 raw 内部检查器候选已在两个真实 cell 和人为构造的反例中实测，但尚未进入生产全局流程。

但这还没有证明完整 identity 失败或 BAL_H 收敛迟缓的全部原因已找到，更没有证明更换内部检查器就能修复求解。原始 identity 门仍 FAIL，真实 native 残差仍高于 1e-6；没有 accepted field、官方 R/T/A 或空间收敛结论。

## 2. 两段求解：科学结论与成本分别记账

“真实 native 残差”指把恢复后的完整场代回原始离散算子，衡量原方程还有多少未满足；“recovery identity”则比较原始作用和凝聚/恢复表示是否一致。前者是求解质量，后者是两条计算路径的一致性。进程正常退出、资源门通过都不能代替这两个科学判据。

| 阶段（measured） | 监督墙钟时间 / s | 外迭代及保存状态 | 原始科学判据 | 结论 |
|---|---:|---|---|---|
| 首次 native 求解 | 333.752768448001 | 8 步完成，保存完整未资格场 | identity＝2.4309679506887283e-10 > 1e-10；native＝0.04626585819263524 > 1e-6 | 第 8 步由 identity 门停止；不是完成 200 步的收敛试验 |
| 从 x8 开始的诊断续段 | 601.0627218169975（含终止清理） | 本段 67 步完成，第 68 步 PC 在途；耐久 checkpoint 为本段 64 步 | 最近 native＝0.021842359971579305，identity＝2.463975257620764e-10，均未过原门 | 600 s 硬限触发 TIME_LIMIT，SIGTERM；无最终完整场包 |

首段 pure KSP 为 57.066331987 s，solver clock 为 75.06004874999053 s，均与 333.752768448001 s 的整段监督时间不同。独立最终 native 重算为 0.046265858192633735；不能用这点显示位差改变上述结论。

续段重新建立 Krylov 基和因子，使用原 x8 非零初值，并非不间断 200 步 FGMRES。计入先前 8 步后，总完成 75 步，保守预算计费 76 步；最新耐久点累计为 72 步。checkpoint64 不能抹掉已完成的 65–67 步及在途 68 步；32/64 的重复 monitor 不计作新迭代。200 步上限名义剩余 124 步不等于授权自动续跑。

本段第 67 步只有递推残差 0.021785871751169337，不能冒充该步的独立 native 残差。11 条 native identity FAIL 记录（含重复采样）全部保留。残差下降只是诊断观察，未证明最终可收敛，也不能据此断言已形成 200 步平台。

## 3. 保存包复核排除了什么

同一完整场、原 RHS 和 retained checkpoint 的对应 payload 逐字节一致；两份保存的独立 native 残差向量之差范数为 0。identity 绝对差为 3.426276423814599e-10，全在非 slave 行，slave 分量为 0。四项分母保存值为 1.4094288749647617，独立重算为 1.409428874964764，相对差重算为 2.4309679506887184e-10，仍 FAIL。

这支持排除本次保存包混淆，并在观测误差尺度上反对 native 重复作用不稳定的解释；不构成原始算子正确性或跨来源算子资格证明。内部大操作尺度为 1738561.7200576293，不能替换原来的四项 identity 分母以获得“通过”。

## 4. cell164：真实对象上的最小机制验证

凝聚先消去单元内部未知量，再从边界/接口未知量恢复内部场。旧检查把恢复得到的内部向量分别送进同一个 LU 重构作用再相减；若两路恰好使用相同的恢复值，就可能相互抵消，而遗漏原始耦合块的误差。独立原始块检查直接计算 Aii·i + Ait·t（本次内部 RHS 和该 cell 的端口贡献为零），避免以恢复公式检查恢复公式。

cell164 按实际独立 interior 行上保存 identity 差最大者选定，远离上下端口平面。原始/定向张量、映射及 MPC 展开身份门通过，LU/H/F/S 四个身份与原始保存 recipe 一致；保存 Aii/Ait/Ati/Att 哈希不等于四块作用都完成独立检验。本次实际数值比较仅覆盖该 cell 的内部行。

| 同一保存 x8 的 cell164 指标（measured） | 范数 |
|---|---:|
| 旧 binary64 内部残差 | 0 |
| 冻结 Ht 的 wider / grouped 旧公式 | 0 |
| 原始块 binary64 残差 | 2.3234124683004288e-11 |
| 原始块 wider 残差 | 2.2163696344155388e-11 |
| 保存的独立 native 内部残差 | 3.061290494933839e-11 |
| raw wider 与保存 native 的向量差 | 2.058170613669388e-11 |

因此自消盲点已经在当前对象上获得证据，不再只是历史 108/144-cell 的类比。但 raw wider 与 native 仍存在非零差距；尚未说明全部来源。不能将其表述为“纯舍入已证实”或“identity 已修复”。首次 cell164 回放未直接记录 i 与 Ht 的逐字节比较，因此该首次记录本身不足以证明两者身份；随后两单元回归补上了直接逐字节证据，见第 5 节。

平台所谓 longdouble/complex256 实际只有 64 位有效尾数（binary64 为 53 位），不是 113 位四倍精度，更不是精确算术。扩展精度只作用于冻结 binary64 输入的乘加；没有高精度装配或高精度因子分解。

此单元诊断监督 4.277201388991671 s，1 次原始局部张量读取、1 次 fresh binary64 局部因子、0 次 wider 因子、0 次外迭代、0 次全局 A 作用、0 个全局 coarse 因子；没有构建完整 finebank 或 p4 空间，未更新解。共享 trace、全局恢复 identity 和完整收敛原因仍未资格化。

## 5. 源码审计与最小检查器回归

只读审计未发现本条实际路径的 RHS、端口符号或共享行重复累加错误。实际 caller 使用 rhs_is_mpc_dual=True；native 与凝聚共用同一 B/D/H，恢复修正的符号正确。

另有两个离开当前路径的 API 缺陷：raw RHS 模式下 native/Schur 的 MPC 对偶转换不一致；泛型 direct B 接口对重复行的 buffered 累加与 reduced 路径不同。实际 caller 和 carrier 的约束使这两项不触发，不能将其写成本次 324-cell 的致因。

### 独立 raw 内部检查器：两单元候选修复已实测

新的独立 helper 只接收原始 Aii/Ait、内部/trace 向量、RHS 和显式 Bi/alpha，不接收 LU 或 H，因而不会沿旧公式发生相同的自消。它检查原始内部方程的余量；仍同时保留旧指标，未更改总 identity 公式或阈值，生产源码未修改。

| 真实保存 x8 对照（measured） | cell164（最大差单元） | cell8（普通对照） |
|---|---:|---:|
| i 与 binary64 Ht 逐字节一致 | true | true |
| 旧内部残差范数 | 0 | 0 |
| 新 raw checker，binary64 | 2.3234124683004288e-11 | 1.1048928515542827e-11 |
| 新 raw checker，wider | 2.2163696344155388e-11 | 1.0880962252647429e-11 |
| 保存 native 内部残差范数 | 3.061290494933839e-11 | 1.536984445137231e-11 |
| raw wider 与保存 native 的向量差 | 2.058170613669388e-11 | 1.031587430953019e-11 |

cell8 在读取 packet 残差前，按“中间物理层、严格非端口、排除 164 后最小实际 cell 索引”选定，非事后挑选小误差案例。两单元的全部 9 项映射/内部-trace 身份门均通过；四 raw 块 hash 绑定及原始 LU/H/S/F 匹配，实际作用仍仅测内部行。

为检验新 checker 会否漏掉非零项，两真实 cell 另用人为制造的非零内部 RHS 和预定内部扰动做控制。扰动响应与 −Aii·delta 的差分别为 8.374080860394655e-13 / 2.1655963865675918e-13，通过各自操作尺度舍入容差 6.960003470816775e-7 / 3.612476267806251e-7。它们是局部响应回归的绝对容差，不是完整 identity 的 1e-10 相对门；制造 RHS 不替代原 RHS，也没有修改保存的原场。

一个 2×2 人为错误 H、非零 RHS、非零 Bi·alpha 反例中，旧公式仅给 2.7755575615628914e-17，新 checker 给 0.1442220510185597，与显式原始方程 0.14422205101855962 一致。缺失 Bi 拒绝、Bi 不能忽略及扰动检测等 9 项控制均通过。这个反例证明 helper 能看见指定错误，不能冒称真实 PDE 残差或真实端口资格；两个真实 cell 的端口支持均为空，非零 Bi 只在制造例中覆盖。

此回归监督 6.031764024985023 s，21 个资源采样，采样进程树峰值 410787840 B，child exit0 且无残留进程。两个 cell 依次重建，各 1 次局部 binary64 因子（合计 2 次）、0 次全局 coarse 因子、0 次外迭代，最大同时仅保留一份 cell raw/factor bundle；无生产修改、无原场更新。当前可称“局部 checker 候选修复已实测”，不能称生产全局集成、共享 trace、总 identity 或 BAL_H 收敛问题已验收。

独立终审已核对全部 21 行资源采样、10 次实际准入、两次完整映射与原始 payload 身份，以及 i/Ht 直接哈希；结论为局部独立 checker 指定回归通过，全局 identity 与求解验收仍未证明。5 项 pure tests 的通过来自原测试日志，终审未重新执行科学计算。

## 6. 资源与资格边界

| 运行（measured） | 地址空间硬限 | 进程树 RSS 门 | 采样进程树 RSS 峰值 / B | 退出与清理 |
|---|---|---|---:|---|
| 首次求解 | 7 GiB | 8 GiB | 3003396096 | exit0，已验证进程退出；科学 FAIL 保留 |
| 诊断续段 | 7 GiB | 8 GiB | 3004440576 | TIME_LIMIT / exit -15，无残留进程；未证明 Python finalizer、cache RESTORED 或逐 native owner 析构 |
| cell164 回放 | 7 GiB | 8 GiB | 390860800 | exit0，已验证无残留进程 |
| 两单元 checker 回归 | 7 GiB | 8 GiB | 410787840 | exit0，已验证无残留进程；全局资格仍未通过 |

四次均记录 zero swap。RSS 是采样同时进程树口径，不是对象累计大小；未计 allocator-release 或映射驻留回收 credit。首段和续段新 artifact cap 各为 128 MiB，cell164 和两单元 checker 各为 64 MiB。资源通过不授予求解、物理或生产资格。

下一项实质问题是共享 trace 的原始四块作用与 Schur/内部重建之间的差异。应保留独立 native 对照、原始绝对差和 1e-10 相对门，在已完成局部零/非零 interior RHS 与制造端口控制的基础上，补齐真实端口、复 Floquet MPC 共享 trace 以及 trace-only/port-only/mixed 回归，再判断是否具备当前 324-cell 全局复核的资格。不得用 native 残差反推被检查量，也不得改分母、放宽阈值或把未运行项写成通过。

## 7. 证据与发布边界

相邻 [evidence.json](evidence.json) 保存源文件 SHA256、关键标量、成本记账和未资格项。原始证据入口以文件 basename/相对路径标识，重型 payload 仍留云端，不随报告上传。

- native_solver_attempt01_terminal_review.json
- native_solver_attempt01_saved_packet_vector_review.json
- native_diagnostic_attempt01_terminal_review.json
- recovery_identity_readonly_audit_20261015/report_zh.md
- phase4_step8_cell_replay_source_terminal_review.json
- phase4_step8_cell_replay_candidate01/attempt01/{summary,result,selection}.json
- phase4_step8_internal_checker_candidate01/attempt01/{summary,result}.json
- phase4_step8_internal_checker_source_terminal_review.json

本次仅 connector 发布中文报告和小 JSON，范围限 docs/task40extra_dot_parallel_cloud。未发布实现代码、矩阵、因子、完整场、数组或大归档；此次发布不附带额外计算。源码审计基线为 322e62e11a80969b3a35f0cbb08b25c11c539ea6；报告提交的远端 HEAD 与该计算来源身份必须区分。
