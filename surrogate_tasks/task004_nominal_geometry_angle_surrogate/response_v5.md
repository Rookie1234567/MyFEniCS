# Task004 Response V5：M4E2/M4F 完成与受控停止

## 1. 执行边界与身份

本轮从 Review V4 的 M4E2 开始。M4E2 先在不可变 train96 和
response-blind candidate pool 上完成，随后按 Gate 直接执行唯一一轮 16 点
M4F；没有访问 validation response，没有执行第二轮主动学习、Task003
Round3、Fisher、geometry sensitivity 或 inversion。

| 身份 | 值 |
|---|---|
| branch | `codex/only-one-13p5nm-surrogate-inversion` |
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| model / route | `S_PROD_FULL3D_STATIC_P5_H10_NY4` / `full3d_static_uniform_n1curl_p5_h10_ny4` |
| mesh / workspace / MPI / thread | `(6,4,14)` / ICNTL(14)=40 / 2 / 1 |
| M4E2 implementation identity | `fee256d732b97767a38d1cc8aa0fb3acecd4da50` |
| train112 dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| train112 tuple hash | `00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68` |

## 2. M4E2 Gates

V2 文件保持不可变；V3 从实际角度坐标重新计算 nearest-support distance，
并用凸包、方向扇区和边界内侧支撑分类
`interior_bracketed / boundary_one_sided_supported /
unsupported_extrapolation`。checker 不信任记录中的布尔值。OOF map 为
RBF k24、Matérn k24/k32、trend-residual，并保留 F4 Matérn k24/k32 的有限
比较；每点包含 truth/prediction/error/std、fold、距离、cutoff、mask、region
和邻居身份。

acquisition quality 的六类信号均未与误差明显反相关；例如 native Matérn
k24 对 `max_error` 的 Spearman 为 `0.86560`、top-20% error recall 为
`0.65`，k32 分别为 `0.85707/0.60`，ensemble Gate 为 `true`。独立 checker
重算 quality 和恰好 16 点 plan，plan tuple hash 为
`c603545cb9266485e03029b91b7dc0fcd4da65a8177fdf868704a9c18610bf51`，最小
归一化两两距离 `0.03994165 ≥ 0.035`，所有 split 隔离和类别下限通过。

## 3. 唯一 16 点 M4F

16 点均使用固定 forward SHA、p5/Ny4、ICNTL(14)=40、MPI2/thread1 和
`compact_surrogate_record`。每个点的 residual、power ledger、mask、runtime
topology、RSS/PSS/USS、swap 和 hash 均保存在 ignored FEM artifact 中；
`case127_post_fem_check.json` 独立重算并报告：

```text
campaign exact measured_pass = 16/16
compact-record and numerical/resource gates = pass
validation_target_accessed = false
peak process-tree RSS ≈ 6.112–6.264 GB; swap = 0
elapsed ≈ 115.6–163.6 s per point
```

campaign manifest 中保留了两次只发生在 PDE 启动前的历史 preflight retry；
最终 resume 没有跳过 numerical failure，并完成 16/16 measured pass。

## 4. train112 与重新资格化

train112 是原 train96 不可变前缀加 16 个新点，独立 checker 重新计算文件
hash、array identity、tuple hash 和 manifest identity，结果为 `pass`。随后
在同一原 train96 test rows 上完成 paired 96→112 learning curve，并对 112
点运行标准五折 training-only CV。

CV 按有限候选真实选择 `gp:F3`, jitter `1e-8`，而不是硬编码模型。其 Level A
结果为：

| target | NRMSE | p95 abs | max abs |
|---|---:|---:|---:|
| `R_total` | 0.0246633 | 0.0370765 | 0.1080872 |
| `T_total` | 0.0120798 | 0.0140645 | 0.0360235 |
| `A_balance` | 0.0332836 | 0.0329176 | 0.1101640 |

composition exact 和 cross-fitted coverage（R/T/A=`0.9464/0.9643/0.9732`）
通过，但 accuracy、supported-window 和 order power Gate 未同时通过。
因此：

```text
aggregate_qualified = false
order_resolved_qualified = false
ANGLE_AGGREGATE_MODEL_SELECTION_LOCK = absent
blind validation = sealed / not run
```

paired 曲线显示 local Matérn k24 最大误差由 `0.1443802` 降到 `0.0932643`，
但仍未达到 Gate；local Matérn k32 几乎没有改善，不能选择性宣称成功。

## 5. 交付与停止

交付内容包括 `SUPPORTED_INTERPOLATION_WINDOWS_V3.json`、M4E2 OOF/quality/
plan、Case127 pre/post/train112 独立 checker、16 点 compact artifact、
train112 manifest、paired learning curve、aggregate/order v3 qualification
和 `outcomes/test_summary_v5.md`。当前停止等待 ChatGPT Review V5；不创建模型锁，
不运行 blind validation 或任何第二轮 FEM。
