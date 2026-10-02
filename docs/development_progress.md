# V24续行记录：账户接口及执行审批已恢复

2026-10-02T14:07Z之后实际只读主机核验通过：新候选核CPU15、PSI full avg10=0、原系统/邻增长余量和磁盘Gate通过。周额度用尽时允许使用现有余额；明确禁止使用重置卡，未调用重置功能。以下认证阻塞是早先真实历史，保留原始失败；本批现继续原Review V21队列，原heavy-stop15:34:23.502588Z、deadline16:04:23.502588Z保持。当前真实数值仍未运行，后续来源与计数由正式run绑定。

# Task042 V24 / Review V21：实现已提交，正式数值执行受认证阻塞

本轮已实现固定八块局部完整LU与同规格粗层配对的数值核、角色reader、有限队列和六个one-run入口。最终小模型定向回归28 passed，六入口均validate；正式SETUP和LW/LCW/LZ/LCZ/VERIFY均NOT_RUN。首次队列未通过空闲物理核准入，数值actor未创建；有界复核找到核后，启动重试因自动审批服务令牌刷新403而未执行。这不是方法的数值负结果；没有新的原方程/场/功率资格或神经增量。

局部块解旨在每次修正中考虑一组相邻未知量的完整耦合，粗层再处理同一低阶空间中的剩余响应。收益尚待真实试验，代价为局部LU/三角解、粗矩阵读取及原算子作用。当前真实局部矩阵、LU和D_L均未构造，不称它们已存在或factor-free。

| 项目 | 本轮实际证据／限制 |
|---|---|
| 原模型 | 0.7nm/384hex/p3/q15/完整40端口；原材料/方程保持 |
| 实现source | 370b7bbe2455448b320ca4272eb62950e4715ecc；尚无formal run source |
| 定向回归／入口 | 28 passed、2个已消费旧用例deselected；6/6 valid |
| 八块实际因子／周期／审核 | 0／0／0；真实资格NOT_RUN |
| 规划容量 | 5709615024B≤8GiB；矩阵+LU1354430592B≤2GiB；derived非RSS |
| 已监督小测试／准入 | 43.5801978582s；树峰156880896B，ownswap/VRAM0；非部署峰 |
| 原方程、E/H、通道和R/T/A | 没有新值；既有负结果保持 |
| 截止 | start12:04:23.502588Z；heavy15:34:23.502588Z；total16:04:23.502588Z，不刷新 |
| Git | 实现ahead1；认证故障后的交付文件本地待commit/push，未伪称已推送 |

唯一下一建议：恢复Codex客户端认证后，原窗口仍有效且fresh资源准入通过时继续已验证的原队列；窗口耗尽则等待下一review明确新的时间窗口，不扩大数值范围。

[本地待提交Response](task042_neural_coarse_inverse/response_v24.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v24.json)。
以下历史正文逐字保留；旧“当前”只指其当时阶段。

# Task042 V23／作用像最小残差对照已收口

按Review V20完成S作用像资格、D同残差粗比较、M四周期暖校正、Z八周期独立零trace及冻结后的唯一FE审核。六个去重状态0/6完整合格，M/Z新求解0/2原方程合格。MR单次最小残差性质通过，但未突破暖平台；零trace散射仍基本未求出。没有神经训练增量、严格同精度加速、目标0.7nm/48小时或merge资格。

本次保持1248个低阶来源的修正方向不变，先计算每个方向在原方程中的响应，再把这些响应正交化。这样可以在同一空间里选出使当前完整残差最小的一次修正，避免旧Galerkin校正只消去部分测试分量却放大完整残差。随后仍保留全部fine自由度运行GMRES。代价是一张大型薄像矩阵、全局薄QR、每次读U并做小三角解；单次最小化不保证完整场准确或后续迭代收敛。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 散射E≤1e-4 | 散射H/curl≤1e-4 | 单通道功率差≤1e-6 | 完整资格 |
|---|---|---|---|---|---|---|
| V21-C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | FAIL |
| D-G | 5.78958683346e-05 | 2.24522366775e-05 | 7.78244591217e-05 | 7.78408347361e-05 | 1.61837477908e-06 | FAIL |
| D-MR | 2.52781296425e-06 | 9.80295427727e-07 | 7.81607966537e-05 | 7.81769594619e-05 | 1.71964931439e-06 | FAIL |
| M-FINAL | 2.50771436526e-06 | 9.72501113856e-07 | 7.80593538145e-05 | 7.80755355416e-05 | 1.69973146436e-06 | FAIL |
| Z-FINAL | 0.068113177161 | 0.0264145476792 | 0.989143298805 | 0.989118901047 | 0.00910569035662 | FAIL |
| Z-CYCLE4 | 0.0690781713672 | 0.0267887760816 | 0.998538390324 | 0.998515077488 | 0.00940673781215 | FAIL |


GLOBAL_TALL_IMAGE_QR_PRESENT；同T1248/tau、40端口，raw与derived分开。实际source `0d64407e9ec8c5d0b1da947a17f7bc390b8ccd52`，正式wall1061.43058951s，历史下界75124.917593s，树峰2061123584B。暖上游精确per-solution账unknown；零trace不是geometry-to-solution fresh。

唯一下一建议：在相同冻结T/40端口下，预登记一套按FE邻接构造的固定p3局部细层作用，替换目前的标量tau项；先验证原作用/容量/线性与完整fine方向，再仅做最多4个暖及零trace周期，与本批scalar-fine控制配对。依据是本批AT作用像只覆盖约0.024%的暖残差平方范数，单次左测试改换可信却M仍停滞、Z散射仍遗漏；这支持检验细层作用是否不足，但不证明它是唯一根因。该建议尚未执行，不自动调patch/ordering/shift、重开p4或扩大模型，需下一review明确合同。

[Response](task042_neural_coarse_inverse/response_v23.md)、[Gate](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v23.json)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v23.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# Task042 V22项目进展／research-only

本批按Review V19完成真实p1传递、固定粗层与PC资格、无PC暖对照N、PC暖校正P、独立零trace路线Z，以及冻结后的独立FE审核V。条件T未准入。原方程合格0/3，新候选完整同离散资格0/3；连同历史暖参照，审核0/4。没有新合格解、神经训练增量或同严格精度加速，最终0.7nm大模型/48小时仍NOT_QUALIFIED。

本次让低阶有限元场提供一组可跨单元耦合的修正方向：先把真正的p1边/面矩插值到原p3有限元空间，再取独立trace。将原p3方程投影到这些方向，得到1248阶小粗矩阵；解粗矩阵后仍保留全部fine方向继续GMRES。它改变每次残差校正，不改变原有限元方程。收益候选是减少困难方向的搜索；代价是真实传递构造、一个有容量上限的全局粗LU、每次额外fine作用与粗解。结果没有显示本固定配置能突破暖残差平台。

| 路线 | 完整周期 | Arnoldi内步 | 原rho起点 | 原rho最终 | native最终 | S+SH | 监督wall(s) | 真实停止原因 |
|---|---|---|---|---|---|---|---|---|
| N | 4 | 1024 | 2.5281170328e-06 | 2.50988202767e-06 | 9.73341741358e-07 | 1060 | 142.759495938 | FIXED_CYCLE_LIMIT |
| P | 4 | 1024 | 2.5281170328e-06 | 2.51429776221e-06 | 9.75054180268e-07 | 2106 | 361.332815065 | FIXED_PROGRESS_RULE_STOP |
| Z | 32 | 8192 | 1 | 0.00411726221107 | 0.00159668985526 | 16778 | 2001.9549088 | FIXED_CYCLE_LIMIT |

唯一下一建议：在同一冻结T、同一暖点原残差上，仅比较一次原作用像最小残差粗校正与当前Galerkin粗校正。前者直接用barS*T的薄QR求能减少当前原残差的T系数，保留原40端口及完整fine方向；不读REF7，不造正规方程，不改T/rank/tau或扫参数。目的是区分“同一粗空间中的左测试/粗细耦合选择”与“必须增加空间”这两个可能性。依据是约99%的trace误差平方范数已有表示，但其两个分量的原A作用约为完整误差作用的2448倍并抵消；这尚不证明唯一根因或病态。本批未实施，须下一review另行授权。

[Response](task042_neural_coarse_inverse/response_v22.md)、[结果](task042_neural_coarse_inverse/outcomes/p1_trace_galerkin_correction_v22.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v22.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# Task042 V21项目回顾

按Review V18执行D0、A、B、C和冻结后的独立V（B存在下述历史向量读取缺口），完整资格 **0/5**，分类 **NOT_QUALIFIED**。B/C未取得完整有限元资格；不宣称完整求解、神经训练增量或同严格精度加速。

本轮分别改变两步：把完全相同类别的局部矩阵按最多64个单元一起乘，减少每次重复展开；然后用固定GCROT配置保留少量修正方向及其方程作用，检验是否减少后续重复搜索。前者是精确作用的工程优化，后者是线性残差修正；均未训练隐藏层或改原有限元方程。代价包括类别缓存、最多33对回收向量、内部Krylov向量、副本、端口闭合、逐周期原审核与保存。

原0.7nm、384hex/p3/h0.175/q15、双Floquet、top20+bottom20通道保持；trace18144、内部13824、slave2082、完整z18184。Si从canonical用户表离线读取：n=0.999885140474+4.32477054e-6i、epsilon=n*n，source0.699999988仅明确alias到nominal0.7，不插值。

表中原rho为旧oracle的完整norm(b-Sz)/norm(b)，分母固定为原完整物理b；wall含该路线本批失败/恢复费用。measured、无量纲残差及秒；共同baseline为V19 L-GPOLY末态，未用V20 N/ILU结果。证据：[逐周期](task042_neural_coarse_inverse/outcomes/records/cycle_history_v21.csv)、[状态](task042_neural_coarse_inverse/outcomes/records/checkpoint_inventory_v21.json)。

| 路线 | 完整边界调用 | 原rho起点 | 原rho最终 | 原native最终 | charged S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|---|---|
| B | 16 | 9.67833470962e-06 | 7.73068606402e-06 | 2.99798928999e-06 | 4656 | 393.743535608 | CALL_LIMIT |
| C | 112 | 9.67833470962e-06 | 2.5281170328e-06 | 9.80413346383e-07 | 30645 | 2939.28866421 | TIME_VERIFY_RESERVE_STOP |

冻结后的独立场审核才读取已有REF7；其实际原native=3.01796304395967e-12、独立total-native=1.43744486618839e-12，没有置零、重建准确解或参考反馈。两种native分母不同，不能互换。下表场误差相对同mesh/p3参考，不是离散误差或连续解误差，全部measured；[完整Gate](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v21.json)。

| 冻结状态 | Schur≤1e-6 | native≤1e-6 | 独立total-native | 散射E≤1e-4 | 散射curl≤1e-4 | 逐通道功率差≤1e-6 | 完整合格 |
|---|---|---|---|---|---|---|---|
| V19-L-GPOLY-FINAL | 9.67833470962e-06 | 3.75329480007e-06 | 1.30239098725e-06 | 7.95003214967e-05 | 7.9510166913e-05 | 1.7855346417e-06 | False |
| V19-L-GNN-FINAL | 1.44393838546e-05 | 5.59964766271e-06 | 1.94307429584e-06 | 9.70793047547e-05 | 9.7083009907e-05 | 5.64706064632e-06 | False |
| B-FINAL | 7.73068606402e-06 | 2.99798928999e-06 | 1.0403004379e-06 | 7.94237400141e-05 | 7.94361776624e-05 | 1.88874663809e-06 | False |
| C-FINAL | 2.5281170328e-06 | 9.80413346383e-07 | 3.40202831061e-07 | 7.81608038914e-05 | 7.81769668025e-05 | 1.71964465112e-06 | False |
| C-CALL32 | 4.43845248007e-06 | 1.72124865592e-06 | 5.9727222794e-07 | 7.88465049064e-05 | 7.88620685216e-05 | 1.8483718407e-06 | False |

自然排序ILU0/P40在V20负结果已收口，本轮分别测试重复局部张量展开的执行成本与固定GCROT回收空间。作用44.536534→23.471869s为工程收益；循环机制必须另看原残差和全部场Gate。实际source97a17aee9a9cc2d91904b4c89f07c4d1cfbd631c, c91954c47d55242fd95ae7efcb44272dcce3a0ec, d7bfcb58632b344f8ed9b9fd1467c6c224df0bc4；新增formal wall3482.125663s，历史下界70970.599785s。失败费用、上游暖初始化成本和旧超时记录保持。

## 最终取舍和唯一下一建议

B/C未取得完整有限元资格；不宣称完整求解、神经训练增量或同严格精度加速。作用实现的收益与循环空间的原残差效果分开；功率及场资格仍由全部原Gate决定，低loss/小内存不能替代它们。这里只是micro固定离散对照，最终0.7nm非可分目标、离散误差、目标规模可扩展容量和48小时均NOT_QUALIFIED。

唯一下一建议：在同一冻结micro上，只预登记一次“固定p1原物理粗层＋现有局部修正”的容量／传递资格及最多4个GMRES256周期对照：让更低阶的原Maxwell方程处理远距离耦合，保留负质量项、Floquet及完整40端口，避免把正定AMS/HX成功误当散射资格。先复核可复用高低阶传递与既有负结果；容量不合格就不启动，任何global p1 factor必须明确披露，不能称factor-free或重开p4强逆。依据是本批无PC循环的同工作量无优势、112调用仍不合格且最后16调用降幅不足5%。可用性、低阶色散误差与收益均unknown，只作为下一review的单一有界建议。 本批未实施，等待下一review；不自动增加循环容量/迭代、建PC、启动新参考或放大模型，不merge master。

[详细结果](task042_neural_coarse_inverse/outcomes/exact_action_recycled_correction_v21.md)、[run](task042_neural_coarse_inverse/outcomes/records/run_index_v21.json)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v21.json)。

以下历史正文逐字保留，旧“当前”仅指其当时阶段。

# Task042 V19最新统一结果：固定R起点原方程抛光

P在每个周期重新搜索256个方向，只留下当前解；L额外保留本路线最近至多3个修正方向，用于减少下个周期重复搜索。两者都继续解完整原方程，保留40端口和单元内部的原恢复。这里改变的是重启之间保存的信息，没有训练网络、改变材料或缩减物理未知量。

| 方法／库 | 实际调用 | 原rho起点→最终 | 本路线S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|
| P_GPOLY | 64 | 0.000146307718165 → 2.23358499521e-05 | 16768 | 2279.93663295 | FIXED_64_CYCLE_LIMIT |
| P_GNN | 64 | 0.000199556374692 → 3.24881797774e-05 | 16768 | 2261.5433094 | FIXED_64_CYCLE_LIMIT |
| L_GPOLY | 64 | 0.000146307718165 → 9.67833470962e-06 | 16962 | 2298.25489228 | FIXED_64_CYCLE_LIMIT |
| L_GNN | 64 | 0.000199556374692 → 1.44393838546e-05 | 16962 | 2327.33009045 | FIXED_64_CYCLE_LIMIT |


| 冻结状态／同一0.7nm micro | 原Schur≤1e-6 | 原native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射curl≤1e-4 | 完整资格 |
|---|---|---|---|---|---|---|
| V18-R-GPOLY | 0.000146307718165 | 5.67386863796e-05 | 1.96882893595e-05 | 8.07999012193e-05 | 7.98192590218e-05 | FAIL |
| P_GPOLY-FINAL | 2.23358499521e-05 | 8.66192707661e-06 | 3.0056833815e-06 | 7.99097168553e-05 | 7.98938859115e-05 | FAIL |
| L_GPOLY-FINAL | 9.67833470962e-06 | 3.75329480007e-06 | 1.30239098725e-06 | 7.95003214967e-05 | 7.9510166913e-05 | FAIL |
| P_GPOLY-CYCLE8 | 6.80805905911e-05 | 2.64019104846e-05 | 9.1614467379e-06 | 8.01429875488e-05 | 7.98921410883e-05 | FAIL |
| V18-R-GNN | 0.000199556374692 | 7.7388716746e-05 | 2.68538372247e-05 | 0.000100199130834 | 9.8749639854e-05 | FAIL |
| P_GNN-FINAL | 3.24881797774e-05 | 1.25990389751e-05 | 4.37185878872e-06 | 9.76389690217e-05 | 9.76039356484e-05 | FAIL |
| L_GNN-FINAL | 1.44393838546e-05 | 5.59964766271e-06 | 1.94307429584e-06 | 9.70793047547e-05 | 9.7083009907e-05 | FAIL |
| P_GNN-CYCLE8 | 9.11307000429e-05 | 3.53408300959e-05 | 1.22632463571e-05 | 9.92146330721e-05 | 9.88453864041e-05 | FAIL |


完整资格0/8，FIELD_AND_EQUATION_PROGRESS_NOT_QUALIFIED。两个V18-R实际末态原Schur起点1.46307718165e-4/1.99556374692e-4；完整FE/MPC/40ports未变。没有训练、Q/image/GK或global p4逆。

新增正式one-run监督wall **9199.970576s**；本批辅助监督wall **102.206160s**（截至费用快照，含失败小测试；后续交付开销计入总elapsed）。V6起formal累计下界 **66613.525719s**，旧辅助unknown保持。同时整树采样峰 **796585984B（0.741879GiB）**，own swap/VRAM **0B**。父队列和子one-run计时嵌套，不重复相加；全部成本标shared-workstation。

[Response](task042_neural_coarse_inverse/response_v19.md)、[完整结果](task042_neural_coarse_inverse/outcomes/post_lsqr_residual_polish_v19.md)、[原Gate](task042_neural_coarse_inverse/outcomes/records/qualification_and_dispatch_v19.json)、[run/source](task042_neural_coarse_inverse/outcomes/records/run_index_v19.json)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v19.json)。唯一下一建议：仅申请一个固定p3全trace ILU(0)预条件的短资格对照：先评估原p3 trace体块装配与因子容量、核对同一barS及完整40端口；Gate通过后从L-GPOLY冻结末态做一次预条件GMRES256周期。此方案需要额外装配和因子内存，须由下一份review明确预算与准入，不能沿用本批低RSS作容量保证；不扫描参数、不使用global p4 LU。本批未实施。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# Task042 V18项目进展

| 固定模型与路线 | 完成/资格 | 新增工作与成本 |
|---|---|---|
| 0.7nm/384hex/p3/q15/40ports; G64/G256 | 两库16/8周期，原方程FAIL | 每库1024+2048 Arnoldi；无Q/U/R加载 |
| 同模型原V17 GK独立R | GP12831/GN11903；完整0/8 | 新GK6484/5784；wall边界，不是已证实停滞 |

新增正式one-run监督wall **19905.129134s**（5.529203h）；V6起formal下界 **57413.555143s**。旧辅助unknown保持。同时整树采样峰 **2576646144B（2.399689GiB）**，own swap/VRAM **0B**，全部成本为shared-workstation。

无hidden训练、新基、PC、global p4 LU或新参考；两库共同随机神经G0，GPOLY不称纯非神经。实际run source `d3e5800ee379168ca33bc3dae595de1c8aa71063`，无production default/merge/目标48小时资格。[回应](task042_neural_coarse_inverse/response_v18.md)、[结果](task042_neural_coarse_inverse/outcomes/gmres_repair_residual_completion_v18.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v18.json)。

以下历史正文逐字保留；旧版本的“当前”仅指其当时阶段。

# Task042 V17：完整递推续算、全空间与原方程GMRES对照

| 同一0.7nm micro／固定Q3098 | 最终LSQR逻辑步 | 新GK measured..charged | G周期 | Arnoldi步 | 最终Schur | 最终native | 散射E误差 | 散射curl误差 | LSQR停止／G停止 |
|---|---|---|---|---|---|---|---|---|---|
| GPOLY | 6347 | 6091..6091 | 0 | unknown; discarded 0..64 | 0.000490220469 | 0.000190109352 | 0.000265162174 | 0.0002631196 | LSQR_RESERVED_G_BOUNDARY / GMRES_INTERFACE_FAILED |
| GNN | 6119 | 6119..6135 | 0 | unknown; discarded 0..64 | 0.000594477082 | 0.00023054046 | 0.000249203787 | 0.000245918456 | LSQR_RESERVED_G_BOUNDARY / GMRES_INTERFACE_FAILED |

新增正式数值监督wall **16284.035028s**；V6起formal累计下界 **37508.426009s**。同时整树采样峰 **2577092608B（2.400105GiB）**，own swap **0B**、GPU分配0；全部成本为shared-workstation。

完整资格0/8；无hidden训练，GPOLY/GNN共同G0，micro不代表目标48小时。

[Response](task042_neural_coarse_inverse/response_v17.md)、[结果](task042_neural_coarse_inverse/outcomes/resumable_full_trace_campaign_v17.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v17.json)。

唯一下一建议：仅在下一份review重新授权后，修复GMRES入口对BarAction.close完整z返回值的接线，并增加一个覆盖真实端口闭合／原audit的最小回归；从当前两库最后可信LSQR trace各完成同一固定GMRES64对照，补齐本批因实现失败而缺失的证据，不增加基、PC、迭代预算或读取参考选点。本批不实施。 未自动实施，merge未批准。
以下历史正文逐字保留；旧版本的“当前”只指其当时阶段。

# Task042 V16：全空间校正三路线收口

| 路线／同一0.7nm micro | 维数Q＋完整补空间 | GK更新／原作用次数 | 原Schur／native残差 | 停止原因 |
|---|---|---|---|---|
| CLOSED-LSQR-0 | 0+18144 | 4096／8523 | 0.0694190731／0.026920979 | STAGNATION_CONTROLLED_STOP |
| AUG-LSQR-GPOLY | 3098+15046 | 816／1698..1714上界 | 0.0126178958／0.00489326771 | RESOURCE_CONTROLLED_STOP；原审核768／向量仅256 |
| AUG-LSQR-GNN | 3098+15046 | 85／181..197上界 | 0.122363732／0.0474531179 | RESOURCE_CONTROLLED_STOP；原审核64／向量仅0 |


固定0.7nm/384hex/p3/q15/40端口，完整同离散0/6；formal监督wall新增下界4447.81145s、树峰4003057664B、swap/VRAM0、shared-workstation。神经仅提供冻结部分方向，不再限制准确解；没有hidden训练。唯一下一建议：在新的review授权和稳定资源准入下，仅做一次冻结GPOLY/GNN的有界配对复试，每64步审核以两个滚动槽先原子保存完整递推／候选，再写汇总，补齐中断终态及同工作量证据；算子、基、精度和迭代预算保持，本批不实施。

[Response V16](task042_neural_coarse_inverse/response_v16.md)、[结果](task042_neural_coarse_inverse/outcomes/augmented_full_trace_lsqr_v16.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v16.json)。以下旧总账原样保留。

# Task042 V15：局部配对与组合完成，多项式组合更好

| 分支/固定模型 | 实际结果与贡献 | 资源/边界 |
|---|---|---|
| task42_neural_coarse_inverse；0.7nm/384hex/p3/q15/40ports | L0-L3，局部1544/组合3098，4数值候选合格/8物理状态0严格资格；UNION-POLY Schur/native .517714/.200771、散射E/curl .283235/.283293，优于同容量NN .579986/.224921/.766071/.766241 | formal 2106.167431s、sampled tree4175888384B、swap/VRAM0、shared-workstation；source db0e68e519767554412c960af14b3c185012f9de |
| 神经与下一步 | 隐藏固定，增维/表示收益不归为hidden训练；两参考投影场约.00113而方程仍差，原因INCONCLUSIVE | 只建议固定POLY空间FE测试函数能量行尺度对照，未实施；目标48h/p4参考/最大模型未合格或未授权，旧p4逆closed |

[Response V15](task042_neural_coarse_inverse/response_v15.md)、[结果](task042_neural_coarse_inverse/outcomes/local_trace_representation_v15.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v15.json)。只提交本分支，等待review，不merge；以下旧总账原文保留。

# Task042 V14：正交decoder完成，物理资格仍为负

| 执行分支／固定0.7nm micro | 完成／实际结果 | 时间／内存／后续 |
|---|---|---|
| task42_neural_coarse_inverse；Review V11→V14 | O0–O4，6+2 profile、10状态，直接Qc decoder与2制造PASS；Schur/native0.797366986/0.309221932，散射E/curl0.733565775/0.733670474，0/10严格合格 | formal2510.272780s、sampled tree3243409408B、swap0/VRAM0、shared-workstation；source 87940891c12ccdec35fca39cd453ab9a29eeeda5 |
| 神经/表示贡献 | 同hidden完整头避免旧一阶过冲，有限hidden原Phi仅降0.088922%，场约0.0941%，无研究正信号；原约0.798平台未突破 | 本射线队列收口；未来仅建议同维几何局部trace表示对照，未实施、merge未批准 |

[Response V14](task042_neural_coarse_inverse/response_v14.md)、[完整证据](task042_neural_coarse_inverse/outcomes/orthonormal_trace_reprofile_v14.md)。canonical材料/原方程/40端口保留，无global p4因子或fallback；旧负结果与账不清零。以下总账历史原文保留。


# Task39extra V6最新结果：递归粗逆未资格化，V5双模型成功基线保留

G1/G2已完成，旧新C真实负结果保留；用户补充授权继续有依据的p4/p2诊断，G5与response_v8尚未最终收口。该授权超出V6原停止分流，不改变物理、精度或安全线；不复跑G1/G2。

| 项目 | 最新结论 |
|---|---|
| V6原始LO | 13步true0.667843080037，1800.799s筛选不合格；COARSE_APPROXIMATION_UNQUALIFIED |
| G1/G2精度 | 固定6输入0/6达LO；正式26I4均未达；映射/残差闭合与成本账通过 |
| 资源 | 新screen峰1491857408B、swap/globalΔ0；仅失败13步，不是2GB成功解/完整求解峰 |
| V5保留 | 原始564/notch576步，完整残差、匹配参考与物理Gate通过；参考448页global out归因UNRESOLVED保留 |
| 分流 | HI未资格化、notch/recovery未运行；G1_G2_COMPLETED_DIAGNOSTIC_CONTINUATION_AUTHORIZED；无W0/5nm/0.7nm/生产默认资格 |

方法和失败边界见[Task39extra V6](task039_extra_physical_multilevel/outcomes/coarse_inverse_replacement_v6.md)。成功V5仍为工作站复现基线；新C已实际测试并关闭本轮有限实现，未启动新的内部路线。

以下完整保留历史正文；“当前/下一步”仅指当时阶段，以本节为最新状态。

---

# Task39extra V5最新状态（历史正文保留）

原始13.5nm/p6h10/MPI1 BAL_H零初值564步、唯一notch576步，完整残差分别9.932289220e-7/9.351705517e-7，匹配离散参考和独立物理Gate通过。原始输出平面错误由同一checkpoint的output-only恢复处理，历史WORKER_FAILED不改写。

两次迭代全系统swap增量均0；条件参考global pswpout增加448页，归因UNRESOLVED，尽管采样tree swap0，仍不能声称整个workflow全系统swap0。未取得2GB或0.7nm/生产默认资格。唯一下一对象为有界内存/分布式物理近似C替代全局p4 LU，同时保持粗细平衡；未实施新路线。

统一结果与证据见[Task39extra V5](task039_extra_physical_multilevel/outcomes/balanced_coupling_v5.md)。以下旧阶段结论按当时范围保留。

---

# Task39extra补充授权：真实难误差已定位

| 当前结果 | 实测与边界 |
|---|---|
| 原始模型/参考 | 13.5nm、1°、p6/h10、MPI1；匹配fine原A6残差1.6160304782604192e-11 |
| 三真实误差 | 相对L2=22.46%/24.92%/31.34%；phase-invariant M0相关>0.9975 |
| 表示与精度 | p4互补范数仅0.8300%/0.8421%/0.8225%；四native A4≤1e-10、零精化；range identity2.53e-12 |
| 主机制 | 物理粗层—细层互补耦合失衡；粗RHS几乎等大反向，相消比1.7–2.0%，粗响应差/互补范数57–59倍 |
| MR抑制 | 单位粗修正剩余场约48%，细层残差增22–53倍；MR小步长后场误差近乎不变，不是MR公式bug |
| 独立资源 | fine参考7,229,845,504 B/574.7957s；诊断3,881,811,968 B/1510.7222s；swap0，不能相加或称2GB资格 |
| 唯一下一对象 | 现有physical p4粗修正与p6互补耦合/平衡；下一轮待资格化设计要求，未实施新PC |
| 未通过 | 旧negative不改判；2GB生产迭代/非可分/0.7nm/official仍未通过，无新参数扫描 |

用户补充授权“直到把真实难误差定位了”的范围完成，不伪装为V4原始范围。真实误差来自匹配离散参考与三旧失败快照之差；其小互补场在物理算子下却产生很强的粗层驱动。闭合方程与场误差测量支持上述定位，不能外推条件数、色散定理、整体近共振或连续真解。

详见[中心说明](task039_extra_physical_multilevel/outcomes/actual_error_diagnosis_v5.md)、[中心JSON](task039_extra_physical_multilevel/outcomes/records/actual_error_diagnosis_v5.json)、[Response V6](task039_extra_physical_multilevel/response_v6.md)。旧V4以下内容保留为历史，当时“参考仍缺失”等状态不代表本次最新结果。

## 历史V4及此前结果（原文当前仅指当时）

# Task39extra Review V4：诊断完成，真实散射参考仍缺失

| 项目 | 最新结果 |
|---|---|
| 正式source/model | b127546f172e46d0b217680338b4e0ea7aa39f12；13.5nm/1°/s/Full3D p6h10/MPI1/线程1/80modes |
| 终态与计数 | DIAGNOSTICS_COMPLETED_WITH_LIMITATIONS；watchdog/launch COMPLETED、exit0；8PC/4互补/10逻辑p4/12MatSolve |
| 表示/粗响应 | 110步投影闭合，eta_space=0.084774901、eta_G=0.092065368、range identity=3.92727e-13 |
| 互补/真实残差 | H6/S6场误差保留0.941689514/0.934259170；JOINT448 LIGHT/JOINT残差比0.999706716/0.999674195 |
| p4精度 | 重建首次1.0086968840613473e-10>1e-10，1次精化9.492574739321824e-13；旧失败保留 |
| 资源/时间 | RSS峰3540959232 B、cap最低8314208256 B、reserve4GiB、swap0、3936样本无违规；outer保守1130.973243s<5400s |
| 清场/范围 | 父进程及2后代均清场；无新full solve、official R/T/A/A_volume/R00_s/p/total/衍射级/EH、p/h/M/MPI/Hybrid扫描 |
| 唯一下一优先 | 取得同A6、同b、同1°的匹配fine参考/真实误差，复用现有packet定位；本轮不造新PC或延长迭代 |

质量投影用无损L2尺子找p4最佳表示，粗响应则用实际p4算子求修正；这个人工误差上两者都较好，不能硬判p4色散/严重粗层失配。互补残差改善却留下大部分场误差；粗方向MR令场误差比0.092→0.213同时残差改善，反映目标不同，不是已证bug。人工e不等于实际散射误差。C4现有2D截面QEP不能提供规定3D Bloch控制，UNRESOLVED，未新建平台。

方法、原因矩阵、数值边界、全部raw哈希及分阶段成本见[中心说明](task039_extra_physical_multilevel/outcomes/diagnostic_completion_v4.md)、[中心JSON](task039_extra_physical_multilevel/outcomes/records/diagnostic_completion_v4.json)、[Response V5](task039_extra_physical_multilevel/response_v5.md)。新7200s计算账与旧V3分开，审计时1142.571742s；编辑/等待另列，最后静态补费见中心JSON。旧7响应/3identity仅按hash复用。

## 历史V3收口（以下当前仅指当时）

# Task39extra：D5最新收口——原A4数值Gate拒绝，7次PC诊断完成

| 项目 | 最新结果与适用边界 |
|---|---|
| 来源与模型 | clean source `bf8e0c1d16c9c86677e866cdf29fd5491f076e32`；原始13.5nm、1°、s、Full3D p6/h10、MPI1/线程1、80 DtN modes；无参考D1/D3诊断 |
| 数据/作用 | 3份历史快照原A6残差复现，最大绝对差2.77556e-16；native独立系数逐位匹配，分项和与A作用一致 |
| 调用计数 | 8 started / 7 completed；第8次JOINT448→LIGHT未完成，不能记为完整PC；已知误差/投影/互补/D4均not_run |
| 终止 | 原A4残差1.0086968840613509e-10>1e-10（超限0.8696884%）；worker DIAGNOSTICS_FAILED，watchdog/launch WORKER_FAILED，outer exit2 |
| 资源/清场 | 同期树RSS峰3777171456 B<实际cap8367992832 B；reserve4294967296 B、最低available9252577280 B；3324样本无违规，swap0；父进程及20个已观测后代清场 |
| 时间 | watchdog mono866.072315784 / BOOTTIME866.072315245 / UTC945.518512242 s；逐段保守收费945.519546580 s，outer含pre/post952.495114811 s |
| 规模 | p6存储173802/独立164592行、252cells；p4存储53084/独立48960、增广53164行、allocated NNZ24730144、factor NNZ53417584 |
| 物理输出与比较 | 无新R/T/A、A_volume、R00_s/p/total、衍射级、复E/H或full solve资格；无p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 后续范围 | 数学根因仍未完成；唯一优先是补存同一失败p4输入，核对增广系统与原A4残差差别/可靠性，再补缺失表示与响应诊断；本轮不重跑或精化 |

详见[中心报告](task039_extra_physical_multilevel/outcomes/nonconvergence_diagnosis_v3.md)与[Response V4](task039_extra_physical_multilevel/response_v4.md)。 PC为求解提供近似修正，本次测量的是同输入单次残差变化；缺少已知误差和投影，不能确定空间/粗响应根因。

## 历史状态（下文当前/0次等仅指当时）

# Task39extra：Review V3 / D5 证据收口

| 对象 | 当前结果 |
|---|---|
| 原始13.5nm/1°/p6h10/MPI1/80modes诊断 | 唯一启动source `24b3dbb67540a4cc2ec3e70ba381ab8a3e41d650`；`TIMEBASE_INCONSISTENCY`，不是新完整求解或数值失败 |
| 完成/未完成 | D0与微型验证完成；setup止于s6_transfer_cycles_started；fresh canonical/原A残差、已知误差、p4投影及PC探测均未完成；完整PC0、互补0、投影0，D4 not_run |
| 时间 | 首次Gate区间mono61.410906241 / BOOTTIME61.410906659 / UTC67.359115896 s，差5.948209655>5 s；245样本发现两次离散UTC相对跳变，系统原因未定 |
| 资源/清场 | 同期树RSS峰639950848 B<cap8417038336 B；reserve4294967296 B、最低effective available12219453440 B、swap0、违规0；parent及已观测后代清场 |
| D2 | 缺完整MPI1峰值上界，参考未启动；REFERENCE_UNAVAILABLE_ON_16GB仅限本轮安全路径，非普遍不可能 |
| 结果边界 | 新残差/official R/T/A/A_volume/R00_s/p/total/衍射级/EH均not_run；历史LIGHT576=0.0791360407785889、JOINT476=0.10535820013809101仍>1e-6 |
| 模型规模/比较 | 历史存储173802行、独立164592行、252cells；fresh NNZ未到达。未新增p/h/M/MPI/Hybrid扫描、非可分或短波资格 |
| 下一步 | 数学原因UNRESOLVED；仅优先时间资格及冻结同输入最小补证，本轮不重试、不提新PC、不merge |

详见[中心报告](task039_extra_physical_multilevel/outcomes/nonconvergence_diagnosis_v3.md)与[Response V4](task039_extra_physical_multilevel/response_v4.md)。本轮只完成证据闭环，未完成数学定位。以下保留历史记录。

# Task39extra：Review V2 / F5 收尾

| Review V2 / F5 | 当前结论 |
|---|---|
| F1 / F2 | 完整packed S6数学等价通过；配对中位0.938459>0.75，速度不足，F2 not_run |
| F3原始模型 | 13.5nm/1°/p6h10/MPI1/80modes；source `60b8df2a24cbcd96e49e018be22fb64f06eeae3f`；零初值476步真残差0.10535820013809101>1e-6 |
| 方法与失败含义 | 保留H6–准确p4–H6三个顺序方向，仅末尾联合选权；局部残差比中位0.979479，rank3/无回退；不足以让完整p6收敛 |
| 用户收尾 | USER_REQUESTED_CONTROLLED_STOP；raw worker CONTROLLED_STOP、wrapper WORKER_FAILED/exit4并列；未触发原自动budget/stagnation Gate |
| 时间限制 | workflow monotonic7588.369777 / UTC8363.831318 s；solve至请求monotonic6791.466003 / UTC7478.995420 s；UTC solve超7200，原因未唯一确定，不能声称全部wall预算通过 |
| 资源与清场 | RSS/PSS峰3351887872/3317217280 B，28753样本均可读；cap8525078528 B、至少4GiB余量无违规；swap0，56 PID清场 |
| 后续 | F4/official锁定，无第三候选、续跑或0.7nm资格；仅F5文档/测试/审阅后提交推送，非master merge |

详见[中心结果与双时钟限制](task039_extra_physical_multilevel/outcomes/packed_and_joint_mr_v2.md)、[Response V3](task039_extra_physical_multilevel/response_v3.md)。局部联合修正改善约2%，不等于完整求解资格；下文V1/A5为历史快照，其未运行语句保留当时含义。

# Task39extra：Review v1 / R6 收口

| 分支阶段 | 当前结果 |
|---|---|
| R1等价S6原型 | 数学对照通过，PC中位74.87089344408014 s对旧22.021386729524238 s，速度Gate失败；R2跳过 |
| R3唯一H6–p4–H6 | source `cbf56e87e515ab0c3fc5756cb6cf52feb047f610`；原13.5nm/1°/p6h10/MPI1/80modes，零初值；582完整PC中位10.293892393587157 s |
| 最后safe /预算 | 576步原A6真残差0.0791360407785889>1e-6；solve7200.255611149943 s性能停止，workflow7966.278611822054 s |
| 资源 /输出 | 同期进程树RSS3352014848 B，swap0，cap与4GiB余量无违规；清场完成；worker终态/normal checker/official物理输出缺失 |
| 事后停止修复 | `597546311feea60d61acb2a9999b706dd895dcf0`仅未来LIGHT opt-in，23局部测试通过；R3未重跑 |

R3用p6平滑替代S6内部p3/p1修正来减少成本，但准确p4逆辅助下外层仍未达到合格残差。两条路线按本轮合同结束，不等于算法已被彻底研究完或否定；S6配合后续contiguous packing重新资格化为not_run。R4非可分、R5/direct/h5 heavy、第三PC与短波均未运行；global p4诊断factor依赖和0.7nm物理收敛仍未解决。见 [R6成本与贡献](task039_extra_physical_multilevel/outcomes/cost_and_contribution_v1.md)、[response_v2](task039_extra_physical_multilevel/response_v2.md)。以下A5历史快照保持原证据边界。

# Task39extra：A5 本机性能停止（历史）

| 正式结果 | 边界 |
|---|---|
| A2R source `54ab46cf4c8378a9b27650ca6963cadb34013a2f` | 原 13.5 nm/1°/p6h10，唯一 reference；solve 3600 s Gate 触发 `PERFORMANCE_CONTROLLED_STOP` |
| 原 A6 真残差，32/64/96/128/160 步 | 0.46338436888430473 / 0.41005441732961595 / 0.3139861672303239 / 0.2753887167051727 / 0.18250767622880507，均未达 1e-6 |
| 中间逆与资源 | 163 次原 A4 reference 全通过 1e-10；workflow 4451.728501909005 s；RSS peak 3588677632 B，swap 0；62 PID 清场 |

163 完整 PC，第 164 只有 pre 开始；最后有效近似解向量记录为 checkpoint160（未收敛）。正常 worker summary/release/recovery/checker completion 缺失，不补造。S6/S3 成本序号误加独立重算为各 326 次，旧 raw 不改；事后窄修 `adc448814c3022fdf6d1a688da69a28238e7db9c` 的最后轻量回归 19 passed，未重跑 PDE。中间逆通过不构成 outer/reference-only PASS；A3/A4/official/5nm/0.7nm 未运行。见 [A5 总结](task039_extra_physical_multilevel/outcomes/summary.md)、[索引](task039_extra_physical_multilevel/outcomes/records/run_index.json)、[移交包](task039_extra_physical_multilevel/outcomes/workstation_handoff.md)。

# Task39extra：13.5 nm 原 p6/h10 阶段同步（此前快照）

| 阶段 | 实际进展 | 边界 |
|---|---|---|
| 旧 A2 setup | 用户受控停止；workflow 5946.47 s，S6 约 98.6 min | outer 未开始 |
| S6 优化后 A2 | S6 143.69 s，至 solve 开始约 553.52 s；workflow 3015.38 s，RSS peak 1849683968 B，swap 0 | 用户按成本停止；7 次完整 PC 各 36 步，第 8 次 partial；outer final 不可用 |
| A2R 诊断参考 | 原 p4 直接逆的显式 profile 已实现，最终 focused tests 38 passed | 原尺寸 `not_run`；主候选未资格化；不是 0.7 nm 已通过 |

S6 精确对角优化省掉不需要的单元耦合计算，保持原积分和约束；A2R 则以额外分解内存换取准确的中间修正，仅用于诊断。不同 PC 的 RHS 不同，A4 残差 0.636–0.847 不能串成收敛曲线；checkpoint 0=1 只是初始值。本次为阶段同步，非 A5 结项。详见 [Task39extra 总结](task039_extra_physical_multilevel/outcomes/summary.md)、[运行索引](task039_extra_physical_multilevel/outcomes/records/run_index.json) 和 [测试摘要](task039_extra_physical_multilevel/outcomes/test_summary.md)。

# 2026-09-05：Task038 Review V19 R4 PML 结构收口

## 当前 V19 authority

R0 的目标是回答一个有限的问题：在原始 p6/h10 物理结构上，局部 PML 双向 sweep
的网格、映射和资源边界是否真实可构造。PML 用人工吸收层近似开放边界，但它会
增加局部网格、系数和编译工作集；local inverse 的代价可能在全局求解前成为
内存 blocker。小型 p2/MPI1 fixture 的 action、owner map、PoU 和 MUMPS 同一
factor 生命周期均为 measured PASS；p6/h10 的真实 symbolic 尝试则在 local
mesh 完成后的 FFCx C 编译阶段触发本机 RSS cap，当前结论为
REAL_ANCHOR_REFERENCE_RESOURCE_BLOCKED。

| 阶段 | 对象 | 结果 |
|---|---|---|
| R0 p2 fixture | 真实小型 PML/local Maxwell + map + MUMPS | measured PASS |
| R0 p6 inventory | p6/h10、173802 rows、4 core、3 interfaces | measured structural anchor |
| R0 p6 symbolic v4 | local mesh 后的 FFCx C 编译 | resource controlled stop；sampled RSS 8609562624 B，sampled PSS 8580238336 B |
| R1 | 原始 p6/h10 zero-start PML double sweep | not_run |
| R2/R3 | low-memory replacement / notch recipe | not_run |
| official physics | E/H、near-field、R/T/A、recovery | not_run |

watchdog cap 为 8585588736 B；Review hard 12 GB 在已观察样本中未触及，warning
10 GB 在已观察样本中未触及，二者尾段状态未知；
timeline 内 swap 为 0。一个 .o 在最后 timeline 之后才落盘，因此完整同期 peak、
尾段 cache 和尾段 swap 必须保持 unknown/partial；不能把事后清场提升为完整
qualification。V19 outcome 和 compact record 见
[PML R0 outcome](task038_extra_full3d_iterative_0p7nm/outcomes/pml_double_sweep_real_structure_v19.md)
与
[PML R0 compact](task038_extra_full3d_iterative_0p7nm/outcomes/records/pml_double_sweep_real_structure_v19.json)。
R0 不是 PML numerical failure，且不证明 0.7 nm/2 TiB scalable solve。

---

# 2026-09-04：Task038 Review V18 fixed restart64 收口

## 当前 V18 authority

V18 对固定 checkpoint-1000 做了唯一一次 restart=64 physical Krylov screen。通俗地说，
它把每次保留的 Krylov 搜索空间从 V17 GMRES(20) 的 20 个方向扩大到 64 个方向，
但仍使用同一 physical operator、positive pMG、RHS 和 checkpoint；因此能直接回答
较长但有界的 restart 是否足以通过短 screen，不能代表新的 PC 或 official PDE。

| 阶段 | 精确对象 | 当前结果 |
|---|---|---|
| qualifier | restart64，additional 64 | PASS；parent process-tree peak 1,583,013,888 B，swap 0 |
| screen | restart64，additional 1024 | V18_RESTART64_NUMERICAL_GATE_FAIL |
| continuation | screen 后至 additional 10240 | not_run；screen Gate 未通过 |
| larger-restart/Krylov-memory lane | 其他 restart 或新的 Krylov 方法 | CLOSED |
| official physics/recovery | E/H、near-field、R/T/A、recovery | not_run |

screen 失败的具体原因是：step512=0.35604872662297266 > 0.25、
step1024=0.27299642739429014 > 0.10，以及 r1024/r768=0.8588033360973709 >
0.85。这是有效 raw/checker 支持的 numerical negative，不是 path/cache 或资源
Gate 失败。parent 的严格 2 GB RSS 线和 swap=0 均满足，但资源通过不等于数学收敛。

完整 residual history、counts、cache、marker、lifecycle 和证据 SHA 见
[V18 outcome](task038_extra_full3d_iterative_0p7nm/outcomes/restart64_physical_checkpoint_v18.md)
与
[V18 compact record](task038_extra_full3d_iterative_0p7nm/outcomes/records/restart64_physical_checkpoint_v18.json)。
V17 Oracle A/B、Q2 negative 与全部旧证据保持不变；0.7 nm/2 TiB scalable solve、
official physics 和 recovery 仍未达成。

---

# 2026-09-04：Task038 Review V17 M6 结项

## 当前 V17 authority

| 阶段 | 精确对象 | 当前结果 |
|---|---|---|
| Q1.1 | 同一 h50 mesh 的 p6/p3 physical action identity | PASS；MPI1/MPI2 worst Galerkin `4.3068152418800024e-14`/`3.631160363261226e-13`，均为 curl |
| Q1.2 | p3/h50 physical inner | PASS；MPI1、MPI2 的 physical/random true residual 均低于 `1e-6` |
| Q2 | p6/h10 checkpoint correction | `Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL` |
| Oracle A | exact p3 coarse span | `EXACT_P3_COARSE_SPAN_FAIL`；`rho_ref=20.97573925716883` |
| Oracle B | disk-backed unrestarted right FGMRES | `UNRESTARTED_KRYLOV_WEAK_SIGNAL`；ratio `0.4006010510326989` |
| W0 | wave-aware interface rank/capacity preflight | `W0_INTERFACE_RANK_CAPACITY_FAIL` |
| Q3–Q6/W1–W4 | 后续路线 | locked/not_run |
| official physics/recovery | E/H、near-field、R/T/A、recovery | not_run |

这里的三个尺度不能混淆：Q1.1 是 h50 action identity，Q1.2 是 p3/h50 inner，Q2
与 V17 Oracle A/B 则分别是 p6/h10 checkpoint 或机制诊断。Oracle A 的 coarse
correction 通过 p3 residual 却放大 fine residual；Oracle B 有真实改善但没有 strong
signal。联合结论为 `NOT_QUALIFIED`，没有授权 fresh 20,000-step PDE、official
recovery 或新的 PC 实现。Q2 的 `1,560,625,152 B` 与 B 的
`1,451,954,176 B` 都是窄 workflow 的 measured process-tree facts，不能写成
full physical solve 或 0.7 nm/2 TiB scalability。

V17 M6 只完成 outcome 文档和 evidence index。后续方向仍是未实现的 Z0 研究边界：
PML/complex-shifted sweeping + compressed interface responses、energy-minimizing
H(curl) FETI-DP/BDDC、matrix-free p-h MG + distributed wave coarse solve，以及
intermediate-wavelength/reduced-geometry pilot hierarchy。它们不是已通过的 PC。

## V16 历史最终 Q/W 收口

## 当前 authority

| 阶段 | 精确对象 | 当前结果 |
|---|---|---|
| Q1.1 | 同一 h50 mesh 的 p6/p3 physical action identity | MPI1、MPI2、pair PASS；MPI1/MPI2 worst Galerkin `4.3068152418800024e-14` / `3.631160363261226e-13`，均为 curl |
| Q1.2 | p3/h50 physical inner | MPI1、MPI2、pair PASS；physical/random final true residual 均低于 `1e-6` |
| Q2 | p6/h10 checkpoint correction | `Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL`；reproduction、inner residual、`rho_ref`、`rho3` 均未过 Gate |
| W0 | wave-aware interface Schur candidate | `W0_INTERFACE_RANK_CAPACITY_FAIL`；rank/byte authority 与同时容量未闭合 |
| Q3–Q6 | 后续数值阶段 | locked/not_run |
| W1–W4 | W0 后续实现阶段 | locked/not_run |
| official physics | full E/H、near-field、R/T/A、recovery | not_run |

这里的区别很重要：Q1.1 只证明同一 h50 离散上两种 physical action 路径一致；
Q1.2 只证明 p3/h50 inner 能把指定 RHS 的显式真残差降到限值；Q2 则在 p6/h10
checkpoint 上测量实际 correction，结果是 numerical Gate 失败。Q2 parent peak
`1,560,625,152 B` 虽低于 MPI1 的 `2,000,000,000 B` 硬资源线，却不能冒充
已经得到正确的 p6/h10 full solve 或 official physics。0.7nm/2TiB scalable solve
也没有证明。

W0 关闭后只完成 Z0 文档，登记四个未实现方向：PML/complex-shifted sweeping
与 compressed interface responses、energy-minimizing H(curl) FETI-DP/BDDC、
matrix-free p-h MG 加 distributed wave coarse solve、以及 intermediate-wavelength/
reduced-geometry pilot hierarchy。它们都是 future research candidates，不是
已实现或已通过的 PC。MPI1 RSS `<2 GB` 是硬线；用户明确 MPI2 超过 2 GB 只记录，
但 MPI2 仍须满足 numerical、finite、repeat、input、provenance、swap 和 lifecycle。

最终文档证据见
[`V16 response`](task038_extra_full3d_iterative_0p7nm/response_v16.md)、
[`Q1 qualification`](task038_extra_full3d_iterative_0p7nm/outcomes/records/physical_pcoarse_q1_qualification_v16.json)、
[`Q2 checkpoint`](task038_extra_full3d_iterative_0p7nm/outcomes/physical_pcoarse_checkpoint_v16.md)、
[`W0 preflight`](task038_extra_full3d_iterative_0p7nm/outcomes/wave_aware_dd_preflight_v16.md)。

---

# 历史首次：Task038 Review V16 Q1 source-authority controlled stop（永久保留）

Q0 physical p-coarse preflight 已通过；Q1 窄核心在 clean core commit 6edf5f5c1255185052a2a5d5fb8dd422f3238f04
实现并完成 focused regression，但固定六 probe formal 未启动。V16 要求 p6/h50
r3_long_tail_derived，而仓库唯一旧 R3 authority 是 p6/h10；当前 F1 p3/h50 和
旧 T2 p3/h50 不是可替代映射，p6/h50 inventory 也未建立。没有资格化的 h10→h50
full-FE dual restriction/projection，因此分类为
CONTROLLED_STOP_PREMEASUREMENT_PROVENANCE / NOT_QUALIFIED，不是 action、数值或资源
失败。Q2–Q6、W0–W4、checkpoint 数值、physical recovery 和 official physics 均
not_run；ordinary default 和 production qualification 未提升。

证据入口：
[physical p-coarse oracle](task038_extra_full3d_iterative_0p7nm/outcomes/physical_pcoarse_oracle_v16.md)、
[Q1 authority compact](task038_extra_full3d_iterative_0p7nm/outcomes/records/physical_pcoarse_q1_authority_v16.json)。

---

# 2026-09-05：Review V18 E1 eventual continuation 用户性能受控停止

V18 E1 在同一 p6/h10 physical checkpoint-2024 上运行固定 restart=64 continuation。
它不是新 PC，也不是 fresh PDE。raw checkpoint 到 absolute `3048`（累计 total-additional
`2048`，由 restore absolute `2024` 可证明 E1-local 至少 `1024` steps）时显式 true residual 为 `0.15346927855972448`；用户判断继续到 `1e-6`
预计需要数日，授权 `USER_AUTHORIZED_PERFORMANCE_CONTROLLED_STOP`。这不是 numerical
或 resource Gate fail：timeline peak RSS `1,466,142,720 B`、swap `0`，低于 MPI1
严格 `2,000,000,000 B` 线。

受控终止发生在 worker/parent closeout 前，完整 cycle/count history 和独立 checker
没有合法输入；这部分只作为 partial raw/lifecycle evidence，不宣称 E1 success。E2
fresh、E3 release/recovery、official complex E/H、near-field、R/T/A、0.7nm/2TiB
scalable solve 均 locked/not_run。compact 与 outcome 见
[`V18 E1 eventual outcome`](task038_extra_full3d_iterative_0p7nm/outcomes/restart64_physical_eventual_v18.md)
和
[`V18 E1 compact`](task038_extra_full3d_iterative_0p7nm/outcomes/records/restart64_physical_eventual_v18.json)。

---

# 项目开发进度：Task000–Task037b

## 2026-08-10：Task037b frozen M10 结项与 Review V7 selective-merge capability

Task037b 在 reviewed Task37b source `361908dd71fc12734b8ac19881d6e0d3aaae5d56` 的
V7 选择性范围内登记冻结 M10 Hybrid iterative research capability。它是显式 opt-in
研究入口，不改变 ordinary direct Hybrid 默认，也不提前宣称已经发布到 master；master
发布仍受 full pytest 与 integrated anchor Gate 约束。

| 维度 | 结论 |
|---|---|
| 冻结模型 | p6/h10、modal p6/h10、13.5 nm、S、10° grazing、10/110 nm、M120/candidate240、MPI8 |
| 算法 | exact Hybrid action；action-consistent modal Schur；两侧 fixed whole-endcap ILU(0)+40-mode DtN Woodbury；right FGMRES90 |
| 数值/物理 | 792 iterations；五项 residual、bottom/top exact traction、recovery、own-physics、80 orders、canonical 与 `12+12` authority comparison 通过 |
| 资源/生命周期 | process-tree RSS `6018.57421875 MiB`（`5.8775 GiB`），swap `0`；M10 cleanup 顺序与生命周期 Gate 通过 |
| ordinary boundary | `research_only`、explicit opt-in；ordinary direct Hybrid/default unchanged |
| 排除路线 | 0.7 nm、参数扫描、fallback、历史 negative machinery、post-V7 scaling 和 production promotion 不在本次能力范围 |
| 下一任务 | Task37c `planned / no task yet`；未创建 task 文件或实现 |

入口与 compact evidence 见
[`Case101 README`](../benchmarks/cases/101_hybrid_iterative_block_solver/README.md)、
[`M10 qualification compact`](../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_mpi8_traction_aligned_full_qualification_v1.json)
和
[`memory closeout compact`](../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v6_memory_optimization_closeout_v1.json)。

## 2026-08-07：Task037 静态凝聚 Full3D 迭代正式结项

Task037 在 reviewed source `d8b16c349f7726b4873ce1932668c12a1ba78926` 的选择性
合入线上完成收口。最终数值 formal source 是
`0fcf08a3f09e3beb137212d41f411823cb2e24e8`；后续 test53、格式和文档合同变化
不改变数值结论。

| 主线 | 实际结果 | 状态与边界 |
|---|---|---|
| E0 Matrix-free DtN | 80/80 modes；C/D `0/0`；action/recovery 约 `1e-15` | component Gate pass；ordinary default unchanged |
| M3a iterative | p6/h10 MPI1/2/4/8 full solve 通过；MPI4 official true | explicit opt-in research baseline；不是 production default |
| canonical | active/full relative L2 `1.2553897989392794e-06` / `7.880394014572244e-07` | `1e-5` comparator pass |
| F/E | frozen ideal-capacity negative；E1 pass、E2 late residual `6/6` fail | controlled negatives；不生产化 |
| Task37b | Review V7 selective-merge qualified research capability | frozen M10 MPI8 已完成；master 发布仍受 full pytest + integrated anchor Gate 约束 |

docs closeout 前的 10 个 code/test selective commits、5 个 Case100 compact records 和最终文档见
[`task037_static_condensed_full3d_iterative/outcomes/summary.md`](task037_static_condensed_full3d_iterative/outcomes/summary.md)。

## 2026-08-03：Task036 direct Hybrid 受控结项与选择性整合

Task036 的目标是修复 Hybrid 在小掠射角、P 偏振和弱衍射通道下不能完整复现
Full3D 的问题。最终证明域分解和 M120 长程传播核心本身可用，但低维端口没有覆盖完整
joint-Cauchy 界面信息；因此停止继续扩大 direct 端口，把通用修复和最小 research oracle
选择性保留，ordinary default 不变。

| 主线 | 实际结果 | 数据身份 / 边界 |
|---|---|---|
| compressed direct Hybrid | M120/M240 未闭合完整界面与全部通道 | `controlled_negative / closed`；not production-qualified |
| strong trace | E jump `4.588e-15`；energy `1.531666e-5 > 1e-5`；固定通道 `77/96` | `research_only`；19个通道失败不能忽略 |
| exact FE trace-chain | one-cell Schur、endpoint Cauchy 与 full trace-chain 证明域分解 correctness | `research_only correctness oracle`；不是 scalable solver |
| M120 modal core | 40/60/100 nm selected-space exact FE 对照约 `1.59e-11–1.95e-11` | retained；不等于 complete global port |
| B1/C1 | B1 `d<=360` controlled negative；C1b/C1c 取消且未运行 | 不恢复 capacity/POD/96-RHS campaign |
| 0.7 nm / 2 TiB | 未得到通过精度和资源合同的 solver | `not solved`；不得写成 conditional estimate 已兑现 |
| selective commits | Group1 `7735a261...`；Group2 `a741ad1b...`；Group3 `4c9e1b9...` | Task036 final SHA `7a033400...`；完整历史留远程分支 |
| 当前测试 | Group3 serial `7 passed`、MPI2 recursion 每 rank `1 passed`；最终 compact targeted `24 passed` + DtN/alias `14 passed`；p2 Full3D ordinary/static PDE smoke 各 `1 passed` | combined suite 在41 passed/107.99s后由用户中断；exit2/KeyboardInterrupt不是代码 failure；小时级 full pytest `cancelled/not_run` |
| Task037 | V7 selective master closeout 已完成；E0/M3a/canonical 证据与 A–F/E 关闭表已登记 | `closed`; M3a 仅 explicit opt-in；Task37b 尚未开始 |

结项入口见
[`task036_forward_solver_bugfix_hardening/outcomes/final_summary.md`](task036_forward_solver_bugfix_hardening/outcomes/final_summary.md)
与
[`task036_forward_solver_bugfix_hardening/review_report_v8.md`](task036_forward_solver_bugfix_hardening/review_report_v8.md)。

## 2026-07-26：Task035c Hybrid逐通道与p6/h10内存闭合

Task035c 用低成本p2/h5定位Full3D–Hybrid弱衍射级误差，再以p6/h10 MPI8
完成六路径高阶authority。普通默认保持`standard_full`；p3/h7.5按用户范围
未运行。

| 主线 | 实际结果 | 数据身份 / 边界 |
|---|---|---|
| channel root cause | Full3D z向使用scalar CG(p)离散相位/端点导数；旧Hybrid使用连续beta/traction | p2/h5 measured diagnosis |
| p2/h5 fix | corrected M120/M160均12/12 power + 12/12 boundary-plane amplitude | diagnostic pass |
| p6/h10 physics | Full3D standard/static、Hybrid standard/static M120/M160六路径均12/12+12/12；residual/RTA/Avolume/interface/field pass | measured MPI8；source `244b62e1...` |
| Full3D static | peak `34.041→14.722 GiB`，下降56.75%；total `2581.55→260.74 s` | measured process-tree RSS，zero swap |
| Hybrid static M120 | rows/NNZ/factor分别下降67.17%/79.63%/67.88%；peak `11.077→7.544 GiB`，下降31.89%；total ratio0.343 | mandatory/preferred memory pass |
| Hybrid static M160 | peak下降29.50%；没有物理收益且更耗时/内存 | M120 selected；M240 not run |
| user 50% target | 未达到；峰值在record-and-release，不在modal coupling本身 | lifecycle engineering gap |
| rank study | MPI1 QEP biorthogonality fail；MPI2 terminal-drain resource authority fail | two controlled negatives；MPI4 not run by stop rule |
| scope | p3/h7.5、h13 adaptive、0.7nm、irregular/tetra/mixed static、new iterative均未运行 | compliant |

完整回顾见
[`task035c_hybrid_channel_memory_closure/outcomes/summary.md`](task035c_hybrid_channel_memory_closure/outcomes/summary.md)，
compact authority见
[`../benchmarks/cases/096_hybrid_channel_memory_closure/README.md`](../benchmarks/cases/096_hybrid_channel_memory_closure/README.md)。

## 2026-07-25：Task035b Review V2 setup、内存下限与最终通道续研

Review V2 在同一 fixed rectangular block grating 和执行分支上并行推进
精度、setup 与内存三条主线；普通默认未改变，未合并 `master`。

| 主线 | Review V2 结果 | 数据身份 / 边界 |
|---|---|---|
| 最强精度点 | fixed p5-trace/p6-interior h13 仍为 89,740 DoF、20,120 rows、10/12 power + 10/12 amplitude | measured MPI8；未达 12/12 + 12/12 |
| fixed-DoF z-node | h13 top2 为实际 8/12 + 8/12；h14 exact-reverse 为 7/12 + 8/12 | 两个 bounded controlled negatives；关闭该 lane；先验投影不作实测 |
| physical selective trace | physical expansion、periodic/exact-sequence、Stage4 row omission、pre-release hook 和 owner-aware MatShell 已有 fixture/correctness 能力 | actual DWR、formal runner、candidate/PDE count 均为 0 |
| setup/cache | h15 non-KSP cold/warm 19.242/6.141 s；h13 19.410/6.696 s | hash-bound setup/resource authority；不替代通道精度 |
| direct rank memory | h15 MPI1/2/4/8 peak 为 1.295/2.158/3.100/4.711 GiB | measured、0 swap；MPI1 是最低实测 direct 点，不是理论下限 |
| iterative | Jacobi、ASM/ILU、physical z-slab + DtN 三条 MPI8 screen 均在 200 iter 不收敛 | controlled negatives；无 official R/T/A/channel；后两条含 local factor |
| Hybrid / 0.7 nm | eligible candidate=0；Hybrid、M/DtN funnel、resource model v3 未运行 | fail-closed；2 TiB feasibility unknown |

当前 blocker 是数值/生产集成而非用户环境：reduced fixed-trace local-Schur
捕获与 standard full-p6 generalized recovery 尚不能在同一次正式 run 中
闭合。没有密码、ABI、MPI 或磁盘硬 blocker，也没有理由重复已经完成的 heavy
PDE。集中回应见
[`task035b_high_order_local_hp_resource_envelope/response_v3.md`](task035b_high_order_local_hp_resource_envelope/response_v3.md)。

## 2026-07-24：Task035b Review V1 显著通道恢复批次

Task035b 只研究 Task034 fixed rectangular block grating；原 G1/G2/Phase F
不规则几何全部为
`out_of_scope_by_user / not_run / not_a_completion_gate`。

| 主线 | 结果 | 数据身份 / 边界 |
|---|---|---|
| p4/p5/p6 baseline | 同一 h10 hexa mesh/hash 上资格化；p6 为 173,802 FE DoF、51,272 active rows | measured MPI8；best available discrete，不是 continuum |
| high-p condensation | assembly-time exact cell Schur + Floquet slave elimination；full p6 matrix 不再分配 | measured；opt-in research path |
| memory lifecycle | p6 full 35.024 GiB 降至 isolated 15.964 GiB；factor release/heap trim 后后处理不再叠峰 | measured process-tree；ordinary default unchanged |
| assembly optimization | latest p6 build 102.32 s；fixed h15 preallocation mallocs=0、build 61.61 s、peak 5.803 GiB | measured MPI8；tensor dedup/preallocation positive |
| p6/h15 | 84,492 DoF，scalar/vector/field/resource pass，significant channels 6/12 power、8/12 amplitude | controlled negative |
| fixed p5-trace/p6-interior h15 | 74,890 DoF preferred band；channels 6/12 power、7/12 amplitude | controlled negative |
| significant channel reference v1 | 机械聚合既有高阶 authority；12/12 通道冻结 power/complex amplitude/magnitude/phase numerical bands | best-available same-code convergence authority；不是 continuum truth |
| 失败通道 adjoint | 16/16 Hermitian adjoint、direct-adjoint 与 finite-difference verification 通过 | measured MPI8；entity localization 仍是 coefficient proxy，不是 actual DWR |
| DtN/port 根因 | q31 与安全 scaled buffer-1 均无恢复；manufactured phase/normalization authority 通过 | 两个 independent negative + algebra authority；不宣称排除所有共同 port error |
| Lane A directional h | z-only h14 7/12+9/12，z-only h13 10/12+10/12；x/y controls 负 | h13 89,740 DoF、20,120 rows、6.411 GiB，是最强实测但未通过 |
| R5 slab 判别 | h14 最大 R5 slab 单次二分得到 89,740 DoF，退化为 5/12+9/12 | controlled negative；按预注册条件关闭 split-position scan |
| global p6/h14 discriminator | complex amplitude 12/12，但 power 9/12 且 92,850 DoF | controlled negative；超过 90k cap 2,850 DoF |
| Lane B selective trace | reference complement/Riesz 与预算审计完成；physical selection 所需能力未闭合 | `capability_stop_not_run`；candidate/PDE count=0，不把审计 pass 写成候选 pass |
| condensed iterative parallel direction | h15 direct authority已绑定，未来唯一 GMRES screen contract 已冻结 | `capability_stop_not_run`；当前无 dedicated hook/history/factor-free inventory，不伪造实测 |
| regionwise h10 | p4-trace N105 为有效 accuracy negative；p5-trace N62 缺 66 gradient modes | measured PDE + structural audit |
| multi-goal DWR | independent R00/R/T adjoints 与 normalized R/T marker pass | measured MPI8 |
| classifier v3 | 252-cell projection/decay；p-up102、p-keep150、h-refine0 | research-qualified；production_qualified=false |
| Hybrid / 0.7 nm | eligible candidate=0；Hybrid、M funnel、0.7 nm PDE 未运行 | fail-closed；planning sensitivity only |

最终分类为 `PARTIAL_WITH_CONTROLLED_NEGATIVES`。Task035b 解决了“rows 下降但
内存不降”的工程问题：只有同时消除完整 matrix、inactive rows、tensor
重复、preallocation 浪费和 factor 生命周期后，NNZ、factor、peak 和时间才
按正确方向下降。Review V1 又证明预算内 structured z-resolution 是当前最强
精度杠杆，但单一方向性 knob 仍不能闭合全部弱通道；选择性 trace 和
factor-free iterative 的下一步受可明确实现的 research capability gap 阻挡。
剩余 blocker 是完整 diffraction-channel accuracy 与相应算法能力，不是环境、
MPI、MUMPS 或 residual，也没有需要用户处理的密码/ABI硬 blocker。

详细证据见
[`task035b_high_order_local_hp_resource_envelope/outcomes/summary.md`](task035b_high_order_local_hp_resource_envelope/outcomes/summary.md)
与
[`../benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md`](../benchmarks/cases/095_high_order_local_hp_resource_envelope/README.md)，
集中回应见
[`task035b_high_order_local_hp_resource_envelope/response_v2.md`](task035b_high_order_local_hp_resource_envelope/response_v2.md)。

## 2026-07-21：Task034 WSL、固定几何高阶矩阵与 adaptive 决策收口

Task034 在 WSL Ubuntu 24.04 的 qualified complex ABI 上完成环境资格化与 post-merge hardening；Review V4 当前等待最终批准，未合并 master。

| 项目 | Task034 结论 | 数据身份 / 边界 |
|---|---|---|
| WSL/ABI | native complex PETSc/SLEPc/DOLFINx stack 通过，零 swap 监测和 watchdog 生效 | measured qualification |
| uniform benchmark | Case093 覆盖 p2/p3/p4 的 S 偏振固定几何序列；p3/h10 Hybrid 为 formal negative | measured；非 continuum proof |
| same-degree closure | p3/h3 与 p4/h5 M80/120/160 funnel 和 Full3D–Hybrid closure 通过 | measured accepted evidence |
| MPI | p3/h5 Full3D/Hybrid MPI1/8/16 identity 通过；MPI32 仅 exploratory | measured；不扩展全部矩阵 |
| supplemental resource stops | p2/h1、p3/h2、p4/h3 Full3D 只完成 assembly 后受控停止；factorization/full solve 未启动 | measured assembly + predicted upper；不得写成 solve |
| p4/h3 authority | 3035.139050935 s、80.537712097 GiB，采用 tracked process-tree compact authority | measured；40 行审计仅此两字段发生并已解决漂移 |
| graded-h | conforming mesh/Floquet/marker mechanism pass；三档 same-error compression 全部 controlled negative | research-only mechanism；field-driven adaptive 未资格化 |
| 0.7 nm | current-layout stress test 的多个单组件超过 2 TiB | engineering stress test；production DoF/M/peak unknown |
| merge | governance/docs/compact facts 可按 manifest 合入；未资格化 adaptive runner/mesh 保持 research_only_do_not_merge_yet | final Review V4 + user authorization pending |
| next | Task035 H(curl) field/goal-oriented adaptivity 仅完成 planning/theory package | 未执行 Task035 code 或 PDE |

统一 40 行事实表由 tracked compact fixture 在无 `benchmarks/artifacts` 的 clean checkout 中字节级重建；重型路径只作为 provenance string。详见 [`task034_workstation_wsl_adaptive_scalability/outcomes/summary.md`](task034_workstation_wsl_adaptive_scalability/outcomes/summary.md)。


## 2026-07-17：Task033 Review V6 F0 与选择性合并收口

Review V6 接受 Task33 的用户缩减范围。F0 没有重跑 PDE，也没有修改 Maxwell、
Floquet、QEP、Hybrid coupling、solver 或 physical postprocess kernel；新增的是
D1 descriptor-only source audit、跨记录执行语义、预测偏差、completion checker、
exact manifest 和文档同步。

| 项目 | 结果 |
|---|---|
| direct 3D p3/p4 Floquet | Case090 MPI1/2/4 共 144 PDE，核心 Gate 全过 |
| QEP p3/p4 | Phase A p3/p4 组件与 selected MPI identity 通过；legacy 全阶 aggregate 保留 p1/p2 负结果 |
| matching trace p3/p4 | Phase B p2 MPI1、p3/p4 MPI1/MPI4 五条通过；积分加阶 delta 0；无 full gather/dense square |
| Hybrid/full3D | 复用 Task032 p2/h5、p2/h3 同阶同网格对照；行数降低 65%–69%，NNZ 降低约 59% |
| p3/h5 Hybrid/full3D | 同阶 closure 通过；Hybrid 2.618 GiB vs direct 7.781 GiB，未证明网格收敛或墙钟加速 |
| fixed-p equal accuracy | p3/h10 accuracy negative；p3/h7.5 由 Review V6 接受为 fixed-p clear success，并将 FE DoF/local-system rows/total rows/factor-NNZ/memory/指示性时间改善 2.571x/2.567x/2.548x/3.557x/1.606x/1.331x |
| p4 / variable-p | p4 target 当前主机资源受限；native variable-p H(curl) capability fail closed |
| adaptive/graded/buffer/1 TiB | adaptive 与 1 TiB 更新移交下一独立任务；buffer 等待 defect geometry；不再阻塞 Task33 |
| prediction audit | p3/h10 1.947→1.980 GiB；p3/h7.5 2.463→3.667 GiB；旧模型未重校准前禁止用于 1 TiB |
| completion/merge | reduced scope complete；original full scope partial/NOT_RUN；精确 selective merge 获批，whole branch 禁止 |
| source | Stage1 `6613f94...`；Phase A `bb830ba...`；Phase B `bd7a602...`/`9ac29db...`；Phase C `b636444...` |

详细结论见
[`task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md`](task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md)。

## 1. 文档定位

本文档记录项目从初始代码审查到 Task033 当前阶段的完整开发进程，面向：

```text
- 项目开发者；
- 后续 Codex/ChatGPT 任务；
- 新加入的维护者；
- 需要判断当前能力、历史路线和下一步优先级的用户。
```

本文档不是逐次实验的原始日志。详细证据仍位于：

```text
docs/taskXXX_*/task.md
docs/taskXXX_*/outcomes/
docs/taskXXX_*/review_report*.md
```

本文档负责回答：

```text
1. 每个阶段为什么开始；
2. 实现了什么；
3. 哪些结果成功；
4. 哪些路线失败或被替代；
5. 当前主线最终保留了什么；
6. 项目现在能做什么；
7. 尚未完成什么。
```

更新时间：

```text
2026-07-26
current branch = codex/20260726-task35c-hybrid-channel-memory-closure
Task028 status = V4 closed and merged to master at 2f9e56d
Task029 status = diagnostic_success; review V2 closed; merged to master at bfb6586e
Task030 status = final review V3 passed and merged to master at 545165b
Task031 status = strong_memory_success_slow_but_memory_efficient; Review V2 passed; merged to master at dae03170
Task032 status = hybrid_direct_engineering_success; Phase 0-10 complete; Case080 302/302; h2 locked by mandatory memory prediction gate
Task033 status = review-v6 reduced scope complete; fixed-p p3/h7.5 clear success with qualifications; original full scope partial by transfer
Task034 status = PASS_WITH_QUALIFICATIONS; Review V3 blockers closed; final Review V4 and user merge authorization pending
Task035 status = Review V6 research baseline; Task035b successor active
Task035b status = CLOSED_WITH_CONTROLLED_NEGATIVES by Review V4
Task035c status = mandatory channel/memory closure complete; 50% Hybrid memory target remains open; response_v1 pending review
```

## 1.1 2026-07-15 最新更新

Task032 Review V1 接受 13.5 nm h5/h3 物理与数值实现，但在选择性合并前要求表格化回顾、
0.7 nm 资源评估、长期规则、manifest 和项目文档闭环；addendum 又明确撤回 pure-modal/y-invariant
优先主线，保留未来复杂 3D 两端。当前 review follow-up 的统一结论为：

| 项目 | 结论 | 数据身份 / 边界 |
|---|---|---|
| 13.5 nm Task032 | `hybrid_direct_engineering_success` | measured/derived，h5/h3 same-grid |
| h2 | `not_run_by_gate` | predicted 两方法均失败，未运行 |
| 参数 1–10° S/P | 30/30 interface/API smoke | measured M4；非 production qualification |
| h3 best direct memory | 3.224 GiB，较 augmented -16.31% | measured simultaneous worker RSS |
| full3D→Hybrid algebra | h5/h3 rows -68.62%/-65.35%；NNZ -59.14%/-59.68% | derived from measured rows/NNZ |
| current direct at 0.7 nm | not resource feasible | analytical projection，非 PDE run |
| 1 TiB final Hybrid | credible conditional opportunity | 尚未证明，需 h/p + scalable modal + iterative |
| ordinary default | unchanged | explicit opt-in only |

`M` 的统一含义是每个传播方向保留的中间截面模式数；M160 即 160 forward + 160 backward =
320 internal modal amplitudes。未来主线是 exact complex 3D FEM ends + generic `epsilon(x,y)` modal
middle；y-sector/pure-modal 只作当前简单结构的可选诊断/reference。

历史顺序已由 Task034/Task035 权威更新：Task034 完成 WSL、fixed-geometry benchmark 与
controlled graded-h 决策；Task035 为 H(curl) field/goal-oriented adaptivity；其后分别启动
scalable modal core、low-memory Hybrid iterative 和未冻结编号的
13.5→5→2→1→0.7 nm wavelength continuation。详情见
[`task032_0p7nm_scalability_assessment.md`](task032_hybrid_fem_modal_direct_baseline/outcomes/task032_0p7nm_scalability_assessment.md)
和 [`response_v1_review_followup.md`](task032_hybrid_fem_modal_direct_baseline/response_v1_review_followup.md)。

Task032 Phase 6f--10 已闭合。clean h5/h3 M120/M160 记录完成物理 E/H、接口连续、
体吸收、五个选面、逐衍射级输出和 augmented/Modal-Schur 对照；两档 M120->M160
最大 total delta 分别为 `6.24e-14/1.22e-14`。h3 M160 相对同网格 full-3D
的 R/T/A 差为 `-2.12e-7/-2.42e-6/+2.63e-6`，场与吸收 Gate 通过。
30 组角度/S-P 参数入口 smoke 全过，但不升级为全区间 production qualification。

六条 clean MPI4 M160 外部内存记录全部数值通过、零 swap。h3
augmented/Schur-fast/Schur-memory-minimal 为 `3.853/3.998/3.224 GiB`；只有顺序
factor 生命周期相对 augmented 下降 `16.31%`。h2 的网格尺度与 factor-payload
预测分别为 `5.365/6.170 GiB` 和 `11.647/13.394 GiB`（中心/上界），均未过
4/5 GiB 强制 Gate，因此 h2 按任务书未运行。最终 Case080 checker 为
`302/302 passed`，分类为 `hybrid_direct_engineering_success`；Review V1 已完成，当前等待
follow-up 复审和用户许可后按 manifest 选择性合并；Task033 在该闭环完成前不启动。

Phase 6a/6b/6c 已按小步完成。上下局部三维 p2 Nédélec/Floquet 网格只覆盖外边界到 z=10/110 nm 接口，中间 100 nm 不再生成三维体单元；每个局部系统只装配其真实拥有的一侧外部 40-mode Fourier-DtN。内部耦合新增分布式 `M x N` trace projection、`N x M` 正/负 traction、`M x M` 负迹映射和无 growing inverse 的 `P+/P-`，内部 unknown/equation 均为 `2M`，没有 dense `N_interface^2`。

Phase 6c 的 MPI 路由按结构化 `(x,y)` cell owner 只交换接口点值，不聚集完整 field/mode；collective 已移出 DOLFINx interpolation callback。修复测试辅助函数的临时 PETSc 包装器后，最终 serial 为 `4/4`、MPI2 每 rank `4/4`、MPI4 每 rank `4/4`，所有具名测试容器均已删除。该子步边界是 block assembly；随后 monolithic augmented matrix 与 MUMPS algebra Gate 已按下一段完成。

Phase 6d 已建立 rank-major monolithic PETSc AIJ：每个 rank 连续保存自身 bottom/top rows，最后一个 rank 再保存 `2M` 内部 modal rows，从而把两个独立 local distributions 合法拼入普通 MPI AIJ。unknown 为 `[u_bottom,u_top,a_b+,a_t-]`，outgoing amplitudes 只通过稳定 `P+/P-` 消元；MUMPS 设置 error-if-not-converged 并显式计算 `||Ax-b||/||b||`。h10 两条解析 Bloch mode 的 serial/MPI2/MPI4 均为每 rank `3/3`；MPI4 矩阵 `2432 x 2432`、`251720` nnz、真相对残差 `3.732133e-13`，setup/solve `0.046960/0.003048 s`。这只分类为 `augmented_algebra_pass`；真实 Phase 3 QEP basis、M 收敛、接口 E/H 连续、official R/T/A 和 full-3D 比较是下一步。

Phase 6e 已完成真实 QEP h5/M2/4/6 研究漏斗，并在 clean source `5c1f12e610dd8c6040389c44c31584ab7fba66cd` 生成 h5/M6 MPI4 集成记录。修复了正负 basis 重复 Poynting evaluator、SLEPc 超额 `nconv`、Windows bind mount 容器内 Git status 卡顿、Nédélec 边界点任意 source-cell 路由和近简并 block threshold 五个问题。clean M6 的 10 个集成 Gate 全过，单体 `13744 x 13744`、约 `1.4704e6` nnz、真残差 `1.8590e-12`；研究漏斗 M4->M6 R/T/A 变化约 `1e-12`，Case080 为 `294/294 passed`。当前仍不称完整 physical pass：pointwise H jump、体吸收、中间选面重建、h3 和 simultaneous RSS 未完成。

### 2026-07-14 前序更新

Task032 已从 Review V2 通过后的 Task031 clean merge `dae03170` 启动。旧目录 `fenics_vector_maxwell_floquet_demo_v2_parallel` 保持 Task031 分支和既有未跟踪材料不变；新目录 `fenics_v3_hybrid_FEM_modal` 从更新后的 `origin/master` clean clone，并创建、推送 `codex/20260714-task32-hybrid-fem-modal-direct-baseline`。迁移、环境和 smoke 证据见 [`task032_hybrid_fem_modal_direct_baseline/outcomes/`](task032_hybrid_fem_modal_direct_baseline/outcomes/summary.md)。

Phase 0 确认本机合格镜像提供 PETSc complex128、DOLFINx 0.10.0.post2 和 SLEPc 3.24 PEP/TOAR；compile/import、8 个 condensation/action 合同测试、最小 Stage4 和 h5 MPI4 target direct 均通过。最小 Stage4 首次暴露 flat preset 仍继承 `50 x 50 x 50 nm` 光栅块的旧回归；通过显式零尺寸 A/B 定位后，只修复三个 preset 几何字段并新增合同测试，原始命令恢复通过。h5 基线为 44,698 FE DoF、80 auxiliary modes、真相对残差 `1.3033e-11`，`R/T/A=0.0890216029/0.4425882787/0.4683901184`，闭合误差 `1.2124e-13`。

Phase 1 已加入默认关闭的 full-3D reference exporter：在 z=`10/30/60/90/110 nm` 输出 40x20 结构化 complex128 E/H，并显式保存 z=10/110 的 x/y tangential traces。接口在单元公共面时从中间模态区单侧取迹，384000-byte 冻结载荷受 64 MiB fail-closed guard 保护，不聚集完整 FE vector。

clean commit `c468c728...` 的正式 MPI4 h5/h3 reference 均通过：DoF 为 44,698/198,438，真相对残差为 `9.734e-12/9.923e-12`，闭合优于 `1.3e-13`；h3 `R/T/A=0.0046130314/0.5836533572/0.4117336114` 与历史 direct h3 一致。h5 与 h3 差异明显，因此 h5 只作快速开发、h3 作为主 reference，不宣称 h5--h3 网格收敛。Case080 已保存 clean identity、命令、image digest、field/diffraction hash 与自动 Gate，checker 为 `271/271 passed`。

Phase 2 已实现匹配 Stage4 x/y 轴的 quadrilateral 截面、`N1curl(p2) x Lagrange(p2)` 混合空间、双 Floquet orientation-aware 约束、无 slave-chain 的分布式 `u=Cq`、`C^H K C` 稀疏约化和原生 SLEPc PEP/TOAR QEP。完整 eigenvector 不聚集到 rank0；Phase 2 electric-L2 只建立稳定场尺度，Poynting/left-right 双正交仍留给 Phase 3。正式 MPI4 record 固定在 clean source `33211a4...`：air h5/h3/h2/h1.5 的 beta 解析相对误差严格降至 `29.5323%/5.58859%/1.12629%/0.454640%`，lossy h2 误差 `1.19656%`，当前材料 h3 beta 为 `0.0753551902+0.00178364869j 1/nm`；最大 QEP 相对残差 `1.8177e-15`，`+/- beta` 配对误差 `7.50e-16`，electric-L2 范数误差 `4.44e-16`。完整 serial suite 为 186 tests/10 skipped，MPI4 Phase 2 为每 rank 5/5，checker 为 `277/277 passed`。接口 coupling 和 Hybrid direct solver 尚未开始，下一步为 Phase 3 分类与最终归一化。

Phase 3 已实现由混合 E 场重构阻抗缩放 H、z 向 Poynting 分类、near-zero flux 的 `Im(beta)` 衰减分支、显式伴随 QEP 左模、`Q'(beta)` left/right 双正交、近简并 block inverse、正反向 identity 和相邻角度/模式数变化的 overlap tracking。全量 serial suite 为 190 tests/10 skipped；Phase 3 serial 4/4 与精简 MPI4 4 项（每 rank 2 skip）通过。clean source `72dca66...` 的正式 MPI4 h10 record 对 air/lossy/current-patterned、air 正反配对和 80°→79.8° tracking 的 9 个 runner Gate 全通过。双正交误差 air/lossy 约 `1e-15`、patterned `2.46e-10`，左右残差约 `1e-16–1e-15`，principal angle 最大 `0.005918 rad`，完整向量不聚集。Case080 checker 增至 `282/282 passed`。h10 仅是分类合同；Phase 4 尚未开始。

Phase 4 已实现 O(M) 存储的 two-port 对角传播：incoming 为 bottom-forward/top-backward，outgoing 为 bottom-backward/top-forward；正反方向分别使用 `+L/-L` 坐标位移，禁止 growing inverse。纯传播 6 项合同、真实 Phase 3 air basis 集成和 MPI4 runner 的 8 个 Gate 均通过；覆盖 100 nm 无反射、lossy/evanescent 被动衰减、37+63 nm composition、reciprocity 负对照和四 rank 一致性。clean source `9206e9c...` 的正式 record 固定 exact Phase 3 record hash；最大 composition 误差 `9.42e-16`，air reciprocity beta/factor 误差 `3.63e-16/2.78e-15`，三个 case reflection norm 为 0。Phase 4 冻结时 Case080 checker 为 `286/286 passed`；Phase 5 见下一段。

Phase 5 已实现匹配网格的 3D Nédélec 切向迹提取、2D mode trace 重构、left/right Petrov 投影、bottom/top 双域法向约定和质量范数 residual。3D→2D 路径只交换接口插值点及两个复切向分量，允许某些 rank 没有本地 source evaluation，不聚集完整 field/mode vector。clean source `b565ac4...` 的正式 MPI4 record 通过 8/8 Gate：bottom/top 各 18 个匹配接口面、162 个 trace DoF，Stage4 两模 Gram 条件数 `30.4995`，系数 round trip/重构 residual 为 `3.78e-16/4.69e-16`，3D→2D 迹误差为 `4.52e-15/6.61e-15`；air 近简并旋转的 projector error 为 `2.11e-8`，且未形成 dense `N_Gamma^2`。完整 serial 回归为 `199 tests / 10 skipped`，Phase 5 MPI4 为每 rank `3/3`，Case080 checker 在 Phase 5 冻结时为 `290/290 passed`；Phase 6 后续进展见本节顶部最新更新。

Task031 Review V1 接受正式 h5/h3/h2 的数值正确性与 absolute memory strong Gate，不要求重跑正式计算；合并前加固集中在 master 同步、端口文档、matrix-free/performance 术语、内存口径和选择性合并边界。分支已真实 merge 当前 `master`，保留 [`project_service_requirements_and_forward_model_roadmap.md`](project_service_requirements_and_forward_model_roadmap.md) 与 [`project_service_requirements_phase1_scope.md`](project_service_requirements_phase1_scope.md)：后续统一规划范围为 `13.5 nm + fixed Si + 1–10° grazing + S/P`，但 Task031 只资格化 theta=80°（10° grazing）、S polarization 的 frozen 单点。

新增 [`iterative_solver_ports.md`](iterative_solver_ports.md)，统一列出 Task27 canonical、Task30 compact、Task31 memory-first 的命令和身份；FGMRES 是当前 adaptive PC 的合法/已资格化 outer port，普通 GMRES 被线性认证阻塞，TFQMR/BCGS 只有未资格化接口，fixed Richardson 与 selective boundary Jacobi 是 research-only numeric negative。Task31 的精确术语是 assembled-F-free public MPC form-action path，不是缓存优化的低层 element-kernel matrix-free；一次性 `release_f()` 不是变慢主因，每次 form action 的装配与通信才是主要成本。

Task030 Review V3 已通过并按用户许可合入 master（merge `545165b`）。Task031 从该 clean merge point 创建独立分支，目标是在 frozen p2/80-mode/exact-condensed target 上继续压缩内存，同时把 explicit true residual 收敛置于所有性能目标之前。

Task031 新增外部 simultaneous RSS/cgroup/swap/stage sampler、public DOLFINx-MPC form action、condensed fine-action lifecycle、PC linearity/determinism certification、exact factor fingerprints 与对象 ledger。研究漏斗否定了 restart50、ordinary GMRES、fixed Richardson、20 slabs、boundary Jacobi 与 factor dedup；保留的组合是 FGMRES90 + Task030 physical-slab/wave coarse + 16 slabs overlap0.125 + assembled-F-free public form action + compact lifecycle。

clean SHA `45a0fc6e...` 的 full h5/h3/h2 分别在 1157/1994/1977 步达到 full residual `9.960e-7 / 9.974e-7 / 9.998e-7`。外部 simultaneous worker peak 为 1.619598/3.474346/7.897675 GiB，h2 legacy internal peak 为 8.176441 GiB。相对 Task030 历史 9.374729 GiB 的辅助观察降幅约 15.8% / 12.8%，因 sampler 不完全同口径，保守结论为从约 9.4 GiB 压到约 8.0–8.2 GiB。h2 达到 strong memory success 且无 swap；代价是 solve 11982.581 s，约为 Task030 的 5.01x，因此分类为 `strong_memory_success_slow_but_memory_efficient`，ordinary default 仍不改变。

Task029 已按用户许可合并；Task030 从 `bfb6586e` clean master 创建独立分支。Task030 建立了 active/master-aware nonmatching H(curl) transfer 与 exact condensed Galerkin 基础设施，但五个正式 p/h 候选 100 步残差均比 Task027 基线差 146–264 倍，证明当前 792D p1 coarse 不是目标慢误差的有效表示。

真正正反馈来自 Task27-derived physical-slab + 75D wave-coarse 架构，并加入 symmetric pre/post sm2、ILU0、subdomain-local shift、factor-only storage 和 FGMRES restart90。Review V2 后，h5/h3 在 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上 clean 复跑，分别用 855/962 步收敛，峰值 1.687653/3.792912 GB；h3 同时通过 3.8 GB 绝对线和相对 Task027 canonical 降低 25.37% 的相对线，iteration ratio 为 1.125。h2 不重跑，保留为 1873 步、full true residual `9.972e-7`、含 R/T/A 峰值 9.374729 GB（-28.33%）的 reviewed historical dirty-worktree reference。因此分类为 `workstation_memory_success_with_qualifications`；ordinary default 未改变。

Review V1 接受数值结果并要求修正 benchmark/provenance。三份正式 records 已从原 artifacts 恢复 source commit、tracked-dirty qualification、完整命令/时间/镜像/host 和 artifact SHA-256；Case060 已接入 203 项真实数值 Gate，三份记录也进入 manifest，使 normal checker 可重复生成完全相同的 summary。当前 ILU1/ILU0 reported factor nnz 相同，不能宣称 factor-nnz compression；factor-only 只在 PETSc 3.24.0 complex build 验证，跨版本需回归。

Task028 已按普通 merge commit 合入 `master`，并完成 master release check。Task029 从该合并点新建独立分支，完成 direct-memory telemetry、外部 0.25 s sampler、matrix/factor inventory、Case050、h5/h3 baseline、H1–H7、profile 筛选和 h2 安全决策。遥测明确区分 simultaneous worker RSS、各 rank 历史峰值和、MPI 进程树与 cgroup；Task28 canonical records 保持只读。

MPI4 h5/h3 baseline simultaneous RSS 为 2328.145 / 8651.098 MB，主峰都位于 KSPSetUp。release-base 公共生命周期候选在 h3 只下降 5.462%；最佳 default MUMPS MPI2 在 h5/h3 分别下降 28.893% / 15.119%，全部 residual/R/T/A Gate 通过且无 swap，但 h3 低于 20% 工程门槛。因此 Task029 分类为 `diagnostic_success`，不产生合格低内存 direct profile。h2 两类外推中央值为 22.214 / 22.330 GiB、区间 18.882–27.913 GiB，G3/G5/G7/G9 失败，未启动 h2。

Review V1 后补充的构建/链接与固定四核审计确认，当前 PETSc/MUMPS 链接可控的 OpenBLAS pthread，但 MPI1×4 在 KSPSetUp 的 CPU 核均值/峰值仅 0.999/1.054，Stage4 相对 MPI1×1 只有 1.054× speedup。最终身份为 `threaded_direct_capability=unavailable_in_current_image`，因此 threaded h3 按 T4 `not_run`；ordinary default 仍不改变。

---

# 2. 项目总体目标

项目目标是建立可验证、可扩展的二维和三维频域 Maxwell 有限元求解框架，重点面向周期微纳结构和 EUV 光栅散射。

长期物理能力目标：

```text
- 2D/3D Maxwell frequency-domain solve；
- real/complex refractive index；
- Floquet periodic boundary conditions；
- PML、Fresnel interface 和 periodic modal port；
- Nedelec H(curl) elements；
- diffraction orders；
- official R/T/A；
- material volume absorption；
- field output；
- mesh/order/angle/wavelength scans；
- direct and iterative solvers；
- low-memory workstation and future HPC execution；
- eventual geometry/material inversion support。
```

当前长期参考模型：

```text
domain = 50 x 25 x 140 nm
period = 50 x 25 nm
grating = 17 x 25 x 120 nm
substrate thickness = 10 nm
top air above grating = 10 nm
wavelength = 13.5 nm
theta_from_z = 80 deg
phi = 0 deg
polarization = s
material = complex Si index
space = 3D N1curl p=2
side boundaries = double Floquet
z boundaries = periodic modal DtN ports
```

---

# 3. 阶段总览

| 阶段 | Task | 主要目标 | 最终状态 |
|---|---|---|---|
| A. 初始整理与物理口径 | 000–004 | 整理代码、R/T/A、体吸收、能量闭合、MPI/p 回归 | 基础工程链稳定 |
| B. 目标几何与直接法边界 | 005–010 | 真实 3D 资源、official DtN、目标几何 direct、BLR | h=2 direct reference 建立 |
| C. AMS/HX 与低维模态路线 | 011–019 | 低内存 Krylov、real split、AMS/HX、sampled Schur | p1 有信号，p2 主线失败并关闭 |
| D. wave-aware 与 FE-response/Schur | 020–025 | residual-aware modes、FE response、PETSc/MPI Schur、cached-Q | 数学结构成立，h=2 response 质量不足 |
| E. auxiliary-free 与 workstation solver | 026–027 | exact condensation、matrix-free、physical slab two-level PC | h=5/3/2 MPI4 达 production residual |
| F. 阶段收口与可复现版本 | 028 | clean master 整合、文档、benchmark、阶段版本 | V4 完成并合入 master |
| G. direct memory forensics | 029 | simultaneous RSS、factor inventory、生命周期/profile 筛选、h2 Gate | diagnostic_success，等待审查 |

---

# PART I：阶段 A——初始代码整理与物理口径

## 4. Task000：初始代码审查与工作流整理

### 目标

```text
- 阅读项目结构；
- 识别 2D/3D 代码边界；
- 建立 task -> outcomes -> review 的开发流程；
- 记录代码问题和后续优先级。
```

### 主要成果

```text
- 建立任务目录规范；
- 建立代码审查和结果追踪习惯；
- 明确理论笔记、运行结果和任务记录的目录职责；
- 为后续 Stage4 验证提供审计基线。
```

### 当前状态

```text
success_type = documentation/workflow success
code_status = 被后续稳定实现替代
retained_value = 可追溯开发流程
```

---

## 5. Task001：Stage4 validation cleanup

### 目标

清理早期 Stage4 路径中的配置、输出和验证逻辑，减少不同案例之间的隐式差异。

### 主要成果

```text
- 整理 Stage4 case flow；
- 清理输出与验证标签；
- 建立较一致的运行 summary；
- 为后续功率口径修正做准备。
```

### 局限

```text
- 当时的 R/T/A 仍不是最终 official 口径；
- 真实目标几何和 p=2 资源边界尚未建立。
```

### 当前状态

后续 Task003、Task007 和 Task008 已吸收该任务的有效成果。

---

## 6. Task002：R/T/A 输出与 volume absorption

### 目标

```text
- 输出反射率、透射率和吸收率；
- 增加有损材料的体积分吸收；
- 比较不同功率计算方式；
- 检查能量守恒。
```

### 主要实现

```math
P_{abs}
\propto
\int_{\Omega_{loss}}
\operatorname{Im}(\varepsilon_r)|E|^2\,dV.
```

新增或整理：

```text
- port power；
- probe Fourier power；
- sampled net flux；
- A_volume；
- energy closure fields。
```

### 关键发现

初始不同功率口径不一致，不能直接将 probe 或 sampled flux 作为 official R/T。

### 当前状态

```text
infrastructure_success = yes
diagnostic_success = yes
initial_physical_result = superseded by Task003/007
```

---

## 7. Task003：Stage4 power consistency

### 目标

建立统一、可信的功率和能量闭合口径。

### 主要成果

```text
- flat-layer analytic sanity；
- port + A_volume 能量闭合；
- probe 和 sampled flux 降级为 diagnostic；
- 统一能量 closure 字段；
- 修正后续主线的功率验收规则。
```

### 长期保留结论

```text
official power = modal port power
volume absorption = material loss integral
probe-plane Fourier = diagnostic only
sampled net flux = diagnostic only
```

该结论持续沿用到 Task028。

---

## 8. Task004：small-cell p convergence、MPI consistency 与全阶段回归

### 目标

```text
- 小尺寸 flat-layer benchmark；
- p=1/p=2 比较；
- MPI1/4/8 一致性；
- Stage1、2A、2B、2C、4 smoke；
- 防止前几轮修改破坏已有路径。
```

### 主要成果

```text
- p=2 明显优于 p=1；
- official port + A_volume 在小模型上稳定；
- MPI rank 数不改变主线结果；
- Stage1/2A/2B/2C/4 的基本路径可以运行；
- 建立长期 regression baseline。
```

### 边界

```text
- Stage2B PML 和 Stage2C Fresnel 当时只做 smoke，不代表高精度验证；
- small-cell 不是目标 3D EUV 光栅物理 benchmark。
```

### 当前状态

```text
production/infrastructure baseline = retained in master
```

---

# PART II：阶段 B——目标几何、资源边界与直接法

## 9. Task005：真实 3D 光栅内存和直接法资源估算

### 目标

评估真实 3D 光栅中：

```text
- mesh size；
- DoF；
- matrix nnz；
- assembled matrix storage；
- direct LU fill-in；
- MUMPS OOC；
- workstation resource boundary。
```

### 关键发现

```text
- assembled matrix 并非唯一瓶颈；
- MUMPS LU fill-in 和 factor workspace 才是主要峰值；
- 粗网格可以完成，细网格 direct 很快进入内存边界；
- 继续仅依赖 direct 无法支持更细 p=2 3D 模型。
```

### 当前状态

保留为容量规划和失败边界证据，不作为当前推荐 solver。

---

## 10. Task006：缩短计算域与 OOC 资源分析

### 目标

尝试用较短 z 域降低矩阵规模，评估：

```text
- 70 nm reduced-height domain；
- direct/OOC 可达网格；
- 结果对 domain height 的敏感性；
- 资源外推。
```

### 成果

```text
- 明确 reduced-height 能显著减小矩阵；
- 修正真实光栅 top probe 位置；
- 记录 OOC scratch 和失败边界；
- 区分 matrix RSS 上界与进程树真实峰值。
```

### 负结果

```text
- 70 nm 域的 R/T/A 与更高域明显不同；
- 不能把 reduced domain 当作物理等价 benchmark；
- OOC 不能自动解决细网格 direct。
```

### 当前状态

```text
resource diagnostic retained
physical benchmark superseded by Task008
```

---

## 11. Task007：恢复 DtN modal amplitudes 作为 official R/T/A

### 目标

明确 Stage4 periodic modal port 的官方功率来源。

### 最终口径

```text
R_total = outgoing top DtN modal power / incident power
T_total = outgoing bottom DtN modal power / incident power
A_volume = material volume loss / incident power
closure = R + T + A_volume - 1
```

### 关键成果

```text
- auxiliary DtN modal amplitudes 成为 official power source；
- probe Fourier 和 sampled flux 降为 diagnostic；
- 有损基底的 T 与 port reference plane 相关这一边界被记录；
- 后续所有 Task 使用统一口径。
```

### 当前状态

```text
stable production power definition
```

---

## 12. Task008：目标几何 p=2 direct benchmark

### 目标模型

```text
50 x 25 x 140 nm unit cell
17 x 25 x 120 nm grating
13.5 nm
80 deg from z
s polarization
complex Si
p=2 Nedelec
double Floquet + 80 DtN auxiliary modes
```

### 主要成果

建立目标模型 direct reference：

```text
p=2 h=2 nm
R = 0.0013429328462348958
T = 0.5992132294442478
A_volume = 0.3994438377095067
R+T+A = 0.9999999999999893
```

同时记录：

```text
- p=1 和 p=2 direct 可达边界；
- p=2 h=1.5 direct setup 被内存杀死；
- p=2 h=1 assembled matrix/交换空间压力很高；
- h=2 是 workstation best-effort direct reference，不是最终无限细网格极限。
```

### 当前状态

```text
current direct reference = retained
ordinary direct default = retained
```

---

## 13. Task009：黑盒 PETSc 迭代 profile 筛选

### 目标

快速测试：

```text
GMRES / FGMRES / BiCGStab
Jacobi / BJacobi / ASM / ILU / local LU
GAMG / FieldSplit / BoomerAMG diagnostics
```

### 关键结果

```text
- 没有现成黑盒组合达到 production residual；
- GMRES + Jacobi 只能稳定降低残差，不能收敛；
- ASM/ILU/local LU 多数停滞或恶化；
- 未收敛配置禁止输出 official R/T/A。
```

### 关键纠偏

早期记录的：

```text
residual_final / residual_initial
```

不等于：

```text
||Ax-b|| / ||b||
```

从此建立 reported/KSP residual 与 explicit true residual 的严格区分。

### 当前状态

```text
negative-result baseline retained
black-box PC route closed
```

---

## 14. Task010：MUMPS-BLR 与 shifted Maxwell 原型

### 目标

```text
- 测试 MUMPS-BLR compressed factorization；
- 打通 A/P 双矩阵接口；
- 测试 minimal shifted/positive Maxwell P；
- 为 AMS/HX 做工程预检。
```

### 正结果

h=2：

```text
FGMRES + MUMPS-BLR eps=1e-5
iterations = 4
true residual ≈ 2.09e-8
R/T/A 与 direct 一致到约 1e-9
```

### 边界

```text
- BLR 仍属于近似直接因子，不是最终低内存迭代法；
- h=1.5 仍在 setup 阶段被内存杀死；
- minimal shifted/positive Maxwell + ASM/ILU 未收敛。
```

### 当前状态

```text
BLR = explicit fallback/reference
shifted A/P infrastructure = historical foundation
```

---

# PART III：阶段 C——AMS/HX、real split 与低维 sampled-Schur

## 15. Task011：低内存 Krylov、AMS/HX smoke 与 matrix-free feasibility

### 目标

```text
- low-restart Krylov + Jacobi；
- real FE-only hypre AMS/HX；
- complex AMS safety；
- matrix-free FE action。
```

### 结果

```text
Jacobi-Krylov:
- 低内存；
- 不收敛；
- 路线基本关闭。

real FE-only AMS:
- p1/p2 小模型有真实收敛信号；
- p=2 h=5 可到约 1e-6；
- 但内存和完整 Stage4 兼容性未知。

complex AMS:
- 当前 build 下崩溃，不安全。

matrix-free FE action:
- 与 assembled action 误差约 1e-15；
- 证明少存矩阵可行；
- 但不解决 inverse/PC 问题。
```

### 当前状态

```text
matrix-free foundation retained
AMS result = research signal only
```

---

## 16. Task012：Maxwell 预条件器文献调研与路线设计

### 覆盖方向

```text
- H(curl) auxiliary space / Hiptmair-Xu / hypre AMS；
- shifted Maxwell / complex shifted Laplacian；
- overlapping Schwarz / optimized Schwarz；
- sweeping / moving PML；
- DtN-aware block preconditioner；
- Rayleigh/Floquet modal deflation；
- matrix-free high-order Maxwell；
- BLR/H-matrix fallback；
- layered/RCWA-like approximate inverse。
```

### 结果

停止盲目添加 PETSc profile，转为有 Gate 的物理预条件器研究。

### 当前状态

理论和路线文档长期保留，但每条方法的生产状态以后续数值任务为准。

---

## 17. Task013：real-split AMS/HX qualification

### 目标

绕开 complex hypre AMS 崩溃，将复杂 Maxwell FE operator 写成实数块系统：

```math
\begin{bmatrix}
\operatorname{Re}A & -\operatorname{Im}A\\
\operatorname{Im}A & \operatorname{Re}A
\end{bmatrix}.
```

### 成果

```text
- complex-to-real matvec 等价误差约 1e-16；
- real hypre AMS 可安全运行；
- same-H1 auxiliary 显著降低内存；
- FE-only p=2 h=5 达到 true residual <=1e-6。
```

### 局限

```text
- 不含 Floquet MPC 后完整结构；
- 不含 DtN auxiliary unknowns；
- 不含目标 Stage4 R/T/A；
- isolated serial research runner。
```

### 当前状态

```text
B-grade research positive
production code not merged
```

---

## 18. Task014a：reduced Stage4 real-split FE/aux block PC

### 目标

把 Task013 FE-only 正信号接到约化 Stage4：

```text
FE block -> same-H1 AMS
aux block -> identity/exact small block
```

### 成果

```text
- Stage4 complex-to-real equivalence 通过；
- FE/aux block indexing 通过；
- MPC 后 AMS data 可构造；
- MPI ownership 和数据布局明确。
```

### 负结果

```text
FE-AMS + aux identity
1000 steps
true residual ≈ 2.15e-2
```

只比 Jacobi 改善约 1.6 倍，不能进入 p=2/full Stage4。

### 结论

FE-only AMS 正信号不能直接搬到包含 DtN coupling 的完整问题。

---

## 19. Task015：DtN/Floquet boundary-aware diagnostic

### 目标

定位 Task014a 的 residual 停滞来源。

### 关键发现

FE-AMS 之后，剩余 residual 几乎全部集中在：

```text
top port
Rayleigh order (0,0)
y/s polarization
```

进一步证明：

```text
- aux block identity/exact/diag 本身不是瓶颈；
- aux-only modal correction 无效；
- diag(A_FE)^-1 Schur 明显变差；
- 真正问题是 auxiliary mode 与 FE trace/volume 的 coupled slow direction。
```

### 当前状态

诊断成功，驱动 Task016–Task021；diagnostic runner 不进入生产。

---

## 20. Task016：dominant zero-order lifted coarse correction

### 目标

构造：

```text
Z = [-P_FE^-1 C_j ; e_j]
```

并尝试 Galerkin、minimum-residual、additive 和 residual-corrected coarse correction。

### 结果

最好改善约：

```text
1.000045x
```

几乎无效。

### 关键结论

```text
aux residual 集中在某个 mode
!=
solution error 可由相应 right lifted vector 修正
```

可能需要：

```text
- left/test space；
- 更准确 A_FE^-1 C_j；
- 非正规系统的不同投影形式。
```

### 当前状态

right-only lifted coarse 路线关闭。

---

## 21. Task017：Petrov/adjoint coarse 与 true-FE sampled lift

### 目标

```text
- 增加 left/test space W；
- 测试 adjoint-aware projection；
- 用更真实的 FE response 近似 A_FE^-1 C_j。
```

### 结果

Petrov/adjoint 路线仍无效；但 true-FE sampled response 出现第一个明显正信号：

```text
top+bottom zero-order y modes
one-shot residual ≈ 3.69e-3
improvement ≈ 5.82x
```

### 限制

```text
- 依赖 SciPy exported-matrix research path；
- FE response 并非 exact；
- 直接塞进 right PC 后反而变差；
- 尚未形成稳定 solver。
```

### 当前状态

Petrov 路线关闭；true-FE residual correction 进入 Task018。

---

## 22. Task018：adaptive residual-corrected true-FE sampled Schur

### 目标

将 Task017 的 one-shot correction 转为 solver-like process。

### 最佳流程

```text
bounded FE-AMS segment
-> compute true residual
-> solve small min ||r-AZ alpha||
-> update x
-> repeat
```

### p=1 h=5 结果

```text
baseline residual ≈ 2.146e-2
best residual ≈ 1.662e-3
improvement ≈ 12.91x
```

通过 strong research gate，但未达到 \(10^{-6}\)。

### 关键发现

最有效的 FE response 不是最精确的 solve，而是带过滤作用的较松近似。

### 局限

```text
- SciPy single-process response service；
- 不是 MPI production；
- p=2 迁移尚未验证。
```

### 当前状态

p=1 research strong positive；允许进入 Task019 p=2 qualification。

---

## 23. Task019：p=2 h=5 sampled-Schur qualification

### 目标

验证 Task018 是否迁移到 p=2。

### 结果

```text
baseline 120-step residual = 1.6386e-2
required top_bottom_y best = 1.6357e-2
improvement = 1.0018x
best creative low-dimensional variant = 1.0804x
```

### 结论

```text
- p1 filtered sampled response 不迁移 p2；
- 增加少量 mode 无效；
- 低维 sampled-Schur 主线停止；
- 不进入 h=2。
```

### 当前状态

失败代码保留研究分支；文档作为重要负结果长期保留。

---

# PART IV：阶段 D——wave-aware、FE response 与 full Schur

## 24. Task020：branch hygiene 与 wave-aware solver search

### 目标

```text
- 整理失败分支；
- 比较 impedance DDM、sweeping、two-level adaptive coarse、matrix-free；
- 寻找 p=2 下一条主线。
```

### 结果

在 default100 算法沙盒：

```text
Route A row-layer DDM proxy -> 无明显改善
Route B diagonal slab sweep -> 变差
Route C residual-aware adaptive coarse -> 唯一正信号
Route D matrix-free action -> 代数通过但不是 solver
```

p=1 Route C 可到 \(10^{-6}\)，p=2 仅约 0.0525。

### 边界

Task020 使用 default100 沙盒，不是最终目标物理模型。

### 当前状态

路线排序保留；Task021 切回真实目标几何。

---

## 25. Task021：目标几何 DtN auxiliary residual-aware FE response/Schur

### 目标

在真实 p=2 h=5 目标模型上验证：

```text
residual-dominant auxiliary selector
+ FE response
+ coupled Schur correction
```

### 关键结果

```text
Jacobi baseline ≈ 0.2026
SPILU coupled m=1 ≈ 9.87e-7
SPILU block Schur ≈ 2.43e-7
exact FE-block Schur upper bound ≈ 8.16e-12
```

### 物理发现

主导 auxiliary mode 稳定为：

```text
top (0,0) s-polarized mode
```

### 结论

真正有效的是：

```text
FE response quality + FE/aux Schur structure
```

而不是单独 auxiliary correction。

### 局限

```text
serial SciPy SPILU/SPLU research prototype
no MPI production
no h=2
no official iterative R/T/A reconstruction
```

---

## 26. Task022：p=2 h=2 Schur/FE-response preflight

### 目标

验证 h=2 是否能沿 Task021 路线推进。

### 成果

```text
rows = 615188
FE DoF = 615108
aux = 80
nnz ≈ 65.45M
assembly + CSR 可完成
peak preflight RSS ≈ 6.277 GB
main selected mode 与 h5 相同
matrix-free FE action 误差 ≈ 6e-16
```

### 阻塞

```text
serial SciPy SPILU high fill -> 估计约 27.8 GB
very low fill -> setup 超时或质量不足
```

### 结论

h=2 失败不是矩阵、mode selector 或 Schur 结构错误，而是无法低内存近似 \(A_{FE}^{-1}\)。

---

## 27. Task023：PETSc/MPI-safe FE-response PC

### 目标

将 Task021/022 迁移到 PETSc/MPI，并补齐 field/RTA 回填。

### h=5 成果

```text
selected response ASM + local LU residual ≈ 9.33e-7
full 80-aux Schur one apply ≈ 2.49e-10
FieldSplit FE-LU ≈ 3.80e-9
```

official R/T/A 与 direct 差约 \(10^{-12}\)。

### 工程成果

```text
- MPI FE/aux index ownership；
- PETSc subblocks；
- solution reconstruction；
- MPC back-substitution；
- official modal R/T/A；
- FieldSplit/Schur engineering framework。
```

### h=2 负结果

```text
plain ASM/ILU response 质量不足，甚至方向错误；
local LU/MUMPS 进入时间/资源边界。
```

### 当前状态

h=5 工程闭环成功；h=2 仍缺强 FE inverse。

---

## 28. Task024：工程迭代求解器 fast track 与复现基础设施

### 目标

```text
- manual right FGMRES；
- CSR export；
- real split；
- AMS/HX/GMG-lite experiments；
- clean reproduction；
- h=2/h=1.5 low-memory preflight。
```

### 基础设施成果

```text
- manual FGMRES 与 PETSc/SciPy 小矩阵一致；
- complex dot 共轭方向修复；
- MPI1/MPI4 residual history 一致；
- vectorized CSR exporter；
- CSR invariants/hash audit；
- clean container reproduction。
```

### 算法结果

```text
m=1 reduced FE-response
20+20 budget residual = 0.17899
100+100 budget residual = 0.15859
```

没有证明相对严格 baseline 的有意义收益，更不是完整 80-aux solver。

### 当前状态

```text
infrastructure success
algorithm fail
manual FGMRES research-only
CSR/audit concepts retained
```

---

## 29. Task025：full-aux cached Schur 与 multilevel H(curl) 尝试

### 目标

```text
- 完整 80 auxiliary unknown；
- Q ≈ A_FE^-1 C；
- explicit small Schur；
- shifted FE smoother；
- p/coarse/AMS/BDDC 等多层尝试；
- h=2 14 GB 内完整 augmented solve。
```

### h=2 成果

```text
80 response columns
Q nnz ≈ 49.2M
outer iterations = 100
full true residual = 0.118475
peak RSS ≈ 13.006 GB
```

这是完整 full-aux 架构的重要研究突破。

### 根本瓶颈

response columns 满足：

```text
min relative response residual ≈ 0.286
max relative response residual ≈ 0.541
```

小 Schur 已精确求解，主要误差来自 Q 质量。

### 多层路线结论

```text
- 当前 p2->p1 / H1 / BDDC / 2D coarse 原型未捕获主要慢误差；
- 真正 3D nonmatching h-GMG 未实现；
- 不能据此否定所有 AMS/HX 或 h-GMG；
- ILU2 内存收益比太差。
```

### 当前状态

cached-Q 架构被 Task026 exact condensation 替代；诊断和历史证据保留。

---

# PART V：阶段 E——auxiliary-free 与 MPI4 workstation solver

## 30. Task026：auxiliary-free exact static condensation

### 架构变化

从 augmented system：

```math
\begin{bmatrix}F&C\\D&H\end{bmatrix}
\begin{bmatrix}u\\a\end{bmatrix}
=
\begin{bmatrix}b_F\\b_H\end{bmatrix}
```

转为：

```math
(F-CH^{-1}D)u=b_F-CH^{-1}b_H.
```

### 主要成果

```text
- exact condensed operator；
- matrix-free low-rank port action；
- no auxiliary global unknowns in outer solve；
- no Q=A_FE^-1 C cache；
- auxiliary back-substitution；
- explicit condensed reference；
- transpose/Hermitian action；
- h5 field/RTA equivalence；
- h2 MPI1/MPI4 action equivalence；
- 1000 repeated applies stable RSS。
```

### h=5 迭代结果

problem-informed z-slab two-level prototype：

```text
iterations = 795
full residual ≈ 9.999e-10
peak RSS ≈ 1.829 GB
R/T/A closure ≈ 1e-12
```

### 关键代码修复

petsc4py complex `Vec.dot` 语义被正确处理为：

```python
np.conjugate(left.dot(right))
```

用于：

```text
MGS
Z^H A Z
Z^H r
```

该修复将 200-step residual 从约 0.259 降到约 0.00105。

### h=2 初始状态

plain matrix-free ILU2 residual 约 0.166；早期 two-level 仍未达到 production。

### 当前状态

exact condensation 成为 Task28 长期稳定模块。

---

## 31. Task027：mesh-robust physical-slab two-level solver

### 原始目标

用 operator-adaptive spectral coarse 构造 mesh-independent Schwarz PC。

### spectral 路线结果

```text
full-slab energy spectral -> fail
interface harmonic -> fail
shifted near-null -> fail
PCHPDDM energy GenEO -> fail
HPDDM recycling -> false residual risk
```

因此 spectral 假设没有成功。

### 实际成功结构

```text
exact matrix-free condensed operator
+ fixed 75D no-RHS Floquet z-hat coarse
+ 16 complete physical z-slabs
+ deterministic owner-computes assignment
+ shifted local ILU1
+ two fixed shifted-F GMRES smoothing steps
+ right FGMRES restart=100
+ explicit true-residual checkpoints
```

### 最终 MPI4 结果

| h (nm) | iterations | true residual | peak total RSS |
|---:|---:|---:|---:|
| 5 | 1201 | `9.839e-7` | 约 1.96 GB |
| 3 | 993 | `9.933e-7` | 约 5.07 GB |
| 2 | 1804 | `9.997e-7` | 约 12.96 GB |

三网格比值：

```math
1804/993 = 1.8167 < 2.
```

### 物理结果

```text
h5: R=0.0890216, T=0.4425883, A=0.4683901
h3: R=0.0046130, T=0.5836534, A=0.4117336
h2: R=0.00134294, T=0.59921324, A=0.39944383
```

### 准确定位

```text
production candidate = yes
tested-range mesh robustness = yes
strict asymptotic mesh independence = not proven
parameter robustness = not proven
physical mesh convergence = not completed
ordinary default = unchanged
```

### 当前状态

Task027 的 fixed coarse + complete physical slab + sm2 成为 Task28 选择性整合目标。

---

# PART VI：阶段 F——Task028 阶段收口

## 32. Task028：stage consolidation、master integration 与 benchmark

### 目标

暂停新求解器扩展，完成：

```text
- Task000-Task027 审计；
- selective merge manifest；
- clean master 上抽取稳定代码；
- 重建 README 和用户文档；
- 建立独立 benchmarks/；
- 重新运行 direct/iterative benchmark；
- 给出最终 master candidate。
```

### 当前已完成

```text
- 从 master@0465b5f 建立整合分支；
- 没有整分支 merge Task027；
- 新增 condensed_dtn.py；
- 新增 physical_slab_two_level.py；
- 新增 stage4_runtime.py；
- 新增 workstation benchmark runner；
- 新增 total MPI RSS telemetry；
- 新增 condensation 与 physical slab tests；
- 选择性归档 Task021-Task027 58 份核心文档；
- 新增 benchmarks/ 目录；
- h5/h3/h2 iterative clean rerun；
- h5/h3 direct rerun；
- 80 unit tests passed，10 skipped；
- focused MPI4 tests passed。
```

### Task028 clean rerun

```text
h5: 1201 iterations, full residual 9.839e-7
h3: 993 iterations, full residual 9.933e-7
h2: 1804 iterations, full residual 9.997e-7, peak 13.080 GB
```

### V1 审查发现

```text
core solver integration = pass
numerical reproduction = pass
ordinary default = pass
history audit = pass
```

但：

```text
benchmark output boundary = fail
benchmark scripts = fail
automatic gate checker = missing
environment reproducibility = fail
documentation completeness = insufficient
sm2 test coverage = insufficient
master merge = blocked pending response_v1
```

### 当前状态

```text
Task028 core consolidation = accepted
Task028 productization = changes required
```

详细要求见：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/review_report_v1.md
```

### Response V1

2026-07-12 在同一分支完成六个 P0 修正：

```text
benchmark output boundary = pass
benchmark scripts = pass
automatic gate checker = 58/58 pass
environment = pass_with_qualification
documentation = pass
sm2 production tests = pass
full suite = 91 passed, 10 skipped
focused MPI4 = each rank 14 passed
h5 clean rerun = 1201 iterations, full 9.839e-7, 1.991 GB
```

环境仍有一项诚实限定：complex MPC 基础镜像固定了本机 digest，但没有公开 pull source，因此不能宣称任意 clean machine 可直接在线重建。当前状态为：

```text
Task028 productization = pass_with_environment_qualification
master merge = pending review v2 and user approval
```

逐项证据见：

```text
docs/task028_stage_consolidation_master_integration_benchmarks/response_v1.md
```

### Review V2 与 Response V2

V2 认为核心求解器和数值结果仍通过，但要求把项目从“开发者能追踪”升级为“新用户能运行、每项能力有理论/代码/benchmark 对照”。同一分支已完成：

```text
- main.py 改为 15 个安全命名 preset，默认 10x10x10 nm Stage1 p1/h5；
- 2D CLI 支持 complex index；3D direct 显式区分 default/OOC/BLR；
- 建立 Quick Start 15 篇、Code Walkthrough 15 篇、Theory 9 篇规范文档；
- 建立 13 个编号 feature benchmark case，每个使用 22 字段契约；
- historical h3/h2 record 拆分 actual source 与 canonical rerun provenance；
- checker 新增 ID、qualified、KSP、coarse condition、physical model 与 artifact provenance Gate；
- 新增 documentation/main preset/lossy port tests；
- 修复 Docker 根挂载时 main.py 导入；
- 修复 2D lossy DtN 把 complex beta 误判为 evanescent、以及在错误参考平面计算 T 的问题。
```

复材料实算确认：TM `R+T+A_volume-1=3.33e-15`，TE 为 `-5.50e-16`；probe 结果仍只作 diagnostic。最新验证：

```text
full suite = 105 passed, 10 skipped（最终重跑前的预期计数，以 outcomes/test_summary 为准）
focused MPI4 = each rank 14 passed
benchmark checker = 87/87 pass
h2 heavy solve = not rerun; numerical records unchanged
```

当前状态：

```text
Task028 V2 implementation = complete
environment = qualified_local_image
master merge = blocked only pending final review and user approval
```

逐项证据见 `response_v2.md` 与本任务 `outcomes/`。

### Review V3 与 Response V3

V3 保持 Task026/027 核心 solver 和既有 3D records 通过，但要求把“目录存在”提升为可执行、可复核、技术准确的交付。同一分支完成：

```text
- Case002 在同一网格完成 explicit/auxiliary 两次完整 solve；
- Case003 冻结 TM/TE complex absorption lightweight records；
- checker 扩展到 143/143，含 lossy、lossless、case files 与 SHA references；
- main.py 增至 17 个 preset，demo/target 物理身份分离；
- Case021 target preset 直接复用 target_stage4_config；
- Case031 增加 PyCharm Docker/WSL External Tool MPI4 workflow；
- 15 篇核心 Quick Start 全部扩展为 16 节教程；
- 11 篇核心 Walkthrough 全部达到源码/shape/ownership/公式/Gate 深度；
- 修正 SparseCoarseVector 字段、smoother-first 顺序、显式 inverse 和 H=I 限制；
- 13 个 Benchmark 全部建立 case-contained contract 并扩展 README；
- Theory 增加统一符号表、module::function anchors 和 2D/3D power constants。
```

最新验证：

```text
full suite = 115 passed, 10 skipped
focused MPI4 = each rank 14 passed
documentation contract = 11 passed
benchmark checker = 143/143 pass
h2 direct/iterative = not rerun; existing 3D records unchanged
```

逐项证据见 `response_v3.md`。当前状态为 ready for final review；master 仍未合并。

---

# 33. 当前项目能力

## 33.1 2D 当前能力概览

当前代码具备或历史上已实现：

```text
- TM vector Maxwell；
- TE scalar Maxwell；
- Floquet periodic constraint；
- manual / MPC backends with restrictions；
- scattered-field + PML；
- Robin port；
- Fourier-DtN port；
- explicit/auxiliary DtN variants；
- real/complex refractive index；
- diffraction order postprocessing；
- R/T and absorption-related outputs；
- field/mesh export；
- parameterized geometry and mesh controls。
```

需要 Task028 文档复核的边界：

```text
- exact supported command for each combination；
- 2D DtN manual-only restriction；
- MPI support restrictions；
- which R/T source is official in each formulation；
- current iterative solver status；
- angle/wavelength scan maintenance status。
```

正式能力矩阵以更新后的 `docs/capability_matrix.md` 为准。

---

## 33.2 3D 当前能力概览

```text
- Stage1 airbox；
- Stage2A double Floquet airbox；
- Stage2B PML airbox smoke；
- Stage2C Fresnel interface smoke/reference path；
- Stage4 flat-layer and block grating；
- p=1/p=2 Nedelec；
- complex material；
- double Floquet MPC；
- auxiliary DtN modal port；
- explicit/static condensed DtN；
- matrix-free condensed DtN；
- direct MUMPS；
- MUMPS OOC；
- MUMPS-BLR fallback；
- official modal R/T/A；
- volume absorption；
- field/mesh export；
- residual/memory telemetry；
- MPI4 complete physical-slab iterative candidate。
```

当前正式目标 solver 状态：

```text
ordinary default = direct
workstation iterative = explicit opt-in
h=5/3/2 = qualified reference set
h=1.5 = not completed
new angle/wavelength/material/geometry = not qualified
```

---

# 34. 当前主要里程碑

| Milestone | 状态 | 关键 Task |
|---|---|---|
| official modal R/T/A and A_volume | 完成 | 002–007 |
| small-cell p/MPI regression | 完成 | 004 |
| target 3D direct h=2 reference | 完成 | 008 |
| black-box iterative exclusion | 完成 | 009–011 |
| AMS/HX real-split qualification | 研究完成，生产失败 | 012–014a |
| DtN slow-mode diagnostic | 完成 | 015–017 |
| p1 sampled-Schur strong signal | 完成但不迁移 | 018–019 |
| target p2 FE-response/Schur mechanism | 完成 | 021–023 |
| h2 full-aux cached-Schur research solve | 完成但不生产 | 025 |
| exact auxiliary-free condensation | 完成 | 026 |
| MPI4 h2 <1e-6 under 14 GB | 完成 | 027 |
| clean master candidate integration | V4 三项加固完成，已获合并许可 | 028 |

---

# 35. 已关闭或暂停的路线

以下路线当前不应重新盲扫：

```text
- ordinary Jacobi/BJacobi/ASM/ILU profile tuning；
- complex AMS direct attachment；
- minimal FE-AMS + aux identity；
- aux-only modal correction；
- diag FE Schur；
- right-only lifted coarse；
- broad Petrov/adjoint W scan；
- low-dimensional top_bottom_y sampled-Schur as p2 mainline；
- cached-Q full-aux architecture as final solver；
- energy spectral/GenEO threshold scan；
- HPDDM cross-solve recycling without explicit true residual；
- unconditional h2 direct on 14 GB environment。
```

这些路线的文档仍有价值，但不进入普通 API。

---

# 36. Task029：Stage4 direct memory forensics

## 36.1 最终状态

```text
Task = Task029 — Stage4 direct memory forensics
branch = codex/20260713-task29-stage4-direct-memory-forensics
base = master@2f9e56d2edddb801780504f681b2ff295d993e02
classification = diagnostic_success
engineering_success = no
threaded_direct_capability = unavailable_in_current_image
h2 = not_run
h3_threaded_direct = not_run
review = V2 technical review pass
master = user-approved; merge pending execution
ordinary default changed = no
```

Task029 的成功是“诊断、基础设施和安全决策成功”，不是“获得了新低内存 direct solver”。这一分类贯穿代码、Benchmark、能力矩阵和合并边界。

## 36.2 为什么启动

Task028 已把目标 p2/h5、h3、h2 的 direct reference 与 MPI4 workstation iterative 路径收口，但 direct h3/h2 的因子内存仍是工作站边界：h3 direct 已约 8 GiB，历史 h2 direct 约 20.5 GiB，超过当前约 14 GiB 环境。此前只有最终/历史 RSS，没有足够证据回答内存是在 DtN 增广、MUMPS factorization、KSPSolve 还是后处理中增长，也无法判断对象释放、rank 数、OOC/BLR 或 ordering 是否值得提升。

如果不先完成分阶段剖析，后续容易把统计口径变化误写成优化，把单网格正信号包装成 profile，或在没有安全余量时直接运行 h2。本任务不解决物理网格收敛、新迭代预条件器、adaptive mesh 或跨机器 COMSOL 性能可比性。

## 36.3 冻结问题与 baseline

冻结模型为 50 × 25 × 140 nm 周期单元、17 × 25 × 120 nm complex-Si block、13.5 nm、theta=80°、phi=0、s 偏振、p2 Nédélec、double Floquet + auxiliary Fourier-DtN。模式策略始终为 `auto_propagating`，top/bottom 各 40 个模式、`n_aux=80`。允许改变的是 direct 生命周期、MPI rank/thread 组合、明确 opt-in profile/package/ordering 与遥测；禁止改变物理、模式、official R/T/A、full solve 和 ordinary default。

基线是 default MUMPS、MPI4、每 rank 1 thread。数值资格要求 full explicit true residual、Task28 R/T/A 绝对差和能量闭合均 `<=1e-8`。内存主口径是外部同一时刻所有 worker rank RSS 的和；cgroup current、swap 和各 rank 历史峰值和分别记录，不混写。

| 指标 | h5 MPI4 baseline | h3 MPI4 baseline |
|---|---:|---:|
| FE / auxiliary / augmented rows | 44,698 / 80 / 44,778 | 198,438 / 80 / 198,518 |
| true residual | `5.225e-12` | `1.382e-11` |
| max Task28 R/T/A abs delta | `0` | `1.865e-14` |
| simultaneous worker RSS | 2328.145 MiB | 8651.098 MiB |
| cgroup current peak | 1729.035 MiB | 8353.727 MiB |
| KSPSetUp / KSPSolve | 1.838 / 0.0467 s | 31.200 / 1.603 s |
| augmented / factor nnz | 4,896,156 / 33,862,428 | 21,317,860 / 266,127,836 |
| swap in / out | 0 / 0 | 0 / 0 |

## 36.4 采用的方法

| 方法 | 解决的问题 | 保护措施 |
|---|---|---|
| 0.25 s external sampler | 把 simultaneous RSS/cgroup/swap 峰值映射到 solver stage | 原始 timeline 留在 ignored artifacts，轻量 CSV 入库 |
| matrix/factor inventory | 区分 base/augmented 存储与 LU fill | PETSc 原始 0 memory/fill 不冒充有效 allocator 测量 |
| progress checkpoints | 标记 `before/during/after KSPSetUp`、solve、RTA、field output | 每个 full run 保留 residual/R/T/A |
| H1–H7 单因素假设表 | 按收益、风险和 stop rule 筛选优化 | h5 先筛，最多两个候选进 h3 |
| clean-source candidate runner | 绑定 commit、image digest、command、profile | tracked-source-dirty 直接拒绝 |
| h2 两路径外推 + G1–G10 | 在高内存运行前给出范围与硬 stop | Gate 未全 true 时 runner 保持锁定 |
| 构建/链接与 `/proc` 审计 | 区分 NumPy BLAS、MUMPS 实际 BLAS 和真实 CPU 使用 | 固定 `OMP=1`、CPU `0-3`，只控制 OpenBLAS pthread |

低风险实现包括幂等 `DirectSolveFailure.cleanup()`、OOC scratch/I/O/cleanup telemetry、显式 MPI distributed factor package 选择正确性，以及默认 `false` 的 `direct_release_base_after_augmentation`。这些基础设施与性能 profile 资格分开审查。

## 36.5 主要实验与实施步骤

实际运行顺序为：h5/h3 MPI4 baseline；h5 MPI1/2/4 rank 诊断；H1 release-base h5→h3；H5/H6 的 MPI2、SuperLU_DIST、OOC、BLR、ordering h5 筛选；唯一正式 MPI2 候选 h5→h3；h2 外推与 Gate；最后按 review 进行 PETSc/MUMPS/BLAS 静态审计和固定四核 h5 MPI4×1、MPI2×2、MPI1×4、MPI1×1。

没有运行 h2 direct；没有在 h5 线程 Gate 失败后运行 threaded h3；没有重建 image 或在 Task029 实现 multilevel solver。建议模板中的 MPI1×2 是可选补点，但 MPI1×4 已同时触发 T0/T1/T3 stop，继续补点不会改变能力身份。

## 36.6 关键结果

### KSPSetUp / MUMPS factorization 是主峰

h3 从 `before_ksp_setup` 到 `during_ksp_setup_peak`，worker RSS/cgroup 分别增加约 6472.43 / 6474.57 MiB。KSPSolve 结束只比 factorized checkpoint 多约 6.98 MiB worker RSS；official RTA 增量不足 1 MiB；field output 形成约 129.06 MiB 的较低尾部平台。base/augmented 共存约增加 729 MiB worker RSS，只占总峰值约 8%–9%。

h3 factor/augmented nnz 比为 12.484；统一 nnz-storage estimator 约 6093/489 MiB。前者是结构计数，后者是估算，不是 MUMPS allocator 实测。

### H1–H7 与候选结果

下表中“相对变化”为同 h 的 `baseline - candidate` 再除以 baseline：正数表示内存减少，负数表示恶化。

| 路线 | h5 worker RSS 变化 | h3 worker RSS 变化 | 数值 | 最终处置 |
|---|---:|---:|---|---|
| H1 release-base MPI4 | +4.767% | +5.462% | pass | 合并显式低风险生命周期控制；非 profile |
| H2 preallocation rewrite | not_run | not_run | `mallocs=0`,`nz_unneeded=0` | 无 allocator 正证据，拒绝 speculative rewrite |
| H3 cleanup/temporaries | 非主峰收益 | full flow 保持 | pass | 合并幂等 failure cleanup |
| H4 direct A_aug assembly | not_implemented | not_implemented | 无 public safe API | 不使用 private framework hack |
| H5 MUMPS MPI2 | +28.893% | +15.119% | pass | 最佳诊断点；h3 未达 20%，拒绝 profile |
| H5 SuperLU_DIST | -14.462% | not_run | pass | 内存和时间负向 |
| H6 MUMPS OOC | +13.744% | not_run | pass | 559,715,776 bytes scratch、1.539×时间；仅 fallback |
| H6 BLR 1e-5 | -3.427% | not_run | fail | residual `4.704e-3`，拒绝 |
| H6 ordering ICNTL(7)=3 | -4.093% | not_run | pass | factor nnz/峰值增加，拒绝 |
| H7 early factor release | 只影响尾部 | not_run | 风险较高 | 不是全局峰值修复，本任务不实现 |

### 少 rank + 多线程最终结论

静态审计确认 PETSc 3.24.0 / MUMPS 5.8.1 通过 `-llapack -lblas` 动态链接 system OpenBLAS 0.3.26 pthread；OpenBLAS API 能读取并修改线程数。NumPy 使用独立 scipy-openblas 0.3.29，只作 Python 侧交叉检查，不代表 MUMPS。活动 PETSc/MUMPS 未显示 OpenMP 构建，正式线程运行固定 `OMP_NUM_THREADS=1`，避免 OpenMP 嵌套；但两个 OpenBLAS runtime 可能形成多个线程池，runnable-thread oversubscription 不能完全排除，CPU affinity 只负责把实际执行封顶在 `0-3`。

| 固定 CPU 0-3 | worker RSS | KSPSetUp | Stage4 | KSPSetUp CPU 核均值/峰值 |
|---|---:|---:|---:|---:|
| MPI4×1 | 2351.707 MiB | 2.385 s | 18.311 s | 3.906 / 4.061 |
| MPI2×2 | 1677.062 MiB | 1.953 s | 20.687 s | 3.272 / 4.025 |
| MPI1×4 | 1399.648 MiB | 23.841 s | 48.273 s | 0.999 / 1.054 |
| MPI1×1 | 1401.988 MiB | 25.578 s | 50.891 s | 0.999 / 1.060 |

MPI1×4 的 worker thread 数从 3 增至 12，但 KSPSetUp 仍约 1 核，Stage4 相对 MPI1×1 只有 1.054× speedup。T2 内存比通过（RSS/cgroup 均远低于 1.20×），但 T0 runtime、T1 与 T3 失败；最终身份是 `threaded_direct_capability=unavailable_in_current_image`，T4 要求 threaded h3=`not_run`。

## 36.7 结果解释

主导机制是 LU fill，而不是 auxiliary DoF 或后处理。提前释放 base 对象只能回收次要共存量；减少 rank 能减少进程重复和总 RSS，却削弱分布式 factorization 并行。OOC 把部分 RAM 压力转成 scratch/I/O；BLR 则引入当前阈值不可接受的近似误差。

线程审计进一步说明：有可控 pthread 和更高进程 thread count，不代表 MUMPS factorization 会多核执行。MPI1×4 的实际 CPU 证据与 MPI1×1 相同，因而不能用静态 BLAS 能力或 NumPy matmul 证明 threaded direct 可用。

## 36.8 h2 预测与 G1–G10

DoF 幂律与 factor-nnz/fill 两条路径给出 h2 中央预测 22.214 / 22.330 GiB，敏感性范围 18.882–27.913 GiB。这里属于外推，不是实测 h2。

| Gate | 状态 | 含义 |
|---|---|---|
| G1/G2 | true | h5/h3 MPI2 数值通过 |
| G3 | false | h3 只降 15.119%，没有双网格 20% |
| G4 | true | h3 无 swap |
| G5 | false | 预测上界高于 13.5 GiB |
| G6 | true | 13.5 GiB 安全上限未放宽 |
| G7 | false | 当前可用内存低于预测下界 |
| G8 | true | 只有一个最终诊断候选 |
| G9 | false | 早期 Gate 已失败，未实现/启用 h2 watchdog |
| G10 | true | Task28 h2 record 未覆盖 |

因此 `h2 = not_run`，不是 pass、fail-run 或 skipped-without-reason。

若未来确有 direct h2 需求，资源规划应使用至少 48 GB、优先 64 GB 的机器，并先实现 watchdog/clean-abort；这不构成当前工作站运行许可。

## 36.9 成功路线、失败路线与负结果

成功并建议保留的是 telemetry、matrix/factor inventory、clean provenance、异常 cleanup、factor package 选择正确性、OOC 证据、显式 release-base 控制、Case050 与 h2 guard。它们改善可观测性、正确性或安全性。

失败或只作诊断的是 MPI2、OOC、BLR、SuperLU_DIST、ordering 和当前镜像 threaded direct；都不得提升为 ordinary/recommended profile。COMSOL GMG 只提供“未来可研究完整多层层次”的定性线索，不是本任务 runtime、R/T/A 或每 DoF benchmark。

## 36.10 最终决策与合并边界

| 对象 | 决定 | 原因 |
|---|---|---|
| telemetry / Case050 / h2 guard | V2 通过，允许合并 | 可复用且有合同测试 |
| failure cleanup / package selection fix | V2 通过，允许合并 | 正确性与异常安全 |
| release-base option | 建议合并，保持默认 false | 低风险，收益不足 profile 资格 |
| MPI2/OOC/BLR/SuperLU/ordering | 不提升 | 内存、时间或数值 Gate 失败 |
| threaded direct | 不创建 profile | 当前 image KSPSetUp 仍单核 |
| ordinary default | 不改变 | 无候选同时通过工程 Gate |
| h2 / threaded h3 | 不运行 | 分别被 G/T Gate 阻止 |
| master | 用户已许可，待执行合并 | V2 技术审查通过；Task030 启动请求提供明确许可 |

## 36.11 局限

factor storage 是 nnz estimator；部分 PETSc/MUMPS raw memory/fill 字段不可用。CPU 核数由 0.25 s `/proc` 累计 CPU 时间差分，不是硬件计数器。线程结论只适用于当前 image、目标矩阵与固定四核条件。完整 field/mesh/timeline 保存在本地 ignored artifacts，不进入 Git。物理 residual/closure 通过也不等于 h3/h2 R/T/A 已完成网格收敛。

## 36.12 下一步及原因

由于对象生命周期、ordering 和当前 BLAS 线程都不是主峰解法，停止继续 direct 微调。下一阶段应优先做 h3/h2 物理网格收敛或 graded/adaptive mesh qualification；若继续降低 solver memory，则研究真正 multilevel H(curl)、low-order-refined multigrid 或带受控 coarse direct solve 的并行 physical Schwarz。只有更换为明确支持 threaded factorization 的构建时，才重新执行固定四核 h5 能力审计。

## 36.13 证据入口

- [Task029 outcomes summary](task029_stage4_direct_memory_forensics/outcomes/summary.md)
- [线程能力审计](task029_stage4_direct_memory_forensics/outcomes/threaded_direct_capability_audit.md)
- [h2 launch decision](task029_stage4_direct_memory_forensics/outcomes/h2_launch_decision.md)
- [Task029 review V1](task029_stage4_direct_memory_forensics/review_report_v1.md)
- [Task029 response V1](task029_stage4_direct_memory_forensics/response_v1.md)
- [Task029 review V2](task029_stage4_direct_memory_forensics/review_report_v2.md)
- [Task029 response V2](task029_stage4_direct_memory_forensics/response_v2.md)
- [Benchmark Case050](../benchmarks/cases/050_stage4_direct_memory_forensics/README.md)
- [Task 回顾标准](task_retrospective_standard.md)
- [direct runner](../benchmarks/run_direct_memory_forensics.py)
- [direct profile walkthrough](../notes/reference/code_walkthrough/30_direct_solver_profiles.md)

---

# 37. 当前未完成问题

## 37.1 Task028 收口问题

```text
- Response V4 已关闭 tracked-source-clean、真实 image digest 和最终提交验证，并以 2f9e56d 合入 master；
- complex MPC base image尚无公开pull source，环境保持qualified；
- `SmallDenseInverse`显式逆、内部下划线依赖和异常路径统一清理为非阻断技术债。
```

## 37.2 Task029 当前问题

```text
- h5/h3 baseline、归因和最多两个 h3 候选均已完成；
- 最佳 h3 只下降 15.119%，未达到 engineering_success；
- h2 预测区间 18.882–27.913 GiB，G3/G5/G7/G9 失败并明确 not-run；
- review V1 更正、V2 技术验收与 response_v2 状态同步均完成，用户已许可合并；
- 当前 image 的 threaded direct 不可用，threaded h3 按 T4 未运行。
```

## 37.3 数值和物理问题

```text
- h=1.5 production solve；
- physical R/T/A mesh convergence；
- local/adaptive mesh refinement；
- angle/wavelength/material robustness；
- near-Rayleigh conditions；
- parameter reuse/warm start；
- lower iteration count and higher throughput；
- slab-internal parallelism / true multilevel H(curl) method。
```

这些扩展在 Task028 期间暂停。

---

# 38. 当前推荐开发顺序

Task28 合并与 Task29 执行已完成。当前强制顺序：

```text
1. Task029 `response_v1.md`、全部 P0 更正和 V2 技术验收已完成；
2. 提交 `response_v2.md` 并完成轻量 release checks；
3. 按用户许可合并 Task029 后，从更新的 clean master 新建 Task030 分支；
4. 不提升 MPI2/OOC/BLR/SuperLU/ordering 为低内存 profile；
5. 不在当前工作站运行 h2 direct；
6. 后续优先物理收敛资格化或真正 multilevel H(curl) 研究。
```

Task028 完成后，如重新开启研究，推荐顺序：

```text
A. h=2 physical mesh convergence / local refinement；
B. fixed profile small angle/wavelength/material qualification；
C. warm start and cache reuse for scans；
D. iteration/time reduction；
E. h=1.5 preflight；
F. slab-internal parallel or true H(curl) multilevel solver。
```

---

# 39. 文档维护规则

每个后续阶段完成后，应同步更新：

```text
docs/development_progress.md
docs/capability_matrix.md
notes/reference/current_version_boundaries.md
benchmarks/benchmark_summary.csv
对应 task outcomes/review
```

更新原则：

```text
- 后续证据覆盖早期结论；
- 成功和负结果分开；
- 研究正信号不包装为 production；
- 未收敛不输出 official R/T/A；
- reported residual 必须与 explicit true residual 区分；
- ordinary default 变化必须显式审查；
- benchmark 必须记录 commit 和环境。
```

---

# 40. 当前一句话状态

> 项目已经从基础 2D/3D Maxwell、Floquet 和 DtN 验证，发展到可在约 14 GB 工作站上用 MPI4 对目标 p=2、h=2 三维 EUV 光栅取得全增广真残差小于 \(10^{-6}\) 的限定迭代解；Task028 已合入 master，Task029 以 `diagnostic_success` 收口并确认 MUMPS KSPSetUp/factorization 是 direct 内存主瓶颈。最佳 h3 候选只下降 15.119%，当前 image 的 MPI1×4 KSPSetUp 仍约 1 核，故 engineering_success=no、threaded direct unavailable、threaded h3 与 h2 均按 Gate 未运行。

---

# 41. Task030：3D H(curl) 多层与低内存迭代研究

## 41.1 任务身份与为什么启动

```text
Task = Task030
branch = codex/20260713-task30-multilevel-hcurl-low-memory-iterative
base master = bfb6586e030efd5208ebd796c39fdc31301e1d6e
physical model = Task27/28 frozen p2 Stage4 target
ordinary default changed = no
current classification = workstation_memory_success_with_qualifications
```

Task029 已证明 direct 的内存主峰在 MUMPS analysis/factorization；MPI2、OOC、BLR、ordering 与线程都没有得到可提升的 h3 工程收益。Task027 虽能在约 14 GB 内完成 h2，但 16 个大 slab ILU1、shifted-F 副本和 FGMRES basis 仍让 h2 达到 13.08 GB。因此 Task030 转向 H(curl) 层级、低 fill smoother、对象生命周期和 Krylov memory，而不继续微调 direct。

COMSOL 报告只提供定性依据：真正多层 Maxwell PC 可能明显低于 direct；它不是当前 FEniCS R/T/A reference，也不能用于跨机器时间排名。

## 41.2 冻结基线与数值合同

物理保持 50×25×140 nm cell、17×25×120 nm Si grating、13.5 nm、theta=80°、phi=0、s polarization、p2 Nédélec、双 Floquet、80 个 auto-propagating modal unknowns、exact matrix-free `F-C H^-1D`、full true residual 和 official modal R/T/A。

Task027 baseline 为 h5/h3/h2 的 1201/993/1804 步和 1.991/5.08/13.080 GB。Case031 h5 100-step residual `2.5737371765314062e-3` 由 SHA-256 pinned record 读取，候选不得手写或覆盖基线。

## 41.3 层级与 transfer 基础设施

实现 `ActiveDofMap`，将 MPC slaves 从 coarse columns 中移除，再逐 active column 用 DOLFINx nonmatching interpolation 构造 p1→p2 H(curl) transfer；每列执行 MPC backsubstitution/homogenize，restriction 为 Hermitian transpose。transfer 支持 MPI CSR cache，fresh/cache action 可复核。

MPI4 目标规模：fine h5/p2 full/active/slave 为 44,698/40,800/3,898；coarse h10/p1 为 1,067/792/275；P 有 145,998 nnz、无零列、adjoint error `1.586e-15`、fresh/cache error `6.410e-15`。精确 coarse operator 使用 `P^H(F-CD)P`，保留全部 80 modes；serial/MPI2 action tests 通过。

这部分达到 infrastructure success，但没有直接得到 solver success。

## 41.4 多 lane 漏斗与负结果

| lane | h5 100-step true residual | 相对基线 | 结论 |
|---|---:|---:|---|
| Jacobi + p/h coarse | 0.680155 | 264.27× | negative |
| z-layer patch + p/h coarse | 0.374864 | 145.65× | negative |
| vertical column + p/h coarse | 0.513599 | 199.55× | negative |
| cell patch + p/h coarse | 0.512730 | 199.22× | negative |
| 16-slab ILU0 + p/h coarse | 0.561064 | 218.00× | negative |

相同 slab smoother 不加 p/h coarse 的 20-step residual 为 0.381817，加 coarse 后反而为 0.685751。说明 transfer/Galerkin 正确，但 792D p1 coarse 没有覆盖当前 Maxwell 近核、梯度和 grazing-wave 慢方向。当前不能声称 pure h-GMG、mixed p/h 或 AMS/HX 成功。

全 80 mode Woodbury 只提供很小改善且增加内存；225D x-harmonic coarse、更多 z hats、去 overlap pre-only、单次廉价 post 和 restart80 都未过 Gate。失败实现没有进入 ordinary default。

## 41.5 正反馈如何继续深化

Task027 ILU1 overlap PC 增加真正 post smooth 后，h5 100-step residual 变为 `1.273503e-3`，达到 strong-positive。此后逐步验证：

1. ILU0 仍为 `1.865566e-3`，说明对称组合后 fill1 不是必要条件；
2. local diagonal shift 不保留完整 shifted-F，residual 不变；
3. factor-only 逐块 setup 后销毁 source submatrix/KSP，只保留因子，action serial/MPI2/MPI4 等价；
4. restart90 仍通过 weak-positive，restart80 失败，因此停止继续缩小。

最终候选固定为 75D wave coarse、16 slabs overlap0.25、ILU0、sm2 symmetric pre/post、local shift、factor-only、right FGMRES(90)。这不是“真正多重网格成功”，而是现有有效 coarse 与更低内存 smoother/lifecycle 的工程改进。

这里的 ILU0 结论只表示“该冻结目标在对称组合下不需要配置 ILU1 才能收敛”。Task27 ILU1 与 Task30 ILU0 的 `global_slab_factor_nnz` 完全相同，当前统计口径不能证明 stored fill 下降。可归因的内存改进是 local shift、factor-only 释放 source submatrix/KSP/PC wrapper 以及 restart90；factor nnz 保持 `measurement_unresolved`。

## 41.6 h5/h3/h2 正式结果

| h | DoF | iterations | full true residual | peak incl RTA | R/T/A | direct max delta |
|---:|---:|---:|---:|---:|---|---:|
| 5 | 44,698 | 855 | 9.924905e-7 | 1.687653 GB | 0.0890216035 / 0.4425882732 / 0.4683901222 | 5.438e-9 |
| 3 | 198,438 | 962 | 9.903890e-7 | 3.792912 GB | 0.00461303218 / 0.58365335775 / 0.41173361173 | 7.719e-10 |
| 2 | 615,108 | 1873 | 9.972228e-7 | 9.374729 GB | 0.00134293442 / 0.59921323601 / 0.39944383222 | 6.561e-9 |

h3 较 Task027 canonical 5.082275 GB 下降 25.37%，h3/h5 iteration ratio 为 1.1251。其 3.792912 GB 同时通过 3.8 GB 绝对线和“相对下降至少 25%”分支。reported/condensed/full residual、80 modes、R/T/A 与 closure 全通过；h5/h3 均为 clean final-HEAD rerun。

## 41.7 h2 预测、实测与当前边界

h5/h3 的 DoF–RSS 仿射/幂律两个独立模型预测 h2 中央值为 9.5298/7.0337 GB；较保守仿射值的 15% engineering upper 为 10.9593 GB，满足 G5/G6。唯一候选 attempt1 的实测峰值为 9.342113 GB，较 Task027 降低 28.58%；1800 步 solve time 2220.43 s，也略低于 Task027 2345.26 s。

attempt1 真残差为 `1.461130e-6`，所以未输出 official R/T/A。随后只对同一 PC/restart 将 max_it 延到 2100；共同 monitor 点残差逐位一致，并在 1873 步收敛。最终 full residual `9.972228e-7`、含 R/T/A 峰值 9.374729 GB、closure `2.639e-9`、direct 最大差 `6.561e-9`。Review V2 明确不重跑 h2，因此这些值的身份是 `reviewed_historical_dirty_worktree_reference`，不是 clean final-HEAD evidence；h2/h3 iteration ratio 为 1.947，且 1873 步仍高于 1200 偏好。

## 41.8 合并边界

建议 final review 接受的内容：nonmatching H(curl) transfer/cache、condensed Galerkin 研究基础设施、local shift、factor-only storage、symmetric pre/post opt-in、Case060、tests 和完整文档。不得提升 p/h solver profiles、Woodbury、x-harmonic、AMS/HX、restart80 或 heavy artifacts。validated infrastructure API 已与失败 candidates 隔离；Task027 canonical 和 ordinary default 均保持不变。master 仍等待 Response V2 后的 final review 与用户明确许可。

## 41.9 局限与下一步因果关系

h2 已收敛，但当前 evidence 只覆盖单个角度/波长/材料/分区，且 1873 步仍高于 1200 目标。下一步优先参数鲁棒性、fallback 和 restart/内存监控；若目标是进一步降低迭代数，应研究 Maxwell commuting projection、梯度/近核 auxiliary space 和材料/端口感知的真正多层 hierarchy，而不是继续扩大当前失败 p1 coarse。

证据入口：

- [Task030 outcomes](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/summary.md)
- [Case060](../benchmarks/cases/060_multilevel_hcurl_iterative_solver/README.md)
- [candidate funnel](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/candidate_funnel.csv)
- [transfer validation](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/transfer_validation.md)
- [h2 decision](task030_multilevel_hcurl_low_memory_iterative_solver/outcomes/h2_launch_decision.md)

## 41.10 Review V1 更正与证据边界

Review V1 的五项 P0 已在同一分支回应：正式 h5/h3/h2 lightweight records 补齐实际运行 provenance；Case060 checker 从文件存在性升级为 provenance、solver identity、80 modes、三残差、R/T/A、closure、direct delta、内存和分类的 203 项 Gate；manifest 加入三份 experimental entries，normal checker 连续生成保持一致；项目级命名统一为 `compact physical-slab low-memory experimental profile`；理论、walkthrough、capability、benchmark 和边界文档同步说明 p/h multigrid solver 失败。Review V2 又把 h5/h3 更新为 clean final-HEAD rerun，并把 h2 固定为 historical dirty-worktree reference。

最终成功求解器身份固定为 `task27_derived_physical_slab_wave_coarse`。H(curl) transfer/Galerkin 是 validated research infrastructure，不是 successful GMG。factor-only 在 PETSc 3.24.0 complex build 通过生命周期测试；跨版本兼容仍需回归。Task27 ILU1 与 Task30 ILU0 的 reported slab-factor nnz 相同，因而不把内存下降解释为已证明的 factor-nnz compression。

## 41.11 Review V2：clean evidence 与 selective-merge 边界

R1 在 final implementation commit `5b81359daee0874793c44b019d9c914b334db483` 上重跑 h5/h3。两次 record 均写 `git_dirty=false`、`tracked_source_dirty=false`、`tracked_source_verification=host_git_clean_attestation`，且 verified clean SHA 与容器 HEAD 完全一致。h5 heavy JSON SHA-256 为 `2be05820cf69db67ba72b257c44624c08e15f7f7ceeae6e479eed2a9e68523f3`；h3 为 `48c9bb51b89a99b7ba1653f8c95f8450e7917f987274c1aef631464484275232`。h2 按审查要求不重跑，保留 `reviewed_historical_dirty_worktree_reference` 身份，并显式链接 clean h5/h3 的 solver/physics 等价性。

R2 把 `hcurl_multilevel.py` 的 validated infrastructure API 限定为 active DoF、nonmatching transfer/cache/validation 和 condensed Galerkin。Damped Jacobi、Galerkin multilevel PC、Modal Woodbury 等 solver-negative candidates 只由 research runner/tests 直接导入，普通 `src.solvers` 不导出。最终工程求解器仍是 Task27-derived compact physical-slab profile，不是 p/h GMG。

因此 Task030 最终状态为 `workstation_memory_success_with_qualifications`。ordinary default 不变；当前分支只可提交 Response V2 并等待 final review，不能直接合并 master 或启动 Task31。Task31 必须在用户批准 selective merge 后，从 clean master 新建独立分支。

---

# 42. Task030 后的当前推荐顺序

```text
1. 提交并推送 Task030 Response V2；
2. 等待 ChatGPT final review，ordinary default 不变；
3. 用户明确批准后，按 selective merge 边界合入 master；
4. 在合并后的 clean master 新建 Task31 独立分支；
5. Task31 优先压缩 Krylov、F/condensed 重复对象、slab factors 与生命周期。
```

# 43. 当前一句话状态（Task030）

> Task030 已获得 `workstation_memory_success_with_qualifications`：Task27-derived compact physical-slab profile 的 clean final-HEAD h5/h3 分别为 855/962 步、1.687653/3.792912 GB，h2 保留为 1873 步、9.374729 GB 的 reviewed historical dirty-worktree reference；80 modes 与 official R/T/A 通过，H(curl) transfer/Galerkin validated infrastructure 正确，但 792D p1 coarse 的 p/h multigrid solver 明确失败。ordinary default 未改变，master 等待 final review 与用户选择性合并许可。

---

# 44. Task031：compact physical-slab 内存优先结构优化

## 44.1 最终状态

```text
Task = Task031
branch = codex/20260714-task31-compact-pc-memory-optimization
base = Task030 merged master 545165b3d29396dcc3a8d5b029089175eafa3c4a
clean implementation SHA = 45a0fc6e19535cb8f14fbfb186f099019612fec2
classification = strong_memory_success_slow_but_memory_efficient
ordinary_default_changed = false
review_status = Review V1 response_v1 hardening complete; pending final review
master_decision = pending review and explicit user approval
```

## 44.2 为什么启动

Task030 已把 h2 从 Task027 的 13.08 GiB 压到 9.374729 GiB并真实收敛，但对内存受限工作站仍接近 10 GiB。Task030 也证明当前 p/h coarse 不是有效慢误差空间，因此 Task031 不再扩大失败层级，而是围绕已经能收敛的 physical-slab + 75D wave coarse，逐项审计 Krylov basis、assembled fine `F`、slab factor、对象重叠和 PC 合法性。

如果不做这一步，工程风险有两个：一是用 per-rank historical peak sum 或 current RSS 下降误判真实峰值；二是为了省 Krylov 存储把非线性 PC 错配给普通 GMRES，得到不受支持的算法。Task031 不解决任意材料/角度鲁棒、真正 mesh-independent multigrid或多 RHS 吞吐。

## 44.3 冻结问题与 baseline

物理仍为 50×25×140 nm cell、17×25×120 nm complex-Si block、13.5 nm、theta80/phi0/s、p2 Nédélec、double Floquet、80 个 auxiliary DtN modes、exact `F-C H^-1D` 与 official volume-absorption R/T/A，MPI4。ordinary config、模式数、物理、RTA 定义与 full residual 都禁止改变。

Task030 baseline：h5/h3/h2 为 855/962/1873 步，full residual 都 `<=1e-6`，peak 1.687653/3.792912/9.374729 GiB。Task031 h3 continuation 需要 `<=3.50 GiB` 或降幅 `>=8%`；h2 解锁还要求 h3 full pass 且降幅 `>=8%`、两套中心预测 `<=8.8 GiB`、保守上界 `<=10 GiB`、无 swap、clean source 和 watchdog。

## 44.4 采用的方法

### 外部同时内存权威

`run_task031_memory_forensics.py` 每 0.25 s 同时采样 live MPI ranks 的 RSS sum、MPI process tree、cgroup current/peak、线程/CPU 和 WSL swap，并从 runner 的 stage JSONL 标注峰值阶段。它不把各 rank 在不同时刻的历史最大值相加。h2 额外强制 `--unlock-h2`、9.5 GiB warning 与 11 GiB controlled termination。

### Assembled-F-free public MPC form action

`mpc_form_action.py` 把 active vector 写入 MPC Function，backsubstitute 后通过 public `dolfinx_mpc.assemble_vector(ufl.action(...))` 计算 action，并显式恢复 MPC slave unit rows。最初遗漏 unit rows 时误差约 0.0263；修复后 h5/h3/h2 action error 都 `<1e-15`。`CondensedDtnOperator` 接受 external fine action，并通过 `require_f/release_f` 只让 assembled `F` 存活到 coarse/slab setup 完成；solve ledger 中没有 `F`。该路径只是 solve 阶段 assembled-F-free，不是缓存优化的低层 element-kernel matrix-free；每次 apply 仍发生 Function/MPC/form assembly 与通信。

### Slab、lifecycle 与合法性

overlap0.125 缩小 factor；compact lifecycle 在 RTA 前释放 KSP/PC/factors/work vectors；exact SHA-256 fingerprints 只允许完全相同 factor 共享。PC certificate 用随机向量检查 linearity/determinism：Task030 adaptive local GMRES PC 的线性误差为 `2.374308e-2`，因此普通 GMRES fail closed，必须保留 flexible Krylov。固定 Richardson 虽达到 `3.611e-15`，却失去收敛能力。

## 44.5 实验漏斗与负结果

| lane | 关键观测 | 决定 |
|---|---|---|
| FGMRES50 | worker RSS -1.89%，residual/time 更差 | `<3%` 停止 |
| ordinary GMRES | PC linearity `2.374308e-2` | 算法不合法，fail closed |
| fixed Richardson | linear，但 200 步 residual 0.7703 | numeric negative |
| 16 slab overlap0.125 | factor nnz -19.59%，residual 略差 | weak positive，进入组合 |
| 20 slab overlap0.125 | factor/RSS/residual 均差于16 slab | 停止 |
| boundary Jacobi1 | stored factor -9.95%，residual 恶化约13.7x | 停止 |
| exact factor dedup | 16/16 fingerprints unique | 无可共享 factor，停止 |
| assembled-F-free public form action | action 等价，200步 RSS约 -2–3%，时间3.18x | 内存优先保留 |

h3 第一次在 max_it1600 时 full residual 为 `5.490e-6`，严格判负；任务书允许 h5/h3 上限 5000 且不以高迭代数自动判失败。同一配置提高安全上限后在 1994 步通过，残差历史与第一次共同点逐位一致，证明是延长同一过程而非参数漂移。

## 44.6 h5/h3/h2 正式结果

| h | DoF | iterations | full residual | simultaneous worker peak | cgroup peak | solve/total s |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 44,698 | 1,157 | `9.959903e-7` | 1.619598 GiB | 1.056248 GiB | 350.851 / 374.342 |
| 3 | 198,438 | 1,994 | `9.973853e-7` | 3.474346 GiB | 2.899216 GiB | 2311.581 / 2370.351 |
| 2 | 615,108 | 1,977 | `9.998454e-7` | 7.897675 GiB | 7.424026 GiB | 11982.581 / 12173.086 |

三份 run 都来自 clean SHA `45a0fc6e...`、同一 image digest 与 MPI4。h3 external simultaneous peak 3.474346 GiB，通过 3.50 GiB 绝对线；相对 Task030 历史口径的观察降幅 8.399% 只作辅助。h2 external simultaneous / legacy internal peak 为 7.897675 / 8.176441 GiB，相对 Task030 历史值的辅助对照约降 15.8% / 12.8%；保守工程结论约 8.0–8.2 GiB。h2 通过 strong `<=8.0 GiB` external Gate，但未达到 stretch `<=7.0 GiB`。峰值在 `outer_krylov_solve`；coarse operator ready 7.867531 GiB，solver release/RTA 约 6.50 GiB。swap in/out=0，watchdog 未触发。

## 44.7 h2 预测与条件解锁

h5/h3 DoF–RSS 仿射外推给出 8.501130 GiB；Task030 h2 按 h3 实测比例迁移给出 8.587349 GiB。以 h5 最弱的 4.032% 收益应用到 Task030 h2 后再加 5% 余量，保守上界为 9.446530 GiB。三者全部过 Gate，才解锁唯一 h2 candidate。实测 7.897675 GiB 低于两套中心预测和上界；没有运行第二个 h2，因为首个已经 `<8.0 GiB`，也没有机制不同且预测 `<=7.5 GiB` 的候选。

## 44.8 数值正确性与 R/T/A

h5/h3/h2 的 reported、condensed true 和 full augmented true residual 一致。official R/T/A 为：

```text
h5 = 0.089021602568 / 0.442588275323 / 0.468390124569
h3 = 0.004613031629 / 0.583653357934 / 0.411733610310
h2 = 0.001342934186 / 0.599213235569 / 0.399443835926
```

energy closure 分别为 `2.460e-9 / -1.270e-10 / 5.682e-9`；对 direct 最大 delta 为 `6.162e-9 / 1.104e-9 / 6.125e-9`，都远低于 `1e-6`。这排除了仅 reported residual 收敛或 public form-action wrapper 改变物理解的可能。

## 44.9 结果解释

Task031 的收益不是来自单一“神奇 PC”。solve 阶段不常驻 assembled `F`、slab factor 规模与 solver/RTA 对象重叠是三个正交来源；restart50 的 payload 模型下降没有转化为足够的 full-process peak。相对 Task030 历史口径的 h5/h3/h2 百分比只能作为趋势证据，不能包装成严格同 sampler 的精确 A/B。

代价同样清晰：public form action 每次需要 MPC field 写入/backsub/assembly，h2 约 13,960 次 form apply，使 solve 达 11982.581 s，是 Task030 的约 5.01x。迭代数只增加约 5.55%，每步平均成本约增加 4.74x；一次性 `release_f()` 不是主要耗时。因此最终分类必须同时包含 strong memory success 和 slow-but-memory-efficient，不能只报道 7.898 GiB。

## 44.10 最终决策与合并边界

建议 review 后选择性合并 external sampler/watchdog、public MPC form action、safe condensed lifecycle、PC certificate、object ledger、测试、Case070 与文档。最终 candidate 只作为显式 opt-in memory-first profile；ordinary default 不变。

不得提升 fixed Richardson、boundary Jacobi、restart50、20-slab 或 approximate factor sharing。16 个 factor 没有 exact duplicate，因此不存在 dedup implementation。不能把 release 后 current RSS 下降冒充 peak success，也不能把冻结 target 的验证写成任意参数数学保证。

## 44.11 局限与下一步因果关系

当前证据只覆盖一个物理/RHS、MPI4 partition 与当前 image；运行方差、其他机器、参数扫描、多 RHS 和跨 PETSc 版本未验证。Task030 与 Task031 的 memory sampler 口径并非完全一致，故所有轻量 record 同时保留 external simultaneous、cgroup 与 legacy internal 值。

下一步若追求平衡，应优化 public form action 的缓存/批量路径，或设计固定线性且有足够平滑能力的 polynomial/Chebyshev local action；不应继续压 restart 或近似共享 factor，因为已有负证据。新路线必须从 h5 action equivalence、PC legality、true residual 与 simultaneous peak 联合 Gate 开始，再进入 h3/h2。

## 44.12 证据入口

- [Task031 task](task031_compact_physical_slab_memory_optimization/task.md)
- [Task031 outcomes](task031_compact_physical_slab_memory_optimization/outcomes/summary.md)
- [迭代求解器端口与合法性](iterative_solver_ports.md)
- [Case070](../benchmarks/cases/070_compact_physical_slab_memory_optimization/README.md)
- [h2 prediction](task031_compact_physical_slab_memory_optimization/outcomes/h2_memory_prediction.md)
- [negative results](task031_compact_physical_slab_memory_optimization/outcomes/negative_results.md)
- [matrix-free validation](task031_compact_physical_slab_memory_optimization/outcomes/matrix_free_validation.md)
- [iterative theory](../notes/theory/iterative_solver_and_preconditioner.md)
- [workstation runtime walkthrough](../notes/reference/code_walkthrough/33_workstation_fgmres_runtime.md)

---

# 45. Task031 后的当前推荐顺序

```text
1. 完成 Task031 分支 full tests、Case070 checker 与 clean-tree 审计；
2. 推送分支，等待 ChatGPT Task031 review；
3. 按 review 修正，不静默改变 ordinary default；
4. 用户明确批准后才选择性合并 master；
5. 后续若继续，优先降低 public form-action apply 时间，而不是重复已失败的 restart/dedup 路线。
```

# 46. 当前一句话状态（Task031）

> Task031 在 clean MPI4 frozen target 上以 assembled-F-free public MPC form action、16 slabs overlap0.125 与 compact lifecycle 实现 h5/h3/h2 全部 true-residual + official-RTA 通过；h2 1977 步，external simultaneous / legacy internal 为 7.897675 / 8.176441 GiB，保守工程范围约 8.0–8.2 GiB，达到 `strong_memory_success_slow_but_memory_efficient`，但 solve 约 5.01x，ordinary default 未改变；Review V1 数值/内存通过，文档加固见 response_v1。

---

# 47. Task035 Phase C/D：estimator 与 mesh-backend bake-off

Review V3 接受 B1/B2 real-FE minimum Gate 后，Phase C/D 在同一执行分支连续完成。Phase C
复用 Task034 accepted p2/p3/p4 field samples，对固定 13.5 nm、10° grazing、S 入射结构筛选
sampled R1、discrete two-level R5 proxy、external DtN split 与 R2 diagnostic。R5 proxy 对
p4/h5 best-available discrete error 的局部相关性为 0.989–0.998，但不是 formal hierarchical FE
solve；sampled R1 相关性为负。Task034 strip/tensor actual PDE 细化证据继续失败 physical gates，
且不是 estimator-marked refinement，所以没有 production estimator。

B3 actual material-interface/corner Nédélec fixture 与 B4 accepted Hybrid Et/Ht、M80/120/160、
DtN/QEP microfixture 均通过 serial/MPI2。Phase D 比较三条 backend：strip/tensor 保留
`controlled_negative`；conforming multi-block hexa 因 Cartesian axis-cut leakage 记录
`hexa_backend_blocker`；tetra actual marked-refine control 从 384 到 1392 cells，正体积、局部性与
Nédélec proxy improvement 通过，但只作为 research control。

首次 MPI2 tetra volume measurement 因 topology vertex ID 错用于 refined geometry indexing
产生伪零值，失败 record 已保留；改用 `geometry.dofmap[cell]` 后 final serial/MPI2 identity 通过。
最终状态为：

```text
phase_c_internal_gate = complete_controlled_negative
phase_d_internal_gate = complete
production_estimator_selected = false
production_backend_selected = false
ordinary_default_changed = false
phase_e_unlocked = false
```

未运行 Phase E/F、目标 adaptive cycle、p4/h5 heavy 或 ordinary-default change。

# 48. Task038：input-driven configuration

Task038 用一个显式 `.dat` 文件统一描述 geometry、materials、incidence、discretization、boundary、method、solver、execution 和 output。这样用户提交的是一份可审查、可复现的配置合同，而不是在多个 preset 或命令行参数之间拼接物理值；它改变用户配置方式和入口，不改变 Maxwell、Hybrid、DtN 的数学实现，也不改变 ordinary defaults。

| 项目 | 当前边界与证据 |
|---|---|
| 迁移范围 | 11 个 ordinary preset 已迁移到 dat；6 个 research/history preset 保留原有 Python replay。 |
| 已连接入口 | ordinary 2D、staged 3D、Full3D direct、Hybrid direct、Hybrid iterative adapters；普通入口为一个 `.dat`。 |
| provenance | 运行 manifest 保存 input/source/physical/resolved-config hash 及执行身份，供结果目录和审阅记录回溯。 |
| source branch inherited evidence | source branch full pytest：1119 passed / 48 skipped / 0 failed / 1514.73 s；这是 inherited source evidence，不是本 integration worktree 的测试结论。 |
| integration status | integration full pytest = `not_run_yet`；本阶段不把它写成通过。 |
| T6 resource boundary | RSS `6585.01953125 MiB`；数值 Gate 通过，但 preferred resource boundary 未满足；这不是数值失败。 |
| 尚未运行项 | current-same-SHA Hybrid iterative MPI1 formal = `not_run`；T4/T5 selected-field capability = `not_run_by_capability`。 |
| 详细入口 | [`Task038 outcomes summary`](task038_input_driven_configuration/outcomes/summary.md)、[`response_v1`](task038_input_driven_configuration/response_v1.md)、[`Review V1`](task038_input_driven_configuration/review_report_v1.md)。 |

## 49. Task038-extra Review V11 S6 closeout

Review V11 的 S1 global transfer/rank/spectral audit、S2 p6/h10 foundation live-set audit 和 S4 p2/p3 LOR-edge small oracle 已按各自范围完成。S5 只完成了 p6/h10 6→3→1 hierarchy 的 setup、identity、lifecycle 与 capacity audit；其资源证据通过，但 6→3 rediscretized energy relative 为 `0.04115402900674629 > 1e-9`，所以 `lor_edge_geometric_mg_v1` 在 S5 关闭，不能提升为 solver 或 production capability。

| lane | status | measured boundary |
|---|---|---|
| S1 | pass | p2 rank 768、p3 rank 2538；peak 788,987,904 B、swap 0 |
| S2 | pass | p6/h10 rows 173,802；cold/retained 983,363,584 B；swap 0 |
| S4 | pass at small-oracle scope | 16/16 cases、8/8 MPI pairs；aggregate SHA `56b7eec1435abc69a38c38af056d8803e8f62a3ff6768b87faa594670c916c4e` |
| S5 | failed algebra Gate | 6→3 energy `0.04115402900674629`；3→1 `2.7851655955739857e-15`；external peak 1,207,476,224 B、swap 0 |
| S6+ | not_run_by_gate | no repair, p1 distributed coarse solver, p6 physical Maxwell, p6/h5 or 0.7 nm PDE |

The immediate blocker is 6→3 interlevel energy consistency, not yet the p1 distributed coarse solver. A supplemental local diagnosis found non-nested p3/p6 GLL nodes and a naive tiled composition defect `0.23558864802518256`; no tiled repair or parameter scan was implemented. The old Q0 negative, foundation-E pass, old spectral controlled negative, HX/PCGAMG closure and ba40358 probe-domain-invalid archive remain immutable. Ordinary default and `master` were not changed.

S6 evidence and explanation are in [`Task038-extra V11 summary`](task038_extra_full3d_iterative_0p7nm/outcomes/summary.md), [`S4 oracle outcome`](task038_extra_full3d_iterative_0p7nm/outcomes/lor_edge_geometric_mg_oracle_v1.md), [`S5 capacity outcome`](task038_extra_full3d_iterative_0p7nm/outcomes/lor_edge_geometric_mg_p6_capacity_v1.md) and [`response_v11`](task038_extra_full3d_iterative_0p7nm/response_v11.md). This is a docs-only closeout; no CI claim is made.

## 50. Task038-extra Review V12 R12 closeout

Review V12 在同一 extra 分支完成了 Route A、Route B、C1 和 C2 的阶段性审计收口。Route A 的 10 个 material classes 局部谱事实通过，但 gradient global adjoint 为 `2.8964367576123248e-11 > 1e-12`，所以路线关闭；Route B v2 的 `6→2→1` structural/setup 证据保留，R4.3 random 在 7000 步因性能趋势受控停止；C1 的 physical-canonical MPI identity 与 C2 的 nested owner work Gate 失败。最终 `selected_hierarchy=NONE`，没有 p6 positive、physical Maxwell、official physics 或 0.7 nm PDE 结果。

| 项目 | 结果/边界 |
|---|---|
| C2 MPI1 diagnostic | `p6-h50`，source `f7d0ac41678b2d18be6c05c1eebfde87adcf9521`；`h3star→h1star` owned work `0.018392534459166617 > 1e-11` |
| C2 resource scope | rank-worker max RSS `486,473,728 B`、rank swap `0 B`；不是 process-tree qualification |
| compact evidence | [`nested_lor_edge_hmg_c2_mpi1_diagnostic_v1.json`](task038_extra_full3d_iterative_0p7nm/outcomes/records/nested_lor_edge_hmg_c2_mpi1_diagnostic_v1.json)，SHA `62a7bbce12dceb77254bae2ead9c8b3ddf8f9dc0d48b5349b5147f7434ecdf79` |
| downstream | p6 positive/physical、R/T/A、h5、2 TiB 与 0.7 nm 均 `not_run_by_gate` |

C2 第一对 transfer 与三个 level bridge 通过，第二对失败无法由现有事实唯一归因到某一条 production 公式，因此没有猜修。C2 local oracle/infrastructure 归为 research-only，owner runtime/test 归为 do-not-merge candidate evidence；ordinary default 未改变。阶段详情、下一架构比较和十问回答分别见 [`V12 route outcome`](task038_extra_full3d_iterative_0p7nm/outcomes/interlevel_route_selection_v1.md)、[`next PC architecture`](task038_extra_full3d_iterative_0p7nm/outcomes/next_pc_architecture_after_v12.md) 和 [`response_v12`](task038_extra_full3d_iterative_0p7nm/response_v12.md)。

## 51. Task038-extra Review V13：C1 selected hierarchy 与 P0 resource stop

V13 的 C1 exact-input p6/h10 same-mesh positive lane 已由 random、gradient、curl、checkerboard 四源全部通过，selected_hierarchy 从 V12 历史的 NONE 更新为 same_mesh_hcurl_pmg_v1_requalified。这个更新只属于 V13 新 source SHA、exact input 和独立 artifact root；V12 的 C1 identity negative、Route A/B/C2 负结果仍原样保留。

| 阶段 | 当前事实 |
|---|---|
| A0 | 已实际运行 6 probes；CLOSED_BY_VECTOR_OR_STABLE_ADJOINT_GATE；gradient pairwise-vs-compensated=2.7478465599487806e-12 > 1e-13；MPI2/A1 not_run_by_A0_gate |
| C0 | MPI1/MPI2 canonical source PASS，source 4dc9b55cd3519a03b23c9d27779c0379cef84f66 |
| C1 | 四源 exact-input v4 PASS；p6/h10；final explicit true residual 2.7889793119815017e-9 至 7.760965317017376e-9；process-tree peak 1,516,544,000 至 1,536,192,512 B；swap=0 |
| P0 | MPI1 physical_rhs，source a05e93af6edb097c1f0ebf0f65e201698db27381；仅 paths_ready；peak 2,024,108,032 B；超过 2,000,000,000 B hard line 24,108,032 B；controlled termination |
| P1/P2/G/D | P1/P2 为 not_run_by_resource_gate；G/D 为 not_run_by_selected_C1 |
| 0.7 nm / ordinary | 完整 0.7 nm PDE not_run；ordinary default、master 未改变 |

P0 watchdog 共 20,518 个 raw samples，最后 elapsed=5167.201565908967 s，warning first=1,813,069,824 B at 5165.438371994998 s，process-tree swap=0、no_orphan=true、returncode=-15、natural_exit=false。没有 worker record、checkpoint、residual、recovery 或 official physics，不能将 P0 写成 numerical/physics failure，也不能把 C1 positive 写成 physical qualification。当前 tracked direct authority 只有 scalar R/T/A/A_volume，缺少 E/H 与 12+12 raw arrays；该 downstream comparison blocker 因 P0 先在 setup 停止而未触达，不是本次停止原因。

本轮保留 P0 ignored root，并将 watchdog compact 与 paths_ready marker 原字节复制到：

- [P0 watchdog compact](task038_extra_full3d_iterative_0p7nm/outcomes/records/same_mesh_hcurl_pmg_p0_physical_v1_watchdog.json)
- [P0 paths_ready marker](task038_extra_full3d_iterative_0p7nm/outcomes/records/same_mesh_hcurl_pmg_p0_physical_v1_paths_ready.json)

原始 raw SHA 为 51e8e531500e733c21f558d44be0a4d8d7a76fe9454800ebc9cb8ad06ab19566，compact SHA 为 0705e170a1835999aece82dfe43d3ff5ccd3cf98800b79a013341b54ed2955e5，paths SHA 为 4f22fd62136515693ebebef4fbfe551e84e46223a0685054dcb9ad1a65108415。P0 的详细说明见 [p6 physical V13](task038_extra_full3d_iterative_0p7nm/outcomes/p6_physical_v13.md)，C1 见 [p6 positive V13](task038_extra_full3d_iterative_0p7nm/outcomes/p6_positive_v13.md)，逐项回答见 [response V13](task038_extra_full3d_iterative_0p7nm/response_v13.md)。

严格资源语义是：2 GB 是 hard stop，1.8 GB 只是 warning。P0 超出 24,108,032 B（约 1.2054%）仍须记录为 FAIL；不能按“只超一点”舍入通过。没有从 13.5 nm cold-JIT peak 外推 0.7 nm/2 TiB 能力，也没有创建 next_pc_architecture_after_v13、feasibility_v5 或未触达阶段 outcome。

## 52. Task038-extra Review V14 J5：cold-staged physical workflow controlled stop

### 背景与基线

V13 C1 的四个 exact-input p6/h10 positive source 已通过，保留 `same_mesh_hcurl_pmg_v1_requalified` 作为 selected hierarchy。V13 P0 的 cold setup 曾以 `2,024,108,032 B` 超过 2,000,000,000 B hard line；V14 J4 随后完成 one-cycle P0R qualification。J5 v3 是在新 source SHA 和全新 root 上测量完整 physical Maxwell workflow 的唯一 formal。

### 身份与方法

| 项目 | 值 |
|---|---|
| source SHA | `ee5920b9fa977a39fea7bc09cfbe155303acdb2d` |
| profile | p6/h10/13.5 nm/s/grazing1/phi0，MPI1，physical RHS |
| operator / PC | exact split matrix-free Maxwell volume、streaming Fourier-DtN、same-mesh pMG |
| Krylov | right GMRES，restart20，max_it20000，true-residual replacement20 |
| cold staging | 七个 precompile group 串行完成，11 个 `.so`；随后启动 solver |
| evidence policy | parent JSONL、cache、markers、checkpoint 保留在 ignored root；不追踪 1.02 GB raw |

### 结果与解释

| 指标 | measured fact |
|---|---:|
| samples / raw | 334,915 / 1,020,808,306 B |
| raw SHA256 | `28c4044f3eebb72ca1991d1c71a67dd30637a7d550e798ffc7f536c28d969cf4` |
| raw first/last timestamp | `1788206276386617381` / `1788228581099334131`；window `22304.712716750 s` |
| solve start → last sample | `16477.100765097 s`；solve_started=`1788212103998569034` |
| full staged peak / swap | 1,450,262,528 B / 0 B |
| readability | RSS/status 全部 334,915 samples readable；PSS 有 6 个 precompile 退出/zombie 瞬时样本不可读 |
| checkpoint-500 residual | 0.48387099430079733 |
| checkpoint-1000 residual | 0.4837947981092168 |
| 500→1000 relative drop | 0.000157472120623114（约 0.01575%） |
| marker boundary | `035_solve_started`；没有 solve_complete/recovery/official |
| records / stderr | parent、worker、partial record absent；worker stderr 0 B |
| classification | `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED` |

最后一个有完整权威文件的 checkpoint 是 1000；manifest mtime 后 raw 仍继续约 3896 s，checkpoint-1500 不存在，实际 stop iteration unavailable。worker/parent/partial record 缺失，所以 per-cycle residual history、matvec/PC/KSP destroy 计数和 driver elapsed_seconds unavailable，不能从步数或公式猜测。用户随后停止 parent 与其 orphan worker groups；进程全部消失，JSONL 停止增长，两个 solution-only checkpoint 完整保留。这是用户控制停止，不是 fixed-cap 20000-step numerical failure；也不是完整 workflow memory PASS。

### 决策、局限与下一步

J6 为 `not_run_by_J5_eligibility`；J7/J8 locked/not_run。official E/H、near-field、R/T/A、`A_volume`、energy closure 和 12+12 raw arrays 均 `not_run`。direct authority 仍只有 scalar packet，缺 E/H 和 12+12 arrays；该 downstream blocker 未被冒充为通过。

V14 当时提出的 V15 独立诊断已在 V15 formal artifact v3 中完成；固定 rank32 global projection 的 span Gate 失败后，Floquet correction 已关闭。当前唯一未授权候选是独立的 wave-aware domain decomposition 预审，不重跑 V15 rank32 projection 或 bounded correction，也不重开普通正定 GenEO/BDDC/HX。

证据入口：[`V14 J5 memory outcome`](task038_extra_full3d_iterative_0p7nm/outcomes/jit_staging_physical_memory_v14.md)、[`V14 J5 physical outcome`](task038_extra_full3d_iterative_0p7nm/outcomes/p6_physical_v14.md)、[`V14 response`](task038_extra_full3d_iterative_0p7nm/response_v14.md)、[`J5 compact`](task038_extra_full3d_iterative_0p7nm/outcomes/records/j5_full_cold_staged_v3_controlled_stop_v14.json)。

## 53. Task038-extra Review V15 F0–F4 收口

| 阶段 | 结果 | 证据边界 |
|---|---|---|
| F0 | predicted central 1,555,934,144 B | 容量预审，不是 formal measured PASS |
| F1 real small p3/h50 | F1_REAL_SMALL_ORACLE_PASS | MPI1/MPI2/checker canonical identity 通过 |
| F2 checkpoint-1000 | identity/algebra PASS | residual relative 6.884466486395685e-16 |
| F3 rank32 | FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE | captured 0.002179823642496248，rho 0.9989094935766222 |
| V14 J5 | CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED | 用户控制停止；不是 fixed-cap 20000-step failure |

F1 的 source SHA 为 fb1b4be71d230b77eff431a7e3dd77eb3a69ba69；80-mode manifest SHA256 为 dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2，fixed selector SHA256 为 7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3。modal/PC canonical MPI relative 分别为 3.7455782853640207e-16 和 8.520822093979077e-16；P/P^H adjoint MPI1/MPI2 为 1.9465463728177503e-15 / 7.26427252913998e-15。具体路径和 record/NPZ/checker SHA 见 [V15 F1 compact](task038_extra_full3d_iterative_0p7nm/outcomes/records/floquet_wave_small_oracle_v15.json)。

V15 formal artifact v3 F2/F3 source SHA 为 c85ec1aab8548e02e8b47cfdcfb03b5c4df377f6。parent natural exit=0，33 markers、7 groups、11 modules、cache unchanged、全部进程消失；process samples=100656，RSS peak=1,447,358,464 B，swap=0，warning=false，compiler peak=2。PSS peak=1,417,525,248 B，但 7 个 transient precompile 退出样本 PSS 不可读；资源 Gate 使用完整 RSS。

F2 stored/recomputed residual 为 0.4837947981092168 / 0.48379479810921644，identity、x/b unchanged、finite、slave-zero 通过，exact action count=1。F3 rank=32，condition ratio=0.05087665596047715，orthogonality=1.4263744029917661e-13，QR reconstruction=2.4622854394555095e-16，projection repeat=2.7273607083155513e-16，PC/action/modal RHS=32/32/32。span Gate 要求 captured 至少 0.90、rho 不大于 0.31622776601683794、ideal 不大于 0.153；实测 captured/rho/ideal 为 0.002179823642496248 / 0.9989094935766222 / 0.4832672167742815，故关闭 correction。

J6 为 not_run_by_J5_eligibility；J7/J8 locked/not_run；KSP、recovery、official E/H/R/T/A、A_volume、12+12 channels、MPI2/h5/full 0.7 nm 均未运行。V13 positive qualification 保留，但 standalone physical production claim 关闭。下一候选只有 [wave-aware DD 设计](task038_extra_full3d_iterative_0p7nm/outcomes/next_wave_aware_dd_after_v15.md)，未授权实现。

V15 formal artifact v1/v2 pre-F2 execution failures 在用户明确次数授权下不计正式数值次数，但 old raw status 不改写；V15 formal artifact v3 已进入真实 span Gate，不能再重跑、改 rank/mode/参数。J5 raw JSONL 1,020,808,306 B 仅以 hash-bound compact 记录，不追踪原始文件。详见 [V15 response](task038_extra_full3d_iterative_0p7nm/response_v15.md)。


## Task39extra_para：原生工作站复现、单核性能诊断与受控停止

本任务从冻结V5 BAL_H + accurate global p4 LU迁移到2TB原生Linux工作站，目标是先复现13.5 nm，再按Gate测试5/3/2 nm。独立worktree及CPU23/监督CPU9安排使本项目不互写隔壁文件、不修改其CPU0–7的8个MPI进程。CPU2外部限频和DIMM高温被记录为独立硬件问题，未关闭热保护。

第一次R1在p4 LU后遇到mode字节身份差。用户移交完整历史manifest后证明仅12处浮点末位差，按原数值容差逐字段验证并保留两端hash。retry1与旧迭代轨迹高度一致，但单步约29.6秒，62步true0.0194332未满足首段1800秒筛选，故停止主阶梯；workflow3997.651秒、整树RSS峰值3.163GiB、swap0、全部清场。没有official场或R/T/A，也没有短波或G的容量/精度结果。

性能诊断把主要装配开销定位到FFCx内核的跨行访问与寄存器spill。保持每个矩阵元素求和顺序、按行遍历后，真实单元CSR装配约3.6倍；合并12个独立系数循环使p6/p4 curl单元作用约2/1.4倍，真实FE逐位等价。PSS降频保留RSS/swap高频监督，并修复已有worker身份失败分类；这些是执行成本改进，不是新PC。释放后RSS只下降4MiB，表明仍需测量allocator/对象保留，不能伪造生命周期压缩成效。

当前交付fail / PERFORMANCE_CONTROLLED_STOP。性能修复有小测试证据但没有优化后完整R1；任务书§11禁止把性能失败当bug再抽签，额外正式验证需明确授权，原screen/数值/物理Gate继续保持。所有正负结果及依赖分组见[summary](task39extra_para_workstation_capacity/outcomes/summary.md)，细节见[response_v1](task39extra_para_workstation_capacity/response_v1.md)；未merge master。

## Task39extra 2026-09-20：2 nm h1.5 实测内存运行快照

run `20260918T035017.294454Z`、source `41caf5141493ad6c5d6c518a64ee74fda8d7a7db` 正在 p4/MUMPS numeric；symbolic facts 已实际记录为 `INFOG1=0`、`INFOG7=4`、`INFOG16=1222577`、`RINFOG1=1100362818940466`，numeric/outer/RTA 尚未取得结果。末次整树 RSS=`477900079104 B`、swap=0；独立1300 GB measured guard仍运行，完整阶段峰值未从大资源日志聚合。54332 cells、p6 35594790 rows、p4 augmented 10608132 rows/4899800920 NNZ、3904 modes（3902 propagating）。

该记录不把末次RSS当全程峰、不把诊断 predicted peak 当严格上界，也不把 5 nm 的600通道套到本次3904 modes。阶段/身份/小资源证据见 [2 nm running compact](task39extra_para_workstation_capacity/outcomes/records/2nm_h1p5_measured_running_snapshot_v1.json) 和 [Response V4](task39extra_para_workstation_capacity/response_v4.md)；历史失败、5 nm资源监督缺口及未完成 Gate 仍按原记录保留。

### 终态补记：global swap attribution Gate

该 run 随后以 `exit=-9` 结束，原 watchdog 分类为 `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`：全局 `pswpout` 从 `2` 到 `73` 页，delta=`71` 页（page size 4096 B，即284 KiB）；同一 stop sample 的整树 RSS=`635625377792 B`、任务树 swap=`0`、MemAvailable=`836791996416 B`、reserve=`324465062092 B`。这不是 OOM、全机 RAM 耗尽或数值不收敛证据；无 numeric complete、outer 或 RTA。

1300GB measured guard 另记 attachment peak=`640141377536 B`，后以 worker RSS unreadable/`monitoring_failed` 停止，触发晚于原 watchdog stop约`0.245228993 s`，不作为最初原因。详见 [终态 compact](task39extra_para_workstation_capacity/outcomes/records/2nm_h1p5_measured_terminal_snapshot_v1.json)；不自动重跑。后续 cgroup v2 swap隔离只作建议，不在本轮修改系统或 Gate。


## Task39extra_para V5：5 nm setup-only 终态

5 nm Si p6/h4 q4 setup-only run `20260924T092250.568977Z`（source `96057565d171077cc84a8dae3cd4eb88b6ff21ea`）自然 exit 0，`SETUP_ONLY_COMPLETED`，setup checks PASS。setup-only/workflow 为 `2023.440526/2028.390414 s`；整树同时RSS峰 `37236830208 B`，watchdog 6192个样本全可读、最大间隔 `0.653519 s`、swap 0、后代清场。p6/p4各175 raw几何类在本run实际形成6个近似tensor组，组内核计时 `292.039/33.847 s`。与旧完整F5 setup `11263.076 s` 比约快 `5.57×`，但旧F5走raw类，本run采用不同source和近似分组；本run不含outer solve、完整A6 recovery、R/T/A或checker，故只记setup候选证据。完整哈希与计时范围见 [compact](task39extra_para_workstation_capacity/outcomes/records/f5_setup_only_v5_compact_v1.json)。主审批准在fresh准入通过时执行唯一F2；未通过任一CPU、身份、内存或隔离条件则不启动。

## Task042：低内存 p4 粗逆首轮，F0完成并等待共享工作站

执行分支`task42_neural_coarse_inverse`，冻结base`ccd357885f7f9be84efe3be07868cc94f13d93fc`，最终分类`WAITING_FOR_SHARED_WORKSTATION`。本轮等待ChatGPT review，未合并master，普通默认未改变。clean F0运行source为`9934c2e08d017124ba70bdc86ec0c22f39ca792f`，后续文档HEAD不能代替它。

启动原因是原A6已经有不物化全局p6矩阵的作用路径，但准确p4粗逆仍存储大型LU，BAL_H每次外层修正要两次粗调用。Task39工作站交接显示粗逆整体昂贵，内部回代/恢复/原A4验算的份额仍unknown，因此不能先假定NN推理快就能加速全流程。本任务保留原方程及验算，分别比较去因子、传统B0、线性降维、NN相对线性的增量。

首轮只冻结original Si块、13.5nm、1°、phi0、s、50×25nm单胞、120nm块高、Full3D p6/h10、同网格p4、双Floquet/完整auto Fourier-DtN。旧252cells/173802/53084 FE storage/80通道仅是历史锚点；当前真实mesh/mode和operator identity未构建。真实粗返回需原A4与端口/恢复<=1e-10、固定RIGHT FGMRES32/max256/zero start；只有F4通过才有条件进入p6原A6<=1e-6及完整场/模态/能量比较。

| 方法 / 目的 | 实际实施与证据 | 结果与范围 |
|---|---|---|
| canonical linked worktree / 隔离源码 | 宿主机核验空NN-Lab、canonical/origin/登记；仅fetch任务ref；用户授权仅追加Task042 refspec以建立upstream | 准备完成时clean、ahead0/behind0；base和初始task提交均祖先；旧工作树保留 |
| 新activation / 隔离环境与写缓存 | 两新venv，FE只读prefix；CPU-only Torch2.7.1；src/TMP/JIT/bytecode/model等全部NN-Lab | clean导入核验complex128/int64、MPI1、线程1；没有JIT/form/FE构造或GPU训练 |
| 独立严格返回协议 / 保留原数学门 | 新src模块持有完整FE+累计port状态，独立三个数值witness、精确slave-zero、身份/容量/步数拒绝 | 33纯数组测试通过；还给出凝聚与p传递/curl-mass非交换反例；未实现真实FGMRES/B0/FE adapter |
| 冻结神经历史 / 避免归因错误 | 只读d91652d SHA下001/004/005的11份实际文档及5个接口，保存blob | 001整体更慢；004exact全16仅局部逆信号；005完整存储超限、非线性无明显线性优势；没有源码或数据迁移 |
| 资源Gate / 保护邻任务 | 2026-09-28T08:57:36Z固定PID/start_ticks/status/affinity与短GPU查询 | 原2nm CPU24约1.150TB RSS仍运行，另两GPU100%；本任务仅CPU14/2GiB轻测试，F1–F5不启动 |

| 实测 / 数据身份 | 数值 / 单位 | 解释 |
|---|---|---|
| 最终33 tests | pytest0.19s；监督workflow1.659649s；RSS67231744B、swap0 | 组件接口验证，不是Maxwell或实际内层迭代资格 |
| 11解析toy返回 | native witness最大1.2757622972373108e-16，port/recovery0 | 受控解析backend，不是teacher/数据集/物理A4 |
| 安装与测试/导入含失败9个顺序监督工作流 | wall合计72.225243s；同时tree RSS最大236548096B，各own swap0 | 0.1s采样父及后代，峰取最大不相加；toy提取另1.751461s，最后静态检查另列 |
| R-LU/B0/LIN/NN、A4/A6/RTA/场/模态 | 全部not_run | 无本轮分母、收益或摊销结论；GPU peak not_run，编辑/Git会话峰未记录 |

唯一实现负记录是初次FE预检错误调用DOLFINx cache API，在无JIT阶段抛AttributeError。原失败3.719178s、179027968B、swap0与清场保留；一次最小修复实际0.10 `get_options()`并增加XDG_CONFIG_HOME隔离后通过。没有数值停滞或参数重试。

本轮决策是交付F0并等待review，而不在邻heavy旁构造FE/teacher/训练或正式PDE。teacher/dataset/basis/model/checkpoint不存在；真实无global p4因子、线性/NN优劣、时间和内存20%改善、NN10%增量均未评价。后续先fresh核查heavy清场和同机lock，再完成F1不建global factor的opt-in factory、真实非零内部/port RHS、尺寸/身份/容量Gate，依次oracle、同表示线性与一个NN、严格粗返回，最后条件p6；不自动启动5/2/0.7nm或无界扫描。

详细证据：[Task042 summary](task042_neural_coarse_inverse/outcomes/summary.md)、[Response V1](task042_neural_coarse_inverse/response_v1.md)、[Git/环境隔离](task042_neural_coarse_inverse/outcomes/environment_and_isolation.md)、[架构/oracle](task042_neural_coarse_inverse/outcomes/architecture_and_oracle.md)、[provenance](task042_neural_coarse_inverse/outcomes/dataset_and_model_provenance.md)、[run index](task042_neural_coarse_inverse/outcomes/records/run_index.json)、[测试](task042_neural_coarse_inverse/outcomes/test_summary.md)。新增协议和activation仍为research-only；没有fresh PDE或production merge approval，ignored缓存/下载/日志不提交。


## 2026-09-28 Task042 V2：用户授权受控共享，真实F1–F4完成

本节更新上面的F0历史等待状态。用户明确允许仅Task042在其他heavy仍运行时受控共享，替代§2.3 heavy禁令/全机独占锁，不取消精度、资源或Gate，不宣称F0正式review通过；原任务/review/response_v1保留。真实运行使用自有nonblocking flock、一次一阶段、现场选CPU0（48物理核无SMT）、MPI1/math/编译1、nice10/idle I/O、整树16GiB/12GiB、own swap0。两GPU持续训练，隔离CPU-only Torch FP64/intra-inter1/Loader0；不改邻任务。无cgroup委派，采用已验证整树采样停止，不冒充内核限制；额外128GiB邻增长规划余量，disk/artifacts门保持。

F1核实原13.5nm p6/h10/同网格p4、252cells、173802/53084 FE storage、80DtN，完整A4=PH A6P相对差3.366065072840215e-15、非零内部/端口制造解p4/p6原残差1.2255722548154e-14/2.0935547822786585e-14。后续p4-only与同F1 Schur CSR hash严格一致，21824rows/8184464NNZ，无private audit CSR。F2准确参考8项/teacher384对全部<=1e-10，256/64/64按整问题/seed划分；global LU仅offline，destroy/退出清场后oracle/训练/候选。oracle ranks16/32/64/128最高validation表示比.51382457/native最佳残差比.33388418，有诊断正信号但非严格返回。

F3同basis/B0/归一化/FP64，线性小解码基线与一个2hidden64 residual MLP，103040参数、300epochs、validation选51，有载训练19.036174s/监督22.267641s，heldout不用于选型；冻结Torch/NumPy相对差5.71091e-17。F4三路线同clean source7216efa605bae155ee383fd716c0fae422448b52、16heldout，各从构造没有global p4 LU、仅有界cell/patch/bottom，无fallback或数值调参重跑。

| 阶段/方法 | 实际数字 | 结果与证据 |
|---|---|---|
| R-B0严格粗逆 | 原PH b6 A4=0.9986549671，port=0.4654717527；486.668s / 851476480B | 1/16仅zero，非零256步未达1e-10；shared-workstation；[逐RHS](task042_neural_coarse_inverse/outcomes/records/strict_rhs_metrics_v2.csv) |
| R-LIN严格粗逆 | 原PH b6 A4=0.9982615363，port=0.2394959774；1239.273s / 1032511488B | 1/16仅zero，非零256步未达1e-10；shared-workstation；[逐RHS](task042_neural_coarse_inverse/outcomes/records/strict_rhs_metrics_v2.csv) |
| R-NN严格粗逆 | 原PH b6 A4=0.9984559263，port=0.1799872838；1238.082s / 1006587904B | 1/16仅zero，非零256步未达1e-10；shared-workstation；[逐RHS](task042_neural_coarse_inverse/outcomes/records/strict_rhs_metrics_v2.csv) |

终态COARSE_INVERSE_NOT_QUALIFIED：没有F4合格路线，三独立进程合格计时与条件F5/p6最终物理解/全部RTA/A_volume/场/通道not_run，不能生成official结果。去全局因子已实现，但传统低内存、线性降维与NN都未提供严格逆，G-neural无正信号；共享load/cache/lifecycle条件下G-time/G-memory inconclusive，N=1/10/100合格摊销未定义。数值尝试含4次实现失败监督wall共8250.064s，最大同时整树RSS2359627776B，own swap0，未分配Task042 VRAM；不累加阶段峰。

未见持续PSI压力，固定邻身份/CPU时间保留；短phase缺实时可比指标，不能证明绝对零干扰。两个继承schema2文档枚举fail在精确起点复现；final focused/static见[测试](task042_neural_coarse_inverse/outcomes/test_summary.md)。完整source/hash/所有RHS/时间/内存见[summary](task042_neural_coarse_inverse/outcomes/summary.md)、[response_v2](task042_neural_coarse_inverse/response_v2.md)、[run index](task042_neural_coarse_inverse/outcomes/records/run_index_v2.json)。无5/2/0.7nm或无界扫描；仅推送本执行分支，停止等review，不合并master。


## 2026-09-28 Task042 V3：有界几何重叠对照，仍有全局停滞

起因是V2三路线全部15非零不合格。用户仅授权一个新有限批次，沿原13.5nm/p6h10对应p4/252cells/80DtN及1e-10合同，保留旧B0/负结果；继续Task042受控共享CPU，不进入F5。先复用9个旧state重算真实Schur/native/port，映射最大7.44e-15，未发现接口错误；KSP/operation/native/port不同分母及port绝对量澄清，未改loss。CPU证据纠正oracle33、F4-B045，旧“全部CPU0”概括不准确。

新几何PC借用真实Nédélec cell trace/MPC支撑形成重叠，252个192trace+80port局部原Schur块，canonical限制/次数平均延拓；因子构造前上界与实际均合规，无global p4 LU/hidden fallback/private audit CSR，普通默认不变。same256预算对3个consumed RHS逐步独立验算。

| 已消费诊断RHS / index | 旧B0原A4 | 新GEO原A4 | 新GEO port closure | 新GEO port绝对残差 | 末32步Schur降幅 | 严格返回 |
|---|---|---|---|---|---|---|
| physical_PH_b6 / 0 | 0.998654967105 | 0.891957825531 | 0.00773091335604 | 0.187210874612 | 5.70298292157e-06 | False |
| unseen_port_only / 10 | 0.954192801905 | 0.935861877336 | 0.725338952963 | 0.000935056697255 | 1.23982140442e-05 | False |
| unseen_mixed / 11 | 1.000780838 | 0.932010701839 | 0.677921290639 | 0.000951255917368 | 1.24422653291e-07 | False |

局部划分使部分native残差下降，但末周期global方向仍停滞、严格返回未通过，不能把port相对分母增长当绝对改善。按预登记停止teacher/表示扩展/训练；R-LIN固定Q/native范数下精确最优，不能默认同Q MLP胜出。新未消费集合freeze后已选但not_run，F5/official/shortwave/GPU均not_run。两新阶段wall2636.49526309s、同时整树峰1074900992B、swap0；shared-workstation，perfinconclusive，邻身份/CPU推进未能量化影响。整树16GiB/12GiB、MPI1/math1/own lock/独立cache/只清理本树，无cgroup委派不假称内核上限。

终态BOUNDED_STRUCTURAL_GLOBAL_STAGNATION，research-only，待review，无master merge；未扩大网络或扫描。依据真实全局停滞，下一步需review决定新的空间/接口响应方向，不能直接加epoch。[response_v3](task042_neural_coarse_inverse/response_v3.md)、[summary](task042_neural_coarse_inverse/outcomes/summary.md)、[逐步历史](task042_neural_coarse_inverse/outcomes/records/full_residual_history_v3.csv)、[Gate/资源](task042_neural_coarse_inverse/outcomes/records/run_index_v3.json)。


## 2026-09-29 Task042 V4：有界全局误差两层实测，严格粗逆仍未资格化

按同分支正式Review V1完成必要P0、16原train问题64步采样128真实x_star−x_m、两条同rank128的完整Schur编码及各三次唯一诊断。局部R-GEO-CELL80-v3、原13.5nm/p6h10对应p4、80完整DtN/A4/A6/MPC不改；旧Q只读取解基，旧native U/R与NN权重不带入。两层C+(I−CS)B(I−SC)通过真实S与四恒等式，实测2C/1B/1S，构造与在线没有global p4 factor/私有audit CSR/fallback。

| 路线 / 已消费RHS | 原A4相对残差 | 固定Schur/RHS | port绝对范数 | port operation-relative | 严格返回 |
| --- | --- | --- | --- | --- | --- |
| TWOLEVEL-OLDPOD-V4 / 0 | 0.99858818727 | 0.999092817197 | 0.0333030546374 | 0.0654894807753 | False |
| TWOLEVEL-OLDPOD-V4 / 10 | 0.949242609663 | 0.971634245187 | 0.000954707150083 | 0.480383202996 | False |
| TWOLEVEL-OLDPOD-V4 / 11 | 0.905073739084 | 0.97721673465 | 0.000949297617596 | 0.235770374702 | False |
| TWOLEVEL-ERROR-V4 / 0 | 0.999863649936 | 0.99961809965 | 0.0256415022841 | 0.0849928945237 | False |
| TWOLEVEL-ERROR-V4 / 10 | 0.937175812499 | 0.957474274981 | 0.000927512266936 | 0.334601298612 | False |
| TWOLEVEL-ERROR-V4 / 11 | 0.901084822725 | 0.963534624076 | 0.000946698188098 | 0.203706802155 | False |

两路线均strict0/3，native/固定Schur没有同时达到physical和mixed各0.1；BOUNDED_TWOLEVEL_NEGATIVE，P4未解锁，seed420620计划16项仍未消费；不进入F5/p6/短波/official结果。六阶段wall1534.00828393s、同时整树RSS峰1128828928B、own swap0；每次现场核实选CPU0/MPI1/math1，own lock/16GiB树监督、独立cache，只降低自身nice/I/O，无cgroup委派不冒充内核限制。未观察持续压力，邻阶段缺可比指标，无零影响或无争用加速声明，全部shared-workstation/performance inconclusive。

用户Task042受控共享授权仍有效；Review替代V3局部停滞禁止空间研究前提，旧负结果原文/raw不改。新teacher/NN/GPU not_run，神经贡献不归因。P0/P1 source8b792d78…、P2/P3 source5691d79…、文档HEAD不代替运行SHA；仅本分支推送等待review，不merge。[Response V4](task042_neural_coarse_inverse/response_v4.md)、[全局空间结果/费用](task042_neural_coarse_inverse/outcomes/two_level_global_error_v4.md)、[source/资源](task042_neural_coarse_inverse/outcomes/records/run_index_v4.json)。


## 2026-09-29 Task042 V5：冻结对象失效定位完成，未取得新的严格解

按Review V2在相同S、R-GEO-CELL80-v3 B、OLDPOD/ERROR rank128 Z/U/R上完成D0–D4，12/12共同states和3已消费准确参考离线资格核验，24同r作用/192原方程审核与每空间16个有效补空间探针。残差与解误差覆盖分开，两个空间都不覆盖大部分当前物理残差；部分固定组合未利用保留Br＋Z的Schur下降能力，但原A4/port未严格通过。完整TV最小奇异值4.771224799/3.034800156，没有near-null证据，真实全局奇异与唯一根因未确定。

终态FIXED_OPERATOR_LOCALIZATION_COMPLETE，仍NOT_QUALIFIED；原V1–V4负结果不改。新训练/空间/长KSP、fresh seed420620、F5/p6/短波/GPU/official均not_run；只提出一个保留局部搜索方向的有界组织对照建议，未实现。四正式run source5d82651af0f723c73487783deb43969f05d46ed3，wall1144.401529s、整树RSS峰1135407104B/own swap0，MPI1/BLAS1、逐次现场CPU0/0/0/13、自有16GiB树监督/独立cache，全部shared-workstation/performance inconclusive；无cgroup委派不冒充内核连续上限。邻任务只读观察，没发现持续压力，缺可比阶段耗时，不承诺零干扰。无global p4 factor/private audit CSR/fallback，不改原A4/A6/MPC/full80/1e-10。

[Response V5](task042_neural_coarse_inverse/response_v5.md)、[同向量结果](task042_neural_coarse_inverse/outcomes/failure_localization_v5.md)、[hash/source/完整费用](task042_neural_coarse_inverse/outcomes/records/run_index_v5.json)。仅原执行分支交付等待review，不merge。


## 2026-09-29 Task042 V6：旧p4路线关闭，材料阻塞下完成神经FE接口

Review V3正式转向由网络生成原Nédélec边／面矩、用原方程求当前场；期望避免全局分解，成本增加优化与正反向作用，收益尚unknown。旧小块／固定低秩／系数网络路线CLOSED_RESEARCH_NEGATIVE，V5 augmentation不实施，历史负结果保留。本批N0真实384-cell p3居中缺口网格，FE34050／独立trace18144／slave2082，air200／substrate48／block136／notch8，y/z变化；但Si0.7nm源／复n缺失，MATERIAL_0P7NM_BLOCKED。空气top20通道仅derived，底侧／总库存unknown。

N1局部FE矩／orientation／MPC插值差约1.8e-15；固定11696参数FP64 3×64网络生成18144 master trace，15/30求积差1.1695e-15，合成非Hermitian梯度FD最大9.7612e-9、chunk配对6.8049e-16。真实S/Sᴴ/native/port/恢复未构造，完整N1不通过，NEURAL-TRACE／FREE-FE-OPT／FE-LSQR、参考／enrichment、E/H／RTA／能量验算均not_run；没有物理解／神经增量或48h能力证据，不由梯度或参数量判成功。

一次[0,L]原配置与新居中坐标接口修复后成功，source2a2cb4af78ba869a26a1254b4b4b76c9ac158366；初次失败source64c128c3541887e22788343692cc4f7832a45696原证据保留，预算不重置。三正式run总wall26.136697164s、整树同时采样峰314408960B/own swap0，现场CPU0/0/12、MPI1/数学1、既有FE/ML独立cache、自有锁/16GiB树监督，无cgroup委派不称内核连续限额。用户Task042受控共享授权继续；两GPU持续负载，本任务GPU/VRAM0；无邻任务修改，未发现持续压力，影响与无争用性能inconclusive，成本shared-workstation。无真实目标／p4全局因子、private audit CSR、hidden inverse/fallback或准确目标解读取，无旧teacher／seed420620消费。23相关pytest＋两ML断言及局部静态／输入通过；Review V3 GitHub4表4math通过。

目标尺寸／材料／通道／精度／实际配额／完整步成本和所需步数unknown，最终0.7nm／48h NOT_QUALIFIED。唯一下一最小步骤是审核Si0.7nm原始材料源／版本／单位／符号／数值，本批不自动实施、不回旧p4、不启动最大模型、不merge。[Response V6](task042_neural_coarse_inverse/response_v6.md)、[完整结果](task042_neural_coarse_inverse/outcomes/neural_fe_single_solve_v6.md)、[source和资源](task042_neural_coarse_inverse/outcomes/records/run_index_v6.json)。


## 2026-09-29 Task042 V7：材料解除后的真实单次神经FE对照

Review V4按用户原表永久固化SI_OPTICAL_CONSTANTS_USER_20260929_V1于input/materials/si_optical_constants_v1.json，四行离线转换／历史／alias／未知拒绝回归通过；0.699999988原行明确alias至nominal0.7，不插值、不伪造数据库版本，实际n=0.999885140474+4.32477054e-6i、epsilon=n*n。V6 blocked档案原样，本轮MATERIAL_READY_USER_SUPPLIED。

原384cell/p3/h0.175、三维缺口、双Floquet/DtN真实库存top20+bottom20=40，FE34050/trace18144/内部13824/slave2082；physical2b532f91550316b16a304f3be9ae78605816b5a2aba556f548b5bd794f82e6de。真实S/Sᴴ/native/非零内部与port/恢复身份差<=8.491e-15，真实FD最大1.8213e-9，完整N1通过；复用V6材料独立矩，不重跑F0。

顺序NEURAL1611closure(wall)/FREE2000closure/LSQR1921步(action)，原Schur0.913263/0.797339/0.071603、native0.661163/2.179411/0.028728、port op0.003140/0.446120/0.656568，全失败。NN/非神经全场L2差0.06920/0.10551/0.10464、闭合0.07034/0.00734/0.00337，不合格；LSQR散射误差近1，loss下降不能代替场。三状态冻结后独立p3一次LU，释放再验算，参考Schur6.424e-12、native3.018e-12、独立native1.437e-12、R/T/A0.117645819/0.877047783/0.005306398、A_volume同、闭合2.906e-12。一次UFL后处理表达式修复仅重放验证，新增LU/solve0，失败费用保留。

8正式run wall8579.825040766s、最大同时树采样RSS1073967104B、own swap0/GPU0、全部后代清场；V6 carry101.861302031s＋全部辅助费计入10h。用户受控共享授权/现场选核/MPI1/math/Torch1/own lock/16GiB树监督及独立缓存继续，无cgroup委派不称内核连续限额，无邻环境/affinity/watchdog/锁变更；未见持续PSI，影响与性能inconclusive。N1source70f5f543…、三路线7c4037a2…、参考19adac7e…、验证1ff6f8ba…完整hash在run index，文档HEAD不冒充运行source。

NEURAL_OPTIMIZATION_NEGATIVE、神经增量NOT_DEMONSTRATED、最终0.7nm/48h NOT_QUALIFIED；p4 enrichment无合格候选不准入，旧p4路线关闭，seed420620/旧teacher/GPU/F5/p6/最大模型/四波长扫描not_run。唯一建议固定pilot目标解无关的对角变量尺度均衡LSQR对照，原loss/验算不变，未实施需review。32相关pytest、Ruff/format/compileall、Review V4 GitHub4表1math通过，无ABI安装/全仓清理/CI声明。[Response V7](task042_neural_coarse_inverse/response_v7.md)、[结果](task042_neural_coarse_inverse/outcomes/neural_fe_single_solve_v7.md)、[完整资源/source](task042_neural_coarse_inverse/outcomes/records/run_index_v7.json)。只原执行分支待review，不merge。


## 2026-09-29 Task042 V8：尺度负结果，等价批量化工程观测

本轮固定原0.7nm/384hex/p3/40port对象，只将列单位均衡以及同网络八单元同时计算，另修复异常保存边界，三项独立。C1七测试PASS；C2唯一D由原组装S列范数、setup无factor，1915步/S1999/Sᴴ1919最终Schur0.068283273738/native0.026675035784/scattered L2差0.998598490718，严格/研究均失败。C3三状态full trace/loss/grad/clone Adam/FD等价PASS，固定参数三pair中位降幅48.55%，35107584B缓存，不训练、不把成本收益写成解通过。初次C2额外未用3369888B moment包在新source最小收口，原真实RSS/数值保留，无完整重放。

11正式supervised wall791.658916180s/树峰816152576B/own swap0/无GPU；全aux/失败/V6+carry不重置，最终资源账linked。受控共享CPU/MPI1/mathTorch1/DataLoader0/自有锁/16-12GiB树监督/独立cache保持，无cgroup内核连续保证，邻任务不操作；无持续PSI压力，影响与无争用加速INCONCLUSIVE。旧p4仍关闭，最终0.7nm/48h、神经数值增量未资格化，target单步/步数/存储unknown。唯一下一建议：固定pilot上仅对已经冻结的误差方向做原S/恢复/端口分量审核，复用已有p3参考作离线核对，定位残差下降为何没有恢复散射；不训练、不建新PC、不扫描。 未实施，停止等review，不merge。[Response V8](task042_neural_coarse_inverse/response_v8.md)、[完整结果](task042_neural_coarse_inverse/outcomes/scaling_and_execution_v8.md)、[最终费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v8.json)。


## Task042 V9：固定误差定位完成，旧求解负结果保留

| 对象／阶段 | 本分支新增结果与边界 |
|---|---|
| 0.7nm/384hex/p3/40端口/MPI1 | Z0/NN7/FREE7/LSQR7/LSQR8/REF7共6状态；D0–D4完成，无新solve/train/LU/PC/loss |
| 误差与真实场 | Se=r-r_ref≤2.925e-12，齐次恢复≤3.082e-16；NN散射范数比0.457259/相关0.999809，LSQR7/8幅值约0.26%/0.37%，均未资格化 |
| 区域／原作用 | y分量和上下(0,0,s)主导，全域四区分布；LSQR8方向增益0.0683784、体/port抵消0.059273/0.000209768；根因未唯一确定 |
| source／共享费用 | a1dc3466294c30b6de292468d6dd1aa9b685b193；唯一stage234.760s、树峰0.939442GiB/swap0；首次checker失败保留，e21仅数组审核修复 |
| 资格／下一步 | FIXED_ERROR_DIAGNOSTIC_COMPLETE≠solver PASS；原V7/V8及旧p4负结果保留，最大0.7nm/48h仍NOT_QUALIFIED；只建议后续有界原V内部作用平衡检查，未实施 |

身份、40复通道、区域、方程分量与累计资源见[Task042 V9](task042_neural_coarse_inverse/outcomes/frozen_error_localization_v9.md)、[Response V9](task042_neural_coarse_inverse/response_v9.md)。受控共享CPU授权继续，无cgroup委派不冒称连续限额；未观测持续PSI压力，邻影响INCONCLUSIVE。原seed420620封存，不改变其他Task合同/记录，不merge。


## Task042 V10：自主线性头与端口多路径完成，仍未合格

固定0.7nm/384hex/p3/40端口，隐藏层给空间函数、原方程直接求线性输出系数；N0→A→B1→B0→C→D1/D2完成。A/B1/B0/C的Schur分别0.912888/0.797694/0.797324/0.798258，native0.687417/4.381516/10.964503/0.309567；场误差0.635–0.732远高于1e-4，原方程1e-6未过。C原Hhat闭合端口到6.509e-17，只改善端口和native放大；无P/P+故E/P未准入。B0原loss略好、B1场略好，没有合格已学习特征增量。D1参考辅助同空间场差约1e-3但仍超门限，D2固定误差curl/mass强抵消，唯一根因INCONCLUSIVE；参考诊断不回传训练。

12正式launch共650.093757705s，整树同时采样峰2.213718GiB/own swap0；B1继承NN7原7142.986s及必要FE/moment设置，历史carry10209.145962639828s不重置。共享CPU现场核11/13/0、MPI1/mathTorch1、自有锁/16-12GiB采样watchdog/原单个7h总截止；未观测持续PSI压力，缺可比邻速率，影响/正式加速INCONCLUSIVE。无cgroup委派不称连续kernel cap，邻任务不操作。D2序列化一次最小修复只审核保存向量，失败保留，未重做FE分项；B三见证后补时序偏差披露。

原task/review/response及全部负结果/材料/算子/普通default保留；无global p4 factor/完整S或CSR/正规方程/ILU/Riesz/fallback，无新隐藏训练/GPU/最大模型。最终25相关pytest和ML三见证通过，Review V7实际3表5公式；不声明CI。唯一下一建议是固定随机特征空间的非零已知系数制造RHS回收，进一步区分数值链稳定性与目标表示/弱响应；未自动实施。全部可执行路径耗尽后提前交付，不填满7h，不merge。[Response V10](task042_neural_coarse_inverse/response_v10.md)、[完整结果](task042_neural_coarse_inverse/outcomes/autonomous_neural_head_v10.md)、[费用](task042_neural_coarse_inverse/outcomes/records/resource_costs_v10.json)。


## Task042 V11：稳定头内部门限失败，真实隐藏更新未准入

Review V8取消“固定空间无P/P+就不准改变hidden”的旧限制，改为先用原action制造的已知解验证线性头，再做真实完整VarPro梯度和有界隐藏更新。本批固定0.7nm/384hex/p3、原Si canonical表、完整40端口及seed420906随机hidden；采用economic QR `P=ZR`，原S逐列作用于Z、gelsd/cond1e-12与Hhat40闭合，写回真实网络并审核。M1小系数制造残差1.23470e-14、已知z差5.53650e-13通过；M2约1.30e5系数的稳定头初始残差3.11751e-7，一次同分解修正后仍2.89518e-8＞1e-8。物理基线真实网络对薄预测残差差3.95983e-8＞1e-8，即使P/A都数值rank1560，S1/S2仍失败；数值满秩不称精确最优。

因此真实S3三方向FD0、S4试探0/接受0，不绕过Gate用Adam，不能把未测隐藏学习写成负证明。求解队列冻结后独立S5验证：原Schur/native0.797721738/0.309359507＞1e-6，散射E/curl差0.734256809/0.734361587＞1e-4，端口闭合2.051e-19及恢复6.104e-13虽通过却不能使全场合格。R/T/A_balance/A_volume0.0849663/0.7980459/0.1169878/0.00485487、能量闭合0.112133，全部仅未资格化诊断，无新official结果。M2修正与大系数敏感性相关但唯一根因INCONCLUSIVE，固定空间原残差平台也未突破。

MAIN clean source a2cba71533edafb4fa1c701eae503e7ab526eac4；唯一同分解修正与独立FE VERIFY source036e36ec637488b1baddd9b061c80c6f34cde254。三正式监督wall574.980116768s、最大同时采样树RSS4668329984B、own swap0；V6–V10有载carry11159.165418899036s不清零，正式wall累加下界11734.145535666961s。MPI1/mathTorch1/CPU0现场选核、自有锁/16-12GiB树监督、独立环境缓存、无GPU或邻任务操作；没有cgroup委派，性能/干扰INCONCLUSIVE shared-workstation。无global p4因子/完整S或CSR/ILU/Riesz/fallback，旧路线关闭；最终0.7nm/48h NOT_QUALIFIED，不扩大模型。Review V8真实GitHub5表5数学块；最终12 pure-array pytest、ML三断言与raw checker通过，结果发布显示另核。唯一建议下一review考虑对冻结M2作一次有界浮点来源归因，未实施。[Response V11](task042_neural_coarse_inverse/response_v11.md)、[完整负结果](task042_neural_coarse_inverse/outcomes/stable_head_varpro_v11.md)、[source/费用](task042_neural_coarse_inverse/outcomes/records/run_index_v11.json)。只推送本分支待review，不merge。

## Task042 V12：固定头真实损失的梯度 Gate 未过，有限函数值备选为负

Review V9 明确允许不依赖旧头驻点的普通隐藏偏导，旧 V11 M2／实际输出头 `1e-8` Gate 仍 FAIL。沿原0.7nm/384hex/p3/40复端口、canonical Si/q15/action/seed420906，T1复用旧P/A完成M2与物理RHS的三段残差向量分账；物理网络回写、`Pγ/Zc`、原作用对薄列组合差分别3.80478e-8/2.36230e-7/1.04273e-12，不能解释0.7977原残差平台。T2真实完整loss同点分辨率2.22045e-14、复数小测试通过；但三物理hidden方向在规定h最小1e-7时相对FD差0.06346/0.07599/0.17425，未达1e-5稳定区，故T3 L-BFGS未准入。F8次两方向函数值试探最小loss2.80461＞起点0.31818，0接受更新／0头提议。独立T4只验原V11修正物理状态，Schur/native0.797721738/0.309359507、散射E/curl0.734256809/0.734361587，仍无micro同离散资格、official R/T/A或最终48h资格。

两个受影响T1接线失败原证据保留，分别为纯QR子进程旧探针附带MPI遭沙箱socket拒绝、事件字段重名；两次最小修复后 clean `d9df7068ca3310a0499164251a57841dbdfbc7f5` 用于三个成功one-run。五次监督wall合计182.268s（成功109.503s）、最大同时树RSS2322427904B/own swap0、全部后代清场；V6–V12正式有载可核下界11916.413697s，历史辅助费未知。现场CPU0/MPI1/数学Torch1、自有锁/缓存与16/12GiB采样树监督、GPU0；无cgroup委派不冒称连续限额，邻任务未修改，共享影响/速度INCONCLUSIVE。独立raw checker一致性PASS只说明证据自洽，梯度及物理资格false；旧p4路线仍关闭，无global因子/完整S/CSR/hidden inverse。唯一下一建议是固定同头同三方向的JVP/VJP及原作用线性化配对，未实施。见[Response V12](task042_neural_coarse_inverse/response_v12.md)、[完整负结果](task042_neural_coarse_inverse/outcomes/actual_loss_block_descent_v12.md)、[逐run资源](task042_neural_coarse_inverse/outcomes/records/resource_costs_v12.json)。只推送本执行分支待review，不merge。


## Task042 V13：独立切向与有限隐藏／输出头补偿完成，物理资格仍失败

本批先直接计算隐藏参数变化如何改变全部有限元边／面积分量，再同步调整输出头以保持大系数抵消；代价是一套薄QR和一次三RHS最小二乘。相同0.7nm、384hex/p3、40复端口和canonical Si材料不变，原Maxwell/MPC/DtN与普通default不改，旧p4强逆继续关闭。新的向量切向Gate不追溯改变V11头1e-8或V12标量FD的历史FAIL。

| 阶段／与何种基线比较；measured/derived、无量纲 | 结果、负信号及决策 |
|---|---|
| A固定头三方向，独立逐层JVP与原VJP | 向量FD相对差约1e-10，真实dual运算差约1e-17；新TANGENT_VECTOR_VERIFIED，不是solver资格 |
| B同原点固定头响应 | 最佳线性gain1.3e-17至1.8e-16＜2.03e-11分辨率门，0试探／0接受，继续C |
| C真实联合hidden/head，从同起点独立运行 | 首次联合Taylor失败；一次有界预登记复核后2方向合格。5试探／1接受，hidden改变量3.26e-6，J从0.3181799855降至0.3181797580，相对下降7.149e-7＜后续1e-4门限，停止第二／第三步 |
| head-only twin，检验只有输出头是否解释收益 | loss282.766917，Schur/native23.780955/9.222344，明显恶化；同步补偿维持抵消，但无有用的神经场增量 |
| D冻结后独立3状态、旧REF7只作验证 | 接受点Schur/native0.797721453/0.309359396，散射E/curl0.734256339/0.734361116，能量误差0.112132933；严格原方程1e-6／场1e-4均FAIL，OBJECTIVE_ONLY_IMPROVEMENT |

实际候选source `33f7d613b1341fa585f0324ead6039bf28211fff`；A/B/首次C source `978a59efeae9891a848c5fac581ec32e4fc9a5b8`；一次末尾JSON writer错误最小修复后，已保存记录恢复和D source `7615baae2f0d75fbc47c05be392b35ef2878c431`。没有重做优化或将恢复source冒充候选source；失落的小实LS系数和失败逐作用计时unknown，失败S/SH44次source-derived分账。六正式wall243.725626s，同时采样树RSS最大2852761600B/own swap0/GPU0，全部清场；V6起可核有载下界12160.139323s，历史辅助unknown保留。每run现场CPU0、MPI1/数学Torch1、自有锁/独立cache/16-12GiB树监督，无cgroup连续内核保证。未见持续PSI压力，邻影响与无争用性能INCONCLUSIVE shared-workstation，未改邻任务。

所有R/T/A仅未资格化诊断，无official结果、无global p4因子/全局S/CSR/正规方程/hidden inverse/fallback；一次薄分解P/A rank1560/1560，新P/A构建0。最终25相关pytest与4个CPU ML手动小测试通过，无全仓pytest/MPI2/4/CI声明。最终0.7nm/48h仍NOT_QUALIFIED，p4新参考、最大模型、GPU/网络或rank扫描未运行；旧数据与历史保护。唯一下一建议是改变输出正向坐标避免病态R回写成巨大的相消系数，未实施需新review；此批收口不自动重复同配置诊断。见[Response V13](task042_neural_coarse_inverse/response_v13.md)、[完整结果](task042_neural_coarse_inverse/outcomes/tangent_scale_head_compensation_v13.md)、[raw与资源](task042_neural_coarse_inverse/outcomes/records/run_index_v13.json)。只推送执行分支待review，不merge。


## Task042 V20：固定p3不完全因子／端口对照收口

| 路线 | 周期 | 原rho起点 | 原rho最终 | 下降% | S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|---|---|
| N | 4 | 9.67833470962e-06 | 9.39226219695e-06 | 2.95580305139 | 1052 | 193.57554083 | FIXED_CYCLE_LIMIT |
| P0 | 4 | 9.67833470962e-06 | 9.6529428923e-06 | 0.262357296786 | 1056 | 281.796204941 | FIXED_PROGRESS_RULE_STOP |
| P40 | 4 | 9.67833470962e-06 | 9.63671604509e-06 | 0.430018859409 | 1056 | 330.972634754 | FIXED_PROGRESS_RULE_STOP |


S0/N/P0/P40/V已实际执行，完整0/5。natural native ILU0配置固定（level0/shiftNONE），K nnz3852576，GLOBAL_P3_INCOMPLETE_FACTOR_PRESENT；无global p4 factor、hidden训练/Q/image新建。P40约1.0043倍暖残差改善，低于T/C准入，迁移/零trace未运行。原Schur/native和逐通道功率仍失败，低loss/近参考场不替代资格。formal wall874.948403s、同时树峰934690816B/ownswap0/VRAM0；formal累计下界67488.474122s，历史aux unknown保留。成本shared-workstation，邻影响与加速INCONCLUSIVE。

正式source d41470d17d2babf29fabb0960886b0f60ae2aceb，38 focused passed；七dat与实际端到端验证。正式监督在原窗口内结束，总elapsed交付已超4h，延后reader测试因剩余0未启动；不刷新预算。没有新p4/最大模型/merge。见[Response V20](task042_neural_coarse_inverse/response_v20.md)、[结果](task042_neural_coarse_inverse/outcomes/fixed_p3_ilu0_port_v20.md)、[费用/截止](task042_neural_coarse_inverse/outcomes/records/resource_costs_v20.json)。唯一下一建议为申请一个固定几何ordering短对照，未自动实施。
