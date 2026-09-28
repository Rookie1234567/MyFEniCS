# 原方程、严格返回接口与未运行 oracle

粗逆是求解器中把粗层残差转成修正的一步。原实现提前构建全局 p4 LU，后续反复回代；候选要改成原 A4 上的迭代求解，并把传统/线性/神经方法仅放在这个内层的辅助修正中。方程、边界通道、传递和最终验算保留。

```math
A_4=P^H A_6P,\qquad C=P A_4^{-1}P^H.
```

BAL_H先做粗修正，再对剩余误差做细层平滑，最后抵消平滑对粗层方程的破坏；每个外层PC通常调用两次C。因此既要测去因子的内存收益，也要测每次迭代粗逆增加的作用和验算成本。

## 冻结源调用链与复用边界

| 现有模块 / 接口 | 审计发现 | Task042 决策 |
|---|---|---|
| `physical_balanced_coupling.PhysicalBalancedCoupling` | C→A→H6→A→C反馈，独立PH balance<=1e-8；拥有返回向量并清理 | 保留BAL_H数学；未改该模块 |
| `physical_inexact_balance.InexactBalanceLedger` | 保存两次非精确粗残差差并审核；允许非零粗缺陷 | 首轮不用宽松inexact路线，仍要求每次1e-10 |
| `P4CellCondensedInverse.apply` | 缩减任意内部RHS、因子MatSolve、局部恢复和port state | 原 LU接口保留；新backend不冒充该类型 |
| `P4RefinementLedger.solve` | 类型绑定LU inverse、实际因子计数、累积端口、原A4复算、最多2次准确精化 | 不伪造MatSolve、不绕过ledger；独立新验证器 |
| `RetainedCondensedRuntime.attach_p4_factor/build_bal_h` | 构造MUMPS因子后绑定LU ledger，build_bal_h明确要求factor已完成 | 不把旧profile复制后称候选；F1须在factory之前选择不建global factor的opt-in路径 |
| `apply_original_a4` / `port_closure` | native原物理作用与H*a-D*c独立；旧port_closure合同为zero_port_rhs | 非零port load的真实effective RHS和closure需在F1显式扩展，不能照搬零port回调 |
| `P6CellCondensedAction.reduce_rhs/recover_storage/evaluate_native_residual` | 任意内部/端口载荷、严格slave-zero、完整恢复、native与augmented残差恒等式 | 可复用已存在action/recovery对象；不额外复制private audit CSR |
| `physical_retained_fgmres.run_retained_fgmres` | trace+port RIGHT FGMRES32/max2048/zero start，独立恢复原A6与port/internal/identity | F5保留；本轮没有启动 |

单元凝聚是先精确消去单元内部未知量，再求公共边界和端口，可降低全局空间，但不能先把p6凝聚矩阵投影成p4。纯数组反例得到独立凝聚p4的8，而p6凝聚后投影为4.666667；curl与mass也必须先相加再凝聚。新测试只证明这两个代数禁区，不替代真实传递/FE配对。

## F0 新接口

[coarse_inverse_protocol.py](../../../src/solvers/coarse_inverse_protocol.py) 只定义返回合同，不实现内层FGMRES、B0或FE构造。`CoarseRHS/CoarseState` 持有独立complex128 FE/累计port数组；`InversePlan`声明operator SHA、局部因子和表示容量；backend报告固定RIGHT/restart32/zero-start/最多256步。

| 检查 | 固定规则 | 测试证据 / 限制 |
|---|---|---|
| native原方程 | mandatory quantitative `ResidualWitness`，relative<=1e-10，不能只给PASS字样 | 解析复数toy；F1仍须绑定真实A4和非零port的effective RHS |
| port closure | 独立回调检查累计端口，不接受最后一次增量 | toy错误port被拒绝；真实H/D/port load尚未绑定 |
| 内部恢复 | 第三个独立数值witness必须通过1e-10 | toy内部坐标；实际cell recovery未运行 |
| 零/finite/存储 | 全FE+port零才直接零；complex128、尺寸、finite；slave输入/返回逐位0 | 非零port且FE零仍调用backend；极小幅值不因norm下溢当零 |
| 身份/迭代 | operator SHA一致；plan变更拒绝；设置或步数超限拒绝 | 声明验证，不能证明backend实际执行了FGMRES；F4需要真实计数 |
| 因子/表示 | 仅cell/patch/bottom；patch<=6000、bottom<=2048；factor总载荷<=512MiB；表示<=512MiB | 构建前声明容量，无实际PC；不能作为物理分配证明 |
| 失败 | 抛 `CoarseReturnRejected`，保存 audit/RHS/state；sink错误保留原拒绝 | 没有LU fallback；真实packet持久化适配待F1 |

所有现有数值源未修改，候选没有接线到普通runner。新模块只依赖NumPy；纯数组进程未加载FE库。FE预检虽然导入PETSc等库，但没有Mat/KSP/factor构造。故只能说F0没有构建global p4 LU，不能给尚未存在的部署candidate颁发G-no-factor通过。

## 历史神经接口与 oracle

精确固定参考 SHA `d91652dd2d611d6d6bedd10e677c3f7030c07d4f` 的实际文件/blob/依赖见 [审计JSON](records/neural_reference_audit.json)。通过只读GitHub读取，没有fetch该分支或迁移源码。

| 历史 / 数据身份 | 教训 | 本轮处理 |
|---|---|---|
| PARA001 measured历史 | 单slab ILU+NN 861→854步，整体156.746→452.641s，内存增加 | 不把ILU常驻再附加NN作为默认部署 |
| PARA004 measured历史 | 全16 exact two-step 861→566步；solve更慢、存储更多；one-step失败 | 是局部逆改善的全局信号，不能当所有NN的数学上限 |
| PARA005 measured历史 | model+basis27.824 + private CSR40.458=68.282MiB，超过50.505MiB；全局未集成；非线性无明显线性优势 | 完整容量记账、共享exact audit；R-LIN强制对照 |
| 旧 model接口 | FP64实虚pack、operator/checkpoint SHA和fail-closed可借鉴；存在显式fallback/ILU+NN类 | 只借鉴合同，不迁移fallback或private CSR |
| 旧 capture / teacher | raw-only开关、capture provenance、one-factor/many-RHS/destroy；默认可保存local correction，teacher一次concat全部RHS | F1/F2需raw-only、整轨迹split、<=32流式batch，teacher退出后才训练 |

F2 POD/小最小二乘oracle的目的是先判断有限basis能否表示难误差，避免把表示失败误判为训练不足。R-B0处理未学习全空间，R-LIN与R-NN使用同一basis/数据/FP64和预算。rank仅16/32/64/128、表示<=512MiB，网络一类两hidden、至多两个预登记width、epochs<=300、总有载训练<=2小时。当前均未实现/未运行，未改变参数来获得正结果。

F1继续前需冻结真实axes/tags/MPC/mode/integration/physical SHA、验证非零内部及port RHS、候选构造时实际容量账，并取得同机heavy lock与独立邻任务清场证据。F4统一16未见RHS全部严格通过后才做三次独立计时；仅合格路线才能F5。未来外层与全部物理验算门限保持任务书原值。
