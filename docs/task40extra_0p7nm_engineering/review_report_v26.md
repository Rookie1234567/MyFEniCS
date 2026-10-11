# Task40extra Review V26：复用完整原尺寸体积证据，完成 reference q 消费与成本实测

## 0. 审阅结论与本轮决定

**V25 已取得实质进展：原尺寸真实 target 的全部 30,464 个单元完成了体积作用、右端凝聚和内部恢复，保存数据的独立回读通过。完整 reference q 的生成数据也已落盘，但消费者的原生对照和完整 CSR 尚未形成合格结果。V26 应从这些已有完整数据继续，主交付是完整 q 消费者、全行结构和条件 CSR，并在资源允许时继续测一个完整 q 的分解生命周期。** 不再安排新预条件器、小模型迭代比赛或新增有限 panel 作为主线。[R1]、[R2]、[R6]

这里的“体积作用”是计算给定场在全部材料单元中产生的方程响应；“凝聚”是先在各单元内消去内部未知量，仅把接口未知量交给外层计算，最后再恢复内部场。q 则是规则参考问题经周期变换得到的一个分块。参考问题用于帮助真实非分离问题迭代；其单个 q 验证成功，不代表真实问题已经求解。

| 审阅对象 | V26 判定 | 后续行动 |
|---|---|---|
| 全原尺寸 target volume、凝聚 RHS、全域内部恢复 | 接受保存数据恢复后的完整诊断 PASS | 沿用；不因 q 路由或收据修改重新生成这批数据 |
| V25 q0/q4 的完整生成数据 | 接受 producer 已落盘的事实，consumer 尚未资格化 | 保持旧文件只读，直接接 saved-stream 恢复 |
| PETSc 输出所有权修复 | 源码修复方向成立，定向测试通过；真实 native 复验未运行 | 本轮补实际调用；不把单测当数值终点 |
| 完整 q0 行计数、CSR、factor | 全行结构/CSR 未完成，factor 未运行 | 同包顺序推进；满足准入时自动继续一个 q 的生命周期 |
| 2 TB / 48 h | 仍未证明可达，也没有被此次 SEGV 否定 | 用完整 q 的实测替代样本外推；显式计入重复分解 |
| 普通 bug | 在同一固定窗口修复后继续 | 不为变量名、selector、序列化或回读再停一轮聊天 |
| 最终原尺寸准确场、official R/T/A、合并 | not_qualified / do_not_merge | 保持最终物理、精度与资源验收要求 |

**本轮最少应交出“完整 q 消费者通过 + 完整全行结构与真实资源条件”。** 如果数值 CSR 或 factor 被真实 RAM、索引宽度、磁盘或时间门挡住，保存已经完成的完整对象和具体缺口；如果门允许，就继续完成，不能把“修好了 SEGV、11 tests passed”写成这一整轮的终点。

## 1. 冻结身份、证据范围与终极目标

| 项目 | 冻结值 |
|---|---|
| 仓库 / 唯一执行分支 | Rookie1234567/MyFEniCS / task40extra_0p7nm_engineering |
| 本次审阅结果 HEAD | d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7 |
| HEAD 提交时间 | 2026-10-11T06:32:40Z |
| HEAD 说明 | Record V25 complete target volume and saved reference q failure evidence |
| 前一份 Review V25 提交 | 4a524251339e00ad481b29af61df4f4625ed2581 |
| Review V25 之后的差异 | 10 commits，29 files |
| 完整体积科学数据 source | 144134e4ccc70bf55cf7bc9a0c14835baad8bbea |
| 完整体积保存数据恢复 source | 11f6207ff866da30559e943a8eb4352089acb1b0 |
| 最新 q0/q4 producer source | 9d0f4dbfc730dd620b709d048e33e9da6c77520c |
| 已提交 Vec 所有权修复 source | ed83343df52f7c46df52d9daf4e4a3a28c8cdb5b |

终极目标继续固定为：**50×25×140 nm 原尺寸、0.7 nm 波长、真实非分离 Si/air 三维模型、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN，在 2,000,000,000,000 B 整机物理内存内、task swap=0，单场必要准备/JIT/构建/求解/恢复/输出/checker 合计不超过 172,800 s。** 当前 Nx=272、Ny=8、Nz=14、p=6、32,060 模式是原尺寸资源与算子 pilot，最终离散精度尚未资格化。[R16]、[R17]

本次审阅读取远程 response、两个 V25 compact、run index、汇总和相关数值/流程源码，并重新计算六份索引文件的 UTF-8 内容 SHA-256，全部与 run index 一致，见附录 A。Chat 审阅环境没有取得本机 ignored 的约 3.89 GB volume 原始数组、12.18 GB q 文件和完整 live ledger，因此本报告接受的是 hash-bound 执行证据与保存数据 checker，并结合源码审计；不声称 Chat 自己重新进行了 FE 或原始大数组回放。[R1]、[R2]、[R3]、[R4]

本轮新增和修改集中在完整 volume、selected q、紧凑映射与 service/campaign/stage。普通 target worker 和 MUMPS backend 在这 10 个提交中没有改变，所以完整 target+PC+物理 RHS 的正式求解接线还没有由 V25 证明闭合。

## 2. V25 已跨过的实质节点：完整原尺寸体积

### 2.1 完整覆盖与独立见证

这次不再是一个边轨道或有限行块。完整 target 采用真实非分离几何，全部 30,464 cells、29 个原始类别和 60 个方向类别参与；full storage 为 20,181,348 行，独立未知量为 19,897,344，其中 active trace 为 6,188,544，内部未知量为 13,708,800，约束 slave 为 284,004。[R2]、[R5]

独立原生体积响应来自原始形式的 FullspaceSplitVolumeAction，未拿候选 Schur 矩阵自身充当见证。借用的 PETSc 输出先复制，再做后续调用；保存数据回读同时检查覆盖、输入、凝聚、恢复与 residual。第二组见证在全部 30,464 cells 的内部状态和内部 RHS 上均非零，避免只用边界或零内部数据掩盖恢复问题。[R2]、[R5]、[R7]、[R10]

| 完整域见证 | Schur / 凝聚方程相对误差 | 原生方程相对 residual | 恢复后 full-storage forward error | 判定 |
|---|---:|---:|---:|---|
| case 0 | 2.89194550785866e-14 | 6.091298454929457e-14 | 2.0241723674506166e-12 | 原见证通过 |
| case 1，同一 LU 修正前 | 1.6169801236254536e-13 | 原始值保留在旧见证 | 1.6167809853040123e-11 | forward 超过 1e-11，保留原失败 |
| case 1，同一 LU 修正一次后 | 1.6169801236254536e-13 | 1.4134870345986256e-15 | 1.2501798433208044e-13 | 通过，trace 不变 |

表中体积作用/方程门为 1e-10，恢复 forward 门为 1e-11。forward error 是恢复向量与见证向量之差的二范数除以完整见证 storage 向量的二范数；误差来自内部恢复，但不是仅以内部分量范数归一化。这次修正是在已有局部 LU 上修正内部恢复误差，没有增加新预条件器，也没有放宽阈值。它说明恢复路径需要保留校正与实际成本，不说明全局迭代次数已经下降。[R2]、[R5]、[R16]

科学运行 20261011T024026.570042Z 在数组落盘后因 mappingproxy 收据序列化失败；随后保存数据恢复 20261011T033624.351783Z 得到 RECOVERED_SAVED_WITNESS_PASS，11/11 checker 条件通过，checker 状态为 PASS_SAVED_READBACK_ONLY，FE_rerun=false。原 WORKER_FAILED 与后续 recovery PASS 应并列保留，不能重写成原进程正常退出。[R1]、[R2]

### 2.2 时间和内存能支持什么结论

以下均是原正式 worker 的完整父区间；conservative workflow 是包含外围费用的另一口径，不能与 watchdog 时间相加。

| 对象 | watchdog 父区间 s | conservative workflow s | 同时整树 RSS B | 专用 cgroup peak B | task swap |
|---|---:|---:|---:|---:|---|
| 完整 target volume 科学运行 | 1,804.2103085 | 1,990.0629696 | 7,449,296,896 | 11,029,651,456 | 0 |
| 最新 q0/q4 producer + 后续失败运行 | 1,281.4087936 | 1,422.1191074 | 11,709,558,784 | 13,548,032,000 | 0 |
| 早一次 degree160 FFCx 受控停止 | 156.6194 | 不与最新运行混算 | 13,439,320,064 | 13,480,509,440 | 0 |

来源：[R3]。这些值是不同对象的实测，不能用第一行和第二行比较“新旧 PC 节省百分之多少内存”。

**完整 target 体积诊断已在当前本机资源边界内跑到科学见证完成，这是继续原尺寸工程工作的依据。** 但约 30 分钟包括准备、构建、两组作用、恢复、native 对照和持久化，不是一次体积 matvec 的耗时。互斥子阶段计时未完整保全，应写 UNKNOWN；不能除以两组见证当作每次迭代成本，也不能把保存数据恢复的秒级费用冒充新 FE 时间。[R2]、[R3]

## 3. 完整 reference q：数据已经有了，缺的是消费者与 CSR

### 3.1 实际对象和数据规模

q0 阶段使用去除 notch/void 的 regular reference，并从 Ny=8 的全参考域提取 twist-0 两胞 sector，局部网格为 272×2×14，共 7,616 cells。q0 的 trace 宽度为 773,568，端口 aliases 为 4,076，增广形状为 777,644×777,644；配对 q4 有 3,856 aliases。因此已保存的 surface stream 覆盖 **q0+q4 合计 7,932 modes**，不是仅 q0 的 4,076 modes。[R2]、[R6]

“端口”是在截断边界上表示向外传播/衰减模式的未知量；B/C 把端口作用送入体积/接口方程，D 把场投影回端口，H 保存原始模式归一化。这里沿用原始模式清单和 H：local H=global H/4，端口坐标按 1/sqrt(local H) 缩放。源码未发现新的 branch/H/gauge 公式错误，但完整消费的数值验收尚未完成。[R6]、[R9]

| 已保存文件 | 字节数 B | 完整对象的用途 |
|---|---:|---|
| v25_selected_q0_surface_functionals.bin | 11,230,840,064 | 全部 7,932 aliases 的原始 B/D 行号、值和 H |
| v25_selected_q0_volume_classes.bin | 226,645,122 | 共享 Schur 类及全部 7,616 cells 的精确 expansion/active maps |
| v25_selected_q0_local_H_p.npy | 127,040 | 完整 local H |
| v25_selected_q0_original_to_active_int32.npy | 21,009,152 | 原始行到 active trace 行的映射 |
| v25_selected_q0_map.npz | 348,496,973 | 完整 Q0 映射 |
| v25_selected_q4_map.npz | 348,492,573 | 完整 Q4 映射 |
| 合计，derived | 12,175,610,924 | 由以上六项字节数相加 |

六文件来自 run 20261011T053811.673002Z，完整 hash 列于附录 B。11.23 GB 是流式端口数据的磁盘体积，不能当成 q0 CSR 大小，也不能乘八冒充所有 q 的内存实测。[R2]

还需修正新 manifest 的身份措辞：入口已用 replace 去除 air_void_box_nm/cell_notch，实际计算 regular/local reference；但末尾把外传 target 的 physical_model_sha256 写在 regular_reference_physical_model_sha256 字段。新记录应分别冻结 parent_target_identity 与实际 regular_cfg/local_cfg、材料、边界、MPC、模式和编号身份。保留旧 producer/source/hash，不修改旧科学数据，也不把参考问题写成真实非分离 target。[R6] 1019–1024、2025–2058。

### 3.2 失败的正确分类

最新 q 运行的终止表现为 PETSc signal 11 SEGV、随后 MPI abort，未形成完整 stream manifest、replay NPZ 或 native witness；完整 CSR 和 factor 均未完成。已提交修复保证 _native_volume_apply 复制借用输出且只销毁自己创建的 source Vec，定向测试 11 passed；修复后的真实 native 调用仍未运行。[R1]、[R2]、[R6]、[R14]

这一所有权错误与崩溃现象相符，修复方向成立；但缺少 native stack 和修复后实测，不能声称它已被证明为唯一根因。最新失败运行的 conservative 时间 1,422.1191 s 小于该次准入限值 2,429.3084 s，记录无 resource stop event，故不能归类为资源不足或超时。[R3]

早一次 degree160 FFCx 巨型表构造确实触发 RESOURCE_CONTROLLED_STOP。后续换为既有有界积分表达，源码仍用同 degree 的 Basix interval Gauss tensor-product，没有降低积分 degree。此处沿用已有适用范围的 production surface 证据，不把它扩大成新 reference 全量独立再积分证明。[R1]、[R6]、[R20]

最新 q 的 task cgroup swap=0；host pswpin 增 1,087 pages、pswpout 增 15,780 pages 的归因仍 UNKNOWN，不能记作本 task 使用 swap。保留宿主诊断和 reserve 检查即可。[R3]

### 3.3 为什么下一轮应复用，而不重生成

当前代码先执行两组完整 persisted replay，再调用 native，最后才保存所有 replay/native 数组。所以从控制流看，崩溃前可能已经算过两组 replay；由于结果没落盘，既不能写 PASS，也不宜断言它们从未执行。准确状态是 **NOT_SAVED / NOT_QUALIFIED**。[R6] 1510–1637。

六文件已包含消费者所需的 Schur 类、cell expansion、Q0/Q4、lookup、H 和端口数据。V26 可先做纯保存数据消费，再最小重建参考 FE/MPC 完成原生见证。主要返工应限定在尚未闭合的消费与 native 部分。

native volume 的独立性来自原始 FE 形式；native B/D 在此处仍读取同一保存 surface stream。因此本轮新资格证明的是完整消费、凝聚、投影和 volume 接线，不能宣称 7,932 个模式经过第二套独立表面积分。继续沿用已有 production surface/gauge 证据即可，不新增一遍全量 producer 作为前置门。[R6] 813–938、1374–1388；[R8]

## 4. 已能定位的同包修复：防止修一处、下一处又停

下表是源码审计发现，不是新的数值失败实测。它们应在恢复包中一并处理；只做相应轻量测试，再继续完整对象。

| 问题及位置 | 具体影响 | V26 处理 |
|---|---|---|
| 借用 Vec 的生命周期；selected_q0 798–810 | 已修复 copy/destroy 边界，但真实 native 复验缺失 | 保留复制输出，只销毁自有 source；实际重复调用后保存见证 |
| replay 保存点在所有 native 检查之后；1510–1637 | 后续崩溃会丢失已经算出的完整输出 | 输入先保存，每个 stream/native 输出返回后立即原子持久化 |
| CSR 分支用未定义的 volume_native/c_native/d_native/h_native；1906–1909、1945–1948 | 该分支走到此处会 NameError；不是早先 SEGV 的原因 | 统一为实际定义的 native_volume/native_c/native_minus_d/native_h；stub 覆盖 CSR 后检查 |
| stream-only PASS 缺 original_H_p；CSR 未建分支还缺 direct_only_support | checker 对所有 PASS 都要求这些字段，会使成功数据再次卡在收据 | 把完整 alias/H/内部零支撑与身份放到 optional CSR 之前，统一各终态字段 |
| q4→q0 理论零输出用自身极小范数作相对误差分母；1595–1598；checker 3153、3202–3234 | 舍入级泄漏之间的差值可被错误放大为 O(1) | 跨 q 差值和 leakage 使用对应非零 diagonal 响应尺度；worker/receipt/checker 同步 |
| 第一组 native 分量已算出，随后四次重新计算整套分量；923–938、1544–1563 | 无需的 native volume 调用和全 surface stream 读取 | 第一次返回并保存完整 component dict，后续投影复用 |
| volume stream disk estimate 漏 class_payload；534–545；reload 只在首类做容量门；599–622 | 磁盘或共驻容量低估 | 先核对全部 class header 与总载荷，再准入；包括全部类、maps、向量、workspace |
| q0 未用已验证的 compact action maps，且旧/重载 Q maps、FE/action owner 共驻 | 非必要全局映射和生命周期重叠提高峰值 | 相容时复用紧凑 maps；saved-only、native、CSR 阶段及时释放不用的 owner |
| 完整 row counts 在 CSR allocation 前已有，却等 builder 返回后才保存 | CSR 门失败时完整结构成果也丢失 | counts/offsets/nnz/支持路由先保存，再准入数值数组 |
| selected-q stage 未累计 future_co_resident_reserve_bytes | 若直接接 factor 路径，漏 symbolic/numeric 预留 | 新单 q 生命周期显式计入相应 reserve，避免与分项重复计数 |

源码依据：[R6]、[R7]、[R9]、[R11]、[R12]、[R18]。不得把最后一项描述为 V25 已发生的 factor 资源错误，因为 V25 没有运行 factor。

### 4.1 分量复用为什么不损失独立性

_native_component_reduced_actions 内部已经分别用 trace-only 与 port-only 场计算 volume、C、−D、Hhat。第一组完整 x1 调用返回的每个分量，与后面四次纯输入调用取出的相应分量使用相同输入、恢复公式和原生 callback；可以直接保留并左乘 Q0 的共轭转置。[R6] 813–938。

按现有调用路径计算，完整验收目前需要约 7 套分量计算，即 **14 次 native volume apply 和 21 次 provider sweep**。复用后保留两个不同 q0 输入和一个 q4 输入，只需 3 套，即 **6 次 native volume apply 和 9 次 provider sweep**。这是源码推导的调用数减少，不是已测出的墙钟加速倍数；纯 stream replay、构建与回读费用还要另外计时。

### 4.2 理论零输出的正确门限

对于输入位于 q 的同一组见证，用对应 native diagonal 输出的非零范数作为固定尺度；配对分支记为 q'。应保存以下所有量：

```math
\begin{aligned}
s_q&=\left\|y^{\mathrm{native}}_{q\leftarrow q}\right\|_2>0,\\
e_{q'\leftarrow q}
&=\frac{\left\|y^{\mathrm{stream}}_{q'\leftarrow q}
-y^{\mathrm{native}}_{q'\leftarrow q}\right\|_2}{s_q}
\le 10^{-11},\\
\ell^{\mathrm{stream}}_{q'\leftarrow q}
&=\frac{\left\|y^{\mathrm{stream}}_{q'\leftarrow q}\right\|_2}{s_q}
\le 10^{-11},\\
\ell^{\mathrm{native}}_{q'\leftarrow q}
&=\frac{\left\|y^{\mathrm{native}}_{q'\leftarrow q}\right\|_2}{s_q}
\le 10^{-11}.
\end{aligned}
```

q0→q4 与 q4→q0 都执行；保存绝对范数、s_q 与归一化结果，由 readonly checker 从数组重算。尺度为零或无效时明确失败，不能用 0/0 得到 PASS。正常 diagonal 与非零 volume/C/−D/Hhat 仍保留各自的 1e-11 相对门，不能一律除以较大的总响应来掩盖端口误差。原始 H 的 1e-12 归一化门保持。[R6]、[R11]

这是修正理论零量的比较尺度，未放宽数值容差；若出现真实非零泄漏、错误 alias 或 H/MPC 不一致，停止受影响数值路径并保留实际数据。

## 5. V26 连续工作包：完整 q 恢复、结构、CSR、条件 factor

### 5.1 阶段一：只读复用 V25 producer，尽早保存完整 replay

在现有 service/campaign/stage/watchdog 内接通 saved-stream operation。该入口是本轮待实现接口，不假称当前 CLI 已支持。读取附录 B 的六个文件及旧 failure index、冻结模式清单，核对长度/hash/shape/dtype/完整 alias 和行号范围；不默认再生成 11.23 GB surface stream。

新恢复 manifest 同时绑定旧 producer source/run/window/hash 和本次 replay source/run/window。补充实际 regular/local 配置及 target 父身份；不得伪造旧 run 已有 complete manifest。不能从后来的新数据补写原失败收据中本来没有的量。

volume stream 自带全部 Schur 类与 cell maps，纯 replay 不必建立完整 FE。未单独保存 interior_rows 时，应由正确的保存身份恢复支持信息；使用 lookup<0 处理无 active 行时，仅允许经过范围检查的精确零值跳过，任何非零无映射行都拒绝，负行号不得进入 NumPy 索引。不能把所有无映射行直接当作可丢弃内部项。[R6] 394–505、599–727。

保存两组不同且所有元素非零的 q0 输入，以及一组所有元素非零的 q4 输入；每次消费后立即保存完整总输出、四分量及配对分支输出。阶段失败仅重做缺失依赖。新源代码若只改回读、序列化或路由，不使 V25 已有科学 payload 自动失效。

### 5.2 阶段二：最小 reference native 重建，完成完整消费者资格

只重建本阶段必要的 7,616-cell regular reference FE/MPC、局部恢复与原生 volume action，读取既有 surface stream。必要重建的真实费用记入新窗口；不重做已通过的原尺寸 target volume。

fresh FE/MPC 的行号、材料、边界与保存 lookup/Q maps 必须一致。若排序不同，要给出显式编号映射并验证，不能把旧 Q 直接套到新编号。修复后的 Vec 所有权和第一组分量复用在真实调用中兑现；每次 native 输出返回后先保存，再计算后续结论。[R6]、[R7]、[R10]

消费者完成标准：

1. 全部 7,616 cells、q0 的 773,568 trace rows 和 4,076 aliases、配对 q4 的 3,856 aliases均有完整库存。
2. 两组 q0 diagonal 与 q4 diagonal 原生对照、q0 的 volume/C/−D/Hhat 分量对照通过原 1e-11 门。
3. 两方向 off-diagonal 差值与 stream/native leakage 通过第 4.2 节同尺度门。
4. 原始 H、alias 无重叠、direct-only 内部 B/D 零支撑通过既有门；不截模式，不改 gauge。
5. readonly checker 只从已保存数组和身份重算；运行 exit、数值、覆盖、资源、文件完整性分别给状态。

这一步完成后登记完整流式消费者 PASS；它可以在不一次存下整个矩阵的情况下给任意完整输入计算结果，但尚不是可直接交给 MUMPS 的 CSR 或已求解的 reference inverse。

### 5.3 阶段三：先保全完整结构，再继续完整数值 CSR

CSR 是把矩阵每一行的非零列和值连续存放的稀疏格式。完整结构计数先回答“每行实际要多少位置、合计多大”，数值 CSR 再填入对应复数值，最后才有直接分解的输入。

沿用 ROW_TILE_BOUNDED_CSR_V17 的全部行构建，选 requested_blocks=((0,0),)，不建立 q4 CSR 或其他 q CSR。可以在 minimal native 后释放 FE owner，再用保存 Schur/expansion/surface 的 adapter 提供现有 contribution/layout 接口；尽量不要把 producer、native owner、两套 qmap 和 CSR 转换同时保留。[R6] 1727–1738；[R8]；[R9]

V17 已在数值数组准入前得到完整 wide counts、prefix offsets 与 nnz。应在这一位置持久化 shape、逐行 count/offset、最终 nnz、dtype 上界、payload、支持路由与 hash，而不是等整个 CSR builder 成功返回才保存。只保存首末几行或一个 panel 不满足完整结构交付。

对于当前 777,644 行、complex128 值和 int32 索引，纯 CSR 数组容量为：

```math
M_{\mathrm{CSR}}
= (16+4)\,\mathrm{nnz}+4(777{,}644+1)
=20\,\mathrm{nnz}+3{,}110{,}580\ \mathrm{B}.
```

这是 derived 公式；完整 nnz 尚无实测，不能先声称当前 16 GiB 一定容纳或一定容纳不了。公式不含 FE、maps、SciPy/PETSc 转换、工作向量和 factor。wide prefix 必须先检查 int32 上界；若超界，明确 INDEX_WIDTH_LIMIT，保留宽计数，不能强转溢出或静默更换当前资格化 ABI。[R9]

资源允许时，本包继续完整数值 CSR，保存全数组/完整行块、回读两组输入并与已经资格化的 stream/native 对照。现有磁盘 mmap 构建仍会触及并弄脏整个 CSR，必须按全 touched payload 计入 cgroup 内存；不能以“在磁盘”把内存申请写成零。[R9] 2626–2656。

若整块 CSR 准入失败，完整流式消费者、全行 counts、精确 nnz/字节和可恢复支持路由仍须交付。真正按块保存/释放的数值行块可在其实际共驻门通过后继续；不得绕过原 mmap 门宣称 solve-ready。用完整结构计算本机缺口和下一环境的明确需求，不退回有限模式采样。

### 5.4 阶段四：新授权的条件单 q 生命周期

**本 Review V26 在完整 q0 数值 CSR 通过独立见证、ABI/索引范围及当前本机资源和余时门后，允许自动继续该实际 q0 的 conversion、symbolic、numeric、fresh residual probe、非零 RHS solve 与 eviction。** 这是比 V25 build-only 新增的条件范围；不要求再等一轮聊天。若不能准入 numeric，也要保留完整 CSR、symbolic 成本和原始内存估计，说明具体缺口。

symbolic 是先分析稀疏消元结构并估计后续因子资源；numeric 才真正分解数值。当前 OneQRefactorV19Mumps 的构造器强制全部 8 个 q CSR，并逐 q 做 symbolic preflight，不能传入只有 q0 的字典，也不能假造 q_count=1 绕过完整 profile 合同。[R18] 949–956、1006–1010、1107–1121。

建立受限 selected-q 研究入口，复用/提取现有 exact MUMPS 基元及其资源、残差、销毁检查。无需复制数值分解器，也不改变现有全 q backend 的覆盖合同。保留 complex128、资格化 int32 与 exact 控制；factor probe 沿用 1e-10 true residual 门，不启用新的近似压缩。因子对同一完整 q 的重复 RHS 求解可以验证复用，但不能当作完整逐 q PC 的 warm reuse。[R18]

每阶段准入必须覆盖当前 source CSR/owner、PETSc 输入、转换副本、symbolic/numeric reserve、向量与 checker。selected-q stage 现有 callback 只加 additional_payload_bytes、matrix_payload_bytes、workspace_bytes，会漏 V19 的 future_co_resident_reserve_bytes；新 route 必须显式纳入本阶段真实预留，且不与细分项重复加总。[R12] 1057–1066；[R18] 1742–1811。

保留现有保守 symbolic guard 及 INFOG 解释口径，symbolic 后再次准入 numeric。不能为了进入 16 GiB 而无证据削弱 guard；若 guard 限制成立，报告 CSR 和 guard 的精确需求。独立单 q 研究无需虚构完整 target KSP 已共驻，但不得将其峰值当作完整 PDE 峰值。

记录完整生命周期父区间和不重叠子计时、原始 INFOG、factor entries、cgroup/RSS/swap、factor/Mat/Vec 同时存活计数、销毁后余量。每完成一阶段立即保存；一次完整 factor 生命周期足以取得第一份成本，不把反复 benchmark 当成前置门。单 q 成功仅登记 selected-q 生命周期资格，不登记全 reference inverse、全局 KSP、target PDE 或 official R/T/A。

## 6. 怎样把这些结果推进到 2 TB / 48 h

### 6.1 当前路线解决的不同问题

V25 没有新增预条件器，也没有新的完整 KSP 迭代结果。“预条件器使迭代减少”和“整个求解内存减少”仍需分别计量。紧凑 maps、共享 Schur 类、保存流和 owner 及时释放可以减少对象表示/重复生成成本；单槽 factor 降低同时驻留的因子数，却仍保留全 q CSR，并可能增加重复分解时间。[R1]、[R7]、[R8]、[R18]

整机内存应按同一时间实际存活的对象统计，2 TB 不是给某一个因子的独占预算：

```math
M_{\mathrm{host,other}}+
\max_t\left\{
M_{\mathrm{FE,MPC}}+
M_{\mathrm{volume,maps}}+
M_{\mathrm{ports}}+
M_{\mathrm{reference,CSR}}+
M_{\mathrm{factor,work}}+
M_{\mathrm{Krylov}}+
M_{\mathrm{recovery,output,check}}
\right\}(t)
\le 2{,}000{,}000{,}000{,}000\ \mathrm{B}.
```

主 FGMRES 同时保存搜索方向和预条件后的方向，也需计入。仅当前 6,188,544 active trace rows、complex128，按 2m+1 个向量估算，restart m=30 为 6,040,018,944 B，m=60 为 11,981,021,184 B；这是主向量组的 derived 容量，尚不含 ports、额外 scratch、真实实现附加向量及最终精度网格增长。[R2]、[R16]

### 6.2 最大时间风险：不是只付一次 factor

OneQRefactorV19Mumps 保留全部不可变 q CSR，初始化逐 q symbolic preflight 后销毁临时因子；cache miss 又从 CSR 建 PETSc 输入、symbolic、numeric 和 fresh probe。上层完整 PC 按 sector/branch 遍历 8 个 q，单槽切换即驱逐，正常连续完整调用中通常每个 q 都重新分解。[R9] 834–947；[R18] 949–956、1107–1121、1364–1505。

因此总时间宜按实际重建数与实际 RHS 求解数记账，而不是只乘外层迭代次数：

```math
\begin{aligned}
T_{\mathrm{field}}={}&T_{\mathrm{prepare,JIT,build}}
+T_{\mathrm{initial\ symbolic}}\\
&+\sum_q F_q\!
\left(t_{\mathrm{convert},q}
+t_{\mathrm{fresh\ symbolic},q}
+t_{\mathrm{numeric},q}
+t_{\mathrm{probe,check},q}
+t_{\mathrm{evict},q}\right)\\
&+\sum_q S_qt_{\mathrm{RHS\ solve},q}
+T_{\mathrm{target\ actions,transport,Krylov}}\\
&+T_{\mathrm{recover,output,final\ check}}
\le172{,}800\ \mathrm{s}.
\end{aligned}
```

F_q 为真实 factor rebuild 次数；S_q 仅计 startup、PC、augmentation 和其他验证 RHS 的求解次数，排除已计入 probe/check 项的 fresh-factor probe MatSolve，不能直接使用包含 probe 的 backend_mat_solve_total。各类调用分开记录。identity hash、admission、assemble 与 factor factory 的时间也归入相应完整父区间；当前若干子计时未覆盖这些外围工作，不能简单把子项相加当总成本。[R18]

下表只是算术情景，用来说明为何需要完整单 q 实测，**不是本项目性能预测**。假设 8 个 q 周期耗时相同、每次 PC 各重建一次，且暂时不计其他全部费用：

| 假设每 q 完整重建/求解周期 | 每次 PC 的 8 q 成本 | 48 h 内理论最多 PC 次数 |
|---|---:|---:|
| 60 s | 480 s，8 min | 360 |
| 300 s | 2,400 s，40 min | 72 |
| 600 s | 4,800 s，80 min | 36 |

真实可用次数还须扣除构建、原算子作用、恢复、输出与 checker。q0 只校准 q0，其他 q 的 fill 和成本不能默认相同。若实测说明单槽重复分解不满足预算，下一决策应先按真实 2 TB 共驻账选择可负担的 factor/结构复用与调用安排，再考虑是否需要改变数学路线。不要在分解成本尚未测量时又启动一个新 PC。[R18]

### 6.3 何时可以离开当前参考验证，进入真正大模型

| 推进节点 | 必须回答的问题 | 达标后的直接动作 |
|---|---|---|
| 当前完整 target volume | 全域消元、作用、凝聚 RHS 和恢复是否正确 | 已通过，沿用 |
| V26 完整 reference q consumer / counts / CSR | 全模式消费是否正确；完整一块究竟多大、多贵 | 资源允许直接测本 q factor；不再扩展有限 panel |
| 完整单 q factor 生命周期 | 实际 fill、转换/分解/solve/释放成本及资源余量 | 形成其余 q 和完整 reference inverse 的明确容量/时间计划 |
| 全 reference inverse + 真实 target 算子/RHS/恢复接线 | 全 q 覆盖和必要算子正确性、首次完整场的资源预算 | 准入原尺寸 pilot 第一次完整场运行 |
| 原尺寸完整场 | 实际迭代/调用数、全原方程 true residual、物理量和全部时间/内存 | 校准 48 h 模型，推进规定离散与物理精度 |
| 最终准确工程结果 | 原目标全部精度门，整机 2 TB、单场 48 h 全账 | 才能宣布终极目标达成 |

**成功求解之后检查的 A6/物理结果门，不能反过来要求“先有成功的原尺寸解，才准许第一次原尺寸解”。** 首次运行的前置是正确接线、必要算子见证与有余量的资源证据；求出场后再执行完整原方程 residual 和物理门。V25 的 S-only 全体积 PASS 不是完整 A6，当前 Ny=8、Nz=14 也不自动代表最终精度合格。[R16]、[R17]

若本机 16 GiB 被完整数据证明不足，下一 response 应交精确 q0 输入/结构、共驻清单、symbolic 或 factor 需求、运行入口与迁移准备包，供已有主控安排下一阶段资源。V26 不自动 SSH 或改工作站，但也不能在此后继续用小模式样本代替已经明确需要的完整规模运行。

## 7. 新固定窗口、连续执行与分类

### 7.1 V25 保留的历史与费用

V25 T0=2026-10-11T00:38:41Z，数值 cutoff=06:18:41Z，总 deadline=06:38:41Z，旧窗口已结束。最后 worker_end seq14616 累计 19,398.5879813 s，数值余额约 1,001.412 s；收口 seq14617 累计 20,674.0876186 s，数值余额为零，总余额约 925.912 s。UTC 与账面一致；结果 HEAD 在 06:32:40Z 提交，早于总截止。[R3]、[R4]

主控收口账本不可变前缀为 16,875,657 B，SHA-256=fcfc08881b123a80961c7fe7704af5f9f6c46f3939475a56d9976edc9b7bf972。索引后 push/readback 尾段的完整收费未闭合，应保留 UNKNOWN，不写成零，也不因此冻结 V26。不得刷新旧 T0、恢复旧余额、覆盖失败或重写旧 artifact 身份。[R3]、[R4]

已知失败包括 class-coverage 字段错误、mappingproxy 序列化、保存回读缺 NumPy import、mode-key 摘要不一致、degree160 构造受控资源停止、最新 PETSc SEGV。它们各自保留实际 source/run/费用；资源停止、实现失败、数值超门和纯回读失败分别分类。[R1]、[R2]、[R3]

### 7.2 V26 合同

| 项目 | V26 执行要求 |
|---|---|
| 工作目录 / 分支 | /home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering / task40extra_0p7nm_engineering |
| 新 T0 | 本包第一项实际实现、测试或准备开始时一次冻结，不等 FE 启动 |
| 总窗口 | 21,600 s；实现、测试、准备、运行、提交/推送/回读全部计入 |
| 收口 | 预留 1,200 s；数值 cutoff=T0+20,400 s；总 deadline=T0+21,600 s |
| 本机资源 | 资格化 runtime、complex128/int32/MPI1、动态 host reserve、16 GiB 专用 hard cap、task swap=0 |
| 并发 | 同时只有一个 heavy case，使用既有主控/执行者与独立 watchdog |
| 本轮必做主线 | 旧完整 q 数据恢复 → 完整 native 消费者 → 全行结构/条件 CSR |
| 条件扩展 | 完整 q0 CSR 与资源/余时通过后，继续本 q symbolic/numeric/probe/solve/evict |
| 范围边界 | 不自动全 8 q factor、target PDE、SSH、工作站、新聊天/工作树、新 PC 或 master 合并 |
| 角色 | 本机执行者实现/测试/运行/证据；主控集中审查并提交/推送同一分支 |

campaign registration、service resolver、selector、stage、required checker 必须同包接通。目前多处硬绑定 V25 路径/hash/operation；只新建 campaign_window_v26.json 不够。使用明确的 V26 登记对象和实际 scope，不删除身份/时间校验，也不把任意路径改成可授权入口。[R11]、[R12]、[R13]

优先在前约一小时内完成已定位局部修复、轻量 route/receipt 测试并启动保存数据消费；随后以完整 native 和全行结构为主，余时按实际准入继续 CSR/factor。这里是顺序和预算指导，不是对尚未实测对象的耗时承诺。窗口内 source 可以因修复更新，每次 actual run 冻结新 source，原 T0/deadline 不变；相关 gate 修复后继续，其他已有数值证据不自动失效。

普通路径、dtype、变量名、返回 schema、checker、超期测试 fixture 和 closeout_seconds 合同错误，应局部修复并定向复验后继续。真实数据身份/ABI 不一致、数值超门、内存/磁盘/索引宽度门或固定截止，才停止受影响路径。崩溃先确认后代进程全部结束，再恢复缺失步骤，不能重叠启动 heavy case。

V25 测试记录为：ownership 定向组 11 passed，较宽 route 组 17 passed，另一组 74 passed / 1 skipped / 6 failed，后者涉及陈旧 campaign fixture 和缺 closeout_seconds。不得合并写成全部回归通过。compileall/diff 通过；Ruff 未安装、native 修复后重跑、全 CSR/factor/PDE、全仓测试、MPI2/4 与 CI 均不能宣称通过。[R15]

新数值能力进入可复用 src 核心，selected-q 入口保持薄的研究编排，service/checker 负责路由和回读。不要继续在 task-numbered 文件复制另一套 solver；架构整理限定为本轮恢复与 selected-q factor 必需接口，不做无关重构。

## 8. Response V26 的实质交付标准

下一份 response 先给完整对象的结果与成本，再给 bug/test 清单：

1. **旧数据实际复用了什么？** 逐文件 source/run/hash/字节、新消费者 source/window；新建 surface producer 次数应有实数，正常复用路径为零。
2. **完整 q 消费者是否通过？** 两组 q0、一组 q4 的完整数组、四分量、双向 leakage、全部 alias/H/MPC 身份及独立 saved checker。
3. **消除了哪些重复工作？** 实际 native volume/provider sweep 次数与互斥生成、读取、replay、native 耗时；区分代码推导与实测。
4. **完整结构与数值对象到哪一级？** 全行 counts/offsets/nnz、完整 streamed action、数值 row tiles、CSR、PETSc 输入分别报告，给 dtype、字节、hash、恢复入口。
5. **单 q 生命周期到哪一步？** 未准入写精确 source CSR、转换/guard/因子预留、余时和缺口；完成则给 raw INFOG、true residual、全过程时间/同时峰值与销毁结果。
6. **距离 2 TB / 48 h 还有什么未知？** q0 以外各 q、全 PC 重建次数、target 完整算子/RHS、真实迭代数、恢复输出与最终精度分别列出，并给下一直接行动。
7. **能否继续完整大模型？** 满足准入就明确推荐下一完整规模运行；缺资源给数据支持的具体需求，不再泛写“继续小样本验证”。

本次 V25 总体判定为 **partial_with_material_progress**：完整 target volume 接受；reference q producer 完整、消费者未资格化。V26 的责任是消费已有大规模成果并测到完整 q 的真正代价。最终 PDE、精度、2 TB / 48 h 和 master 合并资格仍未闭合。

## 附录 A：本次远程内容 SHA-256 复核

以下六文件按远程 UTF-8 内容重新计算，与 run_index 的 review_v25_evidence_index 一致；这不是 ignored 二进制 payload 的 Chat 本地回读。

| 文件，相对任务目录 | 内容 SHA-256 |
|---|---|
| outcomes/records/target_operator_probe_v25.json | c6825bfd69ae0abf862ceda264ac4eb824e42cf8cf4acb00939c955540774267 |
| outcomes/records/time_resource_accounting_v25.json | 4dd9ddf9af09209938483c61699b7d8ba42e42debcb52d3d10f982405eee5487 |
| response_v25.md | 711b7aa6ca7016e07a007a9a610579bcf73f87be357882627a0167fce6e218b7 |
| outcomes/summary.md | 03e34410f84d7ec7e2b738b4377d457eea2388ec02d124d4f3376816fb2bd2ef |
| outcomes/test_summary.md | 18ec4e1a30734ce9351b0eaae3bc3293ab5427194e9971798abda8eef7b08254 |
| README.md | dee107005910bec20cb0e38c8e566a102d2ee511b6e7dfb77e78be69c5292f39 |

## 附录 B：V26 应复用的 V25 q 原始数据身份

共同 run 目录位于 results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261011T053811.673002Z。以 [R2] 的真实 artifact 路径为权威，不用本文拼接路径替代实际存在性检查。

producer source=9d0f4dbfc730dd620b709d048e33e9da6c77520c；input SHA-256=7c7fcc172968bb291d6834bac6c4f2d3b71b3f1a1efb836129f5dfb872082407。旧记录所带 ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241 应明确其 target 父身份，实际 regular/local reference 身份按第 3.1、5.1 节另行冻结。

| 文件 | 旧 payload SHA-256 |
|---|---|
| v25_selected_q0_surface_functionals.bin | 92fb011dc9bc551728079d10f8cd26e8810668b0ab5df78189c3466e2cbd4613 |
| v25_selected_q0_volume_classes.bin | f76b1dad7b863c0e4fc32ca7cdbd793436a22cc2386a59b79e6297eac94e390b |
| v25_selected_q0_local_H_p.npy | f79de1ec28568f9a1d05f4bd6743a497d9dcc729654cf0a04e56d92d912c5a21 |
| v25_selected_q0_original_to_active_int32.npy | f473037848f72d886ddb0a421d6240fe77788f799740168c234c9340ba1a963d |
| v25_selected_q0_map.npz | cad0ea1d34c26cea53b07965d80b952733944a8003ee9aa09cf922e08bc71e20 |
| v25_selected_q4_map.npz | 871e1a86715588fb6157fe5bbc96bf545d207629e4ad480eafd7ee4cd383a2f4 |
| v25_q0_failure_artifact_index.json | c7f687e6054e0506d03d4443bfaede58bfa46d76476b5270844d3d792cb3f026 |

## 附录 C：可直接交给 Codex 的执行文本

请在现有 Task40extra 主控/本机执行对话继续执行最新 Review V26。先拉取 task40extra_0p7nm_engineering 分支，完整读取 docs/task40extra_0p7nm_engineering/review_report_v26.md，再核对 canonical worktree、HEAD、工作树、ABI、run index 与旧 artifact 身份。

本次审阅的 V25 结果基线是 d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7。目标保持原尺寸 50×25×140 nm、0.7 nm、真实非分离 Si/air、complex128、整机 2 TB、task swap=0、单场全部必要费用 ≤48 h。当前 Nx272/Ny8/Nz14/p6 是原尺寸工程 pilot，最终精度没有自动通过。

这轮的主交付是：复用已有完整 q 数据 → 完整 saved-stream/native 消费者通过 → 完整全行结构和条件 CSR → 资源与余时允许时继续一个实际 q0 的 factor 生命周期。不要把修完 Vec bug、11 tests passed 或新增一个有限 panel 当作整轮终点。

一、接受并沿用 V25 的完整 target volume。
全部 30,464 cells 的体积作用、RHS 凝聚、内部恢复已由保存数据 checker 通过。case1 的同一 LU 修正和原 forward 超门记录都保留。不要因 q 路由、序列化或收据修正重跑这批原尺寸科学数据，也不要另造预条件器或重启小模型迭代对比。

二、新建一个 V26 固定窗口并一次接通路由。
总窗口 21,600 s，收口预留 1,200 s；从本包第一项实际准备/实现/测试起冻结 T0。数值 cutoff=T0+20,400 s，总 deadline=T0+21,600 s；修复后不刷新 T0。保留 V25 全部 source/window/失败/费用。
一次接通 campaign registration、service resolver、selector、stage、watchdog 与 required checker；仅新建 V26 JSON 不够。维持当前资格化 runtime、complex128/int32/MPI1、动态 host reserve、16 GiB 专用 hard cap、task swap=0、一次一个 heavy case。

三、优先恢复 20261011T053811.673002Z 的完整 producer。
使用 Review 附录 B 的六个只读文件和 failure index，核对实际路径、字节、SHA、shape/dtype 和全库存。surface stream 已含 q0+q4 共 7,932 aliases，11,230,840,064 B；六文件合计 12,175,610,924 B。不要默认再生成一遍。
旧 producer source=9d0f4dbfc730dd620b709d048e33e9da6c77520c；新的恢复 source/window 单独登记。把原 target 父身份与实际去除 notch/void 的 regular/local reference 身份分开，不修改旧 payload/source，也不伪造旧 complete manifest。
先做纯保存数据 replay，再最小重建 7,616-cell reference FE/MPC 和 native volume/recovery；fresh 编号必须与保存 lookup/Q0/Q4 一致，若不同需显式映射。无 active 映射的行只可在范围合法且值精确为零时跳过，不能负索引或丢弃非零项。

四、把已知后续失败点在同包修好。
保留 _native_volume_apply 的复制和所有权修复；实际重复调用后验证，不把单测当 native PASS。
输入先保存，每次完整 stream/native 输出返回后立即原子保存，不能等全部检查结束才落盘。
CSR 分支的 volume_native/c_native/d_native/h_native 与实际定义不一致，统一名称并用轻量 stub 覆盖该分支。
original_H_p、direct_only_support、完整 aliases 与实际模型/MPC 身份前置，stream-only PASS 和 CSR_NOT_BUILT 分支均满足 checker 合同。
q0↔q4 理论零输出的差值和 stream/native leakage，用相应非零 native diagonal 输出范数作同一尺度，保持 1e-11；保存绝对范数和尺度，readonly checker 同步重算。非零 diagonal 四分量继续用各自 1e-11 门，H 继续 1e-12。
修正 volume stream 磁盘预估漏 class_payload、reload 只为首类准入的问题；计入全部类、maps、向量、workspace。能复用 compact maps 就复用，释放不再需要的 live FE/action/qmap owner。

五、直接消除重复 native 工作。
第一次 x1 的 native component 函数已分别完成 trace-only/port-only 分量，返回并保存整套 volume/C/−D/Hhat，供后续投影和 checker 使用，不再为四个分量分别重算整套。
保留两组不同且所有元素非零的 q0 输入，以及一组所有元素非零的 q4 输入。按源码路径预计 native volume 调用由 14 次减到 6 次、provider sweep 由 21 次减到 9 次；记录实际调用数和时间，不把这个推导写成实测加速。
完整验收覆盖 q0 的 773,568 trace rows、4,076 aliases，配对 q4 的 3,856 aliases和全部 7,616 cells。native B/D 使用同一 saved surface stream，应准确写成独立消费/投影对照，沿用已有 production surface/gauge 资格，不新增全量再积分作为前置门。

六、消费者通过后本包直接推进完整 q0 结构与 CSR。
复用 V17 bounded row-tile、requested_blocks=((0,0),)。在数值 CSR allocation gate 之前保存全部 row counts、wide offsets、nnz、shape、dtype 范围、字节需求、可恢复支持路由和 hash。
当前 q0 为 777,644×777,644；complex128/int32 纯 CSR 字节为 20*nnz+3,110,580，其他 owner/转换/factor 另计。wide prefix 先验 int32 上界；不强转溢出。
资源允许即继续完整数值 CSR、全数组/行块回读和两输入对照；mmap 全部触页仍按 cgroup 内存计。若不准入，交完整消费者、全行结构和精确缺口，不退回小 panel。真正分块的数值存储也要按实际共驻门执行，不能把磁盘存储冒充 solve-ready。

七、满足条件时直接测一个完整 q0 的生命周期。
本 Review 已条件授权 conversion → symbolic → numeric → fresh true-residual probe → 非零 RHS solve → eviction；无需因“V25 是 build-only”再次停审。
不要直接调用强制全 8 q CSR 的 OneQRefactorV19Mumps 构造器，也不要假造 q_count=1。增加受限 selected-q 研究入口，复用现有 exact MUMPS 基元与原 residual/销毁检查，不放宽全 q production coverage。
准入包括 source CSR、PETSc 输入、转换副本、symbolic/numeric reserve、向量和 checker。现有 stage callback 会漏 future_co_resident_reserve_bytes，必须显式纳入且避免重复计数。保留既有保守 guard、INFOG 解释和 1e-10 fresh probe 门。
每阶段完成即保存；numeric 门不通过也交完整 CSR、symbolic 成本、原始 INFOG 和明确缺口。单 q 成功不等于全 reference PC 或 target PDE。不得自动全 8 q factor、启动 target PDE、SSH、切工作站或新建执行聊天/工作树。

八、普通 bug 在同一窗口内修复并继续。
selector、变量名、dtype、schema、序列化、checker、过期 fixture、缺 closeout_seconds 只需局部修复和定向复验；保留失败 source/run/成本，新运行冻结新 source，不清零历史。
真实身份/ABI/数值/资源门或固定 cutoff 才停止受影响路径。失败后确认整组后代已退出，再恢复缺失步骤。不要重装环境或反复全套测试来代替完整对象交付。

最后提交 response_v26、operator/resource compact、run index、summary/test_summary 和模型/进度总账，先回答完整 q 到了哪一级、实际 nnz/字节/峰值/耗时、factor 到了哪一阶段，再列 bug/tests。48 h 预算按真实 factor rebuild 和 RHS solve 次数计费，probe 与业务 RHS 分账，避免重复计费：当前单槽在完整逐 q PC 中通常每 q 都重新分解，不能只算一次 factor，也不能把 q0 当作所有 q 的实测。

本机执行者负责实现/测试/运行/证据，由既有主控集中审核、提交并推送同一任务分支。交精确 HEAD、source/input/ABI、原始负结果与哈希回读后等待下一次审阅；不合并 master。

## 附录 D：冻结来源

除 R16 固定于前一份 review 的正式提交外，以下均固定于本次结果 HEAD；正文源码行号用于定位，不表示相应路径已经实际运行。

- [R1] V25 response
- [R2] V25 operator compact
- [R3] V25 资源与费用
- [R4] 运行和证据索引
- [R5] 完整原尺寸体积见证
- [R6] selected-q producer/consumer
- [R7] 凝聚与紧凑映射
- [R8] P6 action/provider/恢复
- [R9] q 映射、V17 全行构建和 reference inverse
- [R10] 独立原生体积作用
- [R11] service 与保存数据 checker
- [R12] stage 与容量准入
- [R13] 窗口登记
- [R14] selected-q 定向测试
- [R15] 测试结果与未运行项
- [R16] 上一份 Review V25
- [R17] 任务目标
- [R18] 单因子槽与 exact 生命周期
- [R19] 当前任务导航
- [R20] 有界 production surface 与 probe

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/docs/task40extra_0p7nm_engineering/response_v25.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v25.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/docs/task40extra_0p7nm_engineering/outcomes/records/time_resource_accounting_v25.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/task40_v25_complete_volume.py
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/task40_v25_selected_q0.py
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/hcurl_assembly_time_condensation.py
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/p6_cell_condensed_action.py
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/task40_v10_p6_yorbit.py
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/fullspace_physical_action.py
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/scripts/task40_v20_service_workflow.py
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/runners/task40_v20_stage_runner.py
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/runners/task40_v10_campaign.py
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/test/test_task40_v25_selected_q0.py
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/docs/task40extra_0p7nm_engineering/outcomes/test_summary.md
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/4a524251339e00ad481b29af61df4f4625ed2581/docs/task40extra_0p7nm_engineering/review_report_v25.md
[R17]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/docs/task40extra_0p7nm_engineering/task.md
[R18]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/task40_v10_p6_mumps.py
[R19]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/docs/task40extra_0p7nm_engineering/README.md
[R20]: https://github.com/Rookie1234567/MyFEniCS/blob/d9bde16eaede7a85e72d9e16f786a4e1ae7a3ed7/src/solvers/task40_v22_operator_probe.py

