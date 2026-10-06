# Task041 Response V11：Review V9 H0/H1进行中记录

**状态：进行中。** H0的旧场读数、证据绑定、短波长缺口盘点和最小接线审查已完成。H1 fixed-H6反馈门的serial受控坏输出节点及MPI2五selector组已通过；public single-dat接线和W 5 nm真实场仍未运行，H2–H4也未完成。Review V9的0.7 nm/2 TB/48 h目标仍未达。

| Review V9 H0要求 | 处理 | 证据/边界 |
|---|---|---|
| 按共同边界给出5 nm非重叠阶段wall | 从两场 `consumer/markers.jsonl` 取`stage`/`wall_seconds`并计算相邻差值；monitor独占时间为unknown | [V9 H0 outcome](outcomes/hybrid_0p7nm_2tb_48h_v9.md) §逐段wall；[machine record](outcomes/records/task041_v9_h0_readonly.json) |
| 汇总1920 response与side审计全量工作 | 收入cost/modal/outer每侧行数、Q/P/PH/A6/H6调用、内部KSP迭代、P4回代和精化；指出modal 976条/侧中16条为样本/重复而960条才是formal | 两个1980行原始audit hash绑定在record；selected `operation_seconds`按phase/side保存per-RHS rank-max sums与缺失覆盖数，不累计为阶段墙钟 |
| 解释A6局部指标和完整consumer时间 | 并列局部融合/两RHS信号、outer完整阶段、P4计数差和两场 `performance_not_isolated` | 不把全流程差归到A6、P4或环境；outer PC计时按包含关系解读 |
| 13.5 nm anchor与接线链 | 记录Invocation `c0ef9dd4e7b2410182543d6c18a5e178` 的已存fixed-H6结果；说明public单`.dat`入口到factory路径、5 nm `5e-13` P4 target保留方式 | 不重跑数学未变anchor；P4精化与modal repeat/linearity是两个不同门 |
| H1 fixed-H6反馈门组件 | fixed-H6分支以8次固定反馈作用检查复数重复/线性及近零绝对误差；serial单参数1 passed，MPI2五selector每rank 8 passed | 只资格化组件门、受控错误共识和清理fixture；未证明public单`.dat`路由或真实5 nm FE |
| H3材料、通道与容量只读审计 | 记录已存在PEP/TOAR、2 nm的ncv/mpd未知、0.7来源线索、air-only keys与derived容量缺口 | 未下载全表、未生成W 0.7输入、未运行QEP或PDE |

## 主要结论

1. 最新完整5 nm场通过数值/物理门，但public-to-finalizer wall为`202124.563261555 s`（56.146 h），大于48 h目标。与9月28日的同类consumer时间相差约`+6.76%`，但两场source不同且均`performance_not_isolated`，只能作描述。
2. 两场内部KSP迭代合计同为30296；10月3日P4 backsolve与refinement各多8686次。数据证明计数工作有变化，不证明其单独导致wall差。
3. 最新13.5 nm Si fixed-H6场是已完成研究锚点，可复用其数学不变部分；它不是W 5 nm、2 nm或0.7 nm性能证明，也没有每一个outer内层的独立终检数值。
4. 2 nm已有TOAR实现与producer数据；不是待迁移算法。0.7 nm缺正式钨材料封套、完整W外部keys和合格的h/M阶梯，2 TB与48 h都没有实测资格。
5. 下一阶段沿既有`run_case.py`→launcher→public supervisor→candidate worker→exact-side→factory路径接入默认关闭的fixed-H6研究opt-in，并让有界复数repeat/linearity门只替换该fixed-H6研究分支预付的side sample repeat；保持原outer方程、注册P4 target、恢复和最终物理门。受保护资源文件只允许保留原dirty内容并叠加独立最小hunk。

## 接线审查边界

建议使用现有`python scripts/run_case.py <one-case.dat>`和Task041 public supervisor/candidate consumer命令链，不引入第二runner，也不把flag塞入新`.dat`身份字段。未来实现需要以同一命令/manifest实际透传opt-in，worker不接受只有wrapper局部修改的隐式开关。13.5 Si仍要求`target=None`；5 nm W必须继续绑定registered cell-condensed正式case、`5e-13`侧区P4 refinement target和最多两次同factor correction。模态fixed-H6 repeat/linearity是另一个PC门，二者不能互相替代。

如果systemd service config也要验证flag与public argv一致，`src/runners/task041_service.py`包含受保护的Node0内存Gate工作区；以后只能叠加窄hunk并完整保留原五个dirty文件身份，不能用整文件替换或将该工作混入阶段提交。输入校验文件也有受保护Node0/2 nm改动；当前建议不新建`.dat`字段，因而不需要动它。

H0只读阶段没有执行测试、ABI、MPI、QEP、FE或checker。fixed-H6反馈门的production实现保持在source SHA `64ef9439ee2d527049877edfa88ce8e848e4370600f1a8b9ee41d4684709dea3`；本次H1测试阶段只改test350故障注入fixture，没有再改数值core。运行fresh serial/MPI2 ABI及下列定向测试，没有运行QEP、FE或public consumer。serial与MPI2父wall已按独立attempt各记一次V5，ABI/static/rank-local时间不计。

## H1 fixed-H6反馈门组件验证（非真实FE）

| attempt | 范围与结果 | parent `CLOCK_MONOTONIC` wall | 证据 |
|---|---|---:|---|
| Serial | `test_side_balh_fixed_h6_feedback_gate_rejects_invalid_outputs_and_cleans_up[nonfinite]`，1 passed；在原apply完成后仅污染最后rank输出，清理后完成真实allgather | 5.001762014115229 s | [serial stdout](../../results/task041_v9_fixed_h6_feedback_nonfinite_serial_20261006T032822Z/serial_pytest.stdout.log)、[attempt](../../results/task041_v9_fixed_h6_feedback_nonfinite_serial_20261006T032822Z/serial_pytest_attempt.json)、[compact](../../results/task041_v9_fixed_h6_feedback_nonfinite_serial_20261006T032822Z/serial_test_compact.json) |
| MPI2 | 五个selector、四种坏输出/重复/非线性故障参数；两个rank各8 passed，无warning；最后rank的非有限输出使全rank一致拒绝，随后collective可继续 | 5.001988966949284 s | [MPI2 stdout](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/mpi2_pytest.stdout.log)、[attempt](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/mpi2_pytest_attempt.json)、[compact](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/mpi2_test_compact.json) |

两次源码身份均为core `64ef9439ee2d527049877edfa88ce8e848e4370600f1a8b9ee41d4684709dea3`、test350 `941606bba844cdeabad3c44bedfe86c2578df7370690621c0a6611bbc32482a6`。setup门8次`S_H`、每侧H6 8次apply/16次矩阵乘、8次C动作与既有GMRES 9次solver作用加1次末检预算分列；这不是正式求解成本或性能结果。五条受保护dirty路径未变。V5 ledger由122条增至124条，SHA `60ee77b84661f91944ceffb22e9ab544178d607403f20696b5ffcd875f32fe67`；本轮仅增加两条pytest parent wall合计10.003750981064513 s。[唯一追加receipt](../../results/task041_v9_fixed_h6_feedback_mpi2_20261006T033051Z/v5_ledger_append_receipt.json)。

此阶段未接入`scripts/run_case.py`，也未运行W 5 nm。因此下一步仍需补齐public single-dat开关与service命令绑定，随后在注册W/5 nm/p6h4/M480/MPI8 case上按Review V9做一次真实consumer；保留`5e-13` P4 target和原五项真实残差、恢复及物理门。
