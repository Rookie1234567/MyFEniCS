# Response V3：Task40extra Review V2 执行收口

## 执行结论

Review V2 的 P1–P7 证据、正负结论和未运行边界已经整理到 compact records、campaign 与两级总账。P1 的原 M0 公共子单元体积/curl 场门失败；旧 R5 固定坐标样本 PASS 是另一条证据，不能替代 P1。P4 是新的 F3/F5 同 M2 跨网格比较：官方功率差通过，但显著模式、固定样本场和体积 scaled-curl 有超过 1% 的失败项。P3 的 M 模式包络比较与 P1/P4 的 G0/G1 网格场比较回答不同问题，不构成 h 或连续收敛证明。

| Review问题 | 回答 | 证据 |
|---|---|---|
| 80个原传播通道是否足够 | 未能资格化。P3 的 M0→M1 是手动扩展包络、保留原80个传播通道并加入其余模式，同时跨过 P2 reference-metric 配置的组合比较；M1→M2 按披露的事后显著性规则选择 M2。有限稳定性不能证明 M0 截断充分或真实连续边界误差有界 | `channel_study_v2.json`、`review_v2_campaign.md` |
| P1/P4 是否通过场门 | 都有明确场/导数失败项。P1 M0 散射E 2.6113%、散射H/scaled-curl 2.7498%；P4 M2 显著模式振幅1.555605%、固定样本2.743612%、体积 scaled-curl 2.750374%。两阶段官方功率差都低于0.001 | `p1_m0_volume_h_agreement_v2.json`、`volume_h_agreement_v2.json` |
| F1参考metric是否采用 | F1只在 G1 M0 同离散对照中通过所列 Gate，作为剩余 campaign 的配置；G0 原 paired artifact 仍为 `NOT_QUALIFIED`，F1 不能充当 G0 M2 exact-reference | `reference_metric_tensor_v2.json` |
| 电尺寸扩大后如何 | E1 A6 residual `9.7816685e-7≤1e-6`，为诊断点；E2 原 worker residual `9.7930732e-7` 通过残差线但 exit4、official false。v3 只恢复保存场输出，不追认原 worker 成功 | `electrical_size_v2.json`、`repair_ledger_v2.json` |
| P6证明什么 | 三个真实材料 tag 的局部块与非零 RHS 恢复闭合通过；M=3904 是固定16列批次的合成重采样动作，不是高M完整物理端口或 TB 容量结果 | `p6_local_block_inventory_v2.json`、`resource_components_v2.json` |
| 下一工程方法 | 仅提出一个波传播感知、有界局部子域加递归 matrix-free 接口粗校正设计；旧42宏块/强逆候选有 fresh negative，不改名复做 | `review_v2_campaign.md` |

正式模型的源码身份逐个绑定如下，不能把 F3 的 SHA 套给 F5：F1=`1d7d790088d6ea0f30aed2ef1073fb1b86e68155`；F2 最终尝试=`37635226002787beb26a24baba3a8da333027239`；F3=`a43f7f76a0df0f4440b77834846973b2de7ea3a8`；F5/E1/E2=`63dd2a7378153f2ab5094eb5e7a98d05758a39bf`。P6诊断源码=`5f9efdbae1c668ffa4426731156ec4afe9325eb2`。E1稳定`run_id`为`task40extra_0p7nm_nonseparable_e1_manual_m2_growth_v1`；目录时间戳不是`run_id`。input、physical model、native ordered-mode identity 和 raw-file SHA 见 `records/run_index.json` 与 `records/electrical_size_v2.json`。F3/F5 native `ordered_mode_sha256` 均为`7336482596276ee033f211ea84635d91678591f40705b208025622a0a35dd253`；F1 G1 M0 native identity 是`c3ff9c0cf35e2d183f44ed3fb7448d4aa586bb6fdf7f9dc9ba78dc25011c693a`。这是按模型区分的native identity；不把F1值解释为F3/F5的key-list digest。E1 native mode identity 为`d1ea3dadce6e546ac7fce32493edb0fab09d7de22208850aca0a139a23b1e52b`。

## 正式模型与资源摘要

| 模型 / 稳定 run_id | source SHA | 网格 / 模式；A6 residual | R / T / A_volume（raw/offline标记非official项） | workflow / KSP；process-tree RSS / swap | 状态 |
|---|---|---|---|---|---|
| F1 G1 M0 / `...g1_reference_metric_f1_v1` | `1d7d790088d6ea0f30aed2ef1073fb1b86e68155` | 880 cells / 80；`8.648911990579289e-7` | `0.07612407122165808 / 0.9057692393459813 / 0.018106713007727038` | `2252.535 / 1674.835 s`；`6,891,311,104 / 0 B` | G1 M0同离散reference通过；仅一次性能样本 |
| F2 G0 M1 / `...g0_manual_m1_f2_v1` | `37635226002787beb26a24baba3a8da333027239` | 336 cells / 180；`9.572475880327875e-7` | raw/offline `0.07565188084569026 / 0.9062068016471507 / 0.018141266883419625`；official false | `1123.500 / 809.586 s`；`3,867,545,600 / 0 B` | worker exit4；checker把合法180模式硬编码成80；保存DtN/体积值用于P3 offline比较，未重新发布official result |
| F3 G0 M2 / `...g0_manual_m2_f3_v1` | `a43f7f76a0df0f4440b77834846973b2de7ea3a8` | 336 cells / 340；`7.593610432084708e-7` | `0.0756519019957502 / 0.9062068705222379 / 0.018141268088495303` | `1174.947 / 823.922 s`；`4,006,539,264 / 0 B` | discrete solve/consistency通过；authority-limited |
| F5 G1 M2 / `...g1_manual_m2_f5_v1` | `63dd2a7378153f2ab5094eb5e7a98d05758a39bf` | 880 cells / 340；`8.735322490524255e-7` | `0.07612407127067708 / 0.9057692398169153 / 0.018106713068250728` | `2448.071 / 1797.975 s`；`7,754,170,368 / 0 B` | discrete solve/consistency通过；authority-limited；同 M2 跨网格场门有负项 |
| E1 q=1.25 / `...e1_manual_m2_growth_v1` | `63dd2a7378153f2ab5094eb5e7a98d05758a39bf` | 760 cells / 588；`9.781668525522113e-7` | `0.06235653736791684 / 0.9159264755357902 / 0.021716951725654188` | `4580.375 / 3722.193 s`；`10,650,341,376 / 0 B` | 固定波长、电尺寸扩大诊断；不是 h 收敛序列 |
| E2 q=1.5 original / `...e2_manual_m2_growth_v1` | `63dd2a7378153f2ab5094eb5e7a98d05758a39bf` | 880 cells / 700；`9.793073227317083e-7` | 原 worker 未产生 official output；v3恢复值见下 | `7692.028 / 6776.587 s`；`11,349,196,800 / 0 B` | original exit4、official false；保存场离线恢复单独分类 |

Dof、p4因子行/NNZ、MUMPS INFOG29、分阶段时间和 resource identity 的定义见 [V2 summary](outcomes/summary.md) 与 [resource record](outcomes/records/resource_components_v2.json)。进程树RSS、inventory-ledger、workspace、MUMPS memory estimate/allocated/used、matrix payload、ICNTL23受限工作内存限额与RSS属于不同口径，不相加；本campaign未启用MUMPS out-of-core。PSS 为 null。未从这些单机结果外推2 TiB容量，也未改 workstation cap。

零级反射分别报告`s`、`p`与合计，避免把偏振功率混成一个量：F1 `R00_s/p/total=0.07612359764215308 / 3.4597741445267834e-17 / 0.07612359764215311`；F3 `0.07565142791421035 / 7.233241618502243e-17 / 0.07565142791421042`；F5 `0.076123597691134 / 3.5617837904198074e-17 / 0.07612359769113404`；E1 `0.062356105023958414 / 6.083759436e-16 / 0.062356105023959024`。F2 raw/offline `R00_s/p/total=0.07565140676565715 / 2.0048467438900223e-17 / 0.07565140676565717`，official flag仍为false。E2 v3 recovery `0.05116727309447169 / 7.978116094818559e-19 / 0.05116727309447169` 是保存场恢复值，非原worker official result。全衍射阶仍以 run-index 绑定的官方 DtN 文件为准。

## P1、P3、P4及旧R5样本的区别

P1 是原 G0/G1 M0 保存场在1344个共同子单元上的体积场/独立 curl(E) 对照。总场 E/H 相对差`0.375014% / 0.394900%`通过1%；散射 E=`2.611273%`，散射 H 与独立 scaled-curl=`2.749777%`未通过1%。官方`|ΔR|/|ΔT|/|ΔA_volume|=0.000472098/0.000437636/0.0000345443`通过0.001。checker用时`436.5178109759581 s`，自身RSS峰`620,851,200 B`；没有PDE/operator/factor/KSP。记录 SHA=`9d72efd7f21771c7fd0cc779b7cfb0f9272734fe9cbe1757a014d127e4422925`，checker文件 SHA=`297637ccc7eab585b706c5f78039e12dfc691cca49d757b40fb86d7f09bc6932`。保存的精确调用为：

```bash
source scripts/activate_myfenics_wsl.sh && python -m benchmarks.postprocess_task40_p1_saved_fields_common_subcells --g0-root results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g0_iterative_review_v1__full3d_iterative__mpi1__Mna/20260930T102148.356966Z --g1-root results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g1_iterative_review_v1__full3d_iterative__mpi1__Mna/20260930T105500.302324Z --output benchmarks/artifacts/task40extra_0p7nm_engineering/p1_saved_field_common_subcells/p1_g0_g1.json --root .
```

旧 R5 `h_agreement_v1.json` SHA=`27cc385f28cedf565687ca80f88e7f5123e2ec58d87eb5f0fd4cfd25de4fe158` 是固定坐标样本比较，`H_AGREEMENT_PASS_ENGINEERING_ONLY`，约0.4%的有限样本门通过；它不是P1体积/curl结果。

P3固定同一 G0 离散比较模式包络。M0→M1 手动保留原80个传播通道并扩展包络，同时切换P2 reference-metric配置；因此是组合诊断。该比较列出的体积 E/H/curl 是完整保存场在公共物理子域上的结果，不是80个模式内部的体积误差。M1→M2才是声明的模式阶扩展对照；查看探索性 all-80差异后才固定`M0 power_ratio≥1e-8`显著规则，属于事后规则而非预注册。有限 M1→M2 比较通过，M3未触发；这不能证明M0的原80模式足够，也不能界定连续边界截断误差。

P4比较 F3/F5 G0/G1 两张网格上完全相同的340个有序 M2 key。显著传播模式振幅差`1.555605%`、固定4000样本最大差`2.743612%`、公共体积 scaled-curl 最大差`2.750374%`均超过1%；总场E/H约`0.375102%/0.394986%`通过，散射E`2.611883%`、散射H/curl`2.750374%`失败。官方绝对`|ΔR|/|ΔT|/|ΔA_volume|=0.0004721693/0.0004376307/0.0000345550`通过0.001；功率接近不能覆盖场/curl负结果。无新PDE/operator/factor/KSP。P4记录 SHA=`f9d51b53286cbd5ea46e4eb9e09015b4a16bfe569d669467e524fde6b94d38f9`；checker SHA=`2da4ca377ce6bac866d2aca467486a8fbae3c7468ffb355be027e3d0a991e851`。记录调用为：

```bash
source scripts/activate_myfenics_wsl.sh && python -m benchmarks.postprocess_task40_p1_saved_fields_common_subcells --g0-root results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g0_manual_m2_f3_v1__full3d_iterative__mpi1__Mna/20261001T154625.204407Z --g1-root results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_nonseparable_g1_manual_m2_f5_v1__full3d_iterative__mpi1__Mna/20261002T000242.608221Z --output docs/task40extra_0p7nm_engineering/outcomes/records/volume_h_agreement_v2.json --root .
```

## E2原失败与v3输出恢复

E2 原 worker 在完成求解后发现24×24 diffraction sample配置不满足最少25×7的输出合同，exit code 4，`official_result=false`。原 A6 residual`9.7930732e-7`低于`1e-6`，但不能代替完整输出Gate。v3使用恢复输入 SHA `4c3b70a237d19325a46825526a85ea045e6d3f665a5a6ad4d43781e082461828`，只把保存输出的x采样数从24改为25、y仍为24；复用同一物理模型及保存场，完成15项authority checks、一次native matrix-free A6 action、streaming DtN核验及R/T/A_volume恢复，`A_volume`相对原存储差为0。v3重建p6 mesh/space，但没有构造全局AIJ/H6或p4 factor，没有KSP或完整solve，也没有新PDE。原 worker 的输出合同失败保持原分类。v3 recovery record SHA=`cd303990783bae10618c8bf3ba674a4163db6909871d04c38945c6240fafae4b`。

## P6与P7边界

P6从三种真实材料tag各取一个单元，p6局部张量882×882，内部450、trace432；三次非零RHS恢复closure为`1.43e-11–2.35e-11`，通过`1e-10`。M=3904每tag双遍约`3.739–3.773 s`，按16列批次流过，没有构造M×M块；这是合成重采样压力，不是生产端口矩阵、完整高M模型或容量认证。P6自身RUSAGE RSS峰`455,610,368 B`，task swap未独立采样。

P7只留下一项文档设计。精确接口算子保持`S_ℓ=Σ_j T_j^H S_{ℓj}T_j+Ĥ_ℓ`；原`H_p`经准确消去和trace/port嵌入成为与增广接口算子同尺寸的`Ĥ_ℓ`，包括全部左右端口贡献并只加一次。近似PC的`ΣT_j^H W_jT_j=I`只约束局部patch加权。粗空间选`R_ℓ=P_ℓ^H`，由完整传播Floquet波的端口到边界场/curl迹映射、原MPC/Floquet owner/phase映射、近截止倏逝迹及有限局部接口向量构成。即使物理接口operator非Hermitian，Galerkin粗算子也允许非Hermitian；此配对不把独立物理左右块`D`改成`B^H`。提案限制≤4层、patch≤64,000未知数、活动局部因子≤8且每个≤32 GiB、每patch/层≤32局部向量、block-Arnoldi≤64步且block width≤16、每层rank≤20,000、终层≤20,000维且≤200步、外层≤2,048步，并设workspace/interface/RSS分桶限额。全部待下一阶段现场资格化，既不是容量预测，也不是本轮实现。准确符号、限制、对照和停止条件见 [campaign P7](outcomes/review_v2_campaign.md)。

## 验证、权限和证据入口

既有V2定向测试回执：P4 mode helper `4 passed`（绑定其V2源提交`3f36014253525f5fc7e0e2ee56348bc3628e9024`）；P6 bounded diagnostic fixtures `2 passed`（source`5f9efdbae1c668ffa4426731156ec4afe9325eb2`）。V2早期还运行过serial与MPI2 targeted qualification，但逐条命令、case数、耗时与每项source身份未保留，记为`unknown`，不写成未运行。全库pytest、MPI4、Ruff、CI未运行。本轮只做compact JSON/hash/identity、Markdown合同/链接和diff校验；没有PDE、P6/global factor或full test suite重跑。

ordinary default未改变；没有实施Phase II；没有master merge。e174b91历史hook偏差不改写；本轮后续提交/推送使用Task40 branch-local official hook。P6 hook偏差与E2恢复失败保留在`repair_ledger_v2.json`。

- [Review V2 campaign与P7设计](outcomes/review_v2_campaign.md)
- [V2一级/二级总账](outcomes/summary.md)
- [V2计划](outcomes/records/review_v2_plan.json)
- [P1原M0公共体积/curl负结果](outcomes/records/p1_m0_volume_h_agreement_v2.json)
- [P4 F3/F5同M2体积/curl比较](outcomes/records/volume_h_agreement_v2.json)
- [旧R5固定坐标样本](outcomes/records/h_agreement_v1.json)
- [P3/P4通道记录](outcomes/records/channel_study_v2.json)
- [F1 reference metric资格](outcomes/records/reference_metric_tensor_v2.json)
- [E1/E2电尺寸记录](outcomes/records/electrical_size_v2.json)
- [资源组成记录](outcomes/records/resource_components_v2.json)
- [修复账本](outcomes/records/repair_ledger_v2.json)
- [P6局部块诊断](outcomes/records/p6_local_block_inventory_v2.json)
- [正式运行索引](outcomes/records/run_index.json)
