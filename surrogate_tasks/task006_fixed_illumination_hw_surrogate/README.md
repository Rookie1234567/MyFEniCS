# Task006：固定三照明的高度/宽度结构代理

## 状态

```text
status = controlled_stop_blind_forward_incomplete
execution_branch = codex/only-one-13p5nm-surrogate-inversion
predecessor = Task005 Review V2
purpose = fixed A05/A07/A09 S-polarized h/w forward surrogate qualification
model_lock = created before blind, immutable after blind
blind = 36 original attempts (34 pass, 2 true-residual failures); 4 authorized retries (0 pass)
formal inversion = not authorized
active learning = not authorized
```

本任务先完成一次且仅一次的 12 个 blind geometry × A05/A07/A09 批次。由于
`117.5,17.25/A07` 和 `117.5,17.25/A09` 的固定真实残差 Gate
`true_residual_le_1e-9` 为 false，Review V2 授权的 M3R 先完成 Case143 无 FEM
检查，再对两个 tuple 各进行两次完全相同身份的 fresh-process 重试。四次重试
均以同一 residual Gate 失败，且重复 observable 一致，因此本任务按
`controlled_stop_blind_forward_incomplete` 停止；原始负结果和重试负结果均保留。
Case141/Case144 checker 的 `pass` 只表示证据身份、失败分类和重复一致性检查
正确，不表示代理资格通过。

## 固定物理与照明

```text
wavelength_nm = 13.5
incident_polarization = S
height_nm in [115,125]
width_nm in [16,18]

A05 = grazing 2°, azimuth 0°
A07 = grazing 2°, azimuth 90°
A09 = grazing 4°, azimuth 60°

forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
forward_model = Full3D static uniform N1curl p5/h10/Ny4
mesh = (6,4,14)
MUMPS ICNTL(14) = 40
MPI2 / thread1
observable = task002.fixed-n0-orders.v3
```

## 输入与输出合同

输入只有 `(height_nm, width_nm)`。S0 输出每个固定照明的
`R_total, T_total, A_balance`，使用 log-ratio composition latent 和
softmax 恢复；S0 同时是 production S1 的唯一 side-total authority。S1 输出
冻结反射/透射 m=0 primary channel 的 selected power、other power、side total
和逐点 ledger residual。任何 failed FEM 都不能生成 production sample。

## 已完成阶段

- M0/M1：49 点 mother grid、37 点 training、12 点 blind 设计冻结；79 个新
  FEM 和 32 条 exact reuse 建立不可变 train37 dataset。
- M2R：S0/S1 authority 修正、geometry folds 冻结、固定六候选 training-only
  CV、uncertainty 和 synthetic recovery 完成；M2R selected candidate 为
  `legendre_3`。Case139 deterministic replay 通过。
- model lock：`TASK006_MODEL_SELECTION_LOCK.json` 在 blind 前创建并绑定所有
  dataset、solver、合同、fold、candidate 和 blind tuple identity。
- blind：固定锁和 forward SHA 下串行执行 36 个 FEM；Case141 checker 独立确认
  34 个 success、2 个 true-residual failures，无调参或 response leakage。
- M3R：Case143 无 FEM checker 通过；两个失败 tuple 各完成两次固定身份重试，
  4/4 均重现 `true_residual_le_1e-9` 失败；Case144 只确认负结果身份和重复
  一致性，未建立 canonical retry 或 12/12 qualification package。

完整结果、Gate 数值、失败 formal records、重试遥测和停止边界见
`outcomes/summary.md`、`outcomes/TASK006_BLIND_FAILURE_REPORT.json`、
`outcomes/TASK006_BLIND_FORWARD_RETRY_CLOSEOUT.json`、
`outcomes/BLIND_FORWARD_FAILURE_TELEMETRY.json` 和 `response_v3.md`。

## 明确禁止

```text
不得再次重跑这两个 tuple 或用其调参后再次宣称 blind validation
不得把四次受控失败重试作为 canonical production sample
不得把34条原成功记录与本次失败重试混合成12/12 qualification package
不得主动加点或开始 Task007
不得开始正式 Bayesian inversion
不得扩展连续角度、P 偏振、波长、材料或新的几何参数
不得访问 Task003 frozen validation
```
