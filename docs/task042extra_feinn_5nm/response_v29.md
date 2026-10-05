# Response V29：原尺寸完整口面已实算，固定见证原门通过

本批实际调用主线冻结的边界接口，把 V28 两个代表面扩展到上下全部2,176个口面，完成p4/p6全部32,060模式的作用、伴随、幅值恢复和物理入射载荷。独立保存checker的 **1,027,260项原门检查失败0**。额外逐列诊断仍有 **6,307项失败**，不授予微小内部迹、体内恢复或任意向量精度资格。

边界计算负责区域与外部空间交换电磁场，是完整求解的一部分。本批没有求解体内Maxwell方程、生成新的散射场或训练网络；原尺寸完整解及NN净收益仍未取得。主线原数值类已在本机实际调用，相对路径包默认ready消费完成；主线工作树没有改动，远端尚未接入。

## 1. 权威、输入和实测结果

执行权威为[Review V28](review_report_v28.md)，seal为02a4fb840a9c0cf613c3f4607dfa807b18acfb65，冻结base为fbac3d8777fcfd897d93b898cb9f460f79ddd6ff。canonical为/home/fenics/Projects/NN-Lab-V2，唯一分支task42extra_feinn_5nm。已安全精确fetch/fast-forward，没有新clone/分支、reset、stash、共享配置修改或其他工作树操作。

| 实测对象 / 同一新实例 | 原门与结果 | 证据 |
| --- | --- | --- |
| 输入 | 复用V28已接受的36,263,033B/SHA7dd07d71…，32,060有序key；无重新生成 | [设计](outcomes/records/design_v29.json)、[身份/source](outcomes/records/run_index_v29.json) |
| 原口面 | x90/46/46/90、y4，z=-10/130nm，共2,176面；独立核对实体、方向、周期代表和角点 | [专题](outcomes/full_surface_action_v29.md) |
| p4控制 | 69,632边界trace行；513,630项原门失败0；最大相对8.784101295566122e-11≤1e-10 | [checker/hash](outcomes/records/independent_checker_v29.json) |
| p6目标组件 | 156,672边界trace行；513,630项原门失败0；最大相对7.435717804637401e-11≤1e-10 | [逐字段分子/分母](outcomes/records/full_surface_metrics_v29.csv) |
| 一维矩 | 3,503个精确binary64频率、ell0..6；复用357/新增3,146；最大绝对9.082805012334877e-14≤1e-12，p6全部复用p4 | [独立参考](outcomes/records/independent_checker_v29.json) |
| 主线API | 未修改的FacetPolynomial / BoundaryLayout / DirectionalBoundaryAction，face_inventory=None；两坐标系均计算全口面 | [实际调用](outcomes/records/main_api_handoff_v29.json) |
| 接入包 | 37个载荷文件、251,699,594B；默认ready实际重开；MAIN_API_ADAPTER_LOCAL_PASS_NOT_REMOTE_INGESTED | [接入及限定](outcomes/full_surface_action_v29.md) |
| 额外逐列负结果 | p4 1,360/p6 4,947项失败；微小内部迹全部保留，不裁幅值 | [负结果](outcomes/records/independent_checker_v29.json)、[修复](outcomes/records/repair_log_v29.json) |

最坏p4为seam见证bottom(-56,30,s)、index26290：分子2.1154794583025582e-15，分母2.408304944491443e-5。p6为generic见证top(-67,-35,s)、index8574：分子1.4397376159927008e-13，分母0.0019362456373677684。采用独立参考的原模长，未改成max(1,…)或拟合地板。仅是固定见证经验通过，不是所有向量一致误差界。

实例仍为W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28。旧schema1原件未恢复，historical_bitwise_reproduction=false，旧数值等价UNKNOWN、旧ledger未恢复，不能混用旧B/D/H或因子。本实例全部选中模式为传播模式；不授予倏逝截断或端口收敛。

## 2. 实际失败和有限修复

开发收据键序列化、格式及未使用变量错误在首个实现冻结前修正，原日志和费用保留。保存checker的复杂极化共轭、原清单缺少派生参考面字段通过定向fixture修正；后者曾使c29 worker失败，不是数值失败或OOM。

c129曾把每个极小原生列的范数当成V28原分母，给出FULL_SURFACE_NUMERICAL_FAILED。受测原生积分是完整矩阵，B/D是完整向量；已接受的V28源码对这些完整对象取范数，并检查三个固定复方向。c229恢复这一原规则，继续保存每个逐列失败；门限始终1e-10，候选数组、q60、物理均不改，没有扫描范数或挑方向。

逐列最大积分相对差仍为p4 23.87790429183715、p6 16.805483465112903；参考范数约2.23e-17/1.25e-16，分子约5.32e-16/2.09e-15。B/D单列仍约0.736/0.743。不能因绝对数小就删除，也不能由完整向量通过推断体内消元资格。旧c129状态、CSV、source均不改写。

P0第四个不同根因资格化被旧统一三次生命周期守卫在worker前拒绝。最小opt-in修复区分固定根因、拒绝未知根因，数值case原上限不变；该拒绝耗掉真实样本，费用未重置。健康p4/p6各只有一次producer，后续只读保存数据。[完整failure→hypothesis→change→test→retry账](outcomes/records/repair_log_v29.json)。

当前说明纠正历史术语：recover/original_recover_key是逐模式投影/幅值，完整FE边界返回向量是apply；B使用traction，D使用电极化投影除以原H，不能假定D=B的共轭转置。历史页保留。

## 3. 运行源码、费用与资源

| 实际clean source / 阶段 | receiver全链秒 | 采样同时树峰 / B |
| --- | --- | --- |
| ef9f9f39f350ab1d0243d50ff5ad8386f0e5b935 / 唯一p4 | 153.006203 | 814,727,168 |
| 91023bdc62766c9ffde9471026d8875fac93860b / 唯一p6 | 91.694705 | 910,086,144 |
| c94fe051752ab1576bc8b00548eb12109f18280a / 最终checker | 162.992869 | 545,341,440 |
| 同上 / 包封存和ready重开 | 69.831761 | 178,151,424 |

数学始终c354afa449fb80cfb5012e7d2ff66a3e3e64e088，43文件/1,054,179B闭包；每阶段另绑定40份接收源码、实际dat、模式、布局/矩/见证、ABI、资源和监督。最终17项定向测试、Ruff、compileall全通过，早期失败不改；无full pytest、无关MPI、环境重装或CI声明。[准确source](outcomes/records/run_index_v29.json)、[测试](outcomes/records/targeted_tests_v29.json)。

正式阶段费用合计976.1939919528086s，含加载、PSI、源准备、计算、存盘和审核；嵌套worker/watchdog未重复相加。p4 payload84.349817s含新增一次高精度参考，p6 payload22.813703s复用它，不能称公平冷成本加速比。开发、等待、失败、阅读及发布在同一28,800s连续窗，明示300s保守开场allowance，旧窗不重开；发布/通知尾段在本机交付收据另记。[完整费用](outcomes/records/resource_costs_v29.json)。

CPU-only/MPI1/单物理核/数学1；正式worker新鲜观察最大年龄2.959228s≤15s，均在独立60s PSI后取得。24/24份内外真实样本、前台等待813.597248s≤900s；没有第25份或额外浏览器树。正式采样自身swap0、树已清场，峰值是同时进程树采样；启动前及轻元数据未测峰UNKNOWN，不冒充连续内核硬RSS保证。系统/384GiB邻增长余量不改，未动邻任务。artifact快照966,649,196B＜16GiB。项目精确总累计仍UNKNOWN，旧失联3284s及全部费用保留。

## 4. 接入和最终收口

真实本机包入口：

```text
/home/fenics/Projects/NN-Lab-V2/benchmarks/artifacts/task42extra/w1_receiver/v29/h29/surface_handoff/main_opt_in_bundle/
package_manifest SHA256 e54d17b4184daf258901624afa487a2121fe6a97e2f1478c61c4b3731aed3ba9
```

37个相对路径依赖实际重开。重开检验身份、封存及完整数值报告，不冒充第二次FE重算；实际主线数值消费是P1原三个类的调用，P2是另进程独立收缩。接收方仍须按其合同绑定同实例体积/内部恢复和完整物理门。无跨机、断电或主线远程接收证书。[依赖分组](outcomes/records/selective_merge_manifest_v29.json)。

q60分面及稳定求和修复未触发；Maxwell factor/solve、Gram、NN训练=0。体内full explicit true residual、总/散射E/H/curl、六点场、实际散射复通道、R/T/A/A_volume及完整冷流程均NOT_RUN，边界模式与固定trace见证不是散射前向解。

保持FEINN_MAIN_SOLVER_ON_HOLD / NO_VERIFIED_NN_INCREMENT / FULL_TARGET_NOT_QUALIFIED，M3600较好、Mfinal退化、D0成本否决/D1未运行、全部旧FAIL/UNKNOWN保留。最终原50×25×140nm/Si17/120nm/λ0.7完整3D FE、decimal2e12B整机、ownswap/OOC0、172800s及原精度门尚未达成。

有限网页访问仍Cache miss；新增页没有浏览器视觉PASS，审阅已验收的Review V28范围与执行端旧失败分别保留。[呈现记录](outcomes/records/render_check_v29.json)。本轮全口面辅助交付收口；提交推送精确分支、fetch核对和清场后仅发一次完成通知，随后停止等待审阅，不merge master，不自动开下一批。
