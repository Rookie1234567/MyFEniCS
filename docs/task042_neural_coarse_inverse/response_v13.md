# Response V13：切向核验通过，联合隐藏／输出头更新只有极小的目标函数改善

本批已按 [Review V10](review_report_v10.md) 完成 `V13_TANGENT_SCALE_AND_HEAD_COMPENSATION` 的 A→B→C→D。新方法先计算“参数改变一点，完整有限元 trace 会怎样改变”，再让输出头同步补偿隐藏层变化，避免只破坏原来大系数之间的抵消。**固定头的三个切向通过新核验，联合切向中两个可用；C 实际接受1次隐藏／输出头联合更新，B 接受0次。原方程与场仍不合格，结论为 `OBJECTIVE_ONLY_IMPROVEMENT`，没有取得神经求解增量或最终0.7 nm／48小时资格。**旧 V11 的 `1e-8` 头 Gate、V12 标量 FD Gate 和全部负结果不变。

| 身份／执行边界 | 实际情况与证据 |
|---|---|
| 分支／目录／upstream | `task42_neural_coarse_inverse`；`/home/fenics/Projects/NN-Lab` canonical linked worktree；`origin/task42_neural_coarse_inverse`。origin 为 `git@github-myfenics:Rookie1234567/MyFEniCS.git`，common Git directory 为 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`。 |
| 历史关系 | 干净 V12 `0b81d4cdad2dd2e3c21a68e60b14c35fdc897337` 安全快进 Review `fb994b337960c89d2e70afc93707595258b3bb60`；冻结 base `ccd357885f7f9be84efe3be07868cc94f13d93fc` 和初始任务提交均是本分支祖先。没有回退、改其他 worktree、merge 或 rebase。最终精确文档 HEAD 在推送后 Git 报告中给出。 |
| 真正运行源码 | A、B、首次 C：`978a59efeae9891a848c5fac581ec32e4fc9a5b8`；**实际接受候选：`33f7d613b1341fa585f0324ead6039bf28211fff`**；记录恢复与独立 D：`7615baae2f0d75fbc47c05be392b35ef2878c431`。最后的 checker／文档 HEAD 不代替这些 source。 |
| 物理与数组 | 原0.7 nm／384hex／Nédélec p3／q15／完整40端口；起点是 V12 `INITIAL_V11_CORRECTED`，并核对同一 V11 参数。材料表及 physical/mode/action hash 不变，见 [预登记身份](outcomes/records/plan_and_input_identity_v13.json)。没有使用 M2、NN7 或参考拟合头作初值。 |
| 运行入口 | 四个规定 one-run dat 均已实现并执行；额外一次显式 opt-in 的 C 向量 Taylor 尺度复核、一次仅恢复已保存记录的 dat。六次运行及失败均在 [run index](outcomes/records/run_index_v13.json)。 |

A 用独立逐层 tanh 切向递推，经全部载波、边／面矩、Piola、orientation 与 MPC 得到完整 trace 一阶变化；端口导数采用齐次 `-Hhat^{-1}F dt`，没有混入物理 RHS。三个方向在相邻尺度的向量中心差分相对差均小于 `1e-5`；`h=1e-4` 时分别约 `1.82e-10 / 2.40e-10 / 3.47e-10`。真实损失 dual 的 JVP/VJP 运算尺度相对差约 `5.2e-18` 至 `1.7e-17`；结果尺度相对差约 `2.2e-9` 至 `2.5e-8`，两种口径及相消都保留。端口／齐次恢复恒等式约 `1e-16`。这是新的 `TANGENT_VECTOR_VERIFIED`，**不是旧 FD 或精确 VarPro 通过**。[完整切向证据](outcomes/records/tangent_identity_checks_v13.json)。

B 使用原作用计算方向斜率与曲率。起点观测分辨率 `delta_J=2.03096e-13`；三个固定头方向的最佳线性预测收益只有 `1.32e-17 / 1.85e-17 / 1.82e-16`，小于规定的 `2.03096e-11` 门限。因此 B 保存尺度表后**0次试探、0次接受**，直接进入独立 C；这只否定本批这三个固定头方向，没有宣称所有隐藏方向无效。[尺度CSV](outcomes/records/directional_scale_v13.csv)。

C 从同一起点复用同 hidden 的 `P/A`，重建非 pivoting economic QR 并做三列真实原作用核验；`P/A` 数值秩都是 **1560**，固定 GELSD／cond=`1e-12`，一次3-RHS薄分解。`Hhat` 条件数约 `13284`；三角补偿缺陷 `2.32e-14`。输出补偿把原作用响应范数约 `4.35e4 / 4.97e4 / 1.10e6` 降到 `0.0116 / 0.0108 / 0.131`，但必须再核验实际联合 JVP，不能只信薄矩阵相减。

首次 C 的两档联合向量检查没有稳定区，负记录保留。按观察到的较小步长相消，**预登记且仅进行一次**相邻较大尺度复核，没有放宽 `1e-5`、重分解、读参考或重置计数；方向421201仍失败，421202与梯度方向通过。由这两个实际联合列求实数小最小二乘后，共5个真实网络试探，前4个拒绝、第5个接受：hidden 改变量 `3.26022e-6`，head 改变量 `1.39398`，真实损失 `0.3181799855089551 → 0.31817975803965803`；实际下降 `2.27469e-7`，预测下降 `2.81119e-7`，比值 `0.80916`。相对下降只有 **`7.14908e-7`**，低于下一轮所需 `1e-4`，故第2／3步未运行。[全部试探及独立重审](outcomes/records/coupled_step_history_v13.jsonl)。

同 head 更新、hidden 不变的 twin 损失为 **282.766917**，Schur/native 为 **23.78096／9.22234**。这说明此步需要两组参数同步改变才能维持方程抵消；联合候选的场误差几乎不变，因此不能把它称为有用的隐藏学习收益，也没有按参考结果改选 twin。

| D：同mesh/p3，冻结后3个状态；measured、无量纲 | 原点 | 接受联合点 | head-only twin | 原严格限值 |
|---|---:|---:|---:|---:|
| 原 Schur 相对残差 | 0.797721738 | **0.797721453** | 23.7809553 | `1e-6` |
| 原 native／增广相对残差 | 0.309359507 | **0.309359396** | 9.22234439 | `1e-6` |
| 散射 E L2／scaled-curl 相对误差 | 0.734256809／0.734361587 | **0.734256339／0.734361116** | 0.731445461／0.731535615 | `1e-4` |
| total E L2／scaled-curl；后者也核对本模型 H | 0.076836175／0.076848597 | **0.076836125／0.076848548** | 0.076541982／0.076552868 | `1e-4` |
| selected 复 E／H 相对误差 | 0.085531022／0.066986741 | **0.085530968／0.066986699** | 0.085183893／0.066798707 | `1e-4` |
| 完整40复通道相对误差 | 0.049415152 | **0.049415129** | 0.077861581 | `1e-4` |
| 能量闭合误差 | 0.112132956 | **0.112132933** | 0.103077894 | `1e-5` |

接受点的固定 RHS 端口 `1.46e-16`、恢复 `6.10e-13`、identity `6.60e-13`、slave-zero虽合格，不能替代上表整体失败。R/T/A_balance/A_volume=`0.084966252 / 0.798045949 / 0.116987799 / 0.004854866` 全部仅 **未资格化诊断**；各功率相对参考的绝对差亦失败，无新 official R/T/A。D 一次 FE 环境在求解队列冻结后才读旧 REF7，未重新 LU、未回传参考，之后没有回训。[场与功率CSV](outcomes/records/candidate_comparison_v13.csv)、[40通道原键／极化／参考面](outcomes/records/channel_observables_v13.csv)、[独立 Gate](outcomes/records/qualification_and_dispatch_v13.json)。

C 在实际候选已保存后，末尾 JSON 写入遇到 `mappingproxy` 序列化错误。失败进程与全部试探原始证据保留；**1次最小实现修复**只转换冻结身份对象，随后重读已有参数／向量进行一致性与原审核，未重做 QR、LS、方向、FD 或试探。原小实 LS 系数列表在失败写入时未保存，明确 `unknown`，不猜填；失败 run 的逐作用计时亦 unknown，44次 S/Sᴴ调用仅由原 source 与 journal 推导，单列 derived。接受候选 source 仍为 `33f7d…`，不是恢复 source。

六次正式监督 wall 合计 **243.725626 s**（含失败、恢复、验证）；最大同时采样整树 RSS **2852761600 B≈2.657 GiB**、own swap0、VRAM0，均清场。一次薄补偿进程69.903 s，其中 QR 44.754 s、QR+LS 69.756 s为嵌套计时，不重复加到全流程。正式计数为前向93、JVP9、VJP9、FD扰动48、P/A新构建0、薄分解1／RHS3、小实LS1、audit24；S/Sᴴ合计149（105 measured＋44 derived）。合成小测试额外2个向量扰动也列入总量50，仍小于60。[资源、辅助测试、不可刷新窗口和历史账](outcomes/records/resource_costs_v13.json)。V6起可核正式有载下界升至 **12160.139323 s**，历史辅助未知仍未知；本批总elapsed含研发／交付，不能与243.726 s混称。

全部成本标 `shared-workstation`。六次各自现场选核均为CPU0，MPI1、数学／Torch intra/inter线程1、DataLoader0；独立 FE／CPU ML 环境及缓存、自有锁、16/12 GiB树监督保持。没有 cgroup 委派，实际是独立0.5 s采样 watchdog，不能声称连续内核限额。未观测持续内存 PSI 压力，缺少邻任务可比阶段速度指标，影响与无争用加速均 `INCONCLUSIVE`；未修改邻任务、环境、亲和性、watchdog或锁。候选没有构造完整全局 S/CSR、global p4 LU、正规方程、ILU/Riesz逆或 fallback；薄 P/Z/R/A与分解 workspace 都纳入全过程峰值。

独立 checker 从 raw 数值重算接受、切向、gamma回写、40通道与物理资格；`EVIDENCE_CONSISTENT` 仅说明记录自洽，不是求解成功。相关最终 pure-array、反例与监督测试及 ML小测试、compileall、dat 接线见 [测试](outcomes/test_summary.md)。GitHub表格／公式的实际 server richText 与本地源码检查分别记录，无浏览器像素证据不宣称视觉核验。[完整研究记录](outcomes/tangent_scale_head_compensation_v13.md)。

唯一下一建议，**尚未实施、需新 review 授权**：研究一种在正向求值时直接保持输出坐标稳定的 trace 参数化，避免经条件比约 `2.52e10` 的旧 P／R回写成巨大相消原始系数，再改变 hidden。证据支持检查这一表示机制，尚不证明它能解决全局方程困难；不再自动重复同配置切向／缩步循环，不扩大网络或模型，不重开 p4 强逆。完成交付后只推送本执行分支、清场并等待 review，不 merge。
