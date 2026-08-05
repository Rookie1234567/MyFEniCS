# Task007：Schneider-style objective-GP Bayesian reconstruction benchmark

## 状态

```text
status = authorized_replay_benchmark
execution_branch = codex/only-one-13p5nm-surrogate-inversion
predecessor = Task006 Review V3
new FEM in first execution = 0
formal inversion = false
experimental claim = false
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
