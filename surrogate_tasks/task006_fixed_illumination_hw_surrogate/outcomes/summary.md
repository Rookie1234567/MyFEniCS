# Task006 outcomes summary：固定三照明 h/w training-only M2

## 结论

Task006 M0–M2 已完成并在 training-only 边界停止等待审阅。M2 的目的不是
声称 Maxwell 连续真值已被代理替代，而是检查固定前向离散模型在 37 个
training geometry 上能否被一个有限、可审计的二维模型近似，并测试用合成
响应恢复高度和宽度的数值流程。

| 项目 | 结果 |
|---|---|
| 固定照明 | A05=(2°,0°), A07=(2°,90°), A09=(4°,60°)，S，13.5 nm |
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| forward route | Full3D static uniform N1curl p5/h10/Ny4，mesh (6,4,14)，MUMPS ICNTL(14)=40，MPI2/thread1 |
| mother grid | 49 tuples |
| training / blind split | 37 / 12，tuple hash `7948b6612e8350be1b6fd26aca010036016681f0484f4aa02b56c353f694bb28` |
| train37 records | 111 = 79 new FEM + 32 exact reuse |
| immutable dataset | `task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1`，manifest SHA256 `f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84` |
| blind response accessed | false |
| formal inversion | false |

## M0–M1 证据

M0 冻结 49 点母网格、37 点 training、12 点 blind、三照明顺序和 exact
reuse inventory。Case135 checker 通过。M1 只执行允许的 79 个新 FEM，复用
32 条完整身份匹配记录；Case136 checker 和独立 train37 dataset checker
均通过。所有新记录均绑定同一个 forward SHA、observable schema 和单进程
身份，未访问 blind 或 validation response。

## M2 方法与候选

S0 是每个照明的 `(R_total,T_total,A_balance)`。训练先拟合

```text
zR = log((R+eps)/(A+eps)); zT = log((T+eps)/(A+eps))
```

再用 `softmax(zR,zT,0)` 恢复三项，因此预测组成非负且和为 1。S1 独立
建模冻结的反射/透射 m=0 primary channel 与每侧 residual-other 的
fraction；预测后执行 sidewise non-negative ledger。这样 aggregate 和
order-resolved observable 不会在一个合同里重复计数。

使用固定 geometry-grouped 五折外层 CV；每个 geometry 的 A05/A07/A09
同时作为 test。候选为 Legendre degree 2/3/4、local Gaussian RBF k8、
Matérn-5/2 ARD exact GP 和 degree-2 orthogonal trend + Matérn residual。
GP 使用 8 个确定性初值；每折保存 fitted kernel、LML、边界碰撞、优化状态
和所有 ConvergenceWarning，而不是静默丢弃。OOF 文件保存逐点 truth、预测、
std、误差、fold、region 和 nearest-training-distance。

| candidate | training CV Gate | selection score | minimum 95% coverage | p95 interval width / N1 sigma |
|---|---:|---:|---:|---:|
| Legendre-2 | fail | 4.219003 | 0.864865 | 4.219003 |
| Legendre-3 | fail | 1.480000 | 0.675676 | 0.382976 |
| Legendre-4 | fail | 2.176471 | 0.459459 | 0.021355 |
| local RBF k8 | fail | 263.708534 | 0.918919 | 263.708534 |
| Matérn-5/2 ARD exact GP | pass | 1.000000 | 1.000000 | 0.966271 |
| degree-2 trend + Matérn residual | pass | 1.088235 | 0.918919 | 0.641289 |

因此 `matern52_ard_exact_gp` 是由 training CV 选出的候选，selection 不是
硬编码；当前状态仍是候选待审阅，不是正式 model lock。

选定候选的 S0 最大 NRMSE 为 `9.75281e-5`，S0 最大绝对误差为
`9.95103e-6`；S1 最大 NRMSE 为 `7.78114e-5`，最大 N1-normalized
误差为 `0.010780`。其每个目标的 95% OOF coverage 均为 1.0，区间宽度
有限且为正，sidewise ledger 和 composition 由合同精确保持。

## Synthetic h/w recovery

对每个 outer-test geometry，只使用 outer-training 拟合的模型；先做固定
21×21 coarse grid，再用多个固定起点的有界局部优化。L-BFGS-B 报告
line-search failure 时才执行确定性的 bounded Powell retry；若所有尝试都
不显式收敛，点仍会被计为 rejected。最终 37/37 点显式收敛：

| 指标 | 结果 | Gate |
|---|---:|---:|
| p95 absolute height error | 0.000677341 nm | ≤0.25 nm |
| p95 absolute width error | 0.000137901 nm | ≤0.05 nm |
| max absolute height error | 0.000986796 nm | ≤0.50 nm |
| max absolute width error | 0.000217014 nm | ≤0.10 nm |
| rejected / unresolved points | 0 / 37 | 0 |

这只是把已有 training FEM 响应当作 synthetic observation 的闭环测试，不能
替代 12 个冻结 blind geometries，也不能被解释成实验反演精度。

## 未运行项与停止边界

- 12 个 blind geometry FEM：未运行，且其 response 未访问。
- geometry active learning：未运行。
- formal model lock、正式 Bayesian inversion、实验数据拟合：未运行。
- Task004 blind24、Task003 frozen validation 和 Task007：未触碰。

M2 完成后按 Task006 合同停止，等待审阅决定是否建立正式 lock 或运行后续
blind validation。

## 证据索引

- M0: `outcomes/FIXED_ILLUMINATION_CONTRACT.json`, `HW_MOTHER_GRID.json`, `HW_TRAIN37_DESIGN.json`, `HW_BLIND12_DESIGN.json`, `HW_REUSE_INVENTORY.json`
- M1: `outcomes/M1_RESOURCE_PREFLIGHT.json`, `outcomes/M1_M0_CHECKER.txt`, Case136 record
- dataset: `benchmarks/artifacts/cases/137_task006_train37_dataset/train37/dataset_manifest.json`
- M2: `TRAIN37_MODEL_COMPARISON.json`, `TRAIN37_OOF_PREDICTIONS.json`, `TRAIN37_UNCERTAINTY.json`, `TRAIN37_SYNTHETIC_RECOVERY.json`, `TRAINING_MODEL_SELECTION_CANDIDATE.json`
- independent checker: `benchmarks/cases/138_task006_training_cv/records/case138_check.json`
- source/file identity: `outcomes/M2_IMPLEMENTATION_IDENTITY.json`（包含 M2 基线、训练源文件、runner、checker 和 dataset manifest 的 SHA256）
