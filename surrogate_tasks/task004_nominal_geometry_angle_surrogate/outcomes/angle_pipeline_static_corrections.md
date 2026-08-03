# M0R：Task004 角度流水线静态修正

本轮修正只改变 provenance、checker 和训练期统计的正确性，不改变冻结的
angle tuples 或 FEM 方程：

1. `power OOF` 现在只从 fold 内预测 aggregate/side-total 和 active-channel
   fraction 生成，禁止把 truth totals 当作预测输入。
2. mask agreement 使用运行期解析 mask authority；不再写死某一组 mask。
3. OOF 最近距离只在训练 fold 上计算，不再把自身样本纳入最近邻而恒等于零。
4. `low_grazing`、`high_azimuth`、`cutoff_near` 和 `ordinary_interior` 是可
   重叠的独立标签；region signature 只用于报告，不再伪造互斥分区。
5. 弱/零功率通道的 uncertainty 不再写成零；nearest-neighbour fraction
   只作为 baseline，并明确标记 uncertainty 不可用。
6. dataset loader 和 model-lock guard 采用 fail-closed 逻辑，要求单一
   source SHA、精确设计 hash 和已锁定的 dataset identity。
7. `AggregateModel.predict` 明确取 composition reconstruction 的前三列，
   避免把 `A_volume` 的附加列误当成 aggregate target。
8. `qualify.py` 逐项比较 order identity、wavevector、mask、dispersion、
   power 和 complex amplitude；设计 metadata 使用 schema v2。

实现文件包括 `src/surrogate/angle/{design,qualify,dataset,models,pipeline,api}.py`
以及 `src/forward_data/{task002_full3d,task002_campaign,task002_m4}.py`。
这些改动由 M0R clean baseline `fdf9615...` 资格化；Case124 的正式记录全部
绑定该 SHA。
