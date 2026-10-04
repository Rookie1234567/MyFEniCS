# W1接入V25：固定q60真正贯通消费者，真实数值前置尚未闭合

W1检查把边界上的三维有限元场投影到完整出射模式，再把边界反馈与单元内部量的准确恢复接起来。它检验接口和离散算子的可靠性，不是原尺寸全局散射求解。本轮把主线已存数学组件接到canonical工作树，避免worker/checker读不同目录或在局部暗用旧积分阶次；尚无新的数学、性能或神经收益。

## 实现及实际资格

| 消费者 / 范围 | 本轮改动 | 实际资格 |
| --- | --- | --- |
| manifest/ledger/source | 显式dat→同一个binding；核原字节/hash、完整key顺序、原ledger字段、complex布局和正原H；未知字段/输出越界拒绝 | pure损坏fixture通过；原件尚未收到 |
| 主线数学 | 19文件/365726B的真实本地导入闭包；Git对象只读缓存，不复刻算法或clone | manifest已从冻结Git blob生成；native启动前拒绝，未物化缓存或运行 |
| q60面矩/作用 | 原FacetPolynomial及DirectionalBoundaryAction显式q60；原原点、法向、Piola、原H、projection/adjoint/modal_rhs均有调用 | mock确认参数贯通；实际全key资格UNKNOWN |
| 独立面参照 | 复用已资格化的Fourier–Legendre区间矩及既有Decimal80/110固定64点参照，不共享候选Gauss节点 | 参照在本批原件跨度上未运行，不借V23局部门授予全32060资格 |
| p4/p6局部恢复 | 原完整300/882列、108/450内部量，64模式一批；q60进入B/D、非零内部/trace/port载荷和原直接见证 | derived维数，非本批测量；四项全部未运行 |
| 保存checker | 从原数组重算覆盖、B/D/作用/原分母、原内部及端口方程；独立进程，不调用全局factor/solve | 实际raw未生成；仅保存roundtrip/损坏和门限fixture |
| 本轮全局或NN | 无W0重跑、旧q30重造、W2、全局Maxwell/Gram或网络训练 | 新调用数均0 |

代码入口是[接收说明](../../../benchmarks/cases/w1_receiver/README.md)。数学来源`c354afa449fb80cfb5012e7d2ff66a3e3e64e088`与本轮接口/检查来源`357748671d1e8106027c0ee680cfdedb874837ec`分开绑定。普通默认入口不改；只有`w1_receiver_schema`明确选择本研究路径。公开launcher仍调用`run_case.py`，FE activation与pure入口在同一阶段的明确shell内选择，不混合ABI或顶层import Torch。

## 准入与停止顺序

先有实际p4/p6 Basix方向、非单位两周期缝和角点一次MPC展开轻控制；再接收36,244,923B原manifest及一个配套ledger。之后唯一q60对全部32060物理模式作独立面矩、原H及真实作用对照；只有保存checker完整通过才允许p4/p6上下四个局部原方程及恢复。候选真实不准时保留全量负值，不扫描q/p或替换分母。

| 本轮实测 / not_run | 数据 | 结论 |
| --- | --- | --- |
| 最后轻fixture | 49/49；29新增W1＋20既有接收安全回归；Ruff、compileall和公开validate-only通过 | 接线/保存/时间合同资格，非数值PASS |
| 合格轻监督 | 2.832654745s；树峰111972352B；hard2147483648B、自身swap0、全部子树退出 | 采样同时树口径，不称整批连续kernel cap |
| 原生control | 一次launcher在CPU准入处拒绝，tmux/worker/raw均未创建 | NOT_RUN_RESOURCE_WINDOW_UNAVAILABLE；不是数学失败或OOM |
| 外部原件 | 18个声明路径命中0；三处checkpoint路径命中0，建议目录未创建 | NOT_RUN_INPUT_UNAVAILABLE；不重建AUTO或旧q30 |
| P1/P2全部依赖 | 新全模式测量0、局部case0、local/global factor0、solve0、场0 | 保留UNKNOWN和未运行项，关闭本次数值链 |

初始27测试虽通过，包装误用了默认12GB cap，实测67682304B；保留该流程缺口。随后修正监督目录契约、格式和单核观察器补偿调用，49fixture通过后曾有Ruff变量命名失败；最后正确2GiB监督复验通过。一次轻CPU拒绝后只有一个实际新窗口成功准入，正式control再次拒绝便不再尝试。修复/拒绝/未保留的精确单段费用均在连续总窗或UNKNOWN中保留，不把准备费用删成0。[修复](records/repair_log_v25.json)、[资源](records/resource_costs_v25.json)。

## 原数组与后续接收的边界

主线保存raw的104成员/38026664B/SHAa475bba1…应优先接收；本机没有原件，未用其发布JSON冒充本地重算。旧最坏top,-67,-34,s的q30/q60差5.7059093327和原H组件差4.1493038268保留；旧p4 q30恢复通过和p6计时异常未运行也保留。两积分不一致不能裁决q60是否准确。

居中坐标到ledger绝对坐标的平移和端口相位需成对变换；原H取原整周期及参考面。新接口对这个关系有fixture，实际原件上的归一化、材料和物理RHS仍不合格。局部人为非零负载保证恢复测试有意义，不能称真实照明场；有限缝/角点更不能等同完整全域MPC。

FEINN主求解器暂停、NO_VERIFIED_NN_INCREMENT、D0成本否决/D1未运行以及M3600中期较好/Mfinal最终退化不变。原50×25×140nm/Si17/120nm/λ.7完整3D FE，decimal2e12B整机、ownswap/OOC0和172800s完整流程原门仍未达成。只交本支最小接入包，不复制主线AUTO/W1全体网格、owner/传统PC或dot后端存储，不合并master。

所有大数组、日志、环境与后续只读source cache留ignored；本批没有生成新场或局部raw。历史证据逐字保留，新导航不覆盖旧结果。[完整包与源码hash](records/integration_packet_v25.json)、[输入](records/input_receipt_v25.json)、[运行](records/run_index_v25.json)、[Gate](records/gate_decisions_v25.json)、[选择性依赖组](records/selective_merge_manifest_v25.json)。本批结束停止，未来原件到位仍需新的授权窗口及真实资格，不自动后台启动。
