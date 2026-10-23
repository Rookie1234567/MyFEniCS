# Task43 执行回应：PARTIAL / CONTROLLED_NEGATIVE，送最终审阅

本轮已完成可复核的九次实际接受更新、一次真实局部h动作资格重试，以及第10轮饱和p候选的受控负结果。选择已经停止，最后接受状态冻结为R9。尚未完整证明用户明确要求的“相近精度且独立FE更少”；不会把规模变小或求解残差很小替代这个结论。任务书还要求比较同精度全过程成本，但不要求必须成本获胜；本轮同精度与必要冷启动成本比较尚未资格化。未请求合并master。

| 任务判断 | 实测结果 | 最终范围 |
|---|---|---|
| 表示空间与连接 | p3–6变阶；one-level h及已验mixed p3/4、p4/5组件、周期/悬挂恢复；R9/R10完整方程A6均≤1e−8 | level2/跨h转移未资格化，不宣称所有多层h/p联合组合通过 |
| 实际闭环 | 原θ=.5/同Y6_1/冻结噪声与单位新增FE分数，9次accepted updates；真实h1完成full612/场恢复/A6 | 后验holdout和两控制不反馈选择；非均匀网格迭代尚未实测 |
| R9最后接受状态 | 110472FE=35352trace+75120interior；对Y6_1的η3.995683423e−5、J4.065061945；top(0,0,s)=4.065061945e−6、bottom=2.148245071e−6均>1e−6，其余610功率及E/H/G/四复幅地板通过 | 最终空间精度FAIL；独立holdout另判 |
| R10未接受诊断 | 全180格p6是原规则输出，非预设p扫描。118800FE；η3.154393353e−5、J2.837172688；仅top(0,0,s)=2.837172688e−6超1e−6，另611功率过 | G改善8.412900702e−6<冻结ε9.088158797e−6而未接受，与自身仍一个功率通道未达是两个判断；无transition10 |
| h10未继续求解 | 独立内部292260行已>实际对照237600FE，合法总FE只会更大 | goal-DoF infeasible是推导；未score剪枝、未数值失败，actual trace/FE保持null |
| 真实h1 | 原初始父状态、同冻结plan；600p3叶/47235FE；A6=8.745351252e−10，η=.245641161/J300895.081 | 真正完成一次h action，空间精度仍未合格；不回写历史transition1 |
| 独立后验九组比较 | 六场联合q8/q10、9个有方向场对均由root从原数组独立重算；Y5_1→R9/R10的J为4.0144/2.7865，Y3→R9/R10为1.7695/0.12645，Y3_2→R9/R10为182.556/183.784；Y6_1→Y5_1通过(J=.05917)，→Y3失败(J=2.7107)，→Y3_2失败(J=186.621) | 以Y3为reference的Y3→R10单对有限离散PASS，其余按表FAIL；两控制分布并列。新共同q8/q10不覆盖选择原积分规则，也不证明参考自身q/R/连续精度；[compact及独审hash](outcomes/records/post_selection_existing_fields_validation_v1.json) |

模型尺寸为50×50×140nm计算域、Si块17×20×120nm、λ13.5nm、θ89°/φ90°/s偏振；空气n=1，Si光栅及基底n=0.999002304859+0.00182649365i，ε=n²=0.9980022690345409+0.0036493427323206554i。E采用单位入射场尺度，H使用原物理单位定义；R/T/A_volume和逐级功率均为入射功率比，R00_s、R00_p及R00_total分开报告。具体全量数据、rows/NNZ、阶段wall/峰、source/ABI见统一模型机器表，正文不重复逐轮内部放行过程。

Y3/Y3_2两种6×10×6 p6控制都已从原场真实恢复并核约束：244644存储−7044Floquet从属=237600独立FE，周期实体公式一致。R9比它少53.505%，R10少50%；这些百分比只描述规模，不能直接称同精度压缩收益。Y5_1恢复332640FE；旧12800点E/H及完整612身份过关只证明原场被正确恢复，不能把异源码历史PDE升级为本次fresh reference资格。

## 实现与验证

本轮复用现有数值核心、runner和checker，未建立新的controller或参数扫描。新增后验接线只涉及三个既有恢复/比较文件和已有定向测试：显式停止选择角色、冻结selection/拒绝record/完整asset hash、实际独立Floquet行计数、联合六场q8/q10和有方向的九对完整比较。默认选择阶段仍拒绝holdout/control；诊断使用新schema、selection_eligible=false，不能进入accepted reader。没有机械合入临时六文件G3求解草稿，也没有新增PDE。

后验数值/比较代码与最终focused/full pytest使用source HEAD`3da2fa6c96bb315c18c0bb3dcd80b34a8346b3e0`；本次新增的三份报告生成器不在该HEAD中，由统一模型表、cycle index和图provenance里的脚本SHA绑定，最终送审commit将绑定它们。所有历史PDE均绑定各自run里的source snapshot/ABI/input map，不能把最终代码HEAD追溯覆盖为所有数值尝试的源码SHA。最终报告及文档通过review后提交的精确HEAD、upstream/ahead-behind和工作树状态由送审说明报告。任务基线`405e3aff42ac421a4c99315df1ed9b96941ecbe4`，执行分支始终`task43_hp_adaptivity`。

实际工作站入口`source scripts/activate_task40_phi90_pord64.sh`，Python `/home/fenics/Projects/Maxwell3D-Lab/task39extra_para_workstation_capacity/.venv/bin/python`，PETSc complex128/int64、MPI1、math threads1、CPU1。direct阶段SLEPc为NOT_LOADED_NOT_REQUIRED；旧参考来自各自历史源码，使用原hash/mesh/DoF/样本重现验证，不宣称历史ABI与本次完全同一运行。所有正式计算使用同一native ABI并分阶段资源门，一次一个heavy。

| 最终检查 | 实际命令/结果 | 范围 |
|---|---|---|
| 后验定向与保存场fixture | 最终12passed/11.66s；四文件完整Ruff与compile PASS | 保存36格真实full612/q8/q10；弱量正向raw1/反向.5及固定floor分开；缺行/重复key和功率/幅/aggregate篡改拒绝；无新PDE |
| 最终focused regressions | 冻结argv `python -m pytest -q` 加8个定向文件和1个CLI fixture，完整逐词命令见[最终测试compact](outcomes/records/final_test_attempts_v1.json)：40 passed、3 skipped，pytest报告21.25s；watchdog30.923094s、树RSS峰386,138,112B、task/global swap增量0、exit0清理 | source HEAD3da2fa6；916个Python/shell源和56输入hash由root审计通过；无新PDE |
| 实际全仓pytest | 完整命令`python -m pytest -q`实际尝试；1 collection skip、8 collection errors、test bodies 0 executed，pytest报告91.42s；watchdog104.270419s、树RSS峰406,917,120B、swap0、exit2清理 | 1个Task43忽略artifact同名模块冲突（涉及两个副本路径但只算1 error）+test179 SLEPc key1211220重复注册1 error+旧忽略tmp/task42extra缺模块6 errors；保留原trace，不改忽略规则/副本/环境；不是“8 tests失败”或“0 tests collected” |
| registry文档回归 | `python -m pytest -q src/test/test_183_development_model_registry_markdown.py`：5 passed，0.08s | 在更新模型总账后重跑；局部文档合同，无PDE；命令/stdout/exit/hash见送审包验证compact |
| 定向后验测试及报告脚本 | 后验保存场fixtures 12 passed/11.66s；原四个checker源/测试Ruff与compile通过；最终三份报告生成器Ruff format/check、compileall通过 | 不新增PDE；报告脚本在检查后重生machine inventory/图并把生成器SHA写入figure provenance |
| 文档/轻量hash | final test/postselection/attempt inventory/cycle/report-package JSON解析；三幅SVG XML解析；报告输入/生成器hash、Markdown表格和本地路径检查 | local-only，无CI声明；精确命令/日志hash见[送审包验证compact](outcomes/records/final_review_package_validation_v1.json)；遗留Task038缺路径负项另保留在历史记录 |

## 成本及保留的负证据

完整求解尝试16次、12条科学谱系、accepted9，组件fixture和后验恢复/采样另记。56份完整模型/组件watchdog wall小计63340.73598930752s；R8仅采样窗3109.3891972089186s，合计66450.12518651644s观察下界。最终focused/full suite watchdog合计135.193513449747s作为测试成本独立列出；相加为66585.31869996618s仍非全campaign/完整R8成本。未监控工作、其他测试及导入参考生成不在该和中。R8只有采样窗elapsed下界3109.389197s、窗内观测树峰6,844,891,136B/观测swap0，原supervisor summary缺失/shell143/sender未知；后续成功不补齐这个资源缺口。R9轻量monitor session143事件有原PDE持续存活证据，不能误称PDE停止或推断R8原因。

R5性能停止2230.240470s、原h1未知sender停止、R2前置残差失败、backend JSON末尾失败及仅元数据恢复、p4旧golden负项、原40文件source清单漏transfer及真实运行中补充均保留。h1辅助ABI JSON被误覆盖且旧字节无可恢复副本，是明确的辅助证据链缺口；原worker前置ABI和数值/资源独审仍有效，不伪造缺失字节。R5和R10的Av误差略恶化也保留，不声称所有物理量单调改善。

所有当前候选/控制还没有同时达到全部独立精度和参考自身q/R资格；源、缓存与生命周期也不同。因此不提供同精度加速比、冷启动成本胜出或通用backend速度结论。共享JIT不等于隔离冷启动，更不等于OS页缓存冷。因子对象估算、数组小计与同时进程树RSS峰分开。

## 未完成项和最小后续

| 未完成范围 | 已有具体证据/下一最小判断 |
|---|---|
| G1 level2/跨网格h转移 | 本轮one-level组件及真实h1不是level2资格；若另有后续任务，需独立多层/恢复fixture，不能从p成功外推 |
| G3全部独立资格 | 后验有限场比较不能替代参考自身PDE q/R、候选同空间q19/q32联合检查、R14完整836模式、一次终点校正、双侧壁trace及同精度必要冷成本；本轮没有精度PASS终场，不默认增加三次solve追PASS |
| G4自适应迭代 | 现never-materialized guard拒绝variable-p；外部request未传完整variable-p reduction实体/hanging映射；same-LU限制preonly+LU。均为源码观察，不是迭代Gate测量。后续先明确action/transfer/伴随/粗空间对象，固定一个适配方案做小direct-equivalent完整观测验证，不扫描PC或移植Task41规则y路线 |
| G5 0.7nm缩比pilot | 13.5nm独立精度及adaptive iterative前置未过，所以NOT_RUN；不把13.5nm材料或原模式清单混入0.7nm，不宣称全尺寸0.7nm/2TB/48h能力。完整尺寸的可信DoF/内存/solver可行性预测亦未资格化 |

最终结果为PARTIAL / CONTROLLED_NEGATIVE，可用于审阅规则有效范围与后续最小工作。选择性manifest按production core、runner/watchdog、checker、compact evidence/docs、research-only、do-not-merge依赖组列出；原大型artifact和未应用G3草稿不入Git。当前分支工作树报告将由root审核后再提交/推送同一执行分支，随后等待ChatGPT外部审阅；无merge approval，不合入master。
