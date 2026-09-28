# 实际dataset、basis、模型与运行源码身份

| 对象 | 实测身份 / 数量 | 生产与使用范围 |
|---|---|---|
| 冻结base | `ccd357885f7f9be84efe3be07868cc94f13d93fc`；种子blob`0c5211a0e99b4f1b74ad5e4223b5d91066b57816` | 只读物理定义：original13.5nm、p6/h10、同网格p4，无更短波或几何扫描 |
| 物理SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` | 所有dat相同物理/采样；非旧profile/运行文件复用 |
| 真实原A4 | `150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560`；21824×21824、8184464存储NNZ | F1逐行CSR身份；F2/F4每次重新构建并严格hash一致，无dense gather/私有audit CSR |
| 全通道mode SHA | `d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb` | 80完整auto DtN，包含相位/归一化/复矢量；不减少通道 |
| dataset manifest SHA | `99c354ea4ce85b2dd8284b8f91dab4f2e453b4b9d426034aa47af43e89a14783` | 256train/64validation/64heldout，batch<=32，384对分别原A4审核；[teacher](records/teacher_complete_v2.json) |
| oracle manifest SHA | `507370ad8b120459556e793b67ee2249514308e03cf5f92b02d4631985bccbce` | ranks16/32/64/128；fixed deployment128；validation-only诊断；[oracle](records/oracle_complete_v2.json) |
| Q/U/R basis SHA | `47d23a1c4d760b2ba91327df370bbf61099a9d03e8e67e905dbf676bd2f2d121` | R-LIN与R-NN同basis/native残差像/小三角解码；无在线teacher查询 |
| training features SHA | `591450b4ab5b628c787d7dfe37bee37b96690e36e998065acc2424cfaf927946` | train/validation特征、teacher坐标及完整native Gram/正交常数；不含heldout训练特征 |
| best checkpoint SHA | `460b5631375b09c08b3e9d7ef43e8ef9b04ebe37a86424e824fed9e8bb205eef` | epoch51，validation选；best/latest保存optimizer/源码/实际训练进度 |
| 冻结模型 SHA | `b25b389adf0f22849c434d4eefbe561ea86d36d4d618b2140b8cb7ff1ea2a0e6` | FP64实虚、rank128、2hidden64、103040参数/824320B；仅此一个候选 |
| 实际Torch推理probe SHA | `3469dc585b3362c6d13ebbc9227bc649876f816e0f02f57a50d78403fcd8895a` | 16validation特征与真实Torch输出，FE冻结NumPy再配对<=1e-12 |

dataset raw包、全部逐对残差、labels、split hashes及source见[manifest摘要](records/dataset_model_manifest_v2.json)。raw数据/训练checkpoint/模型权重/基/失败packet在NN-Lab ignored artifacts，只提交轻量JSON/CSV/hash。完整source、input_original.dat、resolved_config、input/physical/source文本、run_manifest/run_summary和资源采样分别保存在本地results；[run index](records/run_index_v2.json)绑定其SHA。

## 划分和归一化

teacher参考用准确p4 Schur LU并恢复任意内部和端口载荷，逐对检查原native A4、port/internal、native与Schur恒等式；384对全部<=1e-10。矩阵相同但RHS来源明确：训练含seed420110的整段合成失败轨迹，剩余seed420200全空间随机非零内部/端口和制造解；validation为独立seed420300，heldout为整个实际physical_PH_b6轨迹和独立seed420400。phase/amp及同问题相邻轨迹完全属于同split，不跨角色随机切分。train/val/heldout固定256/64/64，没有在CPU上缩减。

每pair将raw凝聚RHS、解、full FE RHS和port RHS同除raw范数，并保存原始normalization_scale，零载荷scale=1；F4恢复实际幅值再审核，phase i、1e-3/1e3缩放均显式在heldout中。使用complex128数据、模型float64实虚双通道，未用FP16/TF32或松弛验算。F1实际A6/A4/内部/port接口先通过，后续p4-only身份与F1严格相同，非synthetic toy替代Maxwell。

F4 first16固定为physical、zero、真实内层r0/r32/r128/r256、physical phase/amp、未见内部only/portonly/mixed/phase/amp及manufactured载荷。输入只读heldout的full/port RHS和scale，不读teacher解/初值/系数；终测16一次用于各冻结候选评估后consumed，不能继续用它调参并称fresh heldout。剩余48heldout未作严格粗逆评估，不因teacher曾审核全部64而宣称64候选返回通过。

## 精确运行源码与隔离生命周期

| 阶段 | 真实clean source SHA | 库与对象生命周期 |
|---|---|---|
| 原F0 | `9934c2e08d017124ba70bdc86ec0c22f39ca792f` | 历史import/toy；[response_v1](../response_v1.md)保留 |
| F1成功接口 | `cca180f875bd22146f2d30fa4d004e372135dfbb` | 全p6/p4原作用/传递/恢复，固定B0失败方向；无global p4因子 |
| F2 teacher | `b72448bb2117a0221f041f1b47ac41049750a3c7` | 唯一offline global LU，destroy后worker退出且descendants清场 |
| F2 oracle | `d9de8ad69bfeeac4860e5187e1738c902a3d808e` | 同原p4、B0、streamed POD/原残差像，无global LU；退出后才训练 |
| F3 CPU训练 | `a221d881bae9405c98e351df2b0b9533582e6d50` | 隔离CPU-only ML无FE；300epochs完成，有载19.036s；退出后才候选 |
| F4三个候选 | `7216efa605bae155ee383fd716c0fae422448b52` | 同一clean源码、相同dat物理/hash/RHS组；FE只读冻结NumPy推理，无Torch/teacher因子驻留 |

此前4个F1实现/环境失败和F4-B0 enum解析失败均保留真实source/错误/资源，不冒充数值不收敛或覆盖成成功。enum错误发生在正式load前，仅局部修复后开始正式阶段；无参数扫描。后续交付/报告修正的HEAD不 retro-label 任一run source；文档publication HEAD由其实际push和render检查记录，不能称求解源码。

F0的[原空dataset/model manifest](records/dataset_model_manifest.json)为历史，当前事实为本页和v2记录。新模型没有production资格，不能以checkpoint存在、训练loss下降或oracle正信号替代严格p4返回；F5及official场/模态/功率not_run。


## V3 最新有限诊断（原V2正文保留）

V3只复用哈希绑定的旧0/10/11 RHS、失败state/0/32/128/256快照及原Q/冻结模型作诊断，未重训练/改变basis；新结构仅读取RHS，不读取old/teacher解作初值，零reduced start。结构source冻结后另选seed420620整族16项，数组与求解not_run，不称fresh终测。[未消费计划](records/unconsumed_test_plan_v3.json)。实际两个clean source见[run index](records/run_index_v3.json)，文档HEAD不替代。
