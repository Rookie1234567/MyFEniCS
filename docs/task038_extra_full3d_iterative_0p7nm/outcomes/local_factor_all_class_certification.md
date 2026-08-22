# V6：全部 exact class 的 local-factor certification

## 1. 这份证据回答什么问题

这里的 **local factor** 是每个局部 cell patch 的辅助矩阵 `B0` 的 Cholesky 因子。可以把它理解为：先把一个小的、正定的局部线性问题拆成三角方程，后续 patch solve 只需要前后各一次三角回代，而不需要把整个三维问题组装成全局稠密矩阵。**exact class** 是在离散单元、材料、宽度、方向/约束展开和规范化局部行完全相同的一组 patch；同一 class 只保留一个 packed factor。

本轮只证明了 FC1 的“一次完整 class inventory/factor certification”事实，并没有把它扩展为完整 N2 setup 或 PDE 通过。FC3 随后的 fresh N2 setup 在资源硬线上受控停止，因此整条 local-spectral multilevel family 关闭，不进入 FC4/N3/N4。

## 2. 阶段结论

|阶段|源码/证据|实际结论|边界|
|---|---|---|---|
|FC0|`d9f3c30285e169879891c7bef7896079b5a3babf`|focused implementation/tests PASS：48 passed，1 skipped|只覆盖实现与小合同，不是 p6 全 class formal|
|FC1|`benchmarks/artifacts/task038_extra_full3d_iterative_fc1/d9f3c30_attempt2/p6_h10_mpi1`|26/26 class 独立 checker PASS|local factor certification PASS；不是完整 N2 setup PASS|
|FC2|`d5f86fc14c7f40ec58e3eb75e07146b4eb4cf066`|prospective certification wiring 已接线|没有单独新增的 complete-setup 数值 Gate|
|FC3|`benchmarks/artifacts/task038_extra_full3d_iterative_fc3/d5f86fc/p6_h10_mpi1`|CONTROLLED RESOURCE NEGATIVE|process-tree `2,228,187,136 B >= 2,000,000,000 B`，停止 FC4/N3/N4|
|FC4/N3/N4|无运行|`not_run_by_fc3_resource_hard_stop`|不得写成数值通过或数值失败|

FC1 的 48 passed/1 skipped 来自 FC0 certification 代码收口；FC2 收口后的相关选择测试为 53 passed/1 skipped，compileall、AST 和 `git diff --check` 均通过。这些是源码资格化结果，不能替代 FC3 的资源 Gate。

## 3. FC1 固定身份、class inventory 和阈值

|项目|值|
|---|---|
|formal source SHA|`d9f3c30285e169879891c7bef7896079b5a3babf`|
|case|`p6-h10-mpi1`，degree 6，h=10 nm，MPI 1，complex128，固定 RHS `arange(882)+(0.125+0.25j)`|
|input SHA256|`819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41`|
|class count|26；missing=0，duplicate=0，all processed=true，all pass=true|
|class order SHA256|`a7b649d25c7f843a160816a3c4fe3836243e9639eb7c0ba43dd2901955511028`|
|order repeat|同一 canonical inventory 独立重建；exact=true，repeat SHA 同上|
|rows|每 class 882；factor owner rank 0；MPI1 owner closure：unique=26，duplicate=0|
|factor bytes|`161,991,648 B <= 199,374,336 B`；每 factor `6,230,448 B`|
|dense lifecycle|`dense_class_max_live=1`，完成每类认证后释放；没有把 dense B/RHS 放入 tracked compact|

冻结的数值合同如下；没有为结果调整阈值：

|metric|limit/公式|
|---|---|
|`eps64`|`2.220446049250313e-16`|
|`gamma_882`|`882*eps/(1-882*eps) = 1.9584334154391596e-13`|
|Hermitian defect|`8*gamma_882 = 1.5667467323513277e-12`|
|factorization / normalized backward|`16*gamma_882 = 3.1334934647026553e-12`|
|ordinary relative residual|`1e-10`|
|`kappa2`|`1e8`|
|factor size|`6,230,448 B` per class；global `199,374,336 B` ceiling|

每个 class 的 digest、slot、representative cell identity、882 rows、B/RHS/factor hashes、factor bytes、Hermitian/SPD/eigen/kappa/factorization/packing/triangular residual/backward/repeat 和各 Gate 都在 tracked compact 中逐 class 保存；compact 不复制 dense 数组。独立 checker 输入仍是 ignored raw B/RHS 与 worker facts，它没有导入 runner、solver、PETSc 或 MPI，也没有相信 worker 的 summary 才判 PASS。

## 4. FC1 worst-class 摘要

|Gate|最坏 class（digest；slot）|实测值|限值|
|---|---|---:|---:|
|factor bytes|`0060a10f08d980ac618497c076b8c6d078d6d1841d3f37d8172bc6e5804f8563`; 0|6,230,448 B|6,230,448 B|
|Hermitian defect|`9a0d14a26cbd4f5272f3d9e3cfbeef1acdf521330034b7f960adb9acbee6e63b`; 14|`1.011861373443624e-16`|`1.5667467323513277e-12`|
|lambda-min / SPD margin|`2c0158caba9c69275ba88a85343a15ccffbef4bdb8d463d0be47ca8d18fec301`; 6|`4.495428682394547e-4`|`> 0`|
|`kappa2`|同上；6|`5.768906342088295e7`|`1e8`|
|factorization defect|`48f903688ffb4d930384ca6f8160e39f5938f71871de27fe8db0538d9b534d04`; 7|`9.360591063492774e-16`|`3.1334934647026553e-12`|
|ordinary residual|`13597baf243c7cd52a5080b48e7361b3faa0e45cb4c937aa8a1c140a9e2b0c2a`; 4|`1.1713789755077614e-11`|`1e-10`|
|normalized backward|同上；4|`9.83496351829931e-19`|`3.1334934647026553e-12`|
|packing / triangular repeat|`0060a10f08d980ac618497c076b8c6d078d6d1841d3f37d8172bc6e5804f8563`; 0|relative=0，exact=true|relative=0，exact=true|

这些 worst values 只描述 FC1 的局部 class certification；它们不代表 FC3 已完成全部 252 patch、regional/top retained basis 或 exact physical action。

## 5. FC1 attempt2 的路径边界

FC1 的 artifact 目录名是 `d9f3c30_attempt2`，但不存在对应的 `attempt1` 目录。第一次外层 wrapper 在启动 worker 前因 `--watchdog-command` 后多出的 `--` 被 argparse 拒绝，因而没有创建 worker/root/artifact；为了保持“只一次实际成功 formal worker”和“不覆盖既有路径”，有效运行使用了新的 `attempt2` 路径。FC1 attempt2 的 worker 返回 0、watchdog `already_exited`、no orphan、swap gate true；这不改变 FC3 的后续 hard stop。

FC1 主要 hash：

|artifact|bytes|SHA256|
|---|---:|---|
|worker record|113,457|`f595702f2ba01e08b9702413173a07617a020bb28e6f6b4c74b9d27d90c54cae`|
|watchdog raw|178,042|`34d2ee5b60a1ebac753a415bd8a6fd2a5dd4cd90c3cd301f4d296949ead669a6`|
|watchdog compact|1,901|`c0313fa5ace4f6a57dd898afe5f87fd6c9ebc5de0c05193b2841eeebb7723cf5`|
|independent checker compact|131,002|`2d25ba960fdd6939f5d9d5b66b7619c17c1838cc4b9befdb4a9b49cbaa3d8e80`|
|checker stdout|94,430|`ece0b06bb92ca6a2d768f1d5ffa966a8ea1ef9c2ead3207aea82e1017e27dfb0`|
|worker log|1,341|`e2f3dc46fe7d33e4173419c77473f788dcb50b473cd3c3a2a4aee490cfa055d9`|

## 6. FC3：有效资源 hard stop 与阶段 attribution 边界

FC3 使用 source `d5f86fc14c7f40ec58e3eb75e07146b4eb4cf066`，新 root 为 `benchmarks/artifacts/task038_extra_full3d_iterative_fc3/d5f86fc/p6_h10_mpi1`。watchdog 采集了 3,637 个 authority samples，process-tree memory authority peak 为 **2,228,187,136 B**，冻结 hard line 为 **2,000,000,000 B**，因此 `peak >= hard_stop` 是真实 hard Gate 失败。process-tree swap 为 0，watchdog swap gate=true、no-orphan=true、worker rc=1，watchdog 未把它改写成数值 residual 失败；FC3 classification 是 controlled resource negative。

这里有一个必须同时保留的 provenance 细节：watchdog compact 的 stage peak 和 watchdog fallback `worker.record.json` 因 stop 时没有读到完整 worker record，显示 `startup`、`last_marker=startup`、source null。这只是 fallback attribution，不能当作真实最后阶段。真实 raw marker ledger 和 worker.log 逐条显示并绑定 source `d5f86fc...` 的顺序为：

`preflight -> mesh_space_mpc -> JIT -> subdomain_inventory -> local_factor_build -> local_mode_build -> regional_coarse_build`。

因此资源 hard Gate 本身有效，但阶段结论应写成“进入 `regional_coarse_build` 后，尚未取得该阶段 completion/result，watchdog 在 process-tree hard line 停止”；不能把 fallback 的 startup 当作真实最后 marker，也不因 attribution 缺陷重跑。

|FC3 evidence|bytes|SHA256|
|---|---:|---|
|watchdog raw（3,637 samples）|5,072,603|`1216c79de11fe99bf827e71b8d9cc46114935f5cabbcbf23085ca567761eda99`|
|watchdog compact|1,909|`62172d1e44583168c35ed59fe359282193246eb90d738d529fe044f5a5e3fb0d`|
|fallback worker record|1,849|`2bcfa6c385e81c4e5a2162707544cee7094adbef94f2e8b4cb891b5afadff3f`|
|worker log|2,042|`781c9c56fc57d4f333cec5890cf4173da5c8e4bc96ca235e6d0e0c6ef28dc1a6`|

FC3 在完成 top-level build、post-setup retained sampling、identity apply、canonical evidence 之前停止，所以没有得到可资格化的 252-patch inventory closure、regional/top `Z/AZ/E`、post-setup RSS 或 complete N2 resource pass。`2,228,187,136 B` 是过程树硬停峰值，不是完整 PDE 的内存结论。

## 7. 关闭结论与保留边界

|项|结论|
|---|---|
|FC1 local factor certification|PASS（仅该 certification scope）|
|FC3 complete N2 setup|`CONTROLLED_RESOURCE_NEGATIVE`|
|FC4/N3/N4|`not_run_by_fc3_resource_hard_stop`|
|local-spectral multilevel family|`CLOSED_BY_FC3_RESOURCE_HARD_STOP`；不可继续授权|
|old N2 v1/v2 negative|原样保留，不删除、不覆盖、不重分类|
|production ordinary default|不因 FC1 或 FC2 wiring 改变；未获得完整 N2 qualification|

旧 tracked N2 evidence 仍以原文件为准：v1 compact SHA256 `d02f416956a560c0837d067636d8f62d253c9d04da4e6bbe3b6194dd10098d40`，v2 compact SHA256 `d88330f2c9b038946c8f0b15e22b5850e6812c868366fa50f04e1e9b3962f763`。本 closeout 新增的两个 compact 只引用 ignored raw，不复制 dense B、RHS、factor 或 timeline。
