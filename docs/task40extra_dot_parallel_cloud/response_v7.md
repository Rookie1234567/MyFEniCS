# Response V7：边界平面表示的532模式组件通过

**PASS_COMPONENT_ONLY。** source `a0546264ae1bcc51e2aeedcac33585f4ffc04025` 完成8项小测试和真实532模式、同Gauss、fullMPC的边界组件资格。恢复旧172个空C、174个空D，新空支持均0。没有centered PDE求解或官方R/T/A；p4/p6、原尺寸和2TB/48h仍未资格。

把出射模式振幅的参考位置从全局原点移到实际端口平面，可以避免尚未归一化的小系数在装配截断时被丢掉。本次在截断前直接计算稳定的边界平面相位，并保留原积分规则、全部三维DOF/MPC和有序模式；普通default仍为global_z。它改变了实际存储的算子，不是V6因子内部坐标缩放的重复。

## 数学等价与存储算子变化

| 组件证据 | measured | 可授予的结论 |
|---|---:|---|
| 未截断raw C / D坐标等价 | 4.1297e−14 /4.1300e−14 | 同积分公式、完整模式的坐标变换通过 |
| raw H /每模式FE作用差 | 1.6733e−16 /4.4452e−14 | ≤1e−10组件门 |
| 每模式新stored相对raw完整DOF rank-one损失上界最大 | 1.3678e−13 | 每模式系数范数证书，不是累计全部模式的相对norm上界 |
| 五状态累计raw / centered作用差 | 1.1873e−15 | 采样作用一致 |
| 五状态新stored / raw作用差 | 3.2698e−15 | 采样作用一致 |
| 五状态旧clipped / 新stored作用变化 | 0.03082258966421717 | 明确承认算子改变；不是全算子norm证书 |
| 恢复空C /空D | 172 /174；新空均0 | 全532唯一有序身份及逐模式支撑ledger可审计 |

对象为80cell、p2、λ0.7nm、phi5、manual m±9/n±3的532模式；5个任意fullMPC FE状态含内部DOF。degree19、每quad facet100个Gauss点；4套primary、8套literal oracle的编译规则/节点/权重/实际loaded C绑定。原两阶段cutoff仍为max(1e−30,1e−13×max)。

**旧V6准确解仍是旧已裁剪算子的历史证据，不能作为新centered算子的direct authority。** 需要新centered原A、dense/sparse、恢复和真实三维缺口资格；旧新算子不得要求数值相同，也不能混用旧direct场当新基准。

## recovery、RHS、输出与失败保留

实际production recovery的532×5、完整physical RHS/incident、非零port RHS坐标回环、五状态输出低层组件通过。它们是任意测试场上的组件一致性，不是物理解或官方功率。独立复核确认40项hash、完整有序模式与资源采样；recovery/output通过由冻结源码和完整pytest通过日志支持，未保存逐项残差数组，不补称已独立重算这些数组。

| attempt/source | 实际状态 | whole-tree RSS /监督wall |
|---|---|---|
| 1 /8960b71e… | FAILED_API：缓存Form.code为(None,None)，未完成系数门 | 328318976B /5.8142s |
| 2 /aad8f46a… | FAILED_OUTPUT_COMPONENT_GATE；系数/action早期断言不等于完整通过 | 358445056B /16.9472s |
| 3 /74df81b8… | 同输出失败；partial与controlled-stop packet在断言前保存 | 326467584B /8.5888s |
| 4 /a0546264… small | 8passed、1deselected；pytest1.13s | 325484544B /5.9288s |
| 4 /a0546264… actual532 | 完整test1passed；pytest6.96s | 327430144B /10.3655s |

全部监督记录swap0、后代清场。RSS为采样同时父进程+全部后代，warm JIT/cache；不相加，不是cgroup硬峰。1.5GiB/600s/MPI1/maththreads1门保持。新carrier unique backing为6135040B，是对象库存，不是RSS或目标容量预测。

输出失败来自top(−8,−3,p)的严格reactive零功率在浮点求值出现plane9.3652e−17，而旧signed负舍入被裁成0。修复只对严格lossless、real tangential k、outgoing纯虚非零kz、Maxwell dispersion与transversality成立的模式，要求两种实际场的raw signed功率均落在明确gamma_n机器误差传播界内。原unit_power==0本身不是证书；原1e−10门及amplitude/field可表示性门不变，传播/lossy真实power-underflow负测保留。

## 证据与下一步

- [资格与原始hash](outcomes/records/boundary_component_v7/component_qualification_a054626.json)、[源码身份](outcomes/records/boundary_component_v7/source_receipt_a054626.json)
- [全部532模式ledger](outcomes/records/boundary_component_v7/all532_compact_ledger.json)、[独立复核](outcomes/records/boundary_component_v7/independent_verification.json)、[失败资源](outcomes/records/boundary_component_v7/failure_resources_compact.json)
- [详细组件报告](outcomes/boundary_component_v7.md)

大型raw数组/日志继续留ignored artifacts，完整hash和三次失败记录保留。后续centered p2全原方程/新direct authority尚未运行；p4/p6、multi-rank、完整default回归、目标截断/连续精度、跨机器ABI、restart和原尺寸2TB/48h均不由本组件授予。此组件也不产生任何TB级目标RAM承诺。继续补足主线同一次工作站启动，由用户执行大运行，不推断未发布本机状态。

## 后续候选源码与本次发布边界

发布快照同时含后续centered p2 dense→sparse候选source `2839e7ba2eb91744cd6d6dd0aee519d536f3c237`，状态明确为 **NOT_RUN_PDE_CANDIDATE**。54项定点测试通过、1项真实PDE测试跳过及ABI/compileall检查仅是候选准备，不把a054626组件通过转授给新PDE候选。以[候选差异索引](outcomes/records/boundary_component_v7/centered_candidate_source_inventory.json)逐文件绑定；本次只加文档/证据，不改任何数值源码或启动计算。
