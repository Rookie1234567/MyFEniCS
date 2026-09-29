# V11：稳定输出头与变量投影的有界实测

本批沿用同一个 0.7 nm 三维缺口微型有限元模型。网络隐藏层产生边／面矩组成的 trace 方向，线性输出头决定这些方向的组合；变量投影原计划在每次改变隐藏层后，从原 Maxwell 方程重求输出头与全部端口。为防止在不可靠的线性头上训练，先检查一个已知解确在该空间内的制造问题能否回收。小系数见证通过，大系数见证在一次允许的数值修正后仍未通过，因此真实有限元变量投影梯度与隐藏更新按 Review V8 停止。独立同网格参考验证进一步确认原物理方程和散射场仍不合格。

| 固定对象／身份 | 实际值与证据 |
|---|---|
| 几何、离散、材料 | 0.7 nm、384 hex、Nédélec p3、h=0.175 nm、FE 34050、trace 18144、内部 13824、slave 2082、完整上20＋下20复端口；Si 来自 `SI_OPTICAL_CONSTANTS_USER_20260929_V1`，`n=0.999885140474+4.32477054e-6i`，`epsilon=n²`。 |
| 真正的算子／数据 | 原 physical SHA `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`，mode SHA `93795b53d7c5aef69af66b4ff0a56fa46515771f1ec43332ec929970270ea262`，action packet SHA `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454`；身份及完整 run 来源见[计划](records/plan_and_input_identity_v11.json)、[run index](records/run_index_v11.json)。 |
| 主候选 | seed420906 随机 hidden、原 3×64 tanh／8 载波／FP64 q15 batch8；8576 个 hidden 实参数、1560 个复输出系数和40个复端口。未读 NN7 权重或参考来初始化。 |
| 运行源码 | MAIN `a2cba71533edafb4fa1c701eae503e7ab526eac4`；唯一同分解修正 REPLAY 与独立 VERIFY `036e36ec637488b1baddd9b061c80c6f34cde254`。各自运行前均 clean；最后文档 HEAD 不是计算源码。 |
| 分类 | `STABLE_RECOVERY_OR_HEAD_GATE_FAILED`；同网格物理 `NOT_QUALIFIED`；实际 hidden 更新 **0**、FD 扰动点 **0**。 |

## S0–S2：为什么不能凭数值满秩继续训练

原随机隐藏特征矩阵 `P` 的列相关很强。新方法先做 nonpivoting economic Householder QR `P=ZR`，用原 `S` 对每列 `Z` 重算作用，再以 `gelsd/cond=1e-12` 在正交坐标求头，最后通过三角解回写真实 Torch 输出层，重新生成实际 trace，并由凝聚后的 `Hhat` 精确闭合全部40端口。这个步骤只改善计算坐标，不增加空间方向，也不能把数值满秩称为精确最优。`Hhat` 是40维原凝聚端口块，不是原 `Hp` 或全局 p4 逆。

```math
P=ZR,\qquad A=\bar S Z,\qquad c=\arg\min_c\|\bar b-Ac\|_2,\qquad R\gamma=c,\qquad \alpha(t)=H^{-1}(b_p-Ft).
```

| 同一固定空间的检查 | 真实值 | Gate／含义 |
|---|---:|---|
| `P` 列数／有效秩，`A` 列数／有效秩 | 1560/1560，1560/1560 | 数值满列秩；不证明实际回写达到驻点 |
| `P` QR 重建／`ZᴴZ−I` | 8.14e-16／6.47e-16 | 映射及正交运算通过 |
| `P` 奇异端点／比值 | 8.028e-10／20.200，约2.52e10 | 大系数敏感性背景；不是 `S` 条件数 |
| `Hhat` cond2／原端口配对差 | 13284.163／0 | ≤1e10、非零端口与原块身份合格 |
| M1 seed421101 小系数：raw／稳定原制造残差 | 3.822e-15／1.235e-14 | 稳定头≤1e-8、已知 `z` 差5.536e-13、齐次恢复9.258e-17，**通过**；raw 也通过 |
| M2 原V10-B0无标签大系数：raw／稳定初始残差 | 1.292e-7／3.118e-7 | 稳定头门限1e-8，**初始失败**；raw 亦失败 |
| M2 同一分解仅一次残差修正后 | 2.895180876e-8 | 虽改善约10.8倍，仍高于1e-8；`z` 差4.099e-10、齐次恢复8.64e-17分别通过 |
| 修正后真实物理 `t_net` 对 `Pγ`／`Pγ` 对 `Zc` | 2.461e-11／5.281e-11 | trace回写自身≤1e-8通过 |
| 修正后真实物理残差对薄LS预测／`Uᴴr` | 3.959830234e-8／9.622e-9 | 两者都须≤1e-8；前者**失败**，后者通过 |

M1/M2 的非零 trace 与 port RHS 均由原 action 对已知 `z` 作用产生，未用缓存 `W` 自验，也未混入真实入射 `b` 的端口常数。M2 的已知输出系数范数约1.296e5；物理候选修正后约1.278e5。三组非零原矩映射见证在 MAIN 候选求解之前完成，未重复 V10 的事后补核时序。保存的 `A` 在 REPLAY 用三次新原作用配对，误差≤1.049e-16；修正只重求同一分解的 M2 与物理头，无新 `A`、rank/cond 扫描或隐藏正则。具体 RHS hash、raw／稳定／修正、原方程尺度在[制造见证](records/manufactured_recovery_v11.json)和[输出头检查](records/stable_head_checks_v11.json)。

数值归因必须保留边界：M2 初始稳定头比 raw 差，修正后较 raw 好但仍未合格；这支持“大系数／条件数与回写或薄残差精度有关”的有限推断，**不证明**唯一根因。`P` 与 `A` 数值满秩、端口几乎精确、物理 `Uᴴr` 很小，仍不能掩盖实际网络残差与薄预测的固定原 `b` 差异。原方程 Schur 平台约0.798另表明本空间未提供合格物理解；当前不能把它全归咎于头精度。

初次 MAIN `stage_result.json` 的数值 `physical` 键被后续同名物理身份元数据覆盖，这是**结果封装错误**，不是数值运算通过。原数值行保留于 MAIN 的 ignored `varpro_progress.jsonl`，REPLAY 的 `physical_before` 另保存其主要标量；后续源只把身份键改为 `physical_identity`，没有修改 MAIN raw 或重跑其分解。compact 检查明确引用这些原记录，见[输出头检查](records/stable_head_checks_v11.json)。

## S3–S5：准入、真实场和物理量

小型复数非 Hermitian／非零端口／仿射 RHS 的变量投影梯度单元测试通过。真实 S3 要求每个扰动点重新构造 `P/A`、重求线性头、回写网络和闭合端口；因 S1 的 M2 与 S2 的实际残差差异未过 Gate，真实三方向 FD **未运行**。S4 L-BFGS 试探0、接受隐藏更新0；这是数值资格停止，不能声称变量投影梯度或隐藏学习机制已经失败，也不能绕过改用普通 Adam。S5 在候选冻结后用独立 FE 进程读取原 REF7 一次，未把参考回传求解。详见[梯度与未运行项](records/varpro_gradient_checks_v11.json)、[独立 Gate](records/qualification_and_dispatch_v11.json)。

| 固定真实物理 RHS／方法 | 原 Schur | 原 native | 固定 RHS port | 完整场 total E／scaled-curl 差 | 散射 E／scaled-curl 差 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| 历史 V10-B0 随机头 | 0.797324192 | 10.964503374 | 0.005822466 | 未在本批重测 | 0.732080／0.732146（历史） | 无资格；不同头机制及共享条件，非加速结论 |
| V11 初始正交头＋闭合端口 | 约0.797722 | 约0.309360 | 约舍入量级 | 本批未独立FE验算 | 本批未独立FE验算 | S1/S2失败，原方程未过1e-6 |
| V11 同分解修正后稳定基线 | **0.797721737837** | **0.309359506591** | **2.051e-19** | **0.0768362／0.0768486** | **0.7342568／0.7343616** | 原方程1e-6与同离散场1e-4均失败 |

修正后原增广0.309359506591、原 total 增广0.107347558964、独立 DOLFINx total native0.107347558965；恢复6.104e-13≤1e-10、slave-zero=0。Selected 复 E/H 相对差0.0855310/0.0669867，完整40复通道相对差0.0494152，逐项原键／极化／参考面与幅度见[通道CSV](records/channel_observables_v11.csv)。散射误差显著大于 total 场误差，不能用背景主导的 total 相对数替代散射验算。

| V11修正后未资格化功率诊断 | R_total | R00_s／R00_p | T_total | A_balance | A_volume | 能量闭合差 |
|---|---:|---|---:|---:|---:|---:|
| 原p3 micro，40通道、同参考面 | 0.0849662553 | 0.0849640599／1.28216e-7 | 0.7980459227 | 0.1169878220 | 0.0048548661 | **0.1121329560 > 1e-5** |

同mesh/p3 REF7 的 R_total/T_total/A_balance≈0.117645819/0.877047783/0.005306398。V11 的 R/T/A 对参考绝对差分别0.0326796/0.0790019/0.1116814，体吸收差0.000451532，逐通道功率最大差0.0790029；均不能称 official R/T/A。完整逐指标与原始 FE evidence 在[候选对照](records/candidate_comparison_v11.csv)、[run index](records/run_index_v11.json)。本批只有一个微型模型，没有 p/h、Full3D/Hybrid、M 或 MPI 对照；这些影响 unknown。没有新 p4 参考、p6/F5、最大几何、短波、GPU 或旧强逆复活。

## 完整成本、资源与证据边界

| shared-workstation 单阶段 | 独立 one-run dat／clean source | 含整树监督 wall 秒 | 同时采样过程树 RSS 峰 B | own swap B |
|---|---|---:|---:|---:|
| MAIN，P/Z/A、M1/M2与真实基线 | `v11_main.dat`／`a2cba715…` | 426.511501414 | 4668329984 | 0 |
| REPLAY，仅一次同分解修正 | `v11_replay.dat`／`036e36ec…` | 135.925127663 | 3764645888 | 0 |
| VERIFY，冻结后独立同离散FE审核 | `v11_verify.dat`／`036e36ec…` | 12.543487691 | 683417600 | 0 |

三段监督 wall 合计 **574.980116768 s**，含 outer launcher 的三段 wall 合计 **579.083391703 s**；同时树峰是最大值 **4668329984 B≈4.347 GiB**，不是阶段峰相加。事前 P/Z/R/A、分解副本、网络和端口缓存并存保守规划6092700024 B＜8 GiB。MAIN 中 `P` QR31.702s、新原S对Z的列作用142.138s、`A` QR32.913s、三个 `gelsd` 头29.343/29.454/28.385s；这些均嵌在426.512s中，**不再累加**。REPLAY 核心修正99.434s嵌在135.925s中。累计完整 P/A 构造1、头求解7、候选等效 S/Sᴴ 1583；VERIFY另有原S审核2次，FD0、试探0、接受0，均低于 Review V8 上限。[分阶段和旧有载账](records/resource_costs_v11.json)、[进度journal](records/varpro_progress_v11.jsonl)。

窗口从2026-09-29 22:58:57 UTC起，总截止次日02:58:57、重负载截止02:43:57；没有因上下文压缩重置。V6–V10历史有载 **11159.165418899036 s** 保留，仅加本批正式监督 wall 的可核对下界为 **11734.145535666961 s**；实现、测试、静态与交付时间在 elapsed 窗口内，不能假造为精确有载秒。结果提早收口，不用同一失败设置填满4小时。

启动前现场选 CPU0（不是永久保留核），邻进程仍在；MPI1、数学／Torch线程1、DataLoader0、自有锁、nice10/idle I/O、独立 FE/CPU-ML 与缓存。MemAvailable 948914786304 B，系统＋邻增长预留353748992000 B，磁盘自由3441577926656 B；使用16 GiB hard／12 GiB warn、自身swap0的0.5秒整树采样监督，全部后代清场。无cgroup委派，故不能把采样上限说成内核连续强制限额。未使用GPU、不操作邻任务；当时未见持续内存压力，缺邻任务同阶段对照，影响和无争用速度 **INCONCLUSIVE**。总费用标 `shared-workstation`，不宣称绝对零干扰或正式加速。

代码从构建开始没有候选在线 global p4 LU、完整 `S`／全局 FE CSR、正规方程、ILU/Riesz 逆、私有 audit CSR 或 hidden fallback；持有原局部恢复 packet、40维 `Hhat` 和显式薄 `P/Z/R/A` 及 QR/GELSD 工作区，故省去全局因子不等于零内存。原 A4/A6、MPC、材料、80之外的本模型40通道、原 task/review/历史负结果与普通默认未改。实际 source 与各数据 hash、precommitted clean、监督口径可在[run index](records/run_index_v11.json)逐项核对。

独立 checker 只读原数值字段重算：M1 true、M2 false、修正后 S1 false、S2 false、同离散 false；坏 saved success 标签／坏场／缺通道反例测试通过。最终 targeted pure-array 12 pytest、compileall、ML原矩测试另列于[测试](test_summary.md)；Review V8 实际 GitHub richText HTML 5表／5数学块、列数一致、review原文未改，证据见[渲染](records/review_render_check_v11.json)。结果页发布渲染另核，不用本地Markdown结构检查冒充网页显示。无 full repository pytest、MPI2/4 或 CI 声称。

**唯一下一最小建议，未实施：**固定同一算子、P/A、M2和实际网络写回，做一次有界浮点敏感性归因：分清原作用残差、薄LS残差与大系数回写舍入各贡献，并给出是否能在**不放宽 1e-8 Gate**、不改架构/rank/loss 的情况下可信地表示当前空间。须下一 review 决定具体精度和预算；不自动启动另一套训练或目标模型。最终0.7 nm／48h目标仍缺合格 micro 原方程与真实散射、独立离散精度和目标规模／步数／存储证据，均不能由此微型负结果外推。
