# Task43 V11 正式补充任务书：完整q响应与一次真实局部h试验

日期：2026-10-26。唯一分支：`task43_hp_adaptivity`。实施起点：正式V10 review提交`3d9a6eb051a6599c37c4a26687b8b0cc3db8c76b`。长期数值基线仍为`405e3aff42ac421a4c99315df1ed9b96941ecbe4`。

## 0. 本轮要做完什么，以及新的明确授权

**本轮必须返回科学问题：现有小自由度解的剩余误差主要能否由积分解释；在整批h动作超自由度目标之后，一个事前指定的小h动作是否产生可辨识的输出收益。** 交付应包含实际端点、真实空间计数和完整比较，或确切阻断这些工作的失败实值，不能只交一份文件hash整理报告。

用户在接收V10后明确要求继续推进。上一轮将静态归档关闭后只安排等待，没有提供科学推进任务，安排不充分。本文件是新的正式补充任务书，**从本次提交起前瞻替代V10第9节中与本文件明确新增工作冲突的等待／运行禁令**。V10验收结论、旧review、合同和失败记录不改；本文件不把旧门追认通过。未来本轮执行只依本文件及其逐项映射的机器合同，不建立另一份自主放宽权限的计划。

明确授权一份任务内连续完成：

1. 实现现有研究入口的最小primary-only模式和固定单seed计划，完成相关定向验证。
2. 只读复核旧A2_q3保存primary的q响应；构造R9 seed8的实际h闭包／约束并核预算。
3. **新增一次A1_q attempt3正式求解**：180单元、118800独立FE、q19/q32/R13，保存完整primary，不做extra correction。
4. A1硬门、q扰动门和资源门通过后，**新增一次`R9_H8 attempt1`正式求解**：R9父空间仅请求global cell8作一层h，保留父p与必需闭包，实际独立FE严格小于237600。
5. 对R9、新h候选、冻结Y6_1在共同分区q8/q10点进行一次恢复／采样／比较，报告输出与自由度收益。

**前置门通过后主控在同一授权内继续，不需要在实现、测试、计划构造或A1结束后再等ChatGPT批准。** 主控必须独立检查对应原件和实值，不能只抄代理PASS。任何正式失败不自动重试；资源与证据门按第6–7节执行。

| 项目 | 本轮新增上限 |
|---|---:|
| A1_q attempt3 | 1个正式槽 |
| R9_H8 attempt1 | 1个正式槽，受A1结果及本身前置门约束 |
| 新A2、A1_R、A2_R、C或其他模型 | 0 |
| 定向支持验证 | 最多2个driver；第2个仅局部恢复 |
| 实际h空间准备与旧A2数组复核 | 1个支持driver |
| 三场共同分区后处理 | 1个支持driver |

旧V2以来正式账仍保留“5次已用／原6槽，末槽封存”。另新增本轮2槽，因而该账总包络从6变8，最多累计7/8；**旧第六槽仍不可用**。A1历史2次加本轮最多1次，累计最多3次；A2仍3次，不新增；R9_H8新槽最多1次。V1更早16次模型尝试另有历史总账，不因这个“7/8”消失。sanity1/1、D3 1/1均不恢复。

## 1. 科学依据与结论边界

### 1.1 为什么先这样做

| 已有事实 | 本轮选择及意义 |
|---|---|
| R9为110472 FE，R10为118800 FE；独立精度未过，主要瓶颈是零级s功率，G场差已经较小 | 同时量测完整输出误差J与G，不能只继续优化G后宣称功率精度改善 |
| 旧A1_q1的已存通道变化约8.18e-12，但缺完整primary全场和持久独立A6 | 新A1取得**修复后真实入口**的完整primary端点；不把旧部分输出直接提升资格 |
| 旧A2_q3保存primary对旧Y6的通道功率差约4.51e-11，q8/q10最差归一场差约6.04e-11 | 可从原已保存数组重算有限q响应，不再花一次576单元native求解 |
| h10冻结整批动作的内部FE下界292260已超过237600 | 这个结论没有否定小patch；只求一个已预定seed及其真实闭包来区分成本问题 |
| R13→R14、native与variable-p全面等价仍未完成 | 限制最终物理精度外推；不应阻止同q/R、同父候选数值路线下的一次空间动作响应实验 |

依据：[V1审阅第3–6节](review_report_v1.md)、[V2诊断计划](diagnostic_plan_v2.md)、[V3审阅](review_report_v3.md)、[A2保存primary原数组审计](outcomes/records/v3_root_post_pde_audit/A2_q3_primary_raw_audit.json)。这些是历史证据；本任务书没有在工作站重新读取其ignored原件，执行端需按第3节核验。

### 1.2 前瞻缩小问题，不重写旧负结果

额外同因子回代是重复使用同一LU因子检查解的敏感性。V3要求它严格改善残差，A2_q3未满足，该负结果仍成立。本轮要测的是**正常求解策略结束时的q响应与一个h动作的效果**，因此不再强制额外回代；正常correction策略和严格原方程残差门不变。extra记`NOT_REQUESTED_BY_V11_PROTOCOL`、次数0，不能记为旧extra门PASS，也不能择取历史extra场替代primary。

旧A1_q1确有pre-validation checkpoint，NPZ身份为`0e3553686a87afa639a09009ff8b244c530f5ccc7baacbcf055696ffa41f286d`；不能说完全没有系数。但它不含本次所需的完整primary q8/q10和持久独立A6／原向量闭环。这里明确选择**一次fresh A1**验证修复后的真实入口，而非同时再做一轮旧A1恢复；两条路线不并跑、不根据h结果临时切换。

本轮R9_H8是新的有限假设实验，**前瞻解除仅对此实验要求“双方R14和extra及native参考同核全面通过”的旧前置阻塞**。旧B合同不改，也不称旧B已解锁。R9与h候选必须保持同一实际数值核、物理和q/R；对Y6只报告到同一固定数值目标场的距离／输出响应，不称连续真误差或已证明纯空间误差。

本轮任何成功均不产生`transition10`，不改变accepted9/R9和R10拒绝，不授最终独立精度、同精度成本或迭代资格。

## 2. 固定物理、输入与参考角色

物理模型沿用[task.md第2节](task.md)：50×50×140 nm域，柱x=[16.5,33.5]、y=[15,35]、z=[0,120] nm；z域[-10,130] nm；13.5 nm、新phi90、grazing1°、s入射；材料、Floquet、端口方向及归一化不变。complex128/int64、MPI1、MUMPS direct、单线程。

| 角色 | 固定输入／用途 |
|---|---|
| A1旧基线 | 原R10 q15/q28/R13，180 cells全p6；原`round10_p_up`计划、系数、612通道和已有q8/q10恢复场，旧R10为reference、新A1为test |
| A1新解 | 同R10空间、q19体积分／q32 incident及port、R13；118800 FE；原正常correction一次、extra零次 |
| h父 | R9：180根，28个p5和152个p6，110472 FE，原q15/q28/R13、MUMPS、正常correction一次 |
| h请求 | 仅global cell8，原box=[16.5,5,-10]→[33.5,10,0] nm，父p5；一分八、maximum_level=1，所有子叶继承其root的p |
| h闭包 | 原周期、2:1、材料界面保护与实体p约束全部保留；记录forced roots，不能预写187 leaves或假定无闭包 |
| 固定数值目标 | Y6_1原q15/q28/R13保存场；从原资产清单绑定，不换成更有利的参考 |
| 敏感度来源 | Y6_2只保留旧校准身份；不得本轮重新择优选reference |
| 已揭盲核验与controls | Y5_1以及两份6×10×6控制不用于seed、闭包、阈值、候选排序或参考选择；本轮不新增这些场的比较工作 |

seed8来自已冻结R9→Y6_1的G²贡献`1.3895613869617563e-5`，不是按后验control挑选。固定几何审计SHA为`3fc78f7d728f357fc33b26decd0e6aaa5d3981197cdef4dc49f83633c169a524`，见V2计划。原R9 storage SHA为`7a71623b15afea662956ecd6af89b1d08701631174d1a048d5320e7a3217b893`；原R10计划SHA为`7e8305e0d6117ceeb37e88eb715d98ab5212505a2410161f0b38aff5c7ed1826`。工作站必须核实际字节及其完整既有来源清单；不以本段几个hash代替全部必要输入。

直接解不使用跨h初猜转移，本轮明确不执行该尚未资格化功能。不得加入p-down、第二seed、theta扫描、level2、局部各向异性新内核或新的大参考。

## 3. 一次授权内的实施顺序

### P0：只读确认与最小实现

先安全fetch并核canonical worktree `/home/fenics/Projects/NN-Lab-V2`、分支、upstream与已有改动。读取三层AGENTS及本文件，保护其他工作。只读确认第2节输入可用、旧A2 primary NPZ完整、源文件变化的数值意义及唯一新目录尚不存在；不要再核一遍V10的ELF归档问题。

冻结本轮的单一机器合同`outcomes/records/v11_scientific_restart_contract.json`，逐项映射本文件：目的、phase/attempt/root、已知输入身份、数值设置、比较方向、门槛、预算、测试selectors及允许的源码清单。它是执行绑定，不另建controller或自主授权层；主控须在首次动态验证前核对与本文一致。实现完成后提交源码／测试／合同到同一分支；每次launch记录再绑定实际执行SHA及文件字节，后续非代码文档提交不追认为运行HEAD。合同不含自身提交SHA的循环绑定；P2尚未生成的计划只先固定来源规则与唯一路径，产物SHA在P2终态及P4前置manifest中追加绑定，不回写已冻结合同。

### P1：定向支持验证，最多两次

第一次合并运行新primary-only、single-seed计划、共同点比较及真实main到首个mesh边界的相关fixture。必须验证：

- A1_q3和R9_H8的新phase/root/contract白名单，未知phase和已有非空root拒绝且旧文件集合与hash不变；未取得写入权时异常handler不碰旧目录。
- 实际main在mesh前创建WorkflowLedger，父PID为真实watchdog，phase绝对路径有效；sentinel终止确认没有真实构网、装配或求解。
- primary-only路径没有任何extra调用，正常correction计数与原向量／A6仍留证；调用extra即fixture失败。
- primary、输出和已算样本及时保存；模拟q10、输出或终态写入失败，保留已存原件、非零失败及资格关闭；不建立多文件事务已保证的假象。
- seed只能8，原box/p须匹配，叶继承p、闭包不省略；必须同时满足`0 < Delta_FE = FE_h - 110472`和`FE_h < 237600`，零／负增量及FE=237600均拒绝；不产生p候选或旧selection transition。
- 跨h比较保留不同discretization身份，强制同物理、同共同点和612通道；不能修改原“同空间q比较器”来掩盖空间变化。
- pending包只在专用合同路径、成功P4终态及完整绑定下可恢复；缺失／错配原向量、计划或terminal必须拒绝，不能把旧非official包普遍放行。用小型实值向量验证范数重算和残差门，不只断言scalar/status。
- 第6节唯一启动链实际保持direct watchdog父链、TracerPid绑定和终态清理；同时验证本次所用ABI及CPU1，不能只检查命令文本。

历史D3的20项身份helper不再全套重复。只因本轮改变的路径运行所需节点；不跑全仓pytest、collect-only、MPI2/4、完整p6 FFCx witness或独立导入probe。若第1次有已定位的fixture／接线问题，允许第2次仅补相关节点，保留失败及两次字节身份；第2次后仍有阻塞则停止本轮动态阶段。普通静态lint、路径与文档错误可直接局部修复，不为此另等review。

### P2：实际空间准备＋旧A2有限复核，一次支持driver

使用现有builder实际构R9_H8计划、mesh和约束authority，不装PDE矩阵、不factor、不solve。记录requested/forced roots、leaves、p直方图、independent trace/interior/FE、Floquet从属、carrier、预计凝聚行及612端口行；验证空间合法、`0 < Delta_FE = FE_h - 110472`及`FE_h < 237600`。若失败，不改seed、p或保护闭包，**不启动A1来凑运行次数**。

同一准备workflow只读旧A2_q3的原primary RHS/solution/residual、612原模态、Av和q8/q10数组，与原Y6对照重算已存数据的q差；不新施加算子、采样、积分或求解。重算保存残差范数是算术复核，不能称新的独立A6。保留`historical_endpoint=INCOMPLETE_NOT_QUALIFIED`、extra失败和LIMITED清理；只形成`saved_primary_q_response`的有限结论。原件不可读／身份冲突／q差超过第7节门，则停止受影响科学链，不补造或重跑A2。

并确认R9父与新h候选使用同一数值核和正常correction：逐源变化若只是observer、留证、容器运输，列明依据；若发现影响矩阵、约束、RHS、恢复或物理输出的未资格化改变，不把旧R9当同核基线，停止h路线。不得偷偷加一次fresh baseline。

### P3：A1_q attempt3，一次正式槽

前两阶段全部通过，由主控按第7节放行。完成第2节固定A1模型，保留原正常一次correction；额外correction不执行。原子保存primary原向量／系数、独立A6、full-active与condensed残差、normal计数、612通道、R/T/Av及q8/q10，完成同空间旧R10→新primary比较和完整终态。

所有硬门、q扰动、输入/源码、CPU/资源与清理门通过，主控读取实值并核对后**直接继续P4**，不为阶段通过再等review。q门超限则已有可判别的积分负结果，停止P4；任一工程／资源／证据失败也停止P4，不重试A1，不把部分包升级完整端点。

### P4：R9_H8 attempt1，一次正式槽

使用P2冻结的唯一计划，同R9 q15/q28/R13、正常一次correction，fresh direct MUMPS；extra不执行。实际mesh、authority和FE必须与P2一致，否则在装配前拒绝。

完成恢复系数、原向量、独立A6、full-active/condensed、normal计数、完整612与Av，保存可独立恢复的候选。为避免重复后处理，**本阶段允许体q8/q10统一留给P5**，终态标`SOLVED_PENDING_POSTPROCESS`；solver成功不自动生成最终诊断资格、accepted transition或选择许可。

P4数值硬门、资源及清理失败则停止P5；不能为了一个更好结果再解。P4成功后直接进入P5。

### P5：共同分区比较，一次支持driver

从冻结R9、Y6_1及本轮h候选系数恢复场，在三者实际分区断点并集构造共同q8/q10体Gauss点，三场每阶仅采样一次。q10为主，q8核稳健性。核域体积350000 nm³、点/权/owner、材料分区、总/散射背景及H/curl关系。不得直接拼旧数组，除非坐标、权重、owner和背景逐项一致；原则上本次三场统一重新采样。

复用现有candidate/reference restore、physical_field_comparison和G积分，不新写求解器。保留三者不同离散与solver-route身份。统一以Y6_1为reference，重新计算R9与h的J、eta及各分量；不拼接旧R9的J与新采样的h结果。

旧`_restore_candidate`只接受旧schema及`official_result=true`，不能为了复用它而给P4冒填旧official。抽取其精确恢复主体，或在新合同模式中专门接受绑定成功P4终态的`SOLVED_PENDING_POSTPROCESS`：核零退出、硬门、源码／合同／计划／原向量绑定，仍不授旧official、selection或continuation。旧任意未合格包的拒绝条件不变。旧`_validate_recorded_quadrature_and_cutoff`假设首项candidate、其余historical reference，不能盲传三场；保留R9/Y6_1核查，另核h包的q15/q28/R13、cutoff及共同物理。

每阶样本保存即落盘，q10或写入失败保留已完成q8及P4原包。最终另写联合诊断记录，绑定P4与P5各自的watchdog终态、退出码、源码／合同／输入／输出SHA；不回写旧终态为“早已完整”。失败无重采样或另一次driver自动权；完整采样失败只说明本次诊断未完成。

## 4. 最小代码范围与必须保留的旧行为

现有CLI不能只换root就运行。需要的参数是本轮实现范围，不是假称它们现在已经存在。

| 既有文件 | 允许的最小改动 |
|---|---|
| `benchmarks/task43_hp_adaptivity/h100_anchor.py` | 一个显式`--primary-diagnostic-contract`和`--primary-diagnostic-phase`策略；支持仅A1_q3/R9_H8。复用mesh前ledger、primary包、raw/A6和失败保护；A1完整采样，h允许P5后处理。默认及旧V2/V3验证器保留 |
| `round1_candidates.py` | 同一新合同下只允许R9 seed8的`h_refine`计划；复用`_load_accepted_parent_state`、`_build_next_round_plan`、`_audit_plan`，保留材料/周期/2:1/p闭包。旧Dörfler入口不变 |
| `compare_round1_candidate.py` | 显式`--diagnostic-contract`模式，固定三场、共同q8/q10、不同空间身份及唯一输出root；仅该模式可按合同覆盖旧默认输出目录。复用恢复／采样／物理比较，不调用旧接受transition writer |
| `candidate_checkpoints.py`、`reference_restore.py`、`compare_initial_to_references.py` | 仅上述模式必需的原子保存／记录绑定／恢复调用层小改动；不改物理公式、旧reader或旧reference角色门 |
| 相关现有测试或一个小型V11测试文件 | 第3节明确风险的定向fixture；禁止镜像实现堆PASS数量 |
| 文档／记录／ignored薄启动脚本 | 单一合同、实际命令与源码快照、response_v11及结果表；脚本只调现有模块，不复制数值算法或编排平台 |

本轮不改`a2_native_p6_diagnostic.py`、`src/runners/p6_condensed_direct.py`、共享activation、native capacity profile、watchdog默认策略及数值核心。若必须改变弱式、约束或求解数学才能实现这些有限功能，停止受影响路线并给出确切原因，不私自扩大范围。

特别注意：旧A1/V3强制`--same-lu-tightening`且旧endpoint把extra列为门，不能修改旧门以让新模式通过；新模式使用自己的用途字段。原A1正常correction与本轮primary原向量必须保留。普通candidate的旧A6门为1e-6，本轮新模式明确使用1e-8，不能沿用较松默认。

旧`_recompute_candidate_hard_gates`仅对JSON里已有范数重新做除法，不能用其成功冒充原向量独立复核。新模式必须读取已保存RHS、solution、显式residual和独立A6向量重新算范数，并检查向量、约束、计数与端点身份；这仍是保存数据的独立算术核验，不声称重装算子验证。缺少必需数组时不能用旧scalar/status替代。

## 5. 唯一目录、命令范围与前瞻冻结

唯一新artifact前缀：`/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task43/v11_science/`。已有目录不覆盖，未授权的替代编号/目录不创建；新顶层准备目录可由P0创建，各运行根在首次dispatch时排他创建，非空拒绝。所有大数据留ignored。

| 动作 | 唯一根（相对新前缀） | 唯一启动命令（前缀下`launch/`中的薄shell） |
|---|---|---|
| 支持主验证 | `support/focused_attempt1/` | `bash …/v11_science/launch/focused_attempt1.sh` |
| 必要局部恢复 | `support/focused_recovery1/` | `bash …/v11_science/launch/focused_recovery1.sh` |
| P2实际计划与旧A2数组 | `support/space_and_saved_primary_attempt1/` | `bash …/v11_science/launch/space_and_saved_primary_attempt1.sh` |
| P3正式A1 | `formal/A1_q_attempt3/` | `bash …/v11_science/launch/A1_q_attempt3.sh` |
| P4正式h | `formal/R9_H8_attempt1/` | `bash …/v11_science/launch/R9_H8_attempt1.sh` |
| P5三场比较 | `support/union_comparison_attempt1/` | `bash …/v11_science/launch/union_comparison_attempt1.sh` |

上表`…`唯一展开为canonical路径，不是任意目录。每个正式根内固定`run/`、`watchdog/`、`strace/`及必要source/input snapshot；P5不能把新比较写回原R9/Y6或历史A2目录。薄脚本实际完整argv、环境和hash在dispatch前写入该次独立launch/input-manifest，绑定已经冻结的合同SHA；不把后生成的计划或命令hash回填合同。普通静态编辑／阅读不消耗运行槽，**调用对应唯一launch shell即消耗该槽，包括watchdog前shell失败、ABI或mesh前失败**；不得以未到watchdog、失败改名或删除目录抵扣。watchdog未开始时whole为未取得，记录已有实际计时，不能补造0秒。

P3 worker的固定命令形状如下，先实现并通过P1才可使用：

```text
python -u -m benchmarks.task43_hp_adaptivity.h100_anchor
  --case round1_candidate_mpi1
  --run-root <v11_science/formal/A1_q_attempt3/run>
  --candidate-plan <canonical>/benchmarks/artifacts/task43/round10_p_only_authority_attempt1/plan_output/plans/round10_p_up.json
  --candidate-id round10_p_up
  --candidate-acceptance-contract <canonical>/docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json
  --candidate-parent-selection-record <canonical>/docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json
  --same-lu-solve-residual-correction --direct-factor-backend mumps
  --primary-diagnostic-contract <canonical>/docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json
  --primary-diagnostic-phase A1_q3
```

P4使用同一模块和case，将run-root/plan/candidate-id替换为P2唯一产物及`v11_r9_h8`，phase固定`R9_H8`，仍指原R9 parent，不加extra。P2只调用现有`round1_candidates`新增的`--primary-diagnostic-contract`模式。P5只调用现有`compare_round1_candidate`，固定`--candidate-run-root`为P4的`run/`、`--accepted-parent-selection-record`为上述R9记录、`--attempt-id v11_r9_h8_union_attempt1`、`--diagnostic-contract`为本轮合同；合同将输出唯一绑定为`support/union_comparison_attempt1/comparison/`，不再落入旧默认目录，也不接受任意输出覆盖。该新模式与旧post-selection模式互斥。不得执行A2 runner或用旧V3 contract伪装新attempt。

源码／测试和合同冻结后主控核一次；之后文档不改变所测字节。若P1局部恢复改变受测源码，先提交并在恢复launch记录冻结新字节及受影响selectors，再重跑相关节点，规则合同不变，旧快照和失败保留；不声称整套最终同字节通过。准备与正式启动之间只需复核本轮输入及改动依赖，不再从头重做V6–V10的ELF/204事件/归档审计。

## 6. 环境、父链、CPU与资源预算

### 6.1 同一实际worker的前置门

继续使用`source scripts/activate_task40_phi90_pord64.sh`；只在本次worker shell使用`HWLOC_COMPONENTS=-x86`和`OMPI_MCA_pml=ob1`，不改共享activation或系统配置。OMP/OpenBLAS/MKL/BLIS/NumExpr/VECLIB六项线程变量均1；CPU1、MPI1，检查actual affinity、COMM_WORLD size、complex128/int64和MUMPS实际可用性。不能借D3旧观察替本次实际worker门。

旧D3普通strace包装会改变A1直接父PID，不能照抄。唯一允许的新追踪组织为`exec taskset -c 1 strace -D -ff -ttt -k -e trace=sched_setaffinity,sched_getaffinity … python -u …`，`-D`采用grandchild模式以保留tracee为watchdog直接孩子；不使用pgroup/session模式，不扫描其他启动方式。这个组织必须先在P1真实main sentinel中实测。

P1核watchdog的subreaper确实覆盖tracer，绑定worker PID/PPID/start_ticks与`/proc/<pid>/status`的TracerPid、tracer start_ticks；正常结束和受控故障后均无相关存活后代。每个正式worker在mesh前、装配／factor／恢复等关键阶段核实际父链、CPU1和tracer身份；tracer提前消失／换PID或trace不完整为监控失败，禁止后续阶段。

保留全部affinity事件及采样；任何成功setter设到非`[1]`、活worker的非CPU1采样或未解释setter均否决，主控发现即按已核PID请求受控停止。不把Z态缺测与非CPU1观察混同。正常SIGCHLD等信号分类记录，不要求PDE“零signal”；非预期fatal、异常杀进程和追踪中断须失败处理。trace从taskset之后开始这一边界如实记录；本轮不据此宣称CPU1之外的系统已全面审计。

### 6.2 实际可执行的资源收紧

watchdog shell使用现成环境：`PHYSICAL_NATIVE_CAPACITY=task43_hp_adaptivity_resource_v1`。正式两次另设`PHYSICAL_NATIVE_NODE_CAP_BYTES=34359738368`（32 GiB）；支持driver设`8589934592`（8 GiB）。现有`subreaper_watchdog.memory_envelope`已按node cap收紧，无需新增虚构的`--rss`参数或修改profile。

实际cap取node cap与原动态包络的更严者；原reserve=`max(64 GiB,15%有效总内存)`、available/planning门继续有效。所有运行task-tree VmSwap必须0；global pswpin/out另列，不把其他任务的全局swap归因本任务。一次只运行一个本任务workflow，不干扰相邻任务。

| 类型 | 最多次数 | 工作停止阈值 | 含清理whole-watchdog上限 | RSS上限 |
|---|---:|---:|---:|---:|
| P1主验证＋必要局部恢复 | 2 | 每次270 s | 每次300 s；合计600 s | 8 GiB与动态门更严者 |
| P2实际空间准备＋旧A2数组 | 1 | 840 s | 900 s | 同上 |
| P3 A1_q3 | 1 | 6900 s | 7200 s | 32 GiB与动态门更严者 |
| P4 R9_H8 | 1 | 6900 s | 7200 s | 同上 |
| P5共同分区后处理 | 1 | 1740 s | 1800 s | 8 GiB与动态门更严者 |

正式whole新增最多14400秒；支持whole新增最多3300秒，合计已测运行上限17700秒（4小时55分），不是承诺总人工工作wall。各次失败与preflight都计费，内层阶段时间不再叠加。剩余秒数不换额外次数。未计时编辑／静态阅读另列，不补造计时。

预算依据：旧A1_q1在4882.447秒／9.71 GB到达数值后observer故障；新A1不做extra，32 GiB保留明显余量但不承诺一定完成。旧R10实际authority约207秒、workflow约222秒，P2允许真实空间工作，不套60秒静态限时。历史六场共同比较约1656秒，P5仅三场但仍给1800秒whole；追踪开销计入本次，不作旧新耗时加速比较。

阈值到达即停止工作，剩余时间只用于已有TERM/KILL/reap和保存终态，不能继续求解或临时延长。完整进程树及tracer未清除、退出码不明或whole超限均不能通过；只处理已绑定本任务PID，不杀邻近任务。watchdog无`--cache-path`时不得把空stamp称为实际JIT/global cache已核，不为本轮另清理或重建共享缓存。

## 7. 放行门、端点与比较阈值

### 7.1 两个正式端点共同硬门

- 独立完整active原方程A6≤1e-8，full-active显式相对残差≤1e-8，condensed残差≤1e-9；不能只用KSP返回值。
- normal correction固定一次，保留前后原向量、同RHS、实际计数、正的收敛原因、有限且严格下降的常规残差；extra次数必须0。
- `abs(1-R-T-A_volume)≤1e-5`，Av来自材料体积分，不用1-R-T回填。A1与h各自记录operator、incident/port和Av实际规则；不能把旧A2 automatic改为q19。
- 全部612模态、四组复幅、R/T/Av/R00、空间和恢复身份完整、有限；P4体采样可等待P5，但不能在此前宣称完整比较。
- source/input前后身份不漂移；实际FE／rows按定义记录，h同时满足`0 < FE_h - 110472`和`FE_h < 237600`；资源、父链、affinity、终态及清理均合格。

每次已有输出立即保存；原向量／独立A6／计数和系数是primary包核心。发生任何异常必须保留可读原件和原异常，当前用途资格关闭。单文件atomic replace不是多文件事务；主控联合检查terminal、退出码、包绑定和所有必要字段，不凭一个true放行。

### 7.2 A1 q响应门，以及旧A2保存数据门

| 指标 | q15/q28→q19/q32允许变化 |
|---|---:|
| R、T、Av、R00_total绝对差 | 每项≤1e-6 |
| R00_s/p及每个通道功率绝对差 | 每项≤1e-7 |
| 四组复幅、总／散射E/H、G的固定地板归一差 | 每项≤1e-5 |

沿用旧比较合同的单位、floor和无相位拟合规则；q10主比较，q8也须完整且通过适用的同一组门，任一阶超限不能以另一阶通过替代。A1只有完整端点和这些q门通过才继续h。旧A2只在已保存数据范围通过该比较，不授旧正式端点资格；若原数组读不到或差超限，记录限制并停止受影响链，不重跑A2。

通过只说明事前指定的q15/q28→q19/q32加严引起的变化低于门槛，不提供积分绝对误差的可靠上界；本次体积分与incident/port积分同时变化，不能分别确定二者贡献。被测状态是R10/A1和旧Y6/A2；没有新做R9 mixed-p或h的q19解，不能外推为这两个空间的积分误差已排除。这一限制不阻止同q/R固定h动作响应实验。

### 7.3 h结果如何判别，不制造第10次接受

先通过第7.1节及P5完整数据门，再对**同一共同分区重新计算**的R9与h比较：`Delta_J=J_R9-J_h`、`Delta_G=eta_R9-eta_h`、实际`Delta_FE=FE_h-110472 > 0`、每个通道带符号变化及收益／Delta_FE。零／负增量为计数或空间错误，不能进入收益除法。

固定敏感度尺度沿用既有数值：`epsilon_J=0.12716416232413652`、`epsilon_G=9.088158796603444e-6`。它们是已测敏感度策略，不是严格概率置信区间；新共同采样不得在看到h收益后重估更小门槛。

| 条件 | 本轮诊断标签与含义 |
|---|---|
| `Delta_J > epsilon_J` 且 `eta_h <= eta_R9 + epsilon_G` | `POSITIVE_FIXED_REFERENCE_OUTPUT_RESPONSE`：固定目标场下的输出响应积极；仍不等于独立精度通过 |
| `J_h > J_R9 + epsilon_J` 或 `eta_h > eta_R9 + epsilon_G` | `NEGATIVE_OR_TRADEOFF_RESPONSE`：明确列哪项恶化、是否有另一项改善；不择优删字段 |
| 其余完整结果 | `NO_CLEAR_OUTPUT_GAIN_AT_FROZEN_SCALE`：输出收益未超过冻结尺度；如G单独改善仍报告，不笼统称所有hp无效 |
| 端点、采样或资源门未过 | `ACTION_ENDPOINT_NOT_QUALIFIED`：工程／数值／资源未完成，不当作h方法收益负结论 |

同时原样列旧双门`Delta_G>epsilon_G`、`J_h<=J_R9+epsilon_J`是否成立；无论结果均不写selection transition，不接续已结束的accepted9链。也不要求单个小patch必须最终J≤1才有实验价值。

seed8原G²贡献仅约占R9总G²的1.24%；若仅消除该局部贡献且其他不变，eta下降量级约2.49e-7，低于旧epsilon_G。这是根据已有数值的量级说明，不是对全局PDE收益的预测，说明需同时看实际输出变化。若q8/q10导致上述诊断分类不同，则标`SAMPLING_SENSITIVITY_UNRESOLVED`，不额外重采样或放宽门。

## 8. 必须交付的科学结果及停止后的处置

用一份`response_v11.md`和一个`outcomes/records/v11_scientific_results_v1.json`收口，附必要轻量证据，更新summary、manifest、模型总账和进展。保持三类结果分开：旧A2保存数据复算、新A1 fresh PDE、新h fresh PDE及后处理。只列hash不构成完成。

至少交付以下表：

1. 各阶段实做／未做、次数、实际source、输入、worker/launcher退出、whole与资源、清理；所有失败保留，费用互斥。
2. A1旧→新q的完整分量摘要、最差通道实值／限值、独立A6／显式／凝聚残差、normal及extra计数；旧A2只按保存数据范围另列。
3. h的requested与forced roots、leaf/p、trace/interior/FE、carrier、矩阵rows/NNZ；与110472父和237600目标分别比较，不能用trace或凝聚rows冒充FE。
4. 同一Y6目标下R9和h的J、eta、R/T/Av、top/bottom(0,0,s)带符号偏差、完整612最差项、四复幅、总／散射E/H/G、Delta_FE与收益；q8/q10分别列。
5. 根据第7.3节作出具体科学判断：积分是否可能解释现有差；这个固定小h动作有没有可辨识收益；哪些疑问仍归参考／R截断／标记目标，哪些实际未测。不能只报PASS/FAIL。

正常情况下完成整组后再请求正式审阅。若触发硬停止，交付已完成的实值及确切阻塞，不自行追加槽位，也不重新包装成一轮V10式归档任务。公开报告区分亲读原件、Git摘录、旧证据复用、推断与UNKNOWN。

本轮仍不授权A1_R、A2_R、C新大参考、fresh baseline、成本campaign、迭代、0.7 nm、NN/FTT或合并。源码／文档仅提交本执行分支；没有production merge approval。五项能力在正式新结果审阅前继续空间/选择PARTIAL、精度NOT_PASSED、成本NOT_ESTABLISHED、迭代NOT_RUN/NOT_QUALIFIED；可以新增本轮有限观察，不提前改总状态。

## 9. 方法与启动组织的参考依据

- Ingelström、Bondeson，*Goal-oriented error estimation and h-adaptivity for Maxwell’s equations*，CMAME 192 (2003)，2597–2616，[DOI](https://doi.org/10.1016/S0045-7825(03)00295-0)。其目标量误差研究支持区分场范数改善与特定电磁输出改善；不能把其中的误差估计保证直接套到本仓库。本轮不开发新DWR或求解伴随问题。
- Carson、Higham，*Accelerating the Solution of Linear Systems by Iterative Refinement in Three Precisions*，SISC 40 (2018)，A817–A847，[作者公开稿](https://eprints.maths.manchester.ac.uk/2629/1/cahi18.pdf)。迭代改进的可达误差与精度、条件数等有关；这不证明旧A2非严格下降必然是舍入噪声。本轮只是前瞻取消不属于当前问题的extra实验，保留独立残差与物理门。
- [strace官方手册源码](https://github.com/strace/strace/blob/master/doc/strace.1.in)对`-D/--daemonize=grandchild`说明保持tracee直接父关系。此为选择启动组织的依据，不替代P1在实际版本上的父链、tracer与清理验证；不安装或升级工具。

本文件由ChatGPT制定，只提交任务授权及导航；没有执行本轮实现、支持driver、采样或PDE。执行方按上述明确范围实施，不把任务书提交视为模型已经完成。
