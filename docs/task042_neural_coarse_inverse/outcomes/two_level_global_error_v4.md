# V4 预登记：有界全局误差空间与两层修正

| 项目 | 冻结范围 / 数据身份 | 证据 |
|---|---|---|
| 批次 | `V4_GLOBAL_ERROR_TWO_LEVEL`，planned；起点Review HEAD `333f6aa966284831a68d68afd6a231152fbcc824` | [Review V1](../review_report_v1.md) |
| 原方程 | 原13.5nm、p6/h10对应p4、21824 trace＋port、完整80通道；无p6外层求解 | [单一预登记配置](../../../input/task042_neural_coarse_inverse/two_level_v4.json) |
| 局部部分 | 原 `R-GEO-CELL80-v3`，支撑、Floquet master映射、限制/次数平均延拓、252个272行因子均不变 | [设计与身份](records/two_level_design_v4.json) |
| 新空间 | 原train index12–27，两类各8个独立whole_problem；每题最多64步，8/16/...64捕获解误差 | 同上，16独立家族、最多128列；不是残差POD |
| 对照 | `TWOLEVEL-OLDPOD-V4`只读旧Q；`TWOLEVEL-ERROR-V4`用准确解减当前解；两者重建完整Schur编码 | 原native U/R和神经权重均不复用 |
| Gate | 纯复数代数→真实S配对→训练快照→空间冻结→3项已消费诊断→条件16项新终测 | 不要求局部B先收敛；本轮不进入F5 |
| 资源 | shared-workstation、实时选独立核、MPI1/math1、整树RSS16GiB/12GiB warn、own swap0 | 无cgroup委派，0.5s整树采样停止；性能inconclusive |
| Review文档 | 实际GitHub渲染7张表、5个math-renderer，列数一致；原文未修改 | [检查](records/review_render_check_v4.json) |

局部方法分别修正许多小区域，可能留下跨越整个模型的误差。本批保存少量这样的全局解方向，先消除这些方向能处理的残差，再做原局部步骤，最后消除局部步骤重新引入的同类误差。代价是两个有界长基数组、小三角求解和每次PC额外一次原S作用；是否真正有用由原方程的独立残差决定。

```math
SZ=UR,\quad U^HU=I,\quad C=Z\,\mathrm{solve}(R,U^H\cdot),\qquad
B_2=C+(I-CS)B(I-SC).
```

每次B2严格为2C/1B/1S，使用SC=UUH避免多余S；不生成dense全局投影、法方程或global p4 LU。最大rank128不是必须填满的配额；误差基与SZ仅用固定相对1e-10阈值，至多一次确定性的依赖方向剔除/旋转。旧Q先截至新误差基有效rank；若SZ审计后rank不同，报告unmatched-rank。误差均使用同一canonical reduced坐标和原teacher归一化，不读取诊断或新终测teacher解。

| 分流 / planned | 原判据 | 后续 |
|---|---|---|
| strict诊断 | 三题原A4、port、recovery、约束及identity全部<=1e-10 | 可选一条冻结路线进入P4；诊断不是fresh资格 |
| global-space研究正信号 | physical与mixed原native和固定Schur/RHS各<=0.1，所有独立接口检查通过 | 允许P4；0.1不替代正式1e-10 |
| 两路线均负 | 不满足上述条件 | 保留负结果，结束本批，不扩大空间或训练 |
| 空间数值blocked | 秩、QR、三角解或真实两层恒等式失败 | 该路线停止；独立合格的另一条仍可继续有限诊断 |

最新用户授权继续仅Task042受控共享CPU运行，覆盖其原§2.3已有heavy禁令与全机独占锁要求；不是取消资源、精度、provenance或停止条件，也不代表F0正式review。自有非阻塞锁、一次数值阶段；只降低本任务CPU/I/O优先级、监督并停止自身后代，不改邻任务、环境、亲和性、watchdog或锁。保留系统10%或128GiB余量、邻增长128GiB、磁盘50GiB、artifact20GiB；成本全部标shared-workstation，不声称零影响或无争用加速。

原V1–V3负结果、原task/review/response/raw均保持不变。Review V1明确替代V3“局部量级1停滞即禁止全局空间”前提。当前页是执行前计划，实测将在本批收口写入；新teacher、NN训练、GPU、短波、F5均不在本批范围。只有条件P4全部原A4/port/recovery达到1e-10才称固定operator p4资格，不作为production默认或跨尺度证明。
