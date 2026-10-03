# Response V15：保存数组共同下降诊断完成，维持暂停

按[Review V14](review_report_v14.md)完成A–D。PDE8无标签候选在两态都使G场误差能量略降，但对偶残差能量分别只降0.0217406%/0.0411647%，未达到同时下降0.1%，且预测native增加。ALL16终态的约0.356286%共同改善依赖参考方向；不是无标签求解或真实神经增益。因此维持 `FEINN_MAIN_SOLVER_ON_HOLD` / `NO_VERIFIED_NN_INCREMENT`，不提出或执行新的非线性见证、训练、调权或完成器。

## 身份、实施与数据权限

| 项目 | 完整身份 / 实际结果 |
| --- | --- |
| 精确分支 / review发布 | `task42extra_feinn_5nm` / `229199194bb711ba03ee1294f9c0d884b83a53f9`；只做精确refspec fetch和ff-only，开始0/0、clean、无活跃本任务run、锁FREE |
| 冻结base | `fbac3d8777fcfd897d93b898cb9f460f79ddd6ff`，已核对祖先 |
| canonical / worktree | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` / `/home/fenics/Projects/NN-Lab-V2` |
| 实际新实现/数组分析source | `99f2968be8d715a6f2e6985f5b032c53ca505950`，干净实现commit后唯一正式分析；后续文档HEAD不是该source |
| 原C1生成source / 数组SHA256 | `bc4c2026f8a9510c90424d24f1808a288413bba4` / `22c5200d6744cb3e0e4e360dae597fcb3f26b96bf80d478b2fff7d050ccd2263` |
| 输入与所有hash | [run index](outcomes/records/run_index_v15.json)、[冻结设计](outcomes/records/common_descent_design_v15.json)、[候选权限](outcomes/records/candidate_permissions_v15.json)；只hash实际读取文件，不重验整个历史 |
| 实际阶段 | 来源拆分、固定参数球/两档rcond、无标签候选先hash、共同小问题上下界、原数组独立checker与交付；无新FE/网络/算子作用或训练 |

本轮不是新的场求解：只组合过去保存的参数、FE场与残差方向。F衡量相对当前G场误差能量，R衡量相对当前G对偶残差能量，均从1开始、越低越好。可行步给上界，小型凸组合/球乘子给可重算下界；不能凭优化停止判断“不存在共同方向”。PDE8的候选构造不读取e/Ge/gF或参考列，四候选及ledger成功fsync/hash后才读取参考评价。ALL16、场目标与共同目标点均标参考已暴露的local oracle，不更新真实网络。

## 核心结果及未知边界

| 保存态 / 方向 | 秩 | 共同F / R | 下界L / 上界U | 舍入余量 | 数值界与资格 |
| --- | ---: | --- | --- | ---: | --- |
| M3600 / PDE8 | 8 | 0.996151144653 / 0.999782594069 | 0.99978259407 / 0.999782594069 | 1.49942e-07 | 余量扣除后下界仍>0.999；有限排除信号；余量后界宽未达1e-8：UNKNOWN |
| M3600 / ALL16 | 16 | 0.999312132479 / 0.999312132478 | 0.999312132479 / 0.999312132479 | 1.48959e-07 | 余量扣除后下界仍>0.999；有限排除信号；余量后界宽未达1e-8：UNKNOWN |
| Mfinal / PDE8 | 8 | 0.997525889151 / 0.999588352612 | 0.999588352612 / 0.999588352612 | 6.66165e-09 | 余量扣除后下界仍>0.999；有限排除信号；界宽目标通过 |
| Mfinal / ALL16 | 16 | 0.996437139686 / 0.996437139687 | 0.996437139687 / 0.996437139687 | 7.11407e-09 | 存在≥0.1%共同下降（参考oracle）；界宽目标通过 |


固定半径0.008553653337049638/0.008560515209936437，rcond1e-10与1e-12的秩和目标相同；共264次lambda评估≤512。M3600的保守余量界宽约1.5e-7未达1e-8，单列UNKNOWN；扣余量下界仍在0.999之上，只作有限排除证据。Mfinal的界宽达到目标，ALL16共同点可行。原向量交叉项、零步/残差/场/共同四点及原f分母native详见[专题](outcomes/common_descent_v15.md)、[32行CSV](outcomes/records/common_descent_comparison_v15.csv)、[小系数/谱证据](outcomes/records/common_descent_results_v15.json)、[独立checker](outcomes/records/independent_checker_v15.json)和[Gate](outcomes/records/gate_decisions_v15.json)。

PDE8两态native预测0.885852183253→0.888333231652、0.846541904928→0.847524617952，均增加。固定无标签候选未同时通过0.1%两能量及native不增条件。两态不是独立样本；有限方向负结果不证明全网络不可表达。线性分析没有真正NN收益资格，oracle不作为模型或训练目标导出。

## 测试、资源与交付停止

87项pure定向诊断/checker测试、改动Python Ruff及compileall通过。已知共同可行与真实冲突fixture、独立复数白化、参数半径/置换/相关列、标签隔离、原子保存先后顺序与损坏记录负控均覆盖。一个近相关回变换消减问题经QR/小R-SVD修复并复验，使用1/2局部修复；原失败25通过/1失败和所有费用保留。见[测试](outcomes/records/targeted_tests_v15.json)、[repair](outcomes/records/repair_log_v15.json)。未运行full pytest、旧FE suite或新ABI/PDE资格，不声称CI通过。

正式分析3.391820603s、树峰148770816B，独立checker2.745118386s、树峰194338816B；两者swap0、自身后代已清场。完整7200s预算包含准备、IO、失败、测试、文档、浏览器及发布，最终墙钟/父子不重复计费/历史未知尾段见[资源账](outcomes/records/resource_costs_v15.json)。单核单线程pure环境、整树2GiB/警戒1.75GiB、自身swap/OOC0、系统余量及384GiB邻增长预留；不改变其他项目。实际GitHub关键页检查另见[渲染记录](outcomes/records/render_check_v15.json)，结构检查不冒充视觉通过，旧失败不追改。

M3600较好中期、Mfinal退化、原同p3严格失败、全部中断/重放/费用、缺失optimizer/RNG及未运行积分不改。D0仍成本否决，D1未运行。summary/README/进度/总账仅追加当前数组审计与入口；[依赖组](outcomes/records/selective_merge_manifest_v15.json)不提升production default。

主线已完成Gx/Gz四角对照，dot仍为待实际FE资格化的源码候选；不复制两线求解器或存储工作。原native/增广/独立FE1e-6、MPC1e-10、场/全复通道1e-4、功率/能量1e-5、逐级功率1e-6不放宽。最终原尺寸50×25×140nm、Si线宽17nm/高120nm、λ0.7nm完整三维FE、十进制2TB整机/swap0/172800s完整流程仍未资格化。本轮完成后等待review，只推本分支，不amend/强推/合并master；最终完整HEAD/tracking与清场状态在Git回执报告。
