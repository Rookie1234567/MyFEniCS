# Task007：Schneider-style objective-GP Bayesian reconstruction benchmark

## 状态

```text
status = m3_level_a_complete_primary_j1
execution_branch = codex/only-one-13p5nm-surrogate-inversion
predecessor = Task006 Review V3
new FEM in first execution = 0
formal inversion = false
experimental claim = false

M0–M2 stored-response replay 与 M3 Level-A continuous sequential BO 已完成。M3 只调用冻结 Task006 Legendre-3 surrogate oracle：12 个 off-grid h/w targets、J1/J0、N1/N2 固定噪声、连续 oracle MAP、Matérn-5/2 ARD GP、EI query/update 和低 EI bounded local refinement 均已执行。J1 的 Sobol37 P2 在 N1/N2 均为 12/12、median queries-to-MAP 为 3/2，主 Gate 通过；没有运行新 FEM、正式 inversion 或解封 Task006 validation。

Task007 V1 的一次性 posterior-mean P3 负结果保持不可变，标签为 `one_shot_offline_posterior_mean_not_qualified`，不得解释为 Schneider 方法失败。M3 的实现身份为 `555abf1`，完整结果见 `outcomes/summary_m3.md` 和 `response_v2.md`。
```

## 核心思想

本任务参考：

- P.-I. Schneider et al., *Using Gaussian process regression for efficient parameter reconstruction*, Proc. SPIE 10959, 1095911 (2019), DOI `10.1117/12.2513268`；
- JCMwave 博客：`https://jcmwave.com/blog/2019-schneider-1/`。

与 Task003/004/006 的多输出前向代理不同，本任务针对一组给定 measurement vector，直接构造并学习一个标量反演目标：

\[
(h,w)\mapsto \log_{10}\bigl(F(h,w\mid y_M)+\epsilon_F\bigr).
\]

Gaussian process 近似的是 objective / negative log posterior，而不是 Maxwell response vector。Bayesian optimization 使用 expected improvement 选择下一组参数。

## 我们自己的物理设置

```text
height h in [115,125] nm
width  w in [16,18] nm
wavelength = 13.5 nm
incident polarization = S
A05 = grazing 2 deg, azimuth 0 deg
A07 = grazing 2 deg, azimuth 90 deg
A09 = grazing 4 deg, azimuth 60 deg
forward identity = Full3D static p5/h10/Ny4
```

第一版 primary measurement contract 使用三个照明下的稳健 m=0 反射/透射总功率，共 6 个观测量；aggregate R/T 作为独立 secondary benchmark，二者不得在同一个 objective 中重复计数。

## 首轮数据

只读复用：

```text
37 个 Task006 train geometries：offline objective training source
11 个 Case141 三照明完整 geometries：external replay targets / query pool
```

不完整几何 `(117.5,17.25)` 不进入首轮 benchmark。

## 首轮目的

回答三个问题：

1. 对每个给定 synthetic measurement，37 个预计算 response 是否足以训练一个可靠的二维 scalar objective GP？
2. offline-trained Bayesian optimization 是否比 cold-start BO 和 random search 更少地查询 replay oracle？
3. 两参数 MAP reconstruction 是否能在自己的尺寸范围内稳定恢复隐藏几何？

首轮完成后停止等待审阅。完整合同见 `task.md`。
