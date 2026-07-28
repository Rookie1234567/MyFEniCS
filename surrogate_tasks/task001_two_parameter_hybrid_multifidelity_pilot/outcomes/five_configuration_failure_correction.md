# Task001 M9 五配置失败诊断与受控停止

## 状态

本轮按用户指令停止继续开发，保存为可审阅的 **M9 诊断 checkpoint**。F1 的 trace-map
失败已修正；F2--F5 的物理解经独立 Full3D reference 验证，但 Hybrid P 路径仍未通过原有
正式 Gate。因此不能宣称“五个失败已全部修复”，Task002 继续阻塞。

没有放宽 Gate、提高容差、删除 P、提高掠射角下限或重命名失败状态。Case110 已有 37 个
pass 样本未重跑、未改写；observable schema v2 未修改。

## F1：0.5° / 0° / S

原失败发生在 solver 启动前：正负 reciprocal trace 通过独立数值坐标路径计算，roundoff
被高阶插值和实体归约放大到 `6.988e-8 / 6.308e-8`，超过未改变的 `1e-8` Gate。

修正后 lifted modal coefficient 使用真实 degree，并显式记录 surface quadrature；reciprocal
negative trace 使用同一 canonical coordinate identity，并保留 raw consistency audit；每个
side/role/mode 保存 entity reduction。q12/q14/q18 的最大 interior residual 分别为
`2.7774e-13`、`2.9096e-13`、`2.7774e-13`，slave residual 为零，raw reciprocal
consistency 不超过 `3.4e-16`。这证明 F1 原 trace-map 根因已消除且无需放宽 Gate。

完整求解 checkpoint 的 assembled E 约 `1.3e-6`、energy closure `3.454e-7`；旧
strong-traction density proxy 为 `0.0128`。后续实现把该 proxy 与真正的 variational
conormal dual 分开，避免把 sampled density 当作 exact assembled Gate。

## F2：0.5° / 0° / P

M40/M80/M120/M160 的 interface E 约为 `0.893` 并形成平台；M240/M320/M480 逐渐降低，
M576 continuous 降至 `1.38e-8`。这说明 P trace 需要接近完整 trace rank，M120 不是
收敛表示。standard/static 与 continuous/discrete 的 M120 结果在 roundoff 内一致；独立
reciprocal negative basis、Galerkin test basis、局部 z 加密均未改变根因。

把接口从中间域长度 100 nm 缩到 2 nm 并使用 M576 后，R/T 接近独立 reference，
interface E 为 `2.447e-8`，但 energy closure 仍为 `1.5491e-4`，未通过原 Gate。
middle-domain loss 的体积分 `0.0042349041179860734` 与 Poynting flux
`0.004234904117986632` 相差 `5.59e-16`，排除了 absorption 后处理积分错误。

reconstruction 现显式区分 propagation beta 与 traction beta；E 使用 propagation beta，
H 使用选定 traction beta。exact assembled trace Gate 使用变分 conormal functional dual，
strong traction density L2 只作为 proxy 报告。该诊断修复了度量语义，但没有让 Hybrid P
能量闭合通过正式 Gate。

## F3--F5 与独立 reference

原 Hybrid 失败值保持不变：

| ID | configuration | interface E | interface H | energy closure |
|---|---|---:|---:|---:|
| F3 | 0.5° / 90° / P | 0.8993 | 0.02020 | `8.729e-4` |
| F4 | 10° / 0° / P | 0.6008 | 0.02167 | `2.203e-5` |
| F5 | 10° / 90° / P | 0.6005 | 0.01924 | `2.566e-5` |

没有为得到“pass”而无理由重跑这些 Hybrid 样本。相同配置的独立 global Full3D p4/h10
reference 全部通过 residual 与 energy closure：

| ID | R | T | A | `|1-R-T-A|` |
|---|---:|---:|---:|---:|
| F2 | 0.85842948 | 0.00083315 | 0.14073737 | `6.459e-13` |
| F3 | 0.86093862 | 0.00082812 | 0.13823326 | `1.294e-12` |
| F4 | 0.00183930 | 0.59665798 | 0.40150272 | `1.060e-12` |
| F5 | 0.00181296 | 0.60301099 | 0.39517605 | `1.058e-12` |

因此 P 照明本身和 Full3D 离散解并非失败根因；剩余边界是当前 Hybrid middle
representation/closure 与 p4 Full3D 能量身份不相容。修复它需要新的数值架构决策，已按
用户指令留待后续开发。

## 资源、测试与边界

全部受控 diagnostic 使用 MPI2、zero swap 和 watchdog cleanup。最重的 M576 checkpoint
peak RSS 约 6.7 GiB，没有触发批量 campaign。最终非 PDE 回归为 `68 passed`；JSON、
compileall 和 `git diff --check` 通过。

tracked compact evidence 位于 `benchmarks/cases/111_task001_illumination_robustness/`，raw
artifacts 位于 ignored 的 `benchmarks/artifacts/cases/111/`。实现 checkpoint SHA 为
`13aba78c8ef4645a96871ceaf72eeb751b8eb401`；各 raw artifact 保留实际运行 SHA。

结论：F1 trace repair 可保留；F2--F5 只形成有边界的 negative evidence 和 direct
reference，不得进入正式 Hybrid dataset。Task002、49 点生成、代理训练和反演均未启动。
