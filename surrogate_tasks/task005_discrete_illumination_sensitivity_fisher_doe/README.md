# Task005：离散照明灵敏度与 Fisher DOE

## 状态

```text
status = approved_closed
execution_branch = codex/only-one-13p5nm-surrogate-inversion
predecessor = Task004 Review V9
Task004 = closed_controlled_negative
purpose = select a small set of discrete illuminations for h/w identification
formal_inversion = forbidden
arbitrary-angle surrogate = forbidden
implementation_sha = d24395b377259da129a81384f88d8a4ad74602d2
m5r_new_fem_count = 0
task005_final_status = TASK005_FINAL_STATUS.json
task006_authorization = M0-M2 only
```

本任务不再建立连续角度代理。它从 Task004 不可变 `train112` 中冻结 16 个已有 nominal 角度，复用中心几何响应，并通过直接 Full3D 几何扰动计算：

```text
dy/dh
dy/dw
Jacobian
Fisher information
single / pair / triple / quadruple illumination ranking
```

## 固定物理与数值身份

```text
wavelength_nm = 13.5
incident_polarization = S
nominal_height_nm = 120.0
nominal_width_nm = 17.0
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
forward_model = Full3D static uniform N1curl p5/h10/Ny4
mesh = (Nx,Ny,Nz)=(6,4,14)
MUMPS ICNTL(14) = 40
MPI = 2
threads_per_rank = 1
observable = task002.fixed-n0-orders.v3
```

## 16 个冻结照明候选

顺序为 `(grazing_deg, azimuth_deg)`：

```text
(0.5,0), (0.5,45), (0.5,90)
(1,15), (1,60)
(2,0), (2,45), (2,90)
(4,15), (4,60), (4,90)
(6,30), (6,75)
(8,45)
(10,0), (10,90)
```

所有 nominal tuple 必须在 Task004 `train112` 中恰好存在一次；中心点不得重算。

## 执行阶段

```text
M0  冻结设计、身份和nominal reuse
M1  五角度 coarse/half finite-difference step audit
M2  完成16角度 h-/h+/w-/w+ 数据
M3  单角度到四角度 Fisher DOE
M4  顶级三角度组合的三几何非线性恢复验证
M5  建立DOE lock并停止等待审阅
```

## 主要输出

```text
src/surrogate/doe/
benchmarks/cases/131_task005_*/
surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/
    outcomes/DISCRETE_ANGLE_DESIGN.json
    outcomes/FINITE_DIFFERENCE_STEP_AUDIT.json
    outcomes/M2_DATASET_MANIFEST.json
    outcomes/FISHER_SINGLE_ANGLE.json
    outcomes/FISHER_COMBINATION_RANKING.json
    outcomes/OFF_CENTRE_RECOVERY.json
    outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json
    outcomes/DISCRETE_ILLUMINATION_FISHER_DOE_LOCK_V2.json
    outcomes/M2_RANK_STABILITY_AUDIT.json
    outcomes/ILLUMINATION_COUNT_TRADEOFF.json
    outcomes/TASK001_BASELINE_INTERPRETATION_ADDENDUM.md
    outcomes/FISHER_PARAMETERIZATION_AND_HASH_SCHEMA.md
    outcomes/test_summary.md
    outcomes/test_summary_v2.md
    TASK005_FINAL_STATUS.json
    TASK005_APPROVED_CLOSEOUT.md
    response_v1.md
    response_v2.md
```

## 完成状态

M0–M4 已完成并通过：16 个 nominal tuple 精确复用、40 个 M1 审计状态、
44 个新增 M2 状态与 20 个 M1 exact reuse、Fisher 单/双/三/四角度穷举，
以及推荐三角度在 G1–G3 的恢复 Gate。总新 FEM 为 93/96。最终
`DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json` 已建立，等待审阅；Task004
仍保持关闭，blind24、连续角度代理和 Bayesian inversion 均未运行。

M5R 已以 derived-only 方式完成：没有新 FEM，原始 v1 sensitivity package 和
v1 lock 均保持原 hash；新增 M2 弱通道排名稳定性、照明数量 5% 取舍、派生
灵敏度 supplement、Task001 基准解释、Fisher/hash 语义文档、V2 lock 和
Case134 独立 checker。V2 lock 当前为 `review_ready`，等待下一轮审阅。

Review V2 已批准上述科学结果。已完成 metadata-only provenance closeout：
`TASK005_FINAL_STATUS.json` 记录 M0–M4 implementation SHA、M5R generator
commit SHA、m5r.py 文件 SHA、V2 lock SHA 和 Task006 M0–M2 授权边界。Task005
现为 `approved_closed`。

## 硬边界

不得：

- 修改或恢复 Task004；
- 运行 Task004 blind24；
- 使用 P 偏振入射；
- 增加波长、材料、侧壁角或其他结构参数；
- 将 `A_balance` 与 `R/T` 重复计入同一 Fisher；
- 将 aggregate 与其各衍射级总和重复计入同一 Fisher；
- 开始正式代理训练、Bayesian inversion 或实验结论；
- 超过任务书规定的新 FEM 硬预算。

完整执行合同见 `task.md`。
