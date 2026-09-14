# V19 selective merge 边界：待审，不批准master合并

当前进展（原始模型完成后的增量）：U4 第三次运行已独立核验通过，564 步、最终 A6=9.92314718715201e-7，L2/scaled-curl=1.3644783292666524e-8/4.3714257232960455e-9。R/T/A/A_volume=0.3656257909689885/0.012990632321222292/0.6213835767097892/0.6213835745968793；完整物理 Gate、80模式、近场与守恒通过。全过程 RSS峰值2528460800 B，库存1830284886 B，临时396129600 B，zero-swap与清场通过。该场 monotonic 6609.661379 s、保守结算7210.314085 s；本批累计保守7709.181734 s。源码8a2d5cbba6ed834a6d731a30dd3735c8824fa762；28项只读checker/ledger测试通过。U5同配置准确notch已准入，尚未运行。下方两次失败及其当时停止结论属于历史快照，全部费用保留，不再是当前阻断。

用户最新授权：完整地跑个p6h10的模型，看看结果，如果不是数值gate，那么就修正那些bug。以下两场实现失败及费用保留为续跑前快照；原重放额度不再阻断本次有明确 bug 证据的续跑。准确凝聚、原数值/物理/资源 Gate 和 observe_only 均保持，U4 正在继续，U5 仍以 original 完整通过为条件。

| 依赖组 | 内容 | 数值行为、验证与顺序 |
|---|---|---|
| production numerical/core | 本轮不提升任何研究PC为普通默认 | 当前没有完整p6资格；不得因U2通过合入默认 |
| reusable numerical/core | `hcurl_assembly_time_condensation.py`显式选项、`FullspaceSplitVolumeAction.bilinear_form`、新`p4_cell_condensed_inverse.py` | 增加受限轴对齐hex单元凝聚；旧选项默认保留。先审单元数学/所有权/CSR测试与U2六次调用 |
| reusable runner/watchdog | 新V18 worker、薄dispatch、既有outer stack factory、V18 ledger；`physical_balanced_fgmres` observe_only参数和`finish_pc`错误保留 | 不增加算法；后两处计时修复只有小型测试资格，完整original仍缺。依赖core及profile |
| checker/benchmark | `check_p4_cell_condensed_v18.py`、新dat、schema与测试 | 只读重算数组/范数/计数/资源；BLR拒绝、部分p6不冒充完整通过。依赖对应原始schema |
| compact evidence/docs | response_v19、outcomes、compact/decision、run_index增量、progress/registry | 保留旧负结果与全部失败费用，建议可独立审阅/选择性保留；大数据只给hash索引 |
| research-only | V18 exact/BLR profile及所有original/notch入口 | 只显式opt-in。准确p4合格；BLR额外收益不足；完整p6未资格化 |
| do-not-merge | ignored vectors/matrices/factors/timelines、临时脚本、任何无用户授权或无 bug 证据的重放或生产默认切换 | 不提交大型raw，不扩大epsilon/rank/步数，不使用新PC路线 |

顺序为core→profile/runner→checker与测试→compact文档；这是评审依赖顺序，不是merge授权。99项最终相关测试、旧helper串行/MPI2和U2/U3证据支持上述边界。停止后的最终修复源码为`14f0bdf6627c98c41cac0b6f9784e07a415cd56d`，其后无fresh PDE；用户已明确授权继续完整original并修复非数值Gate的bug，费用和失败记录累计保留。
