# W1 原尺寸边界接收包

本入口把已经冻结的边界计算接到本工作站，并检查同一份输入是否到达全部消费者。它不重建模式库存、不重跑W0，不求原尺寸PDE，不训练网络。普通求解器默认行为不变。

数学来源为主线 `c354afa449fb80cfb5012e7d2ff66a3e3e64e088`，19个实际本地导入依赖与activation文件由[dependencies.json](dependencies.json)绑定。只读Git对象缓存不是新clone。receiver自身源码及已资格化的V23区间矩参照另行绑定，不把文档HEAD当数值源码。

唯一候选为q60。先运行原生Basix方向、非单位Floquet缝及角点展开轻控制，再核对原manifest与配套ledger。缺原件为`NOT_RUN_INPUT_UNAVAILABLE`，建议目录不是接收证明。所有输入、输出、q及源码由同一binding供worker/checker读取，禁止返回主线默认目录。

## 串行入口

先在canonical工作树clean commit，再通过独立持久launcher运行一个dat：

```bash
source scripts/activate_task42extra.sh pure
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/v25_w1_control.dat
```

依次为`boundary`、`boundary_check`；P1独立checker通过后，才可依次启动`p4_top`及其`_check`、`p4_bottom`及其`_check`、`p6_top`及其`_check`、`p6_bottom`及其`_check`。全部文件采用`v25_w1_<stage>.dat`命名，禁止并行启动。局部载荷是人为构造的非零测试数据，不能称物理入射RHS或散射解。

外部输入由显式dat路径选取：manifest固定36,244,923B/SHA52d7ec80…，ledger只接受Review V24两份hash之一。原main checkpoint若可得，优先只读接收，不重复q30。原件和大数组留ignored目录。坐标为主线居中nm，向ledger绝对坐标平移(25,12.5,0)nm，相应端口幅度的相位逆变换记录；H使用原整周期面积及参考面，不能替换为局部面积。

## 资源与边界

本轮连续14400s，数值与checker合计7200s，尾段留1800s。窗口固定在`tmp/task42extra/w1_receiver/window_record.json`，不得重置。轻控制整树2GiB，正式局部组件16GiB/warn12GiB；单空闲物理核、线程1、MPI1、CPU-only、自身swap/OOC0，系统及384GiB邻增长预留、PSI保护不变。

每段沿用独立tmux＋watchdog＋worker，启动前低优先级/idleIO，管理进程也绑定本任务核；先核对旧段清场再启动下一段。保存窗口150s前收口，至少120s；UTC/monotonic差>5s拒绝。矩阵仅局部，模式流式64一批，禁止32060²密集数组。因子释放在独立保存checker前；checker不因结果标签而给PASS，重算原数组分子、分母、覆盖与Gate。

这只是局部W1资格，不证明原尺寸全域MPC、物理RHS或有效解。原目标50×25×140nm、λ0.7nm、完整三维FE、decimal2e12B整机/172800s仍未达到，FEINN主求解器及生产初值继续暂停。
