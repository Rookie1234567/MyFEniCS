# Task004 Review Report V9：最终关闭验收与 Task005 离散照明灵敏度/Fisher DOE 移交

## 1. 审阅结论

本轮正式批准并接受 Task004 的最终关闭交付：

```text
TASK004_FINAL_STATUS.json                    = approved
TASK004_CONTROLLED_NEGATIVE_CLOSEOUT.md      = approved
Task004 README / outcomes summary closeout   = approved
Task004 status                               = closed_controlled_negative
full-domain aggregate surrogate              = controlled_negative
selective aggregate surrogate                = controlled_negative
order-resolved surrogate                     = not_qualified
blind-validation FEM                         = intentionally_not_run (0/24)
```

关闭身份冻结为：

```text
forward_solver_sha   = fdf961545f217d620e22800f2704ae9913a6d270
dataset_id           = task004_angle_nominal_p5_ny4_train112_v1
training_rows        = 112
training_tuple_sha   = 00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68
fixed geometry       = h=120 nm, w=17 nm
forward model        = Full3D static uniform N1curl p5/h10/Ny4
mesh                 = (Nx,Ny,Nz)=(6,4,14)
MUMPS                = ICNTL(14)=40
MPI / thread         = 2 / 1
observable           = task002.fixed-n0-orders.v3
```

本轮没有证据支持恢复 Task004。下列边界继续永久生效：

- 不增加 Task004 training FEM；
- 不执行第二轮主动学习；
- 不调整 Task004 threshold、Gate、kernel、邻域数或模型集合；
- 不运行 Task004 blind24；
- 不将 Case130 checker 的 `pass` 解释成代理资格通过；
- 不删除、覆盖或混入 `train112`、Case124–Case130 及其负结果证据。

Task004 的关闭是科学资格负结果，不是程序、资源或前向有限元失败。

---

## 2. 为什么下一步不再继续“任意角度代理”

Task004 已经证明：

1. 固定几何下，多数角度的局部响应可被近似；
2. 高方位角、Rayleigh/cutoff 高曲率邻域及少量覆盖空洞会产生稳定的尾部误差；
3. full-domain 与 selective surrogate 均不能在冻结合同下可靠召回全部尾部；
4. 继续针对同一 112 点 OOF truth 调规则会形成训练证据过拟合。

但反演真正需要的并不是在完整矩形内对任意角度给出 nominal 响应，而是确定哪些离散照明能可靠区分结构参数：

\[
\frac{\partial \mathbf y}{\partial h},
\qquad
\frac{\partial \mathbf y}{\partial w}.
\]

因此下一步应从：

```text
(grazing, azimuth) -> nominal R/T/A
```

转为：

```text
有限离散角度
+ 直接Full3D几何扰动
-> dy/dh, dy/dw
-> Jacobian / Fisher
-> 最佳单角度、双角度、三角度组合
```

该路线不依赖 Task004 任意角度代理，也不需要打开 Task004 blind24。

---

## 3. 正式批准新建 Task005

批准建立独立目录：

```text
surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/
```

Task005 与历史 `docs/task005_*` 属于不同命名空间；本任务编号仅指 `surrogate_tasks/` 序列。

Task005 目标：

> 在固定 nominal 几何附近，使用离散角度上的直接 Full3D p5/Ny4 中央差分，建立高度/宽度灵敏度，完成基于可测功率响应的 Fisher DOE，并选出供后续结构参数代理使用的少数照明组合。

Task005 不是：

- 任意角度代理的恢复；
- 正式参数反演；
- Bayesian posterior；
- P 偏振入射扩展；
- 波长、材料、侧壁角或其他结构参数扩展；
- Task004 blind validation。

---

## 4. Task005 的核心设计原则

### 4.1 复用 nominal FEM，不重复计算中心几何

离散候选角度必须从 `train112` 中选择。每个候选角度的：

```text
h=120 nm, w=17 nm
```

nominal response 直接从不可变 Task004 数据包读取，不得重复运行中心点 FEM。

几何扰动样本必须继续绑定完全相同的：

```text
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
Full3D static uniform N1curl p5/h10/Ny4
mesh = (6,4,14)
MUMPS ICNTL(14)=40
MPI2 / thread1
observable v3
compact_surrogate_record
```

### 4.2 候选角度必须先冻结，不能根据导数结果改选

Task005 冻结 16 个 structured candidates：

```text
(0.5,  0), (0.5, 45), (0.5, 90)
(1.0, 15), (1.0, 60)
(2.0,  0), (2.0, 45), (2.0, 90)
(4.0, 15), (4.0, 60), (4.0, 90)
(6.0, 30), (6.0, 75)
(8.0, 45)
(10.0, 0), (10.0, 90)
```

单位均为 degree，顺序为 `(grazing, azimuth)`。Codex 必须先验证 16 个 nominal tuple 在 `train112` 中各出现一次；若任一不存在，停止并报告，不能自行换点。

该集合包含 Task001 的基准照明对：

```text
10 deg / 0 deg
10 deg / 90 deg
```

后续必须把新 Fisher 结果与该基准对同口径比较。

### 4.3 先资格化有限差分步长，再批量计算

初始两级步长：

```text
coarse: delta_h = 2.5 nm,  delta_w = 0.5 nm
half:   delta_h = 1.25 nm, delta_w = 0.25 nm
```

在五个代表角度执行步长审计：

```text
(0.5,0), (2,90), (4,60), (10,0), (10,90)
```

中央差分：

\[
D_h(\delta_h)=
\frac{\mathbf y(h_0+\delta_h,w_0)-\mathbf y(h_0-\delta_h,w_0)}{2\delta_h},
\]

\[
D_w(\delta_w)=
\frac{\mathbf y(h_0,w_0+\delta_w)-\mathbf y(h_0,w_0-\delta_w)}{2\delta_w}.
\]

步长可对 `h` 和 `w` 分别冻结。至少 4/5 审计角度必须在主测量合同下满足：

```text
noise-weighted derivative cosine >= 0.98
relative L2 difference <= 0.20
dominant-channel sign agreement >= 0.80
```

若任一参数无法通过，不得进入完整 16 角度计算。

### 4.4 Fisher 不得重复计算同一物理信息

必须分开评价互不重复的测量合同：

```text
M0 aggregate_RT:
    [R_total, T_total]
    A_balance只用于能量审计，不进入Fisher

M1 order_total_robust:
    每个传播衍射级的S+P总功率
    不再叠加R/T/A
    primary power threshold = 1e-3

M2 order_total_extended:
    每个传播衍射级的S+P总功率
    threshold = 1e-5
    通过绝对噪声底限制弱通道虚假信息

M3 polarization_resolved_diagnostic:
    outgoing S/P功率分别使用
    仅作为具备偏振分析器时的次级场景
```

复振幅、相位和由同一功率重复构造的比例不得进入首轮正式 Fisher。

### 4.5 噪声模型必须有绝对底噪

至少评价：

```text
N1 baseline:
    sigma(y) = sqrt((0.01*y)^2 + (1e-4)^2)

N2 conservative:
    sigma(y) = sqrt((0.02*y)^2 + (5e-4)^2)
```

这些是 provisional DOE scenarios，不得称为实际实验噪声。角度组合排名应报告对 N1/N2 是否稳健。

### 4.6 Fisher 使用无量纲参数尺度

冻结：

```text
s_h = 5 nm
s_w = 1 nm
```

\[
\boldsymbol\theta=
\begin{bmatrix}
(h-h_0)/s_h\\
(w-w_0)/s_w
\end{bmatrix},
\qquad
J_\theta = J_{h,w}\,\mathrm{diag}(s_h,s_w).
\]

对角度集合 \(S\)：

\[
F_S = \sum_{a\in S} J_{\theta,a}^{T}\Sigma_a^{-1}J_{\theta,a}.
\]

必须报告：

```text
rank
minimum singular/eigenvalue
condition number
log det(F)
trace(inv(F))
parameter correlation
scaled and physical CRLB
```

CRLB 只能称为给定 provisional noise 下的局部 DOE 指标。

---

## 5. Task005 执行阶段

### M0：设计、身份与 nominal reuse

- 建立冻结 16-angle design 和 tuple hash；
- 从 train112 精确读取 nominal mother response；
- 建立 perturbation schema、dataset ID、checker；
- 不运行 FEM。

### M1：五角度步长审计

- 每角度运行 coarse/half 两级的 `h-/h+/w-/w+`；
- 一次只运行一个 FEM；
- 第一个未解释 numerical/resource failure 立即停止；
- 通过后分别冻结 `delta_h_production` 和 `delta_w_production`。

### M2：完整 16-angle 灵敏度数据

- 对所有候选角度运行冻结步长的四个扰动；
- 已在 M1 计算的对应记录必须复用；
- 建立不可变 sensitivity dataset；
- 保存 raw response、derivative、step audit、resource/provenance hashes。

### M3：Fisher DOE

穷举并排名：

```text
16 single angles
C(16,2)=120 pairs
C(16,3)=560 triples
C(16,4)=1820 quadruples
```

优先选择：

1. 在 N1/N2 和 M0/M1 下均满秩；
2. 最大化 worst-case minimum eigenvalue；
3. 最大化 worst-case logdet；
4. 最小化 worst-case condition number；
5. 在信息近似时优先更少照明。

输出 top-10 single/pair/triple/quadruple，并与 `(10,0)+(10,90)` 基准对比较。

### M4：最终候选的非线性局部验证

对最终推荐的一个三角度集合，在三个未用于差分的几何上运行直接 FEM：

```text
G1 = h=118.75 nm, w=16.75 nm
G2 = h=121.25 nm, w=17.25 nm
G3 = h=118.75 nm, w=17.25 nm
```

使用 nominal Jacobian 做 noiseless weighted local recovery。建议 readiness Gate：

```text
abs(height recovery error) <= 0.5 nm
abs(width recovery error)  <= 0.1 nm
```

若失败，仍保留 Fisher 排名，但不得创建最终 DOE lock；应在下一任务建立固定照明下的局部非线性结构代理。

### M5：停止等待审阅

仅当 M1–M4 全部通过，建立：

```text
DISCRETE_ILLUMINATION_FISHER_DOE_LOCK.json
```

Task005 到此停止。不得开始正式结构代理、Bayesian inversion 或实验结论。

---

## 6. 资源预算与停止纪律

新 FEM 硬预算：

```text
step audit + 16-angle production + nonlinear validation <= 96 solves
```

可复用完全同 SHA/config/schema 的已有 artifact，但必须通过独立 hash/tuple checker。不得为了满足预算跳过失败点或降低数值 Gate。

本地执行继续使用：

```text
WSL2 native Linux filesystem
max_parallel_forward_solves = 1
OMP/BLAS/MKL/NUMEXPR threads = 1
zero unexplained swap
watchdog只清理自身进程组
```

---

## 7. 本轮授权边界

批准 Codex：

- 建立 Task005 目录、设计、代码、Case131 起的 checker；
- 依照 Task005 task book 执行 M0–M5；
- M1 Gate 通过后可在同一执行轮继续 M2–M4，无需再次等待；
- 最终推送当前唯一代理分支并停止等待审阅。

禁止：

- 修改或恢复 Task004；
- 打开 Task003 或 Task004 validation；
- 使用 P 偏振入射；
- 引入波长、材料或新增结构参数；
- 建立任意角度代理；
- 在 Task005 内开始正式反演。

---

## 8. 给 Codex 的执行入口

```text
请执行 git pull --ff-only，并完整阅读：

1. surrogate_tasks/AGENTS.md
2. surrogate_tasks/task004_nominal_geometry_angle_surrogate/
   TASK004_FINAL_STATUS.json
3. surrogate_tasks/task004_nominal_geometry_angle_surrogate/
   review_report_v9.md
4. surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/
   README.md
5. surrogate_tasks/task005_discrete_illumination_sensitivity_fisher_doe/
   task.md

Task004保持关闭。
从Task005 M0开始，严格执行离散16角度、步长审计、Full3D中央差分、
Fisher DOE和三点非线性验证。

不得运行Task004 blind24，不得开始正式inversion。
```
