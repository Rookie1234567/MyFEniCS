# Response V4：交叉网格与四角对照收口

本回执关闭 Review V4 中主线可执行部分：沿用 V3-A 已接受的配对背景归因，不重算背景；按预登记次序完成 Gx560 与 Gz528，并将其与 F3/F5 的保存场组成四角离线比较。结果支持“当前误差对 x 网格更敏感”的方向判断，但显著模式和 Fresnel 散射场的 F3→F5 1% 门仍失败。因此本回执是 **Review V4 范围内完成、带限定的工程结果**，不是原尺寸精度或 workstation readiness 通过，也不是 master 合并请求。

## Review 条目回应

| Review 范围 | 执行与结论 |
|---|---|
| V3-A：配对背景归因 | 复用已发布、同一批保存场的 layered-Fresnel 与 incident-only 配对归因；不重算、不扫描新背景。散射场失败仍按 Fresnel 背景口径保留。 |
| V3-B：x/z 交叉网格 | 完成 Gx560（10×4×14）与 Gz528（6×4×22），比较 G00/F3、G10/Gx、G01/Gz、G11/F5。无第三张网格。 |
| V4：四角物理场 | 对固定公共物理体积比较总/散射 E、H、原始 curl、散射场 `curl(E_scattered)/k0`，以及 x、z 增量和交互量；G1/F5 同量 L2 范数固定为散射误差分母。 |
| V4：模式、功率、接口 | 同一有序 M2 清单比较全部 340 个模式，保留原冻结 11 个显著模式和两条旧失败通道；计算四角 R/T/A 与能量闭合，生成紧凑的跨模块接口包。 |
| 明确停止项 | dot、原尺寸、工作站容量、continuum convergence 均未验证；不改 dot 或 workstation，不改变 solver default，不做额外背景/网格/PDE。 |

## 四个正式离散解

G00/F3、G10/Gx、G01/Gz、G11/F5 的物理模型、材料、入射、周期边界、端口和 340 模式均保持一致。四个官方场的完整 p6 原系统真残差均小于 1e-6；残差只说明各自离散方程被解到规定精度，不说明网格已达到连续解。

| 角点 | x×y×z cells | p6 完整 rows | p4 界面矩阵 rows / NNZ | full-system residual ratio | KSP 秒 | 同时进程树 RSS 峰值 B / swap B |
|---|---:|---:|---:|---:|---:|---:|
| G00 / F3 | 6×4×14 = 336 | 229,680 | 29,332 / 11,293,034 | 7.5936104e-7 | 823.922 | 4,006,539,264 / 0 |
| G10 / Gx560 | 10×4×14 = 560 | 380,040 | 48,660 / 18,782,900 | 9.7334769e-7 | 1,499.305 | 5,255,675,904 / 0 |
| G01 / Gz528 | 6×4×22 = 528 | 359,904 | 45,460 / 17,879,806 | 9.7452954e-7 | 1,522.376 | 5,434,322,944 / 0 |
| G11 / F5 | 10×4×22 = 880 | 595,512 | 75,540 / 29,765,186 | 8.7353225e-7 | 1,797.975 | 7,754,170,368 / 0 |

RSS 是单次 run 同时进程树峰值，swap 为任务进程树峰值；PSS 未采样。p4 rows/NNZ 是准确 p4 界面矩阵的 owned-row `getRow` stored-entry 口径，不是 p6 full rows，也没有计入分解填充。

| 角点 | R_total | T_total | A_balance | A_volume | R00_s / R00_p / R00_total |
|---|---:|---:|---:|---:|---:|
| G00 / F3 | 0.075651901996 | 0.906206870522 | 0.018141227482 | 0.018141268088 | 0.075651427914 / 7.2332e-17 / 0.075651427914 |
| G10 / Gx560 | 0.076124070594 | 0.905769197829 | 0.018106731577 | 0.018106711773 | 0.076123597014 / 1.2442e-16 / 0.076123597014 |
| G01 / Gz528 | 0.075651879550 | 0.906206808259 | 0.018141312192 | 0.018141266669 | 0.075651405471 / 4.0495e-20 / 0.075651405471 |
| G11 / F5 | 0.076124071271 | 0.905769239817 | 0.018106688912 | 0.018106713068 | 0.076123597691 / 3.5618e-17 / 0.076123597691 |

所有角点都满足 `|R_total+T_total+A_volume_total-1|<1e-5` 与 `|A_balance-A_volume|<1e-5`。前者检查端口反射、透射和材料体积吸收之和是否为 1；后者单独核对端口能量平衡吸收与材料体积吸收。最大观测误差约 4.56e-8。相对 G11/F5，G00 和 G01 的 `|ΔR|` 约 4.722e-4、`|ΔT|` 约 4.376e-4，吸收差约 3.46e-5；G10 的四个绝对差均小于 4.27e-8。按 Review 的 1e-3 power gate，四角总 R/T/A 比较通过。

## 方向场与复模式 Gate

四张网格的有限元向量长度和节点位置不同，不能把数组中同一序号误当成同一物理点。volume 对照先取四网格共同的精确坐标分割，再在每个小块重建保存场并积分差值；这样四个解在相同物理位置、相同材料区域上比较，代价是一次离线场恢复与积分。公共区域由 12×4×28 个子单元组成，共 1,344 个；每轴 7 阶张量求积，体积为 24.3966874968 nm³，材料 tag 不匹配数为 0。重复节点仅在完全相同数值时合并，near-distinct 节点没有用容差强行合并。

| 同量 L2 误差，相对 G11/F5 的范数 | x-only G10→G11 | z-only G01→G11 | 交互量相对 G11 |
|---|---:|---:|---:|
| Fresnel 背景下 `E_scattered` | 1.375971e-6 | 2.6118624e-2 | 1.05444e-6 |
| `curl(E_scattered)/k0` | 8.788076e-7 | 2.7503537e-2 | 3.93253e-6 |
| 总 E | 1.976082e-7 | 3.7509897e-3 | 完整记录 |
| 总 H | 1.262070e-7 | 3.9498291e-3 | 完整记录 |
| top `(0,0,s)` 复出射幅值 | 3.234128e-7 | 1.5507592e-2 | 全模式记录 |

前三项是预登记主要判断量；x-only 与 F5 的差小于 z-only 与 F5，假设对三项全部成立。旧 F3→F5 的总场差仍约为 0.375102%（E）和 0.394986%（H），Fresnel 散射 E 与 `curl(E_scattered)/k0` 则分别为 2.611883370447432% 和 2.75037362156526%，超过 1% 门。交互项较小支持当前 x/z 差异主要由 x 增量解释，但不证明 y 或 continuum 收敛。

每个衍射模式用一个复数表示出射波；它同时包含振幅和相位，功率只保留模长信息，因此接近的 R/T 仍可能掩盖模式相位差。有序模式清单含 340 项（80 propagating、210 power-carrying）。`propagating` 是传播模式标志；`power_carrying` 表示有限端口处单位振幅的实能流为正，即 `mode.power_per_unit_amplitude > 0`，它与传播标志不同，故 210 不是传播通道数。四角 manifest 完全一致。选中模式集合仍是从旧 M0 记录冻结的 11 个 key，功率比阈值为 1e-8，入射参考是 top `(0,0,s)` 单位幅值。所有 340 个模式保留原“相对首角幅度”分母，同时补充了 G1 幅值归一化；未重新挑选模式、拟合相位或删除近零模式。

| 比较 | 冻结 11 个模式中最大相对首角复幅值差 | 限值 / 结果 |
|---|---:|---|
| G00→G11 | 1.555605% | 1%，失败 |
| x 增量 G00→G10 | 1.555637% | 1%，失败 |
| z 增量 G00→G01 | 0.010781% | 1%，通过 |
| x-only 与 G1：G10→G11 | 0.010866% | 1%，通过 |
| z-only 与 G1：G01→G11 | 1.555591% | 1%，失败 |

两条旧失败模式保持可见：

| 模式 | G00→G11 相对首角差 | Gx→G1、以 G1 幅值归一化 | Gz→G1、以 G1 幅值归一化 |
|---|---:|---:|---:|
| bottom `(-1,0,s)` | 1.274430% | 2.34773e-5 | 1.260666% |
| top `(0,0,s)` | 1.555605% | 3.23413e-7 | 1.550759% |

两个历史失败通道的复出射振幅以 `(real, imag)` 保留如下；这些值位于物理端口边界，没有相位拟合或平移。

| 模式 | G00/F3 | G10/Gx | G01/Gz | G11/F5 |
|---|---|---|---|---|
| bottom `(-1,0,s)` | `(1.7269438167e-5, 3.1418644829e-6)` | `(1.7469718343e-5, 3.2419174853e-6)` | `(1.7269316419e-5, 3.1414486697e-6)` | `(1.7469723378e-5, 3.2415003732e-6)` |
| top `(0,0,s)` | `(0.2475607417, 0.1198545247)` | `(0.2464738372, 0.1239929216)` | `(0.2475606843, 0.1198545496)` | `(0.2464738784, 0.1239928424)` |

四个角的原始复振幅、各自功率比、两条模式的混合交互量及 340 行全清单在 mode artifact。基于这些门槛，方向性假设获得支持，但 **F3/F5 整体显著模式 1% Gate 未通过**；功率接近不得覆盖该负结果。

## 物理接口与分析身份

紧凑接口包 [`review_v4_four_corner_interface_v1.json`](outcomes/records/review_v4_four_corner_interface_v1.json) SHA256 为 `44a878f85c6e50f5aa5c6b53f58addf1350041c33593cf72ea8cb6b961f29e43`。物理模型固定真空波长 0.7 nm、Si 折射率 `0.9998851703688496 + 4.3236152269189515e-6i`、相对磁导率 1；x/y 周期为 2.592592593/1.296296296 nm，光栅高 6.222222222 nm、宽 0.881481481 nm，缺口为空气并按原解析盒定义。入射为相对 +z 的 θ=89°（掠角 1°）、φ=0°、s 偏振单位幅值。接口包逐项绑定完整输入签名与四个 run manifest/input/physical/vector hashes；保存 x/y/z 精确节点、reference planes、上下端口边界、MPC/Bloch 约束、p6/p4 rows 和局部恢复维数、全 340 模式键与 digest、字段背景及恢复策略、残差和功率、资源采样口径。

复模态使用各自物理端口边界上的 `outgoing_amplitude_at_boundary`，相位约定为 `exp(i*k_z*z_boundary)`；没有相位平移、拟合或重定标。reference planes、实际精确轴节点、polarization basis 的向量和来源函数身份均在接口包中。完整场比较使用 `layered_fresnel` 背景；先从保存的总场直接计算 `curl(E_total)`，减去该背景的解析 curl 得到 `curl(E_scattered)`，再除以 `k0`；因此本文的 scaled curl 定义为 `curl(E_scattered)/k0`，不使用 H 值代替 curl。

| 证据 | 路径 / SHA256 |
|---|---|
| 四角体积分及字段方向结果 | `benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_volume_v1.json`；`5f8004f51cb7d9543730281ace16f296cdc47b0358c66038302bf4f39ac40c17` |
| 全模式与功率结果 | `benchmarks/artifacts/task40extra_0p7nm_engineering/review_v4/four_corner_modes_v1.json`；`e723cf5fd6dc761e3642582af12b921c05453c581903eaf47abac07816d17df2` |
| 跨模块接口包 | `outcomes/records/review_v4_four_corner_interface_v1.json`；`44a878f85c6e50f5aa5c6b53f58addf1350041c33593cf72ea8cb6b961f29e43` |
| 更新后运行索引 | [`outcomes/records/run_index.json`](outcomes/records/run_index.json)；含 Gx/Gz identities、analysis references 及 F3 source 修正记录 |

分析 source SHA：体积方向 worker `9fd0e5aec0019c522741ecc1df41f195831dc752`，全部模式与功率后处理 `55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2`。本轮 launcher 的文件路径启动曾在 import `benchmarks` 时失败；那是工程启动错误，发生在任何 saved run load、场恢复和积分之前。修复提交 `9fd0e5a` 改为 module-based launch，失败事件保留在 [`outcomes/records/run_index.json`](outcomes/records/run_index.json)，不分类为物理或求解负结果。

## 资源、测试与范围边界

volume 离线 worker 用时 864.838 s；单个 subreaper 进程树 RSS 峰值 934,637,568 B、swap 0 B、PSS 未采样，leader exit 0 且 descendants cleared。模式/功率后处理是另一个离线 Python 过程，读取已校验保存记录，不运行 FE/PETSc、场恢复、装配或因子；其独立同时进程树资源没有采样，不能和 volume worker 峰值相加。

定向测试命令 `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_task40_review_v4_volume_runner.py src/test/test_task40_review_v4_directional_cross.py src/test/test_task40_p3_mode_staircase.py` 在代码 source `55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2` 下为 **8 passed in 0.68 s**。项目文档收口另运行 `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_183_development_model_registry_markdown.py src/test/test_29_task_retrospective_contract.py`，**13 passed in 0.03 s**。py_compile、两个 runner `--help`、`git diff --check` 通过。Ruff 不可用（环境无 `ruff` 模块）；没有安装。full repository pytest、MPI4 与 CI 均 `not_run`。

| 未关闭项 | 本回执中的真实状态 |
|---|---|
| dot 分支的新环境真实 FE/MPC 接线、恢复、后端、AUTO 投影 | `HELD / NOT_RUN`；本分支未改 dot；历史 checker `UNKNOWN` |
| 50×25×140 nm 原尺寸模型、32,060 通道 AUTO、完整预算与时间资格 | `NOT_RUN`；当前证据不能证明 2 TB workstation readiness |
| y 方向和 continuum convergence | `NOT_RUN`；只比较固定物理模型下 x/z 两轴交叉节点 |
| 旧 F3 solver source 索引 | 运行身份现由 run_manifest 核正；run_index 保留旧 SHA `63dd...` 与更正值 `a43f...` 及依据 |
| 代码/文档审阅与分支交付 | 本回执和 summary/index/test record 待提交、同执行分支推送并交 review；没有 master 合并 |

执行分支仍为 `task40extra_0p7nm_engineering`。本次 continuation 在 `9fd295624444cf16b6ba393a0a7c3522f0070f73` 开始，V4 离线模式分析绑定 `55feda2c6f5c0e0b9ec4b57a341d209ec8b566d2`；精确最终 HEAD、upstream 和 ahead/behind 在提交/推送回执中报告。没有 rebase、强推、dot/workstation 改动或 master 操作。下一步为 review，不自动启动新的 PDE。
