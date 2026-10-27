# Response V14：90 分钟预算已执行；真实 h 自由度取得，P2 后置字段检查失败

按用户明确授权，原唯一未使用 P2R 改为5400秒工作、5580秒含清理上限，取消事先证明1740秒内完成的条件。实际调用一次，在1596.6148925269954秒后因研究入口字段名错误退出，未耗尽时间。已定位并静态修复该错误；没有第二次尝试，没有正式PDE或后续P3/P4/P5。原失败目录及合同保持原字节。

局部 h 加密把选定单元细分；为了让相邻单元的场相容，还必须细分一个材料闭包单元。独立自由度表示施加连续性与周期约束后真正需要求解的未知量数。本次终于取得实际空间代价，但尚未求解新场，因此不能报告加密后的精度收益。

## 身份与执行边界

仓库 `Rookie1234567/MyFEniCS`，分支 `task43_hp_adaptivity`；正式review `37f3376be410657fbaec86b0412086745419c506` 与用户本轮时间授权共同限定范围。运行HEAD为 `187631108208e34940d65c3e70557e11026de31c`，基线 `405e3aff42ac421a4c99315df1ed9b96941ecbe4`。51项源码/快照、38项输入在执行后、修复前逐项hash一致。后来修复字节不追认为此次运行或旧S1的验证对象。

原合同SHA256 `6aadbf82a9c816e1e272b087aa2189435bb0163df1ed1b55a363295a773dadf1`、recovery manifest SHA256 `fd42af62c989e9b8886c1fb1458a7aa904907d2c241da2f88f6888d1d7340734` 未改。[用户授权记录](outcomes/records/v14_p2r_user_budget_authorization.json)与[实际launch](outcomes/records/v14_p2r_sources/snapshots/launch.sh)固定唯一目录和命令。

## 实际结果

| 项目 | 实际值 | 判定边界 |
|---|---:|---|
| seed / 闭包 | global cell 8；forest root 4；必要材料闭包root 34 | 单一requested seed不变；两个root各细分8叶，继承各自父p5/p6 |
| 网格 | 180 root、194叶；p5 35、p6 159；9 hanging patches | 实际空间构造，未装PDE矩阵 |
| 自由度 FE | 116740 = 79950内部 + 36790独立迹 | 严格落在110472与237600之间；比R9增加6268（约5.67%）；仅数值区间成立，不等于P2整体通过 |
| 从属行消除 | 124012 − 1820 hanging − 5452 periodic = 116740 | 已存审计计数相互一致；预测trace+612模态为37402，实际矩阵rows/NNZ未测 |
| 参考空间工作 | 25个cold key全部完成，169个cache hits，currsize25/max128 | 无缓存逐出证据；194个cell-map完成；未改缓存或数学 |
| authority / cell-map | 1504.7938988739625 / 1420.1027609831654 s | 嵌套wall，不相加；cell-map worker CPU差954.742395186 s |
| 整体终态 | WORKER_FAILED；worker/watchdog/launcher = 1/2/2 | FE后置门抛错，成功bundle及P2 continuation不存在 |
| P3 / P4 / P5 | 全部NOT_RUN | h场J/G及每新增自由度收益未取得；不得拼接旧R9指标 |

[原空间审计](outcomes/records/v14_p2r_sources/plan_output/actual_authority_before_fe_gate.json)、[逐条件复核](outcomes/records/v14_p2r_sources/root_space_diagnosis.json)和[25个冷调用摘录](outcomes/records/v14_p2r_sources/authority_profile_extract.json)保留实际值。主控核全部180个root的194叶继承与15个前置谓词：14个成立，唯一拒绝项为错误派生的全局从属编号标志。原件中的true不改成false，也不补成功终态。

## 具体缺陷与已完成最小修复

`round1_candidates._audit_plan`从 `authority.audit["trace_constraints"]`读取不存在的`hanging_or_periodic_slave_rows_globally_numbered`，默认True；真实producer使用`hanging_or_floquet_slave_rows_globally_numbered`并返回False。派生输出因此错误记为True，`_v11_actual_space_gate`拒绝。这是研究入口元数据接线缺陷，不是实际FE超界或hp方法数值失败。

生产入口仅更正该键名，保留缺失时默认True的拒绝行为。成功main fixture此前也使用同一错误键，掩盖了真实producer差异；现更正fixture并增加实际audit字段为False的断言。没有修改数值核心、共享activation、ABI、缓存或watchdog。主控此前静态审查漏掉此键名不一致，不能用旧12/12通过掩盖覆盖缺口。

两文件仅经stdlib AST解析；最终回归pytest **NOT_RUN**。最新review §9.5限制发现新代码问题后仅静态修正，用户又明确本次一次且不自动重试，故不能用剩余时间重启。原producer的完整audit map未单独落盘；正确键及False来自冻结源码追踪，而现场直接保存的是派生true，证据层次分开。

## 旧 A2 保存数组的复算

本次在空间构造前完成并保存raw/modal/q8/q10四阶段，非新A2求解、重新采样、重积分或算子应用。旧端点仍为INCOMPLETE_NOT_QUALIFIED。

| 量 | 本次复算/读取值 | 限值与范围 |
|---|---:|---|
| 独立A6相对残差 | 3.078522812304335e-10 | ≤1e-8 |
| full-active相对残差 | 1.1972486317982494e-11 | ≤1e-8；native零从属carrier加modal Euclidean口径 |
| returned condensed残差 | 3.0440529386035694e-12 | ≤1e-9 |
| normal correction | 2.2945939789534043e-9 → 3.0440529386035694e-12 | 从旧两份b−Ax快照重算；不补造独立normal RHS/solution |
| 612通道最大功率差 | 4.5076775645469525e-11 | ≤1e-7；相对同一旧Y6_1 |
| q8 / q10的G差 | 6.043732933300416e-11 / 6.04373290835214e-11 | ≤1e-5；516096 / 1008000个旧保存点，E/H总场及散射场亦通过相应门 |
| A_volume | 0.6915175267406917 | 旧材料积分值；与Y6_1差4.146905041579885e-11，未重新积分 |

完整通道差、复幅分组、E/H/G、原向量身份及checkpoint hash见[本次原记录](outcomes/records/v14_p2r_sources/plan_output/A2_saved_primary_q_response.json)和[关键实值](outcomes/records/v14_p2r_sources/A2_key_values.json)。这是固定q扰动对旧场的有限观察，不改变旧失败或独立精度结论。

## 主控终态、资源与费用

主控读取最终6份trace共764行，含全部19个getter和退出尾段：mask均[1]，0 setter、0信号事件。逐行程序核对2187条资源记录及PID/PPID/start_ticks，亲读关键原行、完整调用行及栈；没有以代理PASS替代判定。worker与tracer直接受watchdog监督，MPI1、complex128/int64、六线程变量1；实际主机/proc复核四个已知PID/start_ticks全部消失。51个源码与38个输入在静态修改前未变。

| 成本或资源 | 数值 | 口径 |
|---|---:|---|
| P2R whole-watchdog | 1596.6148925269954 s | 含清理，限5580 s；工作停止阈值5400 s |
| shell时间戳区间 | 1606.313743 s | 覆盖启动前后，与watchdog重叠，不相加；也小于5580 s。shell的whole_limit变量仅记载上限，外层主控监控/验收，不冒称其自带第二watchdog |
| 树RSS采样峰 / swap峰 | 2210361344 B / 0 B | 约2.06GiB，低于8GiB；全局swap入出页增量均0；动态reserve/cap全流未触门 |
| 资源采样间隔 | 0.47027260018512607–1.0550098470412195 s | 配置0.25s之外有采样/调度成本；非连续峰；PSS与完整共享JIT cache未测 |
| recovery支持累计 | 2215.2188096446916 s | 旧618.6039171176963加此次1596.6148925269954；5/5次，失败不退款 |
| 更早V11 | 853.8004706790671 s | 历史另列，不与嵌套阶段重复计费 |

静态launch准备0.07047322392463684 s、本地AST 0.136261862 s、证据抽取1.2776839560829103 s；最终JSON/hash/本轮链接/diff校验0.3350628148764372 s，新增已测静态小计1.8194818568840 s；见[静态校验](outcomes/records/v14_p2r_sources/delivery_static_validation.json)。手工阅读、编辑、监控、Git及草稿检查为not_measured，不补造整轮wall。旧V13静态费用仍在旧记录中，不归零或重复计入本次。

本轮局部错误也保留：主控只读monitor一次把END当作含cache_before，KeyError后修正BEGIN/END关联；代理无据宣称cache逐出，经主控读取原cache数据撤回；代理下游草稿误增文件名attempt并引入不必要27KB helper，主控拒绝，未采用或执行；一次读取草稿note路径错误exit1，定位现存原件后补索引。未采用草稿在ignored准备目录保留，真实下游launch/root未改动/创建。暂存后格式检查另发现新派生CSV使用CRLF，已仅转换该派生文件为LF；原launch_context第9行的尾空格按原字节保留，不修剪历史。失败输出及前后hash另存；未计时。这些未计作新driver，也不能当作动态验证。

## 后续需要完成的具体工作

已完成最小键名与fixture修复；下一技术步骤是对修复后的真实main/audit路径作定向验证，并明确批准一个保留旧失败的P2恢复方式及不可变输入绑定，再由合格P2继续原P3→P4→P5。现有一次P2R额度用尽，不自行新增root、重试、后验拼成功bundle或挪用正式槽。实际26.6分钟完成空间的观测可供下一预算参考，但不是未来运行上界，也不倒推旧D1时点已能证明1740秒。

正式新增0，扩展账仍5/8；旧5/6末槽封存，A1历史2次、A2 3次，原A1_q3与R9_H8条件槽未用。空间PARTIAL、选择PARTIAL、精度NOT_PASSED、同精度全过程成本NOT_ESTABLISHED、迭代NOT_RUN/NOT_QUALIFIED。无生产或merge approval；A1_R/A2_R、其他B/C、fresh baseline、成本campaign、迭代、0.7nm、NN/FTT仍锁定。

交付索引：[机器结果](outcomes/records/v14_p2r_budget_extension_results_v1.json)、[主控终态](outcomes/records/v14_p2r_sources/root_closeout.json)、[原件hash索引](outcomes/records/v14_p2r_sources/raw_index.json)、[最终修复静态验证](outcomes/records/v14_p2r_sources/preparation/local_static_fix_validation.json)。
