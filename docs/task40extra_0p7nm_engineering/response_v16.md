# Review V16 执行回应

## 本轮裁决

V16 的 BOUNDED_STAGING_CSR_V16 路线在 Gx560 上完成了完整 p6 target 求解，A6 真残差、官方物理量和与 V15 保存场的同离散比较均通过。worker monotonic 时间比 V15 记录少约 133 秒；树 RSS 小幅下降约 90 MB，但 cgroup 峰值反而增加约 233 MB，不能认定同时内存已降低。E1 本轮没有进入构建，状态为 NOT_ADMITTED_PREBUILD，而不是一次新的资源停止。P4 确实完成了两个已保存边界面上的 32,060 模式向量作用和端口方程检查，但原有非零 RHS 前向恢复门在上下两面都失败，因此组件总状态仍为 COMPONENT_GATE_FAIL。

Gx560 正式运行使用冻结源码 SHA `54b98a871632a1eef1c34e3542788f5859ee255c`。P4 helper 的本地源身份是 P5 开始时 HEAD `3fffbddc3ebdf597cf25eed5600095d09f24d918`；该 helper 没有接入正式 Gx560 路线。这个 SHA 是文档收口前本地 HEAD，不是最终提交或推送 SHA。P5 只改文档和 compact，未改数值源码、未运行 PDE；执行者未提交或推送，由主控在最终审查后集中提交/推送。

| 阶段 | 执行与结果 | 边界 |
|---|---|---|
| P0 | 核对分支、固定窗口、run index、源码身份和已保存数组 | 固定窗口 T0、deadline 与 SHA 未变；历史失败、费用和未知项保留 |
| P1 | 以 bounded CSR 构建四个 q 稀疏矩阵；保留旧 V12 transform bank，另按 sector system 独立启用 identity cache | 投影/数值累加使用 staging gate；完整 q pattern 仍用全 shape bitset，未获得目标尺寸 row-tile 资格 |
| P2 | Gx560、p6、340 modes 完整求解和输出 | 3 次外层迭代；A6 与 native witness 约 `4.70e-9`，均低于原 `1e-6` 限值；同离散场比较通过 |
| P3 | 对原 E1 做现场预构建准入 | `NOT_ADMITTED_PREBUILD`；没有创建 E1 网格、q matrix 或因子；post-symbolic Gate 本轮 `NOT_RUN/UNKNOWN` |
| P4 | 复用 W11/S2/S5 已保存数组，在 top/bottom 面执行完整 32,060 向量作用与端口检查 | 端口方程通过；S2 known-state forward recovery 两面超限；不改门槛 |
| P5 | 写入四份 compact、回应、结果/测试摘要、README、run index 和项目账本 | 只做文档合同检查；没有新 FE/PDE 运行 |

## 1. Gx560 新构建路线与同离散场比较

Gx560 有 560 个单元（10×4×14）、p6、340 个保留模式和四个 q 通道。CSR 是把稀疏矩阵按行存成连续数组；V16 将 q pattern、投影和数值累加分阶段，限制一块工作区可同时占用的暂存空间。四个 q 矩阵实测 NNZ 为 `15,457,680 / 15,483,524 / 15,600,060 / 15,483,524`，合计 `62,024,788`；行数为 `28,508 / 28,508 / 28,576 / 28,508`。

已界定的收益集中在稀疏累加子阶段：两 sector 的父计时从 V15 `422.540 s` 到 V16 `408.214 s`；其中 sparse accumulation 从 `275.837 s` 到 `16.777 s`，V16 新 pattern construction 为 `110.582 s`。这些子阶段与父阶段有嵌套关系；父计时剩余差额仍 unknown，不能归给某个未测阶段。worker monotonic 全流程为 `2,274.267412 s`，3 次外层迭代；释放参考因子后目标 A6 真残差为 `4.704430002e-9`，独立 native witness 为 `4.704309876e-9`，都低于原 `1e-6` 限值。独立输出 checker 通过。物理量为 R=`0.0761240670863`、T=`0.905769220100`、`A_balance=0.0181067128139`、`A_volume=0.0181067125773`；零级反射分别为 `R00_s=0.0761235935066`、`R00_p=7.34191940688e-22`、`R00_total=0.0761235935066`。

V16/V15 保存场比较通过六类 E/H/curl 量的共同子单元积分、全部 340 个有序模式语义和功率、以及冻结的 11 个显著模式复振幅。场和缩放 curl 的最大相对 L2 差为 `1.632e-12`（限值 `1e-4`），全部模式功率最大绝对差为 `2.368e-13`（限值 `1e-6`），显著模式振幅最大相对差为 `1.258e-10`（限值 `1e-4`）。R/T/A/`A_volume` 的差均小于 `2.72e-13`（限值 `1e-5`）。物理模型、网格轴、几何、MPC、载体和模式身份相同；两份输入文件字节 SHA 不同。比较是在已保存场上完成，不是第二次 PDE。

内存上限有明确适用边界。当前 q pattern 为每个 q block 建一个全 shape 的 uint8 行 bitset，字节数随 `rows × columns` 增长，再加 32 MiB reserve；这仍是 O(N²) pattern，并非目标尺度 row-tile。256 MiB gate 对纯方形 bitset 推导出的行边界约为 43,344，support slices、逐行解码和 CSR construction 会让实际可用边界更低。Gx560 的 q pattern support staging 上界实测 `137,113,676 B`；目标候选保留行约 3.13 million，不能据此说现有完整 pattern 对目标尺寸可扩展。受限投影和数值累加也不能改变这条 pattern 边界。

## 2. 时间、内存与对象存活

| 口径 | V15 | V16 | V16 减 V15 |
|---|---:|---:|---:|
| worker monotonic workflow | 2,407.572 s | 2,274.267 s | −133.305 s（约 −5.54%） |
| 同时进程树 RSS 峰 | 10,294,927,360 B | 10,204,880,896 B | −90,046,464 B |
| cgroup memory 峰 | 11,674,669,056 B | 11,907,702,784 B | +233,033,728 B |
| 四 q MUMPS allocated 上界合计 | 4,645,000,000 B | 4,692,000,000 B | +47,000,000 B |

所以 worker 时间有所缩短，但 cgroup 和因子上界没有降低；两次记录也不是同一时刻受控缓存对照。V16 的保守 UTC budget interval 为 `2,526.263 s`，与 monotonic interval 分开记录。worker interval 没有包含所有外部必需 checker 和离线场比较，完整单场关键路径仍 unknown。C1 保存后复核另用 `0.616 s`，V16/V15 离线场比较另用 `29.976 s`；这些是分开的资格/复核成本，不能冒充 worker 内计时，也不能单独拼成完整单场时间。


### Gx560 求解器、PC 调用与四个 q 因子

KSP-only monotonic solve 为 148.349809164 s；retained-outer-solve clock 到终端快照为 158.978736877 s，独立于 KSP 和 2,274.267412 s worker workflow。三次完整 reference-PC 父调用为 67.115958898、17.492464560、9.798304339 s；均选择 correction candidate 0 且没有增广修正。native evaluation 是父计时内子阶段，不能重复相加。父计时包括 raw q solves、完整状态评估、可选修正、输出转换、证据写入与资源采样；主要 setup 分项和完整准备总时长仍 unknown。

| q | rows | NNZ | factor CSR SHA-256 | numeric 子阶段 (s) | INFOG19 allocated upper (B) | INFOG22 used upper (B) | INFOG9 raw；factor entries |
|---:|---:|---:|---|---:|---:|---:|---|
| 0 | 28,508 | 15,457,680 | `036fa99d56e741c74d1b17ed3afc179c280afaf2727ad1fc60d859928be16488` | 4.276749134 | 1,156,000,000 | 1,015,000,000 | 41,415,880；unknown |
| 1 | 28,508 | 15,483,524 | `bbf15a7e68cce2042dd584971be6b1281fa0e89d0d223df5a3a29b9ceb25eaba` | 5.314689438 | 1,177,000,000 | 1,033,000,000 | 42,179,536；unknown |
| 2 | 28,576 | 15,600,060 | `60b7a85fcd2d29f8e7f2fd6f32de23b0b28fb602d137f0279b5d9992a0e949bd` | 4.573781677 | 1,182,000,000 | 1,037,000,000 | 42,165,112；unknown |
| 3 | 28,508 | 15,483,524 | `a28858650e77298f58640ba9c1c6877f10c4c03131fcc627e325ab3716db864e` | 4.485745297 | 1,177,000,000 | 1,033,000,000 | 42,179,536；unknown |

四个 q numeric 子阶段合计 18.6509655 s，仅是子阶段合计，不是 setup 或全 workflow。销毁前库存快照记录 q0–q3 四个 native factors 同时 live；快照 SHA-256 为 `dcd10562ea4a841b595eeee7d012ba9a555823dd1a11f3640df4a9349b856dbc`。逐 q 原始 JSON 的路径和 SHA，以及同时库存路径见[正式结果记录](outcomes/records/review_v16_formal_results.json)。INFOG9 原值照录，没有依据把它解读成 factor-entry 数。能量闭合为 2.3666513193632e-10，吸收一致性为 2.366651527530017e-10，target condensed native identity 为 5.592504268634092e-11。


对象账需区分两类缓存。原 V12 transform bank 按 Basix/方向状态复用 p6 cell-interior payload，边和面仍走旧路径；它与 identity cache 不是同一个对象。`share_identity_cache` 只缓存 shape 为 450×450、dtype 为 float64 的只读单位阵 I，单个本地库存记为 `1,620,000 B`。target condensation system 与两个 local sector system 各自启用该选项；三套 system 之间没有一个共用的 I owner，也不是借它共享变换矩阵、Schur、LU 或恢复映射。55 个不同局部类别仍保留各自 Schur/LU/恢复对象。参考因子在求解后释放，并在 380,040 长度解向量上重算 A6/native residual；释放引起的 RSS 下降无法归因到某类对象。PSS 按 profile 未启用，保留 null。任务 cgroup swap 为 0；WSL 全局计数增加 52 页入 swap、0 页出 swap，归属不明，不能说宿主全程零 swap。

## 3. E1 与目标容量

E1（760 单元、588 模式、四 q）本轮状态是 `NOT_ADMITTED_PREBUILD`：没有开始网格、symbolic、numeric、KSP 或输出。准入使用当前现场动态 cap `13,432,152,064 B`。保守总投影 `19,192,602,560 B` 超过 cap `5,760,450,496 B`，第一项准入不通过，已足以保持 HELD。未来 symbolic、bank 和向量对象估算合计 `6,994,120,640 B`，小于当前保留证据后的 headroom `13,432,152,064 B`，这是 prebuild arithmetic check；它不代表实际经过 symbolic 后的第二个增量资源 Gate 通过。本轮该 post-symbolic Gate 为 `NOT_RUN/UNKNOWN`。

预计量中最大项是从 INFOG16/17 派生的四 q 未来 numeric 保守估算 `6,530,000,000 B`，不是实际已分配或使用的因子字节，只是未来保守估算。历史 V15 E1 symbolic-stop 当时 reserve 后仅有 `410,038,272 B` headroom，incremental Gate 失败；旧记录继续保留，不改写为本轮事件。完整 E1 numeric 到 checker 的时间预算也没有证明。原尺寸目标仍是 `50×25×140 nm`、波长 `0.7 nm`、十进制 2 TB 与 48 h，尚未资格化。

## 4. 32,060 模式端口组件与恢复门

P4 的 Hhat 向量作用可以理解为：对边界模式向量先作用边界算子，再加上内部场消元后反馈到边界的贡献。分块计算避免在这个组件中生成 `32,060×32,060` 复数稠密矩阵。它复用了 W11/S2/S5 留存的真实数组：S2 arrays SHA `d656ff94…`、S5 arrays SHA `1850543a…`；完整模式清单 SHA 为 `52d7ec80…`。旧的 W1/函数 hash 诊断不表示数组缺失：controller lineage audit 表明 W11 数组实际被复用，历史 source 函数变化只限制“按当前 source 重新生成”的资格主张。早先 inventory bridge 是 P4 之前的快照，不能继续作为缺少 target arrays 的结论。

组件在每面使用真实 882 行（450 interior、432 trace）、q60 积分、16 模式一批和 64 点一块；top 覆盖索引 0–16029，bottom 覆盖 16030–32059。两个面都完成 32,060-entry 向量作用，没有物化全 Hhat 或 mode-square 方阵。raw vector readback 一致且 port equation 子门通过，但 aggregate status 为 READBACK_GATE_FAIL，因 S2 known-state recovery 两面超限。readback 的 D 坐标用生产 gauge helper 转换，不是独立 Di quadrature oracle；此范围不是全目标矩阵或 PDE 资格。

run_01 首次中断报告 top Balpha 与 S2 分区不一致。复核发现它把 450 行 interior 的微小差值除以该子集的近零范数，造成 `0.2147/0.1656` 的 subset-relative 数字。改用完整 882 项 S5 Balpha 范数后，top/bottom 误差为 `1.13e-13/1.04e-14`；interior 差值相对完整尺度仅 `9.56e-16/9.28e-16`。这纠正了旧 Balpha 拦截，不表示 run_02 的其他门通过。

本轮没有精化 recovery 公式。当前 P4 直接 LU 前向重验加载的 `Vii`、`fi`、trace、S2 `Bi` 和 known-state 向量，来自与历史记录相同的 S2 数组 SHA `d656ff94…`；未执行 recovery refinement 时 top/bottom 前向误差为 `2.20293e-11/2.42443e-11`，均超过原 `1e-11` 限值。历史 V11 记录中的 `5.35e-14/5.14e-14` 是同一 S2 数组上已保存的精化合格状态；它不是这次不精化的直接 LU 重验。两者差异尚未归因，不能说是输入或数组不同。局部恢复方程误差 `9.73e-16/1.11e-15` 和原/约化端口方程约 `1.4e-16` 均低于各自 `1e-10` 门，但不能覆盖前向门失败。S5 Balpha 对 S2 Bi/Bt 的完整 882 项归一化比较是另一个独立检查，误差 `1.13e-13/1.04e-14`；它通过不代表 S2 known-state 恢复通过。`Bi alpha` 范数只有 `1.12e-13/1.43e-13`，可能对舍入敏感，但仍只是诊断线索，不是根因证明。

目标候选 `10,228,620` full-storage rows 与 `3,126,332` trace-plus-port rows 是派生计数；32,060 AUTO 模式清单已有保存身份，但不是最终截断资格。P4 没构造目标 q CSR/NNZ，`indptr[-1]` 与 int32 offset 仍未测；PETSc 当前是 int32，故目标索引安全未关闭。一个 32,060² complex128 方阵单对象的派生 payload 为 `16,445,497,600 B`；P4 证明当前 helper 向量路径不分配该方阵，但没有证明全部 production path 已消除此类中间对象。

## 5. 一般 Ny、精度和下一阻塞

Ny=8 小组件没有运行。Ny=8 只是保持几何的候选 global Ny，必须先从 global/local orbit 关系推导实际 K，不能预设 K=8。当前 p6 源码仍断言 global Ny=4、local Ny=2；没有构造候选的 Basix/dofmap 与方向映射、内部 dof 覆盖、primal/dual 传递、伴随功恒等式或完整模式到 q 分支映射，也没有按实际 K 推导并验证 H/RHS/alpha normalization 和全 q correction 上限。不能把配置字面量从 2 改成 8来宣称一般 Ny。

立即的下一阻塞是解释并关闭留存数组上 S2 top/bottom 两个 known-state 前向恢复门（`2.20e-11`、`2.42e-11`，限值 `1e-11`）；保留原门，对数组做定位和独立复算，再由下一轮 review 决定是否需要受限新组件。之后仍须证明目标 y/z 离散误差、完整模式截断、目标 q CSR/NNZ/int32、安全因子填充及全流程 2 TB/48 h。小残差、能量闭合或 Gx560 与旧场一致，都不等于连续精度或目标容量。

证据入口：[结果总账](outcomes/summary.md)、[测试摘要](outcomes/test_summary.md)、[构建与内存记录](outcomes/records/review_v16_build_and_memory.json)、[正式结果](outcomes/records/review_v16_formal_results.json)、[目标组件](outcomes/records/review_v16_target_components.json)、[成本与 readiness](outcomes/records/review_v16_cost_and_readiness.json)、[run index](outcomes/records/run_index.json)。

### 5.1 原尺寸 target readiness 的派生账

本节只整理已有物理身份、解析网格计划和目标 resource ledger 的公式；候选网格没有生成，不能把派生节点称为实际 FE mesh。冻结目标身份为 λ=`0.7 nm`、周期 `50×25 nm`、`z∈[-10,130] nm`，来源是 `outcomes/v14_engineering_to_target.json` 和 `target_ledger_v5`。解析计划的未缩放分界为 `x=[0,16.5,25,33.5,50] nm`、缺口 y 边界 `[6.25,18.75] nm`、z 分界 `[-10,0,40,80,120,130] nm`；原几何缺口盒为 `[25,33.5]×[6.25,18.75]×[40,80] nm`。这些值来自 `src/geometry/task40_nonseparable_plan.py`（SHA `c4f091f88c34a6a0980e2b0e75f2b22a4274042370253176467816a601cde713`）的解析 plane recipe，不表示目标节点已生成。V5 资源账的 x 四段计数是 `[78,58,58,78]`；每段候选节点按端点线性分点即可复现。临时计数假设 y 均分 4 格（节点 `[0,6.25,12.5,18.75,25] nm`），z 段数 `[1,4,4,4,1]`（节点 `[-10,0,10,20,30,40,50,60,70,80,90,100,110,120,130] nm`），所以候选轴格数 `[272,4,14]`、15,232 cells。分类为 `DERIVED_RECIPE_NOT_GENERATED_TARGET_FE`；实际目标轴节点、真实 interface/origin、MPC 和材料 hash 仍未由目标 FE 绑定，本轮不以缩小 Gx784 节点代替它们。

基于实际 32,060 模式 inventory 的 p6 计数是 full-storage `10,228,620` rows、periodic-independent `9,948,672` rows、interior `6,854,400` rows、trace+AUTO-port `3,126,332` rows；对应 p4 interface+AUTO-port 计数为 `1,346,364`。候选计数来自 `v14_engineering_to_target.json` 和 `target_ledger_v5/target_resource_ledger.json`；模式数是 inventory，不是已资格化的最终倏逝截断。q NNZ、CSR `indptr[-1]`、中间偏移和目标整数安全仍未知。

已有 workspace 公式为 FGMRES restart=32 时 `(2*(restart+1)+8)*retained_rows*16 = 3,701,577,088 B`，共 74 个 complex128 向量；full/retained scratch 公式 `24*full_rows*16 + 10*retained_rows*16 = 4,428,003,200 B`。它们是各自载荷，不是同时 RSS。单个局部形状载荷为 raw `882×882` tensor `12,446,784 B`、`450×450` dense interior-LU shape `3,240,000 B`、`432×432` Schur `2,985,984 B`、单个体积 interior↔trace coupling (Vit/Vti) 或 recovery map（`450×432`）`3,110,400 B`；实际 sparse LU fill、复制数和同时存活时间未知。两种增长情形应分开表达：按唯一 geometry/material/orientation class 数 `N_class × per-class payload`，或候选 `15,232 × per-cell payload`；Gx560 实测 55 类不代表目标也是 55 类或每个格子独立。

端口路径的既有稠密收缩为 `dual_di=LᴴD_i`、`xib_primal=XiB·R`、`projected=dual_di·xib_primal` 后转稀疏；目标 C/D/XiB 的实际维度、copies、tile 生命周期没有构建。一个 AUTO 模式对角 H 的 payload 为 `512,960 B`，一个 mode-square dense object 为 `16,445,497,600 B`；H/Hhat 的所有权与同时生命周期未知。P4 helper 实测使用 mode batch 16、point chunk 64，但不能当作目标 tile 内存资格。V12 transform bank 与只读 identity-I cache 是两类独立对象；identity I 由 target condensation 和两个 local sector systems 各自启用，V12 bank 按 Basix/direction-state identity 共享。target class count、全部 q sparse-factor fill/backend workspace、恢复与输出对象重叠以及完整流程同时 RSS 都仍是 `unknown`；十进制 2 TB、48 h 与 y/z 精度均未资格化。


端口耦合和体积 interior↔trace coupling 是不同对象。每个边界面有 M_face=16,030 个模式（top/bottom 合计 M=32,060）：Bi/XiB 为 450×M_face，Di 为 M_face×450，Bt 为 432×M_face，Dt 为 M_face×432；拼接后的全 local-row coupling 为 882×M_face。按 complex128 单份 dense 形状载荷公式 16×n×m，单面 Bi/XiB 或 Di 各为 115,416,000 B，Bt 或 Dt 各为 110,799,360 B，全 882 行 coupling 为 226,215,360 B。全接口 M=32,060 的对应形状各翻倍；这些都是派生形状载荷，不是已分配矩阵。分块临时量同样按 16×n×b 计：生产 Hhat 路线 b=64 时 450/432/882 行分别是 460,800/442,368/903,168 B；P4 helper b=16 时分别为 115,200/110,592/225,792 B。副本数、同时生命周期与目标实际 owner 均 unknown；本轮没有构造这些数组。

公式来源及字段状态已写入 [成本与 readiness compact](outcomes/records/review_v16_cost_and_readiness.json)、[目标组件 compact](outcomes/records/review_v16_target_components.json)、[构建与内存 compact](outcomes/records/review_v16_build_and_memory.json) 和 [正式结果 compact](outcomes/records/review_v16_formal_results.json)。

## 6. P5 收口检查

文档合同与模型登记定向 suite 最终执行为 `29 passed`、`134 subtests passed`（`0.24 s`，pytest 报告值）。测试前的限定 ABI preflight 通过：Python 3.12、PETSc 3.25.6 complex128/int32、MPICH 5.0.1、MPI1，并确认 MUMPS 可用；本次 P5 文档测试不包含 FE/PDE；Gx560 的独立 C1 输出 checker 已通过。全仓 pytest、MPI4、Ruff 和 CI 均未运行，本轮不声称其通过。
