# Task004 Response V6：Required M4G 完成与受控停止

## 1. 范围与不可变身份

本轮执行了 Review V5 的 M4G，仅读取不可变 train112 和已冻结的
response-blind angle design。没有运行 training FEM、第二轮主动学习、24 个
blind FEM，也没有访问 blind responses、Task003 数据、Fisher、geometry
sensitivity 或 inversion。

| identity | value |
|---|---|
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| training rows / tuple hash | 112 / `00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68` |
| model / route | `S_PROD_FULL3D_STATIC_P5_H10_NY4` / `full3d_static_uniform_n1curl_p5_h10_ny4` |
| M4G implementation SHA | `44e9831d4cfae0c95b4e02d59effd6c6fa0b4270` |
| fold seed / fold hash | `20260731` / `8fce8712ec33b7b6913cc5a9d4d7b79e5db773705e4c0403b08fffd753d7f7e8` |

## 2. 冻结 folds 与完整 OOF

`TRAIN112_LOCAL_REFERENCE_FOLDS.json` 固定五折 outer split；112 个样本每个
恰好一次成为 test，保存 old96/new16 身份、tuple、mask-signature support、
nearest training distance 分布和 fold hash。它在局部模型拟合前冻结，之后只
做 provenance SHA 重绑定，没有改变 split 行。

以下四个候选在完整 112 点 outer OOF 上运行：
local RBF k24、local Matérn k24、local Matérn k32、degree-2 trend + local
residual k24。每点 OOF 记录包含 truth/prediction/std/error、fold、邻域 tuple、
fitted kernel/LML/warning、cutoff/mask/region 和 old96/new16 标签。

| candidate | R NRMSE | T NRMSE | A NRMSE | max selection score | supported window | uncertainty | Aggregate A |
|---|---:|---:|---:|---:|---|---|---|
| local RBF k24 | 0.017540 | 0.023495 | 0.036288 | 3.84925 | fail | pass | fail |
| trend + local residual k24 | 0.017030 | 0.024232 | 0.036689 | 4.07189 | fail | pass | fail |
| local Matérn k24 | 0.027526 | 0.018068 | 0.035200 | 4.33840 | pass | fail | fail |
| local Matérn k32 | 0.027062 | 0.023869 | 0.038534 | 4.76395 | pass | fail | fail |

training-CV 选择的是 `L1_local_rbf_k24_s1e-08`，但它仍有
`A_balance` p95=`0.038492`、`T_total` p95=`0.025298`，且 supported-window
Gate 未通过。故不能创建 Aggregate model lock。

## 3. 两种有限集成

E1 在 `zR/zT` latent 中对前三个局部候选取逐点 median，再用 softmax 恢复
R/T/A。E2 只用每个 outer-training 内部的 inner-OOF，以每个 latent target
学习非负且和为 1 的三模型权重；outer-test 从未参与权重学习。

| ensemble | R NRMSE | T NRMSE | A NRMSE | supported window | uncertainty | Aggregate A |
|---|---:|---:|---:|---|---|---|
| E1 latent median | 0.026118 | 0.019499 | 0.037083 | pass | fail | fail |
| E2 non-negative stack | 0.023031 | 0.017979 | 0.035779 | fail | fail | fail |

两种集成都保持 composition exact，但没有同时满足 NRMSE、p95、max、窗口和
cross-fitted coverage 的完整 Level A 合同。没有模型锁，也不允许运行 blind。

## 4. outlier audit 与安全域诊断

`POST_ACTIVE_OUTLIER_AUDIT` 对每个 target 列出 10 个最高 absolute-error 点，
并从冻结距离、cutoff margin、boundary、model disagreement 和邻域证据重建
分类：`coverage_hole`、`cutoff_high_curvature`、`boundary_one_sided`、
`model_instability` 或 `unexplained`。其中主要异常集中在 cutoff/high-azimuth
邻域；新增 16 点也有少数残余异常，不能声称加点已完全闭合空洞。

作为次级、非生产诊断，candidate4096 的结构安全域规则排除未见 mask
signature，得到 `4074/4096 = 0.99462890625` 的 structural support。该文件
明确声明未应用 response-dependent model disagreement 到 candidate pool，且
`full_domain_model_lock=false`；它不替代完整域资格，也不触发 FEM。

## 5. Aggregate / Order 独立结论

Aggregate Level A：`not_qualified_full_domain`。Order Level B 使用训练-CV
选中的 RBF k24 aggregate OOF 重新计算：mask agreement=100%、sidewise ledger
最大误差=`2.220446049250313e-16`，但 primary channel 最大 NRMSE=`0.405996`
且 p95/max 超限，因此 `order_resolved_qualified=false`。

配对报告现在使用 `paired_reference_candidate`，并明确
`diagnostic_only_not_model_lock=true`；不再写入误导性的
`selected_final_candidate`。

本轮按 Review V5 停止，等待 Review V6。禁止第二轮主动学习、任何新 FEM、
blind validation、Fisher、geometry sensitivity 和 inversion。
