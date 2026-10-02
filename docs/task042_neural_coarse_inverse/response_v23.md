# Response V23：同一p1空间的作用像最小残差与全空间暖冷对照

按Review V20完成S作用像资格、D同残差粗比较、M四周期暖校正、Z八周期独立零trace及冻结后的唯一FE审核。六个去重状态0/6完整合格，M/Z新求解0/2原方程合格。MR单次最小残差性质通过，但未突破暖平台；零trace散射仍基本未求出。没有神经训练增量、严格同精度加速、目标0.7nm/48小时或merge资格。

本次保持1248个低阶来源的修正方向不变，先计算每个方向在原方程中的响应，再把这些响应正交化。这样可以在同一空间里选出使当前完整残差最小的一次修正，避免旧Galerkin校正只消去部分测试分量却放大完整残差。随后仍保留全部fine自由度运行GMRES。代价是一张大型薄像矩阵、全局薄QR、每次读U并做小三角解；单次最小化不保证完整场准确或后续迭代收敛。

## 固定身份与真实source

原Full3D模型固定0.7nm/384hex/p3/h0.175nm/q15，三维缺口、1度/azimuth0/s、双Floquet/Fourier-DtN；full34050、trace18144、interior13824、slave2082，top20+bottom20、z18184。T归一化、1248列和tau=0.13558083643793006均未改变；没有重建p1传递。

材料唯一canonical表 `input/materials/si_optical_constants_v1.json`，ID `SI_OPTICAL_CONSTANTS_USER_20260929_V1`。source字符串0.699999988仅明确alias至nominal0.7；实际Si n=0.999885140474+4.32477054e-6i，epsilon=n*n、mu=1；离线用户值原样使用，未插值或索要替代来源。

全部五个正式run source为 `0d64407e9ec8c5d0b1da947a17f7bc390b8ccd52`，运行前均clean。Review锚点 `5c91a8101644f09d6e6e1b45043ae5581394c0e9`，冻结base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。唯一分支 `task42_neural_coarse_inverse`，upstream `origin/task42_neural_coarse_inverse`，canonical linked worktree `/home/fenics/Projects/NN-Lab`、common Git `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git`；只有同分支安全fetch/ff与指定push。最终文档HEAD/实际push时刻由交付receipt和最终报告记录，不能替代以上run source。

physical SHA `2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de`、action NPZ SHA `9196edb807b534217d0c0eb78882125341342784a48ef20ebe2d9421fe636454`；T文件SHA `22e21cd840efb51d2dc66e556d85587088f406dce3221f564109a27b7b096fd8`，Ac文件SHA `d03304fba540afd66d63a00975b655158696d88301e4dd989cdf9e442674b6fc`；其余材料/modes、CSR成员、canonical masters、W/U/R/父状态/实际z均见[来源](outcomes/records/source_inventory_v23.json)、[QR](outcomes/records/setup_QR_v23.json)、[run index](outcomes/records/run_index_v23.json)。新记录引用旧manifest/hash，不再次复制完整旧recipe。

## 方法资格与求解结果

```math
A=\bar S,\quad A_c=T^HAT,\quad W=AT=UR,\quad U^HU=I,
\qquad G r=T A_c^{-1}T^Hr,\quad J r=T R^{-1}U^Hr.
```

MR指原残差最小化，不是Hermitian MINRES算法。U是方程作用像，T是trace空间；Hhat是原凝聚40×40端口块，不是Hp，F不假定Cᴴ。经济型nonpivoting complex128 Householder QR、固定1e-12小块安全阈值；不截列、扫描rank、造WᴴW/显式逆或fine投影方阵。

```math
B_Mr=\tau r+J(r-\tau Ar),\qquad \tau=0.13558083643793006,
\qquad D_{small}=U^HT,\quad D_{small}^HR=A_c.
```

满秩W不单独保证B_M可逆；Dsmall另外通过安全检查，2×2反射反例回归证明D=0时必须拒绝M/Z。R解固定一次三角求解。右外层实际为A(B_M(y))、M=None、每周期y0=0，t_new=t+B_M(y)。固定GMRES256/maxiter1/callback_type=pr_norm、相对容差0、atol=1e-8*norm(原完整b)，成功仍以旧oracle完整残差≤1e-6及全部物理门限判定。

一次1248列W构造耗时61.1547196159s；包含QR/小SVD/资格的分解计时49.359587188s，其中QR 24.936563968s、R/D小SVD 3.108270203/5.58966710791s为嵌套。QR重构7.22411343502e-16，U正交缺陷4.90908200276e-16；R sigma_min/max=0.000811704800798，Dsmall=0.0831859034424，均≥1e-12。8个真实复见证、TᴴW=Ac、DᴴR=Ac、MR驻点/JAT/复线性和旧S/SH配对通过；额外fine作用19≤160，W的1248列另计。

声明 **GLOBAL_TALL_IMAGE_QR_PRESENT**。每张W/U载荷362,299,392B（345.515625MiB）；R 24,920,064B，U+R 387,219,456B。W已释放常驻RAM但保留文件作独立证据，U/R各后续进程只读复用，Uᴴ用BLAS共轭转置而非每PC整阵conj复制。新增workspace规划1727684368B<2GiB，全树规划4948909840B<8GiB；不是RSS或目标规模资格。D另有一次旧Ac有界粗LU和固定一次残差精化，无fine/p4 LU/ILU、私有audit CSR、隐藏fallback或参考分解。历史通用raw标记global_factor_constructed=false语义过宽，本批不据此称factor-free；实际W/U/R与明确factor_status作为因子披露依据。

| 同一RHS的单次粗校正 | 原norm(r) | G后norm(r) | MR后norm(r) | G系数范数 | MR系数范数 |
|---|---|---|---|---|---|
| warm | 2.09020360196e-07 | 4.78673063639e-06 | 2.08995220317e-07 | 8.67995218903e-07 | 1.51823903037e-09 |
| zero | 0.0826782769485 | 0.135928133263 | 0.0783711518318 | 0.0153593994566 | 0.00471946792651 |


两RHS各一次G/J。暖G将原残差范数放大22.9007864683倍，尽管Tᴴ残差约1.33e-21；MR的Uᴴ残差约4.27e-23，完整残差仅下降0.0120274788484%。range(AT)能移除本次暖残差约0.0240535110943%的平方范数，这是由本批实际残差derived，不是历史参考误差的99%trace覆盖，也不是fine条件数。zero单次MR下降约5.20950033749%。MR≤min(G,零校正)不等式满足固定余量；两实际暖状态与薄预测差/norm(b)均≤1.154e-13<1e-11。两个暖修正都真正闭合40端口、保留一次内部特解并旧oracle审核，不是薄预测状态。

| 同0.7nm/p3；无量纲measured | 周期 | Arnoldi步 | 原rho起点 | 原rho最终 | native最终 | 周期S+SH | 监督wall(s) | 停止 |
|---|---|---|---|---|---|---|---|---|
| M | 4 | 1024 | 2.5281170328e-06 | 2.50771436526e-06 | 9.72501113856e-07 | 2096 | 299.147204566 | FIXED_PROGRESS_RULE_STOP |
| Z | 8 | 2048 | 1 | 0.068113177161 | 0.0264145476792 | 4192 | 563.193281008 | FIXED_PROGRESS_RULE_STOP |


M真实四周期下降约0.807030183939%，不足10%，FIXED_PROGRESS_RULE_STOP；Z首4周期rho=0.0690781713672，后4降至0.0681131771610，约1.397%<20%，同规则停止。原方程通过点0，抛光not_run。D校正不作为M/Z初值，M固定V21 C-FINAL，Z独立零trace进程，不读warm/旧Q/网络权重/循环方向；端口和内部特解正常保留。普通数值负结果没有触发增迭代、改tau或换PC。

V22 N/P/Z原记录只读复用，共同周期的每周期524个fine作用前缀可直接配对P↔M、Z↔Z，不插值。4周期新M rho2.507714365e-6，旧P2.514297762e-6、N2.509882028e-6，均不合格。Z4新0.06908优于旧0.10074，但Z8新0.06811高于旧0.06432，后续新路线不准入，不能预测继续结果。新W/QR完整设置131.5988s计入，T构造及暖链上游成本仍保留；共享wall条件不同，不能称无争用加速。见[共同前缀](outcomes/records/historical_control_prefix_v23.csv)、[历史hash](outcomes/records/historical_control_identity_v23.json)。

## 冻结后的原方程与完整场

全部求解/选择/hash冻结且演员退出后，唯一VERIFY在一次FE环境读取REF7；6个去重状态，没有新参考LU、误差投影或回训。其实际Schur=6.42414650329e-12、native=3.01796304396e-12、独立total-native=1.43744486619e-12，小残差保留，没有置零。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 散射E≤1e-4 | 散射H/curl≤1e-4 | 单通道功率差≤1e-6 | 完整资格 |
|---|---|---|---|---|---|---|
| V21-C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | FAIL |
| D-G | 5.78958683346e-05 | 2.24522366775e-05 | 7.78244591217e-05 | 7.78408347361e-05 | 1.61837477908e-06 | FAIL |
| D-MR | 2.52781296425e-06 | 9.80295427727e-07 | 7.81607966537e-05 | 7.81769594619e-05 | 1.71964931439e-06 | FAIL |
| M-FINAL | 2.50771436526e-06 | 9.72501113856e-07 | 7.80593538145e-05 | 7.80755355416e-05 | 1.69973146436e-06 | FAIL |
| Z-FINAL | 0.068113177161 | 0.0264145476792 | 0.989143298805 | 0.989118901047 | 0.00910569035662 | FAIL |
| Z-CYCLE4 | 0.0690781713672 | 0.0267887760816 | 0.998538390324 | 0.998515077488 | 0.00940673781215 | FAIL |


暖M的native过限不替代Schur，Schur仍约2.5倍门限，单通道功率仍约1.7倍门限。D-G原残差大幅上升但散射E略降；D-MR残差最小却场几乎不变，不能将原残差和场当同一个指标。Z-FINAL散射E/H误差约0.989，虽然原rho从1降到0.068，仍基本漏掉散射场，不能称求解成功。

| 状态 | total E≤1e-4 | total H/curl≤1e-4 | selected E≤1e-4 | selected H≤1e-4 | 40复振幅≤1e-4 | 能量≤1e-5 |
|---|---|---|---|---|---|---|
| V21-C-FINAL | 8.17912356651e-06 | 8.18097018782e-06 | 9.08427294495e-06 | 7.16511649663e-06 | 3.21045778938e-06 | 1.9398597273e-06 |
| D-G | 8.14392682728e-06 | 8.14579503936e-06 | 9.05170019067e-06 | 7.12093109447e-06 | 3.20811546356e-06 | 1.78399702588e-06 |
| D-MR | 8.17912280912e-06 | 8.18096941965e-06 | 9.08427240005e-06 | 7.16510841587e-06 | 3.21041333123e-06 | 1.93987792052e-06 |
| M-FINAL | 8.16850734106e-06 | 8.17035572994e-06 | 9.06865522628e-06 | 7.16067080954e-06 | 3.1822030152e-06 | 1.92258819642e-06 |
| Z-FINAL | 0.103508726409 | 0.103508137661 | 0.103514172629 | 0.103503374913 | 0.103375517216 | 0.0114227606457 |
| Z-CYCLE4 | 0.104491874108 | 0.104491417551 | 0.104490397409 | 0.10447262791 | 0.104329053975 | 0.0119690710752 |


total/scattered、系数与场范数、native与独立total-native分开。原mu=1下H=curl(E)/(i*k0*mu)，全域scaled-curl相对误差给出相应H的derived等价指标；selected复E/H独立保留。所有状态的恢复/原恒等式≤1e-10、slave=0、完整端口审核通过，不代表原方程合格。

| UNQUALIFIED_DIAGNOSTIC | R00_s | R00_p | R00_total | R_total | T_total | A_balance | A_volume |
|---|---|---|---|---|---|---|---|
| V21-C-FINAL | 0.117644973437 | 7.01536540619e-13 | 0.117644973438 | 0.117646030384 | 0.87704950259 | 0.00530446702554 | 0.00530640688527 |
| D-G | 0.11764491946 | 7.13109039526e-13 | 0.117644919461 | 0.117645976407 | 0.87704940132 | 0.00530462227318 | 0.00530640627021 |
| D-MR | 0.117644973451 | 7.01543696094e-13 | 0.117644973451 | 0.117646030398 | 0.877049502595 | 0.00530446700734 | 0.00530640688526 |
| M-FINAL | 0.117644976153 | 6.89226016545e-13 | 0.117644976154 | 0.117646033101 | 0.877049482676 | 0.00530448422283 | 0.00530640681102 |
| Z-FINAL | 0.108539072031 | 2.82530436119e-17 | 0.108539072031 | 0.1085405878 | 0.874785206547 | 0.0166742056535 | 0.00525144500778 |
| Z-CYCLE4 | 0.108238024575 | 5.66793337233e-18 | 0.108238024575 | 0.108238853737 | 0.874543523448 | 0.0172176228154 | 0.00524855174019 |


全部R/T/A是UNQUALIFIED_DIAGNOSTIC，不发布official场结果。40复振幅/原键/极化/参考面逐项保留；240项逐通道功率用原批准公式从保存复振幅离线derived，与原max/R/T配对≤1e-12。没有幅相校准、重归一化或四舍五入过Gate。同mesh/p3参考只检查同离散一致性，不是离散误差、continuum或目标模型资格。见[场](outcomes/records/field_checks_v23.json)、[通道](outcomes/records/field_channels_v23.csv)、[逐通道功率](outcomes/records/per_channel_power_v23.csv)。

## 全过程资源、费用与边界

不可刷新start2026-10-02T10:14:18.868457Z，heavy stop13:44:18.868457Z，总deadline14:14:18.868457Z。首次身份检查钟10:13:45Z，另有33.868s前置低负载检查，不隐去；配对窗口未重置。实现/失败/测试/等待/求解/验证/交付都包含在实际elapsed。数值队列在11:05:14.967518Z清场并立刻保存最小result/cost/response，独立验证11:08:01.192986Z清场；最后实际commit/push/交付时间单列receipt，不以准备时刻替代。

| stage | 实际CPU | 监督wall(s) | launch wall(s) | 采样同时树峰(B) | S+SH | B_M | R三角解 | 原audit |
|---|---|---|---|---|---|---|---|---|
| SETUP | 0 | 131.598753646 | 132.992815365 | 1965875200 | 1267 | 4 | 14 | 0 |
| COMPARE | 0 | 12.429613836 | 13.776490887 | 1430302720 | 21 | 0 | 2 | 3 |
| M | 0 | 299.147204566 | 300.517650007 | 1444290560 | 2106 | 1040 | 1040 | 5 |
| Z | 0 | 563.193281008 | 564.568379816 | 1312030720 | 4202 | 2076 | 2076 | 9 |
| VERIFY | 0 | 55.061736452 | 56.4507581979 | 734531584 | 7 | 0 | 0 | 7 |


正式监督wall合计1061.43058951s，launch 1068.30609427s；外层solve/verify监督包含子阶段，不能重复相加。R小解包含Uᴴ作用，M/Z的PC/R计时嵌套不相加；QR、SVD和audit/I/O包含在actor全过程。首次预算快照辅助监督103.611891929s，失败/最后回归/派生检查费用以刷新后的[成本record](outcomes/records/resource_costs_v23.json)为准，不补造未采样的旧费用。历史formal研发下界增至75124.917593s；不是一条成功解的部署时长，暖链精确per-solution上游拆账仍unknown。T原构造约495.33s、原packet/旧基/LSQR与V21C均不能抹掉，零trace也不是从几何开始的fresh run。

全树同时采样峰2061123584B（1.91957092285GiB），包含外层launcher/worker/BLAS/全部后代，不是数组载荷或阶段峰之和。ownswap0/VRAM0，原artifact快照815545453B<2GiB；W/U/R、滚动状态、大日志与可写缓存全部在NN-Lab ignored目录。S/D/M/Z/V实际均现场选择CPU0，其SMT siblings实际仅[0]、无忙核心共享；编号不作为今后固定核。MPI1、数学/实测OpenBLAS1、Loader0、GPU隐藏，自身nice10/ionice idle，不改邻任务。

原系统max(128GiB,10%effective total)、邻增长128GiB和自身16GiB余量、磁盘≥50GiB、PSI full avg10≥0.1百分数连续3次5秒与0.5秒整树监督保持。没有delegated可写cgroup，16GiB是完整树采样停止上限，不称kernel连续硬限额。数值PSI full avg10最大0，无资源停止/重入/冷却；邻任务可比阶段因果影响INCONCLUSIVE，不承诺绝对零干扰。所有费用shared-workstation。

全批charged S+SH=7603/32000、B_M=3120/15000、R三角解=3132/16000、audit=24/120、FE状态6/10。W/QR各1、R/D小SVD各1；G显式L/U pass8，gecon内部次数unknown，沿旧合格LAPACK模型保守上界22另列，不伪造成实测。没有正式数值修复或重放。R01小测试event签名，R02ignored collector括号，R03离线功率reader误用pure activation，R04静态检查首次自引用尚未生成的输出链接：只作局部修复，失败成本保留，未重复FE；根因预算4/4，保守修复时长上界合计600s<2400。精确辅助编辑开始未知保持unknown，不猜填。

| 未运行项 | 原因 |
|---|---|
| M第5–16周期 | 4周期降幅0.807%<10% |
| Z第9–32周期 | 后4周期降幅约1.397%<20% |
| FIRST_PASS抛光 | 无原方程通过点 |
| 新p4参考/最大模型/其他波长/GPU/NN训练/ILU或tau/rank扫描 | 合同边界 |
| 重复参考误差投影、原V22传递/控制campaign | 禁止或优先hash复用 |
| GitHub视觉资格 | 精确页面Cache miss；NOT_VERIFIED |


最终相关pure-array/真实dat接线/事务/读取白名单/奇异反例/截止清场回归及记录篡改反例见[测试](outcomes/records/test_results_v23.json)。五实际dat已实现并validate，正式S/D/M/Z/V均实际one-run。Ruff模块未安装，不改环境；full pytest/MPI2/4/CI/旧campaign not_run。原代码ActionPacket/recover/uncondensed/audit的数学实现未重定向到class64；共享IO/Stage只加保留原默认的显式参数，并有旧pure回归。本地GFM表格/围栏/链接/compile/diff与旧历史字节保护见[静态](outcomes/records/static_checks_v23.json)，旧总账checker问题与review起点逐项相同，不做全仓清理。GitHub精确review/结果页无视觉证据，**NOT_VERIFIED**；本地结构不替代视觉。

## 原因判别和唯一下一建议

| 判别问题 | 现有证据 | 结论与边界 |
|---|---|---|
| 传递/端口/原作用接线是否错误 | 复用T/Ac成员hash、8原作用见证、QR/R/D、真实native/恢复配对 | 本批Gate通过；未发现这类错误 |
| Galerkin与MR的测试目标是否不同 | G消去Tᴴr但暖norm放大22.90倍；MR消去Uᴴr但仅降0.012% | 同空间测试目标确有差异；单次MR更稳 |
| 同T+scalar fine是否足够 | M4未破平台；Z8原方程及散射失败 | 本固定配置有限负结果，收口；不是所有p/multilevel无效 |
| fine谱/唯一根因/更强细层作用收益 | 没有做fine谱或新PC试验 | unknown/INCONCLUSIVE，不外推 |
| 神经训练贡献/目标2TB与48h | 本批无hidden训练、micro未合格、历史费用不完整 | 未证明；不以QR或小内存充当目标资格 |


唯一下一建议：在相同冻结T/40端口下，预登记一套按FE邻接构造的固定p3局部细层作用，替换目前的标量tau项；先验证原作用/容量/线性与完整fine方向，再仅做最多4个暖及零trace周期，与本批scalar-fine控制配对。依据是本批AT作用像只覆盖约0.024%的暖残差平方范数，单次左测试改换可信却M仍停滞、Z散射仍遗漏；这支持检验细层作用是否不足，但不证明它是唯一根因。该建议尚未执行，不自动调patch/ordering/shift、重开p4或扩大模型，需下一review明确合同。

[完整证据导航](outcomes/p1_image_minres_comparison_v23.md)、[逐周期](outcomes/records/cycle_history_v23.csv)、[journal](outcomes/records/progress_journal_v23.jsonl)。本批已清场，等待ChatGPT review；不merge、不继续数值队列。
