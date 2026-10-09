# Task40extra Review V21：把原尺寸推进重点转到端口存储、真实方向和可执行阶段

## 0. 审阅结论与本轮决定

**接收 V20 已取得的原尺寸几何、有限局部/端口实测和 E2 资源停止证据，审阅结论为 `PASS_WITH_QUALIFICATIONS`。V20 的原尺寸主交付仍是部分完成：方向覆盖只有 17/60，原尺寸完整求解入口尚未贯通，目标规模求解和 2 TB / 48 h 均为 `NOT_QUALIFIED`。V21 的主要工作应直接减少真实目标的端口存储风险，并补齐与生产路径绑定的算子证据。**

这里的“端口”是上下开放边界上表示出射、反射和透射波的 Fourier 模式。模式越多，边界数据和它与有限元场的耦合越大。审阅发现，现有缓存实现会把明确缺省为零的局部端口块展开成稠密数组，其中一个零块按“单元关联模式数的平方”增长。这是可以定位、能够保持原方程不变的结构改进，比继续用小模型的三步迭代推断原尺寸更有价值。[端口实现][S10]

本轮继续已有 p6 reference 数学路线与 `ROW_TILE_BOUNDED_CSR_V17 + ONE_Q_REFACTOR_V19`。不以研发第三个预条件器、重复 B0/E1 完整场或新增 E3/Ny16 为主线。此前 V19 已达到的小模型最低退出条件继续有效；E2 完整场是条件项，不成为原尺寸工作的前置门。[上轮裁决][S1]

| 决定 | V21 要取得的具体增量 |
|---|---|
| 第一优先：原尺寸端口库存与存储 | 按生产语义计数真实 support，报告 `sum_m_c`、`sum_m_c_squared`、原 carrier/direct 数据和独立 backing；取消输入明确为 None 的无用稠密零块 |
| 第二优先：有界生产端口作用 | 从生成阶段开始分批，取得真实目标单面 Bα / Dx 作用、局部恢复和成本的独立对照；为全边界适配留下可执行接口 |
| 第三优先：真实方向资格 | 复用已保存几何与 canonical 局部数据，按实际方向/坐标缺口推进 43 类，优先覆盖参与上述端口测量的真实边界类别 |
| 必要工程修复 | 正常写出资源停止和实际阶段完成回执；修复 conversion 与 symbolic 准入中可定位的生命周期重叠 |
| E2 | 只有实现变化、真实容量和完整剩余时间都支持时，至多一次条件续作；原样重跑没有价值 |
| 原尺寸 heavy / full | 保留本轮 heavy=false 的默认与执行边界；明确代码、路由测试、实际数值资格的区别，形成下一阶段可运行合同 |
| 固定窗口 | 沿 V19 同一 T0/deadline 连续推进，不因为 V21、bug、提交或等待刷新 24 h |

**验收看新增的真实目标证据与代码行为。仅补文档、改变状态标签或再得到一个相近小模型 PASS，不构成 V21 的主要实质进展。** 未完成项按实际范围收口；某个包装或报表错误不能暂停其他不依赖它的库存、局部验证和实现工作。

## 1. 本次审阅的身份与范围

| 项目 | 固定身份 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task40extra_0p7nm_engineering` |
| 远程审阅 base | `1d9936104af1eeb151a5bdba500b40cf9922a226` |
| base 提交时间 | `2026-10-09T21:32:37Z` |
| base 提交说明 | `Task40 V20: close out target stages and E2 resource stop` |
| 上轮 Review V20 提交 | `729b3214452dfb6520b349cb1fe35f9d34d5da7b` |
| 原尺寸组件数值 source | `f88d0606a8c351e7185afd9e839e8c8ddfd9bb81` |
| E2 资源运行 source | `4b004d09b17d07a1f19f4c9d8443e76153e69a4b` |
| V20 最终代码冻结 | `c319719433e99fe652754f2844c5d79669b111cb` |
| canonical 执行目录 | `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering` |

自 Review V20 至本次 base 共 14 个提交、49 个变更文件。本次读取最新 response、四份 compact、run index、summary/test summary、目标交接、两个 canonical 输入及直接相关的几何、局部、端口、凝聚、q 因子、worker、stage runner、service/checker 实现。对四份 compact、response、交接文件、test summary 和两个 canonical 输入的远程原始 UTF-8 内容独立重算 SHA-256，九份均与索引一致；文件级结果列于附录。[最新回应][S2]、[运行索引][S7]

本次审阅没有进入执行机，也没有下载 ignored 目录中的场、CSR、因子或完整事件数组重新求解。下文“实测”指远程提交记录报告并绑定的测量；代码推导、条件库存场景、未知和未运行单列。保存包哈希一致不能替代重新施加原方程，引用执行方 checker 结果也不表示本次又运行了一遍 checker。

本报告只新增 review。后续继续既有 Task40 执行者与主控分工：执行者实现、测试、运行，主控审查、冻结并集中提交/推送；执行者不 commit/push。不新建 Codex 聊天、项目、checkout/worktree，不启用 Codex collaboration subagents 或定时自动化，不 SSH、不切工作站、dot、Task042 或其他项目，不写 master。数值实现进入合适的 `src/`；必要 runner 接线保持薄层，不为顺带整理历史巨型文件扩大本轮范围。[任务边界][S18]

## 2. V20 已经把什么推进了

### 2.1 从纯库存计划推进到真实原尺寸几何

原尺寸输入固定为 50×25×140 nm，真空波长 0.7 nm，既有 Si/air、1° grazing、azimuth 0°、s 偏振和三维缺口；x/y Floquet 周期，z Fourier-DtN 开放边界。当前 Ny=8 配置是资源 pilot，p6 是计划采用的有限元阶数。[目标输入][S16]

| 原尺寸项目 | V20 记录 | 能够支持的结论 |
|---|---:|---|
| 实际几何 cells / axes | 30,464 / 272×8×14 | 原尺寸几何已经实际建立和检查 |
| air / substrate / grating cells | 18,080 / 2,176 / 10,208 | 材料区域在真实目标网格中存在 |
| 目标 / filled-reference 局部类 | 60 / 60；共同类 60，目标独有 0 | 两者类目录相同；不表示材料空间分布相同 |
| x 周期边界面 | 每侧 112 | 坐标配对通过 |
| y 周期边界面 | 每侧 3,808 | 坐标配对通过 |
| z 端口边界面 | 每侧 2,176，共 4,352 | 真实边界规模已经确定 |
| ordered mode keys | 共 32,060；每侧 16,030 | 沿原 manifest，未删物理通道 |
| 全局 p6 space / MPC / q CSR / factor | `NOT_RUN` | 几何成功不能升级为全局构建成功 |

MPC 是把周期边界上相互对应的自由度按 Floquet 相位约束起来的映射。V20 目前取得的是几何层面的配对，尚未完成原尺寸全局 p6 自由度与 MPC 构建。[组件记录][S3]、[几何实现][S11]

几何库存/读回记录中的 0.487844814 s 只按该字段的范围引用，不作为完整 mesh 冷构建耗时。目标和参考拥有相同的 60 类也不代表两套 production cache 已经共享同一 backing；跨 target/reference/twist 的实际复制必须另记。

### 2.2 局部/端口有可信正信号，方向覆盖仍为部分

局部凝聚先消去单元内部自由度，只让边界自由度与端口参加外层求解；场输出时再恢复内部量。p6 此处每个单元有 450 个内部自由度、432 个 trace 自由度，完整局部张量有 882 行。它能减轻外层系统，但 LU、恢复和端口数据仍占内存。[局部实现][S9]、[凝聚实现][S13]

V20 续作复用了 60 份保存的局部类记录，新增两次端口局部 Vii 分解，上下各一次。66.727725178 s 是该续作的 local/port 父区间；它不包含此前取得全部 60 类数据的成本。记录中的“reused LU=60”是历史证据复用计数，不能解释为 60 套可直接供 production 使用的活因子已经恢复驻留。

| 两个新端口局部组件 | bottom | top | 原门限 |
|---|---:|---:|---:|
| 已知解前向相对误差 | 4.3895660157e-14 | 4.4567572490e-14 | 1e-11 |
| 原局部 trace 方程残差 | 6.3697011386e-16 | 5.7354684212e-16 | 1e-10 |
| 局部端口方程残差 | 3.0975794245e-17 | 6.4111106027e-17 | 1e-10 |
| 局部恢复方程残差 | 4.4951203815e-16 | 4.8167618289e-16 | 1e-10 |

续作进程树 RSS 峰为 665,841,664 B，专用 cgroup 峰为 700,948,480 B；任务 swap=0，后代清场；PSS=null/`DISABLED_BY_PROFILE`。这些是合并运行峰值，不是分别测得的上下端口峰值，更不是原尺寸完整解峰值。[组件记录][S3]、[成本记录][S6]

关键限制在于：`_local_class_measurement` 当前仍先在 canonical 单盒上调用 `_local_tensor`，然后比较目标代表单元的有序坐标和 permutation。只有 17/60 同时匹配，剩余 43 类没有获得目标方向资格。应称 `PARTIAL_CANONICAL_LOCAL_COMPONENTS`；不能把 43 类统称为数值失败，也不能在未读每类比较字段前断言它们全是同一种 permutation 差异。[局部实现][S9]

局部/端口顶层 `status=PASS` 目前只反映所选代数检查，内部仍报告方向 PARTIAL。后续资源/算子准入必须检查具体 coverage，不能单凭顶层 PASS 放行目标 full。

### 2.3 32,060、16,030 和批次数需要按实际语义读

端口 helper 遍历完整 ordered table 后按 side 过滤，单侧实际施加的是 16,030 个模式。batch=16 时，每次遍历为 ceil(16030/16)=1,002 批；两个主遍历合计 2,004 批。外层 `target_mode_batch_count` 则由完整表 ceil(32060/16)=2,004 派生。两个数字碰巧相等，含义不同。[局部实现][S9]、[端口积分 helper][S12]

应新增“完整 manifest 数、该侧实际 key 数、每遍批数、遍数、实际调用数、独立校验覆盖数”字段，保留原回执不覆盖。helper 已返回实际该侧计数，可先低成本读回整理。

这次已知状态的 RHS 使用候选 B/D 自身制造，所以很小的局部残差首先支持凝聚/恢复代数自洽。当前独立 full-882-row native B/D 积分对照只覆盖每侧一个 key；V20 调用没有开启已有 `verify_analytic_full_rows=True`。不能把它描述成每侧 16,030 个模式全部已经与独立原定义对照。[端口积分 helper][S12]

### 2.4 E2 已完成四个 q CSR，停在首个 symbolic 前

q 是沿周期 y 方向拆出的相位子问题。CSR 是保存非零矩阵行、列和值的稀疏格式；symbolic 阶段决定因子结构和容量，numeric 阶段才根据矩阵数值建立因子。

E2 的 880 cells、p6、700 modes 均保持冻结身份。[E2 输入][S17]四个 canonical q CSR 与变换表完成后，首个 q 的 symbolic 准入未通过。因此 all-q symbolic、numeric、KSP、完整场、官方 R/T/A 和新旧场比较均为 `NOT_RUN`。[稀疏容量][S4]、[正式结果][S5]

| q | 行数 | 数值非零数 | 实际存储 slots | CSR payload / B |
|---|---:|---:|---:|---:|
| 0 | 44,380 | 24,321,244 | 24,331,316 | 486,803,844 |
| 1 | 44,480 | 24,667,953 | 24,699,794 | 494,173,804 |
| 2 | 44,480 | 24,680,813 | 24,712,876 | 494,435,444 |
| 3 | 44,480 | 24,664,625 | 24,696,626 | 494,110,444 |
| 合计 | — | — | — | 1,969,523,536 |

这次四 q 的内容 hash 为 `NOT_RECORDED`，也没有足够证据证明这些 CSR 已作为可跨进程恢复的持久包保存。可以复用已保存的计数和事件，不可承诺再次运行能够跳过其构建。

候选停止为 `RESOURCE_CONTROLLED_STOP`，worker 为 `WORKER_FAILED`/exit 4，run_case 为 3，required checker 为 `NO_PARTIAL_FOOTER`/exit 2，外层为 `CHECKER_FAILED_RAW_EVIDENCE_RETAINED`。这些分类分别描述资源与包装结果，必须保留。缺 footer 是应修的小工程问题，不抹掉已有资源证据，也不把资源停止变成 PDE 数值失败。[最新回应][S2]

此前 E2 的 campaign 路由、ABI 入口失败以及原尺寸早期组件失败继续保留；本次不要求因这些已识别事件回放完整旧运行。


## 3. 现在最值得做的内存改进：端口零块与真实作用

### 3.1 已找到具体的平方增长零块

“缓存模式”会提前保存端口与内部/trace 的多个矩阵，减少以后每次作用的计算量。当前 `build_p6_cell_condensed_action_from_carrier` 提供局部 Bi、Di、ports，未提供的 Bt、Dt、H 本来具有零的含义；`_normalise_port_terms` 却在 cached 路径中为它们分配完整零数组。[端口实现][S10]

令 c 表示实际生产中一个会实例化的局部端口对象，m_c 为该对象实际关联的模式数。不同 target/reference/twist/sector 集合如果各自实例化，应分别计数；只统计 60 个代表类会漏掉其在全域的重复次数。complex128 每项 16 B：

| 当前 cached 对象 | 每对象形状 | 全部对象 logical payload |
|---|---|---|
| Bi、Di | 450×m_c，m_c×450 | 16×900×Σm_c |
| Bt、Dt，当前 factory 缺省为零 | 432×m_c，m_c×432 | 16×864×Σm_c |
| XiB、Bhat、Dhat，凝聚派生数据 | 450×m_c，432×m_c，m_c×432 | 16×1314×Σm_c |
| Hlocal，当前 factory 缺省为零 | m_c×m_c | 16×Σm_c² |

这里的 Σ 表示对实际实例求和。logical payload 是数组形状要求的逻辑字节数，尚不是操作系统实际驻留内存。尤其 `np.zeros` 可能涉及尚未真正驻留的零页，取消这些数组后 RSS 是否下降、下降多少，必须实测。

E2 compact 的独立 backing 数据可与源码逐项闭合。由 Bi/Di staging 推得 Σm_c=12,160，由 raw local 分项推得 Σm_c²=3,712,000；两者均为代码和记录推导，不冒称本次直接扫描了原始数组。[稀疏容量][S4]

| E2 对象 | logical payload / B |
|---|---:|
| Bi＋Di | 175,104,000 |
| Bt＋Dt 显式零块 | 168,099,840 |
| XiB＋Bhat＋Dhat | 255,651,840 |
| Hlocal 显式零块 | 59,392,000 |
| local carrier 合计 | 658,247,680 |
| direct trace maps | 142,836,480 |
| cell port indices | 48,640 |
| 与 compact 一致的 unique 总量 | 801,132,800 |

**其中输入缺省零块共 227,491,840 B 的逻辑存储，是明确的消除对象；不能据此保证 RSS 必然下降 227.5 MB，或者保证 E2 越过下一门。**

compact 的带 alias 总量为 976,188,160 B，扣掉 unique 为 175,055,360 B，已接近 staging 的 175,104,000 B。因此只删除 staging 字典不能声称再释放一整份 175 MB。一个 alias 的引用消失，底层数组可能仍由其他对象持有。

### 3.2 原尺寸已有危险的条件库存场景，尚缺真实 support

原尺寸有每侧 2,176 个端口面、16,030 个模式。若采用“全部 4,352 个边界 cell 都关联本侧全部 16,030 个模式”的条件场景，则：

```math
\sum_c m_c=4352\times16030=69{,}762{,}560,
\qquad
\sum_c m_c^2=4352\times16030^2=1{,}118{,}293{,}836{,}800.
```

| 同一条件场景 | 十进制 TB |
|---|---:|
| Bi＋Di | 1.004581 |
| Bt＋Dt 零块 | 0.964398 |
| XiB＋Bhat＋Dhat | 1.466688 |
| Hlocal 零块 | 17.892701 |
| 上述 cached local 合计 | 21.328368 |

这张表是明确假设下的库存计算，**不是目标实测、必要下界或“2 TB 不可能”的结论**。真实 m_c 由 side、carrier support、内部/trace 分类、实际映射与各实例关系决定。E2 的 Σm_c 就不能由简单的面数乘模式数代替。

它足以说明为什么下一步需要先改表示并测真实 support。V19 的目标 Ny8 CSR 结构上界 176,839,493,968 B 只属于 CSR，不能当成原尺寸总内存。[上轮容量边界][S1]

目标计数器应在分配这些大矩阵之前工作，复用已保存几何和模式身份，按实际 production 规则报告：

1. side、真实 facet/cell、材料/metric/方向类、target/reference/twist/sector 的实例数与对应关系；
2. 每实例模式数的直方图、Σm_c、Σm_c²，完整 manifest 与侧别活动模式严格区分；
3. Bi/Di、trace direct、原 fullspace carrier、派生块、实际非零端口块及其他原始 component cache 的 entry 数；
4. 独立 backing、共享 backing、阶段存活范围与未能精确计数的项；
5. 计数依据是精确 native support、结构上界还是条件场景，明确全局 MPC 未建时的精确性边界。

不依靠浮点阈值把 tiny Bi/Di 判为零，也不为减少计数删 mode。若某项必须构建全局映射才可精确确定，先给有依据的上界和缺失条件，不为了“补齐表格”在笔记本上分配目标大 carrier。

### 3.3 取消零数组必须保留消元产生的真实耦合

本轮允许取消**原输入明确 None/absent 对应的零 payload**。空块仍需有明确的形状与 dtype 语义；已有非零输入应按所属 layout 的原规则处理或拒绝，不能一律丢弃。

令内部自由度为 i，保留的 trace 与 port 自由度共同为 r。完整凝聚与右端项仍为：

```math
S=A_{rr}-A_{ri}A_{ii}^{-1}A_{ir},
\qquad
g=f_r-A_{ri}A_{ii}^{-1}f_i.
```

即使原始 Bt、Dt、Hlocal 为零，消元也会生成真实的 trace-port、port-trace、port-port 作用。所有这些贡献、非零内部 RHS、端口 RHS 和内部场恢复必须保留。真正的 DtN/direct H、端口归一化、符号和复共轭约定不变，B/D 保持独立的非 Hermitian 定义。[端口实现][S10]、[凝聚实现][S13]

可沿 Hlocal 已有 optional 语义推广到 cached；Bt/Dt 用明确零块表示并适配实际消费者。数值测试应针对改变的数学行为，而非逐行镜像实现：同一真实局部数据上比较旧 cached 与新表示的全作用、凝聚 RHS、非零内部/trace/port 输入及恢复；正例与原本应拒绝的非零块行为均覆盖。

如果操作次序或存储格式改变导致矩阵 hash 改变，应登记新 hash 并完成受影响的等价检查。只有实际 identity 相同才继承旧矩阵级证书；不把 B0 的 hash-bound 资格移植到目标，也不因纯包装或文件名修复默认重跑全部历史 PDE。

### 3.4 真正有界的端口作用必须从生成端开始

有界端口作用的意思是：一次只生成一个受控模式批次和有限 facet 的 B/D 数据，立即完成 Bα 或 Dx 累加，然后释放或复用该批次工作区。Bα 将模式系数转成场方程中的耦合，Dx 将场投影到模式方程。收益是避免同时保存所有模式的完整矩阵；代价是增加重算，必须测量。

现有 `port_coupling_mode="streamed"` 只省去部分 XiB/Bhat/Dhat 等派生数组，仍保留 Bi/Di/Bt/Dt、原 fullspace carrier 和 direct maps；`RESEARCH_PORT_LAYOUT` 当前还要求 cached。只翻这个开关不能声称生产路径已经有界。[端口实现][S10]

`fullspace_dtn_action.py` 的当前构建过程有 component cache、staging functional 和 retained functional；其 `construction_numeric_inventory` 可直接扩展用于真实 owner 账。已有 `bounded_direct_term_build` 也尚未在相关 target/twist 调用接入，而且该 helper 接收的 carrier 本身已经构建完成，不能单独解决前端全量驻留。[fullspace carrier][S14]

V21 优先实现一个能被现有 production 操作调用的单面适配器，完成以下闭环：

- 按 side、mode batch、facet 生成；未生成全量 carrier，不积攒全部批次；
- 保留实际有序 modes、全部 882 个原生行、450/432 分区、traction、Bloch/origin、phase gauge、左右耦合及 normalization；
- Bα、Dx、凝聚 RHS 和局部恢复都可与独立 native/解析定义对照；
- 记录生成/tabulation、Bα、Dx、local solve、校验各自耗时与共同父区间，记录当前峰值和最大活批次数；
- 下游仍需生成的真实 Schur/CSR/端口耦合如实计入对象账；前端有界不自动取消下游的真实平方项。

本轮如果只完成真实单面接口和验证，就明确报告其覆盖与生产接入点，继续形成全边界命令/接口合同；不得把单面内存下降写成完整 solver 峰值已下降。

时间方面，V20 两个单面 helper 分别约 32.8713 s、32.9040 s，其中包含验证和局部分解。把其均值机械乘 4,352 得到约 39.76 h，只能作为“逐面照搬验证流程代价很高”的条件示例，不能作为生产一次作用的预测。生产路径应按真实 metric/方向合法共享 tabulation，并独立推导 B/D 的 Fourier 平移相位；验证工作不应在每次预条件器作用中重复执行。跨面/跨方向复用必须有原定义对照支持。

### 3.5 单类 34.26 MB 不是每个真实 cell 的必要持久成本

V20 的 34,260,316 B 是局部组件检查时完整 882² 张量、四个分块副本、LU/pivots、solved Vit、Schur、验证向量/索引等同时存在的逻辑 payload。组件逐类保存和释放，不能乘 30,464 cells，也不能直接当成 production 每类持久库存。[局部实现][S9]

按当前凝聚代码，LU/pivots、recovery、rhs-trace projection、Schur 这些主要持久项合计 12,448,584 B/类。一个 cache 集合的 60 类为 746,915,040 B，再加实际共享的 450² float64 identity 为 1,620,000 B，合计 748,535,040 B，约 0.749 GB。[凝聚实现][S13]

这是代码推导的主要持久项，不含构建临时张量、每 cell maps、ports、多个独立 target/reference/sector 集合或 native 后端。尚未实现的跨集合共享不能提前抵扣。这个拆分有助于把优化精力放到真实大项，而不是把组件验证用的所有数组重复乘到全域。

## 4. E2 的 149.5 MB 缺口：有根据的小修复，条件续作

### 4.1 Gate 算术与停止结论均成立

| E2 首个 symbolic 准入项 | B |
|---|---:|
| 当前 process-tree RSS | 10,079,617,024 |
| 请求 PETSc matrix payload | 486,803,844 |
| conversion workspace | 486,803,844 |
| pending inverse reserve | 315,109,440 |
| selected future co-resident phase | 219,340,224 |
| symbolic guard | 1,947,215,376 |
| numeric reserve，此门尚未进入 numeric | 0 |
| 固定 workspace headroom | 134,217,728 |
| 投影合计 | 13,669,107,480 |
| 当次动态 launch cap | 13,519,601,664 |
| 超出 | 149,505,816 |

两个内存不等式均未通过。全 attempt 实测 RSS 峰 10,929,668,096 B、cgroup 峰 11,908,415,488 B，不能用来否定下一阶段的 future admission；尚未开始的 symbolic/numeric/KSP 仍需空间。task tree/cgroup swap=0；WSL 全局 swap 变化不能直接归因给本任务。[稀疏容量][S4]、[成本记录][S6]

### 4.2 把 conversion 与 symbolic 分成两个真实存活阶段准入

源码 `_symbolic_preflight_one_q` 当前在创建 PETSc 输入前同时计入 matrix、conversion workspace 与 symbolic guard；`_create_slot` 的 indptr/indices/values 转换副本在 finally 中删除，然后外层才调用 factor.symbolic。由此有一个可验证的生命周期改进机会。[q 因子后端][S15]

允许进行以下最小改动：

1. 创建前按转换阶段的真实分配、必要对象、原 future reserve 和 headroom 做完整准入；
2. 创建并装配 PETSc 输入，完成转换临时引用释放；
3. 记录实际 matrix/backing/native owner 状态，重新采样 RSS/cgroup；
4. 按原 symbolic guard、原未来储备、原 cap 和 headroom 再做两个内存不等式检查；
5. 通过第二门才进入 symbolic；若 backing 被保留、allocator 不归还或 owner 销毁失败，真实 RSS/owner 必须反映，不能假定释放。

已经包含于当前 RSS 的输入矩阵不应再作为“未来新增”重复加入；仍真正存活或未来才需生成的对象必须保留。对应 numeric 重建如有相同生命周期，作一致的最小处理，不扩大成后端重写。

在转换临时量无需与 symbolic guard 共存、无额外残留的**条件筛算**中，旧投影减少 486,803,844 B 后为 13,182,303,636 B，相对旧 cap 余 337,298,028 B。它不是新实测，也不保证 numeric 或完整场能够完成。不得据此降低 guard、提高 cap、关闭 swap 监督或取消未来恢复空间。

定向 fixture 应覆盖正常释放、PETSc/backing 仍保留、native owner 清理失败和第二门拒绝后的完整清场。优先从现有记录/小对象验证阶段算术与生命周期，不为这项修复单独重放 B0/E1。

### 4.3 不做收益不足或缺乏依据的抵扣

四 q 的存储零 slots 共 105,977，按 complex128 值和 int32 列索引计算，全部删除只减少 2,119,540 B 逻辑 payload，远小于 149.5 MB，还会改变 CSR identity。它不应成为 V21 主要优化。

pending inverse 也没有证据可直接当成重复计数去掉。staging alias 已经在 unique 账中去重。优先完成明确的零块表示和阶段存活修复，以实际 RSS/cgroup 验证效果，不靠修改记账字段制造可行性。

### 4.4 E2 旧受控停止路径已耗约 1.73 h，重跑需完整预算

E2 user-service 不重叠父区间合计为 monotonic 5,608.418476 s、UTC 6,232.118781 s、保守预算 6,232.119266 s。watchdog 是其子区间，不再相加；两个时钟相差约 623.700307 s，原因为 UNKNOWN。该成本覆盖必要 activation/ABI、run_case 和 checker，到首个 symbolic 前的受控停止为止，不是完整求解时间，也不能自动证明冷缓存状态。[成本记录][S6]

再次 E2 必须同时具备：已冻结的真实实现变化、完整 numerical gates、实际两阶段容量准入，以及用旧受控停止路径约 6,232 s 作规划参考、另为尚未知的 symbolic/numeric/startup/KSP/recovery/output/checker 和收口留出的保守预算。旧路径已含旧 checker/退出，不能当成精确纯装配时间再机械相加；仅“剩余时间大于旧停止路径”不够。

本轮默认优先完成原尺寸端口工作。若条件不成立，E2 标为 `NOT_RERUN_RESOURCE_OR_TIME` 并说明具体原因；已有 E2 资源停止继续有效。若条件成立，至多一次同配置续作，不改变 700 modes、几何、p、容差或物理设置。保存 CSR/场是否可恢复以真实数组、hash、ABI 和身份为准；不存在持久包时重建成本全部入账。


## 5. 把组件验证接到真实目标方向

### 5.1 先拆分 43 类缺口，再验证和应用实际变换

直接复用已保存目标几何、cell 类和 canonical 张量，先列出每类“坐标顺序是否匹配、permutation 是否匹配、材料/宽度/Jacobian 是否匹配”。43 类是尚未资格化的集合，不要求无差别再建 60 个盒子和 60 次全新 LU。

允许用有界 native patch 或已证明合法的基变换取得原尺寸代表类资格。patch 要保存父网格 cell/facet/顶点到 patch 的映射、真实有序坐标、材料、metric 与方向。若重编号改变 Basix/DOLFINx 方向码，必须验证并应用实际 primal/dual 变换；不能直接复制或改写 `cell_info`，再把 mismatch 字段设成 true。

变换的覆盖包含体张量、B/D、RHS、凝聚、恢复与功配对关系。canonical 保存块只能作为可复用数据输入；其目标方向资格由新的独立 native 证据确定。优先补有界端口适配器实际使用的 top/bottom 类，再按有界代表类继续，其余类及时 checkpoint。最终 60/60 才可写该代表类覆盖完整；部分完成报告实际 k/60、最坏误差、未完成原因。

这些代表类检查仍不等于全局原尺寸 p6/MPC 或所有 q 映射完成。类缓存的合法重复利用与全局映射正确性分别验收。

### 5.2 充分利用现成解析检查，补全该侧模式的独立见证

已有 `stream_boundary_correction` 的 `verify_analytic_full_rows=True` 路径使用独立 Legendre/指数积分矩，按频率缓存并逐 key 比较全部原生 B/D 行，限值为 1e-10。V21 应让新生产适配器的实际输出也接受此类独立检查，并绑定到真实 facet 坐标/方向约定。[端口积分 helper][S12]

验收目标为每侧 16,030 个活动模式 × 882 个原生行，完整有序表仍为 32,060。保存实际检查次数、最大归一化误差、最坏 key/row、side、模式/方向身份、解析参数、batch 上界和流式 digest。只检查首个 key 或用候选 B/D 自造 RHS 不替代这项独立性。

如果本窗只能完成部分 key/类别，按真实覆盖保存 `PARTIAL`，剩余项下一阶段接续；不以少量 key 的通过授予全模式资格，也不要求为报表重复积分已由同身份完整检查的数据。解析检查用于资格验证；生产每次 Bα/Dx 不重复整套高精度验证。

保持原局部方程 1e-10、已知态 forward 1e-11、直接 trace carrier 1e-14 等适用门限。已有同因子、最多三次残差修正沿原合同使用，矩阵与解保持 complex128；V15 的有界不精确 q solve 1e-8 不取代局部 forward 门。保存 V17 已关闭的 S2 证据，不无改动重跑它。[上轮合同][S1]

### 5.3 数值读回与身份检查分开报告

保存的 60 类 canonical 包已有局部张量/Schur/恢复读回检查；新 port 包目前的 `_readback_component_packet` 主要核验 hash、key、shape、dtype，service partial checker 则核验文件、身份与阶段。不能合称“独立全目标端口数值 checker PASS”。[局部实现][S9]、[service checker][S20]

V21 最小补充是：从保存的有界原始数组独立重算适用的局部方程、恢复残差和汇总统计；对逐 key 流式解析验证保留实际 coverage、误差和输入/源码 digest，并明确哪些原始行没有全量持久化。checker 不重新实现完整 solver，不以读 JSON 的 PASS 布尔值代替核算。新数值检查失败时保留原值与门限，不回写旧回执。

## 6. 阶段入口需要的有限修复

### 6.1 已有 worker 路由，成功阶段与 checker 还未接齐

当前 target 的 `build_and_symbolic`、`one_q_numeric` 已有真实 worker 调用；heavy=false 时在 preflight 受控停止，符合本机范围。可是在实际 worker 成功后，结果写在 `summary["v20_stage_result"]`/candidate summary 中，没有统一生成 service 要求的 `v20_partial_result.json`。[stage runner][S19]、[worker][S21]

同时，service 的 `STAGE_PREFIXES` 对这两个阶段仍只期望 `["preflight"]`，并硬要求 heavy=false。它能检查“未获 heavy 授权时的拒绝”，不能检查未来真正完成的 symbolic 或 q0 numeric。当前 E2 因资源停止缺 footer 而再次走成 checker failure，暴露同一收口缺口。[service checker][S20]

target 的 full 还在 stage runner 中被无条件受控拒绝，service 的目标阶段集合也没有 full。因此当前交接不能写成“只改一个 heavy 标志就能算原尺寸完整场”。[目标交接][S8]这项状态必须在 V21 如实修正，不掩盖已有部分路由的价值。

### 6.2 用实际到达阶段生成统一回执

新增或统一一份结果 schema，语义至少分为以下四类，名称可与现有公共 schema 协调：

| 实际状态 | 回执必须表达 |
|---|---|
| `AUTH_NOT_GRANTED` | 仅 preflight；未启动目标 heavy |
| `RESOURCE_CONTROLLED_STOP` | 停前真正完成的阶段、实际 gate 输入/上限/差额、后代及 native owner 清场 |
| `STAGE_COMPLETED` | 请求阶段真实完成，q coverage/数值门/身份齐全；仍 official=false |
| `STAGE_FAILED` | 具体身份、数值、资源监督或清理失败；保留异常和原始证据 |

`attempted_stages` 与 `completed_stages` 分开。发生 local_component 失败不能仅因进入函数就把它写成 completed；cleanup 不完整不能输出合格的受控停止。

partial checker 按实际授权与 outcome 检查，不用“heavy 必须 false”代替真正阶段验收。至少覆盖：

- run/source/input/physical/mesh/mode/ABI 身份和实际 artifact hash；
- 真实 all-q CSR/symbolic coverage、先 symbolic 后 numeric 的次序；
- q0 numeric 仅选择 q0、实际 numeric build 次数、原 fresh-factor probe 1e-10，以及生产折叠 physical RHS 的 1e-8 门；
- 槽位、PETSc matrix/factor、probe Vec 和进程树清场；
- `official_result=false`、尚未运行项、真实父时钟与费用。

q0 的独立 physical RHS 不能用随机 probe 替代；首个 q 通过也不能升级成全部 q 数值已资格。[单 q numeric 合同][S22]

先利用现有 E2 raw evidence 写一份新的只读重算/解释回执，验证四 q 完成、首个 symbolic 前停止和 Gate 算术；保留历史 worker/checker 退出码与 `NO_PARTIAL_FOOTER`，不为它补写仿佛当时已经存在的 footer。再用轻量成功/拒绝/失败 fixture 检查新 schema，不需要为了 footer 修复再跑一遍 E2。

### 6.3 未来 first-full 必须是可达流程

本轮可以完善受保护的 full 路由设计、实现和轻量合同测试，但不启动未授权的目标 heavy。交接明确哪些只完成代码、哪些已做路由测试、哪些已实际运行。

未来首个原尺寸 full 的依赖按运行时点分开：

| 时点 | 必要条件 |
|---|---|
| 启动前 | 合法执行授权，冻结物理/网格/modes/source/ABI，实际机器内存与剩余时间准入 |
| 同次构建后、KSP 前 | 真实 primal/dual/Floquet mapping，全部 q CSR/symbolic、实际 factor/probe/startup、原生算子和恢复见证；允许本次 run 生成证据 |
| 求解/输出后 | 完整原 A6、恢复、官方物理量、独立 checker、真实内存/零 swap/全过程时间验收 |

不得要求先有目标原 A6 PASS、目标 R/T/A PASS 或 `target_solver_qualified=true` 才允许第一场 full；这些属于运行后结果。正常迭代尚未达到终态残差时，按原迭代和资源条件继续，不当成已终态失败。

Ny8/Nz14/32,060-mode 的精度仍未资格化，不妨碍将来获准后用它做原尺寸求解与资源 pilot；但它不能自动代表最终准确器件解。最终精度资格与 first-full 运行权分别处理。

## 7. 怎样从这里推进到 0.7 nm / 2 TB / 48 h

### 7.1 当前少迭代的收益与代价仍要分开

已完成的小模型说明当前参考预条件器可以工作。V19 E1 仍是目前新路线最新完整增长场：外层 3 步，原 A6 为 1.40358436565e-8，但 workflow 为 6,584.210970 s、RSS 为 12,093,280,256 B；旧 p4 历史 E1 为 4,580.375191 s、10,650,341,376 B。新路线历史比较仍约慢 43.75%、RSS 高 13.55%，两者 source 和精度背景不同，不是严格的因果性能实验。[上轮分析][S1]

one-q 已有减少 B0 同时峰值的证据，同时引入重复 symbolic/numeric/probe 成本。因此进一步推进必须同时看构建、因子生命周期、端口与恢复的总成本，不能仅盯迭代数。V20 没有新完整 E2，未改变这个判断。

### 7.2 2 TB 要按真实存活阶段和独立 backing 核算

最终十进制物理内存上限为 2,000,000,000,000 B。目标机器的 OS/其他进程/监督余量必须留出，task swap=0。未来准入还要满足当时真正的可用 RAM/cgroup 限制，不能把本机约 13.52 GB cap 或输入中的 16 GiB 当成普适常量。

```math
M_{\mathrm{task,peak}}+M_{\mathrm{OS/others,reserved}}
\le 2{,}000{,}000{,}000{,}000\ \mathrm{B}.
```

每阶段列清 mesh/global maps、局部缓存、原/派生端口、全部 q CSR、单 q PETSc 与 symbolic/numeric、变换表、Krylov/startup/work vectors、JIT、恢复和输出。逻辑模型按同时存活的 unique backing 加原生/临时对象取阶段最大值；不能把所有历史峰值相加，也不能把已经包含于实测 RSS 的逻辑数组再次加入同一时点投影。

真实目标 support、production 全边界作用、q 填充/因子峰值仍是未知项。V21 先用端口结构修正和有界适配减少最大风险，随后才有依据决定原尺寸 build/symbolic 和一个 q numeric 的下一阶段。某个 q 本身过大时，轮换单槽无法解决其容量；应由实际 target symbolic/numeric 决定后续结构选择。

### 7.3 48 h 必须覆盖必要的完整单场路径

48 h = 172,800 s。单场必须计入必要 activation/prepare/JIT、几何/局部/端口/q 构建、全部实际 symbolic/numeric/probe、startup、KSP、恢复、输出及 checker。不得把必要预热或缓存构建移到表外，也不能把嵌套子时钟重复加到父区间。

下一阶段应以真实生产调用计数估算：

```math
T_{\mathrm{single\ field}}
=T_{\mathrm{prepare/build}}
+T_{\mathrm{factor/startup}}
+T_{\mathrm{KSP\ including\ repeated\ PC}}
+T_{\mathrm{recovery/output/check}}.
```

端口作用必须分开报告首次生成与后续复用时间；one-q 必须记录实际 cache miss、numeric/probe 次数和每次完整成本。V19 的 223.134378 s 只是 28 次 numeric factor build 的部分累计，不能当成整套反复分解成本。B0/E1 的 4 次 startup＋3 次 PC 也不能预先套给原尺寸。

有了目标组件实测后，给“明确可计数部分、尚未知部分、保守场景、阻止下一阶段的具体项”。只有目标全路径实际完成后才授予 48 h；当前不能给出有证据保证的完成日期。

### 7.4 小模型退出、首次原尺寸场、最终准确目标是三个层次

| 层次 | 当前状态 / 下一步 |
|---|---|
| 小模型数学路线与基本生命周期可用 | V19 已达到最低退出条件，继续复用 |
| 原尺寸真实组件与有界生产端口可用 | V20 部分完成；V21 以库存、存储、方向/独立作用验证推进 |
| 原尺寸完整候选场可运行 | 还需目标实际 mapping/all-q/因子与资源证据、可达 full 路由和合法机器准入 |
| 最终准确原尺寸解满足 2 TB / 48 h | 还需原 A6/官方物理/完整 checker、真实资源时间和原尺寸 h/p/模式精度资格 |

原尺寸资源 pilot 的网格并未证明足够准确；最终输出和误差目标沿[任务书][S24]与后续已冻结合同。最终还要检查主要 E/H、scaled-curl、散射量、显著衍射级、吸收及 h/p/模式截断变化。小代数残差说明方程解得好，不说明当前离散已经准确逼近连续问题。精度研究 campaign 与一场计算的时钟分别记，单场必要准备不能遗漏。

## 8. V21 执行顺序、固定窗口与验收

### 8.1 本轮接续同一窗口，不新增 24 h

| 字段 | 固定值 |
|---|---|
| window path | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_w19_wsl/campaign_window_v19.json` |
| T0 | `2026-10-09T01:45:00.727771902Z` |
| deadline | `2026-10-10T01:45:00.727771902Z` |
| 新加坡/北京时间 deadline | 2026-10-10 09:45:00.727771902 |
| closeout reserve | 600 s |
| window SHA-256 | `b1591b7cf03b79aaf0820d352e636bdb79a6800bb19489eba92375cb73cbe6b0` |

V20 只读 snapshot 的 15,879.143056 s 是当时余额，不能当成收到 V21 时余额。审阅时钟 **2026-10-09T23:17:24Z**，由固定 deadline 减该 UTC、再减 600 s 得到的数值预算上界仅 **8256.728 s（约 2.294 h）**。这不是实际账本余额，保守 ledger 可能给出更少额度；接收时必须沿既有 campaign API 重新读回。[窗口与成本][S6]、[运行索引][S7]

review、等待、修复、提交均不重置 T0/deadline；旧失败、unknown 和费用不清零。若接收时已过截止，只做必要收口与现有结果交接，本报告不自动另开下一窗口。

### 8.2 在窗口内连续完成可独立验收的工作

1. **核对并接续。** 主控/执行者核对新 review、现有 worktree/source/input/ABI 与窗口。先读保存结果，定位缺口；不为了重新取得 PASS 复做已完成的无改动阶段。
2. **优先落地端口实质改进。** 取消输入明确缺省的稠密零块，完成目标对象计数，运行同输入的作用/RHS/恢复对照；尽早形成可冻结、可复核的代码与 compact。
3. **接入有界真实单面作用。** 把生成、消费、释放贯通到现有生产操作接口；同时完成所用真实边界方向与独立模式/原生行验证。随后在余额内扩展方向/模式覆盖，逐批保存证据。
4. **并入必要收口修复。** footer/schema/checker 和两阶段准入用最小 fixture 关闭；不让外层状态误分类阻断独立的目标组件工作。
5. **条件选择 E2。** 只有第 4 节的真实容量和完整剩余预算成立才继续一次，否则明确不重跑，将资源留给上述目标工作。
6. **及时交接。** 在固定收口余量前停止新增耗时工作，保存覆盖、实际成本、尚存对象与未完成项，由主控审查提交/推送。

以上是依赖顺序，允许独立的轻量实现/读回交错推进，同时仍只运行一个 heavy。普通 schema、路径、EOF、回执或计数 bug 先局部修复并 targeted rerun；不因此换环境、重装、重跑全仓库测试或重放完整 PDE。真实 ABI、身份、数值、内存、swap 或 cleanup 门失败，停止依赖该门的计算并保留证据；继续不依赖它的工作，不降低门限。

这是有限的存储/生命周期和适配改动，不要求在剩余窗口内重写整个求解器。优先级最高的是可验证零块消除、真实目标对象账和有界生产单面作用；全 60 类、全模式独立覆盖按同窗能力完成，未完成部分明确 PARTIAL。不能用“所有附属任务尚未齐备”阻止已经可安全验证的真实增量。

### 8.3 V21 必须交付的可审阅结果

| 分项 | 可接受的证据 |
|---|---|
| `TARGET_PORT_INVENTORY` | 实际实例范围、support 计数/上界、Σm_c/Σm_c²、direct/carrier/派生块、unique/alias 与阶段 owner |
| `ZERO_BLOCK_STORAGE` | 原输入 None 的语义保持，作用/RHS/恢复对照；逻辑节省与实测 RSS/cgroup 分开 |
| `BOUNDED_PORT_ACTION` | 从生成端起有界，真实目标单面接入、调用/批次/内存/分阶段时间与独立 native/解析对照；部分则写范围 |
| `NATIVE_CLASS_COVERAGE` | 实际 k/60，坐标/材料/metric/方向身份、最大误差、未关闭类别 |
| `MODE_OPERATOR_COVERAGE` | 每侧实际已核 key/882 rows 数、最大误差和最坏项，避免 full-table 与 side-active 混淆 |
| `STAGE_RECEIPT_AND_ROUTE` | 受控停止、完成、失败可核算，原失败不覆盖；full 路由的代码/测试/实测资格分列 |
| `E2` | 新实际 outcome 或明确不重跑原因；不能沿旧 field 名称暗称已求解 |
| `TARGET_FINAL_QUALIFICATION` | 仍 false，直到真正满足原尺寸精度、原方程、资源和完整时间条件 |

更新 `response_v21.md`、outcomes/summary、test summary、run index 与精简 V21 records；按仓库规则同步发展/模型总账，保留所有 V20 原记录和失败分类。相同事实使用单一 evidence index，避免再复制多套不一致 schema。

轻量记录至少含 source/input/physical/mesh/mode/ABI SHA、实际命令、run ID、runtime、归一化/门限/最大误差、覆盖数、parent/child clock、swap、峰值口径、raw artifact path/hash 与清场。新测试优先覆盖数学改动和实际失败路径；文档/metadata 修复只作相关检查。

E2 compact 中 `saved_old_130_mode_comparison` 当前为 NOT_RUN，是不适合 E2 700-mode 身份的字段名。未来记录改为明确 full-700-mode 比较字段，保留旧字段历史，不以 130-mode 子集代替 Review V20 已冻结的 E2 同离散全场/模式比较。

本报告不给 master merge approval，不授予目标重型计算或工作站运行权。当前授权范围中的局部实现、测试、有界原尺寸测量和条件 E2 按本报告连续推进，无需逐阶段等待下一次 review。

## 9. 文档核验与证据身份

本次没有执行 PDE、pytest、MPI 或性能测试；V20 执行方的测试范围另见[测试摘要][S23]。审阅工作包括源代码与记录交叉核对、Gate/owner 算术复算、九份关键远程 UTF-8 文件的 SHA-256 检查，以及本报告 Markdown fence、表格列数、引用与回读身份检查。GitHub 页面视觉渲染检查受当前会话能力限制，不冒称已完成；执行方收口时沿文档合同检查实际 rendered view，格式问题局部修正，不回放数值计算。

下列是本次重新计算并核对的文件 SHA-256；它们与 Git blob SHA 是不同身份，不能互换。

| 已核验文件 | SHA-256 |
|---|---|
| review_v20_component_closure.json | `bf607b2de0ad80b7170c0c85996d55c0ad02bd5d964d19067bd3c8d300d1962d` |
| review_v20_cost_and_readiness.json | `acd0c3ecb6a3cf2a3acb0b0c33fd53f8969e6b4380f855a9352525c0b13a11c8` |
| review_v20_formal_results.json | `03c936c4824185a1e97c1971d9ce432163bdae443d5cd8f261d950c2075f3b99` |
| review_v20_sparse_capacity.json | `197bd9cdfd6ea32e7c131333ca378b0f865bf61b6937211ea03168786be3cd23` |
| response_v20.md | `f12b7bd8df5ad9b4d3952822910f0ae66e921b07a088a776e67d1cc50bfbf455` |
| target_stage_handoff_v20.md | `24a89874504ed518fadbdca86ceda81cae97873d99eef5ec8c8fad58113f3a8a` |
| test_summary.md | `7c0ee49b9f8f057676f0a7fe2efeec7fa2eaebd8b532d1e1d12aec334229d375` |
| target_original_ny8_resource_pilot_v20.dat | `f6726d005713b586f1bccfbf6904dd64f3f1f31dd3b069607b55e9b430d294c7` |
| nonseparable_e2_p6_reference_v20.dat | `a693197de34410202d28f7ab0077904bda46685d1ac87b6667f383c92468d621` |

以下来源均固定到本次审阅 base；历史数值以其各自明确的 source/run 身份为准。Git 中的路径/hash 证明已提交的记录身份，执行机 raw artifacts 仍需后续执行方在实际读回时核验。


### 来源导航

| 来源 | 内容 |
|---|---|
| [S1][S1] | Review V20 与继承的数值门 |
| [S2][S2] | V20 response |
| [S3][S3] | 组件覆盖及数值记录 |
| [S4][S4] | CSR、owner 和资源停止 |
| [S5][S5] | 正式结果及未运行项 |
| [S6][S6] | 成本、窗口与准备程度 |
| [S7][S7] | 统一 evidence index |
| [S8][S8] | 原尺寸阶段交接 |
| [S9][S9] | 局部/端口组件实现 |
| [S10][S10] | 局部端口表示与作用 |
| [S11][S11] | 原尺寸几何和类定义 |
| [S12][S12] | 独立端口积分和流式 helper |
| [S13][S13] | 装配时凝聚与缓存 |
| [S14][S14] | 原 fullspace carrier 构建 |
| [S15][S15] | 单 q 因子和准入生命周期 |
| [S16][S16] | 原尺寸 canonical 输入 |
| [S17][S17] | E2 canonical 输入 |
| [S18][S18] | 本任务执行边界 |
| [S19][S19] | 目标阶段 runner |
| [S20][S20] | service 与 partial checker |
| [S21][S21] | 生产 worker 接线 |
| [S22][S22] | q0 numeric / physical RHS 检查 |
| [S23][S23] | V20 测试摘要 |
| [S24][S24] | 原任务目标和数值合同 |

[S1]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/review_report_v20.md
[S2]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/response_v20.md
[S3]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/outcomes/records/review_v20_component_closure.json
[S4]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/outcomes/records/review_v20_sparse_capacity.json
[S5]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/outcomes/records/review_v20_formal_results.json
[S6]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/outcomes/records/review_v20_cost_and_readiness.json
[S7]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[S8]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/outcomes/target_stage_handoff_v20.md
[S9]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/solvers/task40_v20_local_components.py
[S10]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/solvers/p6_cell_condensed_action.py
[S11]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/geometry/task40_v20_geometry.py
[S12]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/solvers/task40_w1_local_probe.py
[S13]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/solvers/hcurl_assembly_time_condensation.py
[S14]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/solvers/fullspace_dtn_action.py
[S15]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/solvers/task40_v10_p6_mumps.py
[S16]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/input/task40extra_0p7nm_engineering/target_original_ny8_resource_pilot_v20.dat
[S17]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/input/task40extra_0p7nm_engineering/nonseparable_e2_p6_reference_v20.dat
[S18]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/AGENTS.md
[S19]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/runners/task40_v20_stage_runner.py
[S20]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/scripts/task40_v20_service_workflow.py
[S21]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/runners/task40_v10_worker.py
[S22]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/src/solvers/task40_v20_numeric_stage.py
[S23]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[S24]: https://github.com/Rookie1234567/MyFEniCS/blob/1d9936104af1eeb151a5bdba500b40cf9922a226/docs/task40extra_0p7nm_engineering/task.md
