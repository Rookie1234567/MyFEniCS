# 13.5 nm 原生复现：第一次运行的失败与性能证据

当前 R1 **未通过**。p4 装配和一次 LU 已完成，随后旧固定通道哈希校验失败；没有进入 outer，不存在 official 场或 R/T/A。失败目录完整保留，尚未正式 retry。

| measured 项目 | 本次原生 Linux R1 | 历史 WSL V5 / 解释 |
|---|---:|---|
| workflow | 2731.774616 s | 本次因身份校验失败退出，不与完整旧 solve 混比 |
| p4 体矩阵装配 marker 区间 | 2301.507451 s | 旧全部 setup 至 solve_started 约 667.726223 s；本次确实异常慢 |
| H6 setup | 188.589008 s | 同时存活对象峰值约 1.256 GiB |
| fine physical setup | 119.367685 s | 同时存活对象峰值约 1.464 GiB |
| p4 numeric marker 区间 | 7.914063 s | 含该区间准备开销，不冒充纯 factor CPU 时间 |
| 整树同期 RSS 采样峰值 | 2992881664 B | 约 2.787 GiB；各阶段峰值不可相加 |
| p4 augmented rows / NNZ / factor NNZ | 53164 / 24730144 / 53417584 | 与旧规模一致，不代表 residual 通过 |
| swap / 清场 | 0 B / 全部后代已清场 | 6075 个资源样本；完整分阶段覆盖见 compact |

八秒 perf 采样的 99.75% 位于 FFCx 单元积分函数。固定同一份生成 C 的单单元诊断耗时 8.331346 s；O3 加 march=native 为 7.054665 s，仅 1.181 倍，矩阵相对差 1.51684e-16。它不足以解释整体差距，未修改正式 JIT 参数。单个单元诊断不能代替完整算子资格。

监督进程原先与 worker 共用 CPU8，采样消耗约四分之一核心。运行中已将监督进程迁到 CPU9；按用户要求，将本任务 MPI launcher/worker 移到 CPU23（socket0，界面 CPU1）。隔壁 CPU0–7 进程未修改。后续 launcher 已固定监督 CPU9、worker CPU23，5 个已有定向测试通过；这防止直接抢占同一逻辑核心，但仍共享 CPU1 的缓存和内存带宽，不能承诺零性能影响。

旧哈希为 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`，原生实际为 `d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb`。在本机直接加载旧 V5 dat 也得到后者；physical hash 和 80 通道数一致。一次仅限诊断进程的 NumPy CPU 分派关闭实验又得到 `40b02a2cd1c0c83f8f5475d1ecb1fc231a473d336bf265e4d6511ada0d4ed151`，说明浮点序列化身份可能受硬件执行路径影响，但还未取得旧逐字段数值，不能宣称差异均已解释。未替换固定哈希、未降低数值 Gate，等待笔记本小型元数据移交。

完整来源、逐阶段时间/峰值及原始 artifact hashes：[R1 compact](records/r1_attempt1.json)。R2、S5、S3、S2、G 均 `NOT_RUN_BY_PREVIOUS_GATE`。这是过程记录，任务尚未结项。
