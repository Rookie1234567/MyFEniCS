# W1 原尺寸边界接收包

本入口把已经冻结的边界计算接到本工作站，并检查同一份输入是否到达全部消费者。Review V25 §8明确授权一次确定性输入恢复：仅从冻结Git源码生成模式元数据，逐字节匹配旧manifest，然后继续原生控制和q60全模式代表面资格。它不重跑W0、不求原尺寸PDE、不训练网络。普通求解器默认行为不变。

## 当前接续：Review V25 §8

旧ledger和旧NPZ仍未取得。新`bitwise_reproduced_v26`来源分支只在36,244,923B、完整manifest SHA、32060有序key SHA及固定Git物理身份全部一致时准入；新receipt记录真实来源、监督与清场，不冒充旧ledger。恢复失败停止B，不更换ABI试hash。

先clean实现commit，再串行运行`v26_rb_input_recovery.dat`、`v26_rb_control.dat`、`v26_rb_boundary.dat`、`v26_rb_boundary_check.dat`，均由`python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat`启动。唯一`R_B_window.json`从接线准备计10800s，R及接线1800s，数值/checker合计7200s，尾段1800s；R成功不重置。旧92项A资格复用，新增凭据/计时/全部频率覆盖只作增量资格。本包不自动运行B2局部LU/恢复，主线按自己的Review承担；下文旧入口及失败记录保留为历史，不是当前授权。

数学来源为主线 `c354afa449fb80cfb5012e7d2ff66a3e3e64e088`，19个实际本地导入依赖与activation文件由[dependencies.json](dependencies.json)绑定。只读Git对象缓存不是新clone。receiver自身源码及已资格化的V23区间矩参照另行绑定，不把文档HEAD当数值源码。

当前权威为[Review V25](../../../docs/task042extra_feinn_5nm/review_report_v25.md)。A修复保存记录的科学验收链，B在原件和资源齐备后做原生验收。缺原件为`NOT_RUN_INPUT_UNAVAILABLE`，建议目录不是接收证明。**A轻测试通过只资格化逻辑；B未运行，W1仍未获得物理资格。** A阶段记录见[stage_A_v26.json](../../../docs/task042extra_feinn_5nm/outcomes/records/stage_A_v26.json)。整包完成前不创建另一份暂停回执。

唯一候选为q60。现在先核对原manifest、配套ledger与A受测源码，再启动原生Basix方向、非单位Floquet缝及角点展开控制。所有消费者共用科学身份，包括原件、模式顺序、q、数学依赖、实际接入源码文件和窗口；每个stage另绑定自己的dat字节。监督失败、退出非零、未清场、未封存、缺原数组或错hash均不能进入依赖阶段。文档HEAD变化不使相同数值源码的合格证据失效。

## 串行入口

先在canonical工作树clean commit，再通过独立持久launcher运行一个dat：

```bash
source scripts/activate_task42extra.sh pure
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v26_w1_control.dat
```

依次为`boundary`、`boundary_check`；P1独立checker通过后，才可依次启动`p4_top`及其`_check`、`p4_bottom`及其`_check`、`p6_top`及其`_check`、`p6_bottom`及其`_check`。全部文件采用`v26_w1_<stage>.dat`命名，禁止并行启动。旧V25输入及失败窗不覆盖。显式`prerequisite_paths`可指向同一科学身份／窗口中已封存且清场的正确producer；不同尝试另开输出目录，不重复正确worker。

当原件仍缺时，包装返回`B_NOT_STARTED_INPUT_UNAVAILABLE`，不建B时钟、tmux或native worker。A资格文件为`tmp/task42extra/w1_receiver/v26/A_qualification.json`，绑定92项实际定向测试、JUnit、监督结果和源码hash；测试全部为pure逻辑fixture，局部Basix及直接积分stub范围明确，不是FE证书。原件到位后仍须完成真实B0/B1/B2，不能用合成状态替代。

外部输入由显式dat路径选取：manifest固定36,244,923B/SHA52d7ec80…，ledger只接受Review V24两份hash之一。原main checkpoint若可得，优先只读接收，不重复q30。原件和大数组留ignored目录。坐标为主线居中nm，向ledger绝对坐标平移(25,12.5,0)nm，相应端口幅度的相位逆变换记录；H使用原整周期面积及参考面，不能替换为局部面积。

## 独立检查与真实载荷

保存checker现在读取真正会被下一阶段使用的`qhat_alpha`及`affine_internal_rhs`，重算原／约化trace和port、全部内部恢复、原B/D列、p/side分区及原mode/H。它通过原块乘法核验worker已经算好的内部解，不新增checker因子或solve。为此采用本支明确的exports-only补丁，在独立文件导出原c354afa已有中间量；只读数学闭包不修改，原LU/solve和积分调用次数不变，派生文件另外记录hash。

移位后的面积分、Bα、D/H及伴随分别检查；真实入射固定掠入射1°、φ0°、s、上空气／下Si，端口振幅和参考面相位进入实际`modal_rhs`。另核对空气／Si平面背景的入射边界载荷与界面连续关系。这里检查的是**边界入射源**，不是三维缺口的体源或完整散射解。局部内部恢复继续使用独立制造的非零内部／trace／port载荷，两个用途不混用。

区间矩参照保存原数值、Decimal80/110字符串、固定频率范围及hash，checker从这些字段重算≤1e−12门，不接受仅有PASS标签。所有相对差使用原分母，近零标记保留。统一JSON写出支持有限NumPy标量，拒绝NaN/Inf及数组／复数直接进入JSON，flush/fsync／原子替换后重开确认；数组保存在NPZ。

## 资源与边界

本合同采用A≤3600s、B首次为真实输入准备后连续≤10800s的两段窗口。B的worker与数值checker合计≤7200s，尾段留1800s，控制stage也扣此共享费用；`B_window.json`只可首次创建，绑定原件和A资格hash。中间真实外部等待另计日历成本，不能声称整包14400s日历内完成，更不证明最终48h。旧V25连续14400s及2846.101466s费用不重置。

轻控制与pure检查整树2GiB，正式局部组件16GiB/warn12GiB；单实测空闲物理核、线程1、MPI1、CPU-only、自身swap/OOC0，系统及384GiB邻增长预留、PSI保护不变。全机swap仅诊断，自身swap仍停止。采样整树限制不冒称连续kernel限额。

每段沿用独立tmux＋watchdog＋worker，启动前低优先级/idleIO，管理进程也绑定本任务核；先核对旧段清场再启动下一段。保存窗口150s前收口，至少120s；UTC/monotonic差>5s拒绝。矩阵仅局部，模式流式64一批，禁止32060²密集数组。因子释放在独立保存checker前；checker不因结果标签而给PASS，重算原数组分子、分母、覆盖与Gate。

这只是局部W1资格，不证明原尺寸全域MPC、物理RHS或有效解。原目标50×25×140nm、λ0.7nm、完整三维FE、decimal2e12B整机/172800s仍未达到，FEINN主求解器及生产初值继续暂停。
