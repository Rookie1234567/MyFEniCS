# Task004 response V2

本轮完成了 Review V1 要求的 M0R、M1R、M2R 和 M3R 前向资格化，且保留了
Case123 的所有冻结 angle tuples。正式数值记录统一绑定 clean implementation
SHA `fdf961545f217d620e22800f2704ae9913a6d270`：Full3D static uniform N1curl
p5/h10、axis counts `(6,4,14)`、MPI2、每 rank 单线程、S polarization、
observable-v3。

结果如下：

- 原失败点的 ICNTL(14) ladder 在 40% 下两个独立 fresh-process full solves
  都通过，actual observed value 也是 40%，因此冻结最小稳定值 40；没有运行
  不必要的 80/120，也没有使用 OOC/BLR 或放宽任何 Gate。
- 五个 anchors `(0.5,0)`、`(0.5,90)`、`(10,0)`、`(10,90)`、`(5.25,45)`
  全部通过 residual、energy、fixed-order power、runtime topology、zero-swap
  和 comparer identity Gate。最大 aggregate 差异为 `1.17e-14`，最大 shared
  power 差异为 `1.17e-14`，最大 shared complex-amplitude 差异为 `1.65e-14`。
- 16 个 training canary 全部 `measured_pass` 后，继续完成其余 80 个点；
  96/96 training FEM 最终均为 `measured_pass`。全部 103 个正式记录（2 个
  ladder + 5 个 anchors + 96 个 training）均为同一 SHA、同一 model/route、
  同一 observable schema，且没有 swap。
- training index 0 的第一次启动只因误用了非 baseline interpreter 而得到
  `interrupted_retryable` preflight；该 attempt 在 PDE 之前停止，未产生数据，
  随后的 baseline fresh process 通过。它不是 numerical failure，也没有覆盖
  原目录证据。

本轮仍然没有读取或运行 24 个 blind-validation FEM，没有创建
`ANGLE_MODEL_SELECTION_LOCK`，没有做 surrogate training/CV、active learning、
angle DOE、Fisher ranking、geometry sensitivity 或 inversion。Task003 Round3
及其 frozen validation 也保持封存。下一步应先由 ChatGPT 审阅本轮 clean-SHA
和 96-point training evidence，再决定是否进入 training-only dataset/CV；在
审阅前不自动解封 validation。

独立复核入口：
`benchmarks/cases/124_task004_mumps_workspace_and_anchor_requalification/checker.py`。
