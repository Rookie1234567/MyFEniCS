# Outcome Summary

## Task

task008：50 x 25 x 140 nm 目标尺寸、80 deg 斜入射、official DtN-port R/T/A 本机 benchmark 与资源边界。

## Branch

`codex/20260706-target-50x25x140-oblique80-official-benchmark`

## 运行设置

| item | value |
| --- | --- |
| domain size | 50 x 25 x 140 nm |
| period | 50 x 25 nm |
| grating size | 17 x 25 x 120 nm |
| substrate thickness | 10 nm |
| top air above grating | 10 nm |
| air_height parameter | 130 nm |
| incident angle | theta_from_z = 80 deg, phi = 0 deg |
| incident plane | x-z |
| polarization | s, E along y |
| material n | substrate/grating = 0.999002304859 + 0.00182649365j |
| power source | dtn_port_modal_amplitudes + A_volume |
| solver | default MUMPS direct, MPI=8 |

## Geometry Validation

| check | result | note |
| --- | --- | --- |
| domain height | 通过 | air_height=130 nm, substrate=10 nm，总高 140 nm |
| grating_width_y = period_y | 通过 | mesh builder 支持 full-span y，未使用 24.999 nm fallback |
| material tags | 通过 | grating 为 17 x 25 x 120 nm，y 方向全周期填充 |
| Floquet side boundary | 通过 | full-span y grating 与 y 周期边界无输入冲突 |
| Results 输出 | 通过 | results 运行目录仍保留，git 只提交轻量 raw_runs |

## Oblique Incidence Validation

| item | value | note |
| --- | --- | --- |
| theta_from_z | 80 deg | 从上方空气向下传播 |
| phi | 0 deg | 横向波矢在 x 方向，ky=0 |
| kx | 0.458350341046 | kx/k0=0.984807753012 |
| ky | 0 | ky/k0=0 |
| kz | -0.0808195317434 | kz/k0=-0.173648177667, downward |
| Floquet phase x | -0.600741134898 + -0.799443612046j | exp(i*kx*Lx) |
| Floquet phase y | 1 + 0j | exp(i*ky*Ly) |
| polarization | (0, 1, 0) | s polarization |
| k dot E | 0.000e+00 | 应接近 0 |
| DtN port modes | top/bottom = 40/40, total = 80 | 周期小于旧 100 x 100 nm 案例，模式数低于旧 708 |

## Assemble-Only Matrix-Scale 资源评估

| p | h/nm | status | cells | dofs | aux modes | rows | nnz | A matrix GB | RSS upper GB | elapsed s | last stage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | completed | 1680 | 6157 | 80 | 6237 | 2.278e+05 | 0.00514 | 2.21 | 11.04 | stage4_dtn_augmented_matrix_finalized |
| 1 | 4 | completed | 3780 | 13192 | 80 | 13272 | 4.776e+05 | 0.0108 | 2.11 | 3.476 | stage4_dtn_augmented_matrix_finalized |
| 1 | 3 | completed | 7776 | 26319 | 80 | 26399 | 9.361e+05 | 0.0211 | 2.23 | 3.477 | stage4_dtn_augmented_matrix_finalized |
| 1 | 2.5 | completed | 11760 | 39259 | 80 | 39339 | 1.385e+06 | 0.0313 | 2.27 | 4.329 | stage4_dtn_augmented_matrix_finalized |
| 1 | 2 | completed | 24570 | 80122 | 80 | 80202 | 2.791e+06 | 0.063 | 2.49 | 5.783 | stage4_dtn_augmented_matrix_finalized |
| 1 | 1.5 | completed | 54332 | 173885 | 80 | 173965 | 5.987e+06 | 0.135 | 2.86 | 9.068 | stage4_dtn_augmented_matrix_finalized |
| 1 | 1 | completed | 178500 | 559546 | 80 | 559626 | 1.902e+07 | 0.429 | 4.47 | 21.58 | stage4_dtn_augmented_matrix_finalized |
| 2 | 5 | completed | 1680 | 44698 | 80 | 44778 | 4.896e+06 | 0.11 | 2.8 | 22.28 | stage4_dtn_augmented_matrix_finalized |
| 2 | 4 | completed | 3780 | 98012 | 80 | 98092 | 1.061e+07 | 0.238 | 3.25 | 12.31 | stage4_dtn_augmented_matrix_finalized |
| 2 | 3 | completed | 7776 | 198438 | 80 | 198518 | 2.132e+07 | 0.478 | 4.31 | 22.14 | stage4_dtn_augmented_matrix_finalized |
| 2 | 2.5 | completed | 11760 | 297982 | 80 | 298062 | 3.190e+07 | 0.715 | 5.73 | 32.53 | stage4_dtn_augmented_matrix_finalized |
| 2 | 2 | completed | 24570 | 615108 | 80 | 615188 | 6.545e+07 | 1.47 | 8.91 | 69.68 | stage4_dtn_augmented_matrix_finalized |
| 2 | 1.5 | completed | 54332 | 1347234 | 80 | 1347314 | 1.427e+08 | 3.2 | 13.9 | 240.1 | stage4_dtn_augmented_matrix_finalized |
| 2 | 1 | timeout | 178500 | 4379752 | 80 | 4379752 | 4.599e+08 | 10.3 | 14.1 | 2407 | stage4_dtn_base_matrix_assembled |

## Direct Solve Boundary

| p | last completed h | first failed h | failure stage | matrix GB | RSS upper GB | note |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1.0 | - | not_reached | 0.429 | 18.1 | p=1 在计划网格内 h=1 direct completed；未继续尝试 h<1。 |
| 2 | 2.0 | 1.5 | default_direct_signal9 | 3.2 | 14.4 | p=2 h=1.5 default direct 在 KSP setup 阶段被 signal 9 kill；p=2 h=1 assemble-only 已先超时。 |
| 2 | 2.0 | 1.0 | assemble_only_timeout | 10.3 | 14.1 | p=2 h=1 未进入 direct 计划；assemble-only 在 base matrix assembled 后 2400 s 超时并出现大量 swap。 |

## p=1 Official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | dR prev | dT prev | dA prev | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 0.999977 | 7.567214e-06 | 1.565155e-05 | 1 | -1.887e-15 | - | - | - | completed |
| 1 | 4 | 0.99987 | 1.227806e-05 | 1.172440e-04 | 1 | -1.776e-15 | -1.063e-04 | 4.711e-06 | 1.016e-04 | completed |
| 1 | 3 | 0.999535 | 7.299528e-06 | 4.579219e-04 | 1 | -2.220e-15 | -3.357e-04 | -4.979e-06 | 3.407e-04 | completed |
| 1 | 2.5 | 0.998606 | 4.473059e-06 | 0.00138971 | 1 | 4.219e-15 | -9.290e-04 | -2.826e-06 | 9.318e-04 | completed |
| 1 | 2 | 0.991687 | 2.984621e-06 | 0.00831009 | 1 | -7.438e-15 | -0.00692 | -1.488e-06 | 0.00692 | completed |
| 1 | 1.5 | 0.944379 | 4.262951e-05 | 0.0555787 | 1 | 1.599e-14 | -0.0473 | 3.964e-05 | 0.0473 | completed |
| 1 | 1 | 0.094582 | 0.423887 | 0.481531 | 1 | -2.265e-14 | -0.85 | 0.424 | 0.426 | completed |

p=1 的结果从 h=5 到 h=1 变化很大，h=1 才进入接近 p=2 粗网格趋势的区域，因此 p=1 不应作为最终物理收敛结论，只适合作为本机可跑边界和低阶对照。

## p=2 Official R/T/A 收敛

| p | h/nm | R | T | A_volume | R+T+A | closure | dR prev | dT prev | dA prev | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 5 | 0.0890216 | 0.442588 | 0.46839 | 1 | -7.061e-14 | - | - | - | completed |
| 2 | 4 | 0.00355403 | 0.561917 | 0.434529 | 1 | 4.041e-14 | -0.0855 | 0.119 | -0.0339 | completed |
| 2 | 3 | 0.00461303 | 0.583653 | 0.411734 | 1 | -3.324e-13 | 0.00106 | 0.0217 | -0.0228 | completed |
| 2 | 2.5 | 0.00271219 | 0.592824 | 0.404464 | 1 | 7.860e-14 | -0.0019 | 0.00917 | -0.00727 | completed |
| 2 | 2 | 0.00134293 | 0.599213 | 0.399444 | 1 | -1.066e-14 | -0.00137 | 0.00639 | -0.00502 | completed |

p=2 从 h=5 到 h=2 的 official R/T/A 呈现更可信的趋势：R 降到约 1.34e-3，T 升到约 0.599，A_volume 降到约 0.399。h=1.5 direct 被 kill，因此本机 default direct 的 p=2 最细完成点是 h=2。

## p=1 vs p=2 对照

| comparison | R abs diff | T abs diff | A abs diff | note |
| --- | --- | --- | --- | --- |
| h=5 common mesh | 0.91096 | 0.44258 | 0.46837 | 同一 h，对比低阶/高阶离散差异。 |
| h=3 common mesh | 0.99492 | 0.58365 | 0.41128 | 同一 h，对比 p 阶差异。 |
| h=2 common mesh | 0.99034 | 0.59921 | 0.39113 | p=2 h=2 是本机完成的最细 p=2 direct。 |
| finest completed | 0.093239 | 0.17533 | 0.082087 | 本轮本机最细完成点对比，不是同一 h。 |

p=1 finest 与 p=2 finest 仍不接近，说明本任务不能把 p=1 h=1 当成可靠替代；后续若追求最终物理 benchmark，应优先走 p=2 更细网格的迭代法或更大内存机器。

## Direct Solve 资源规模

| p | h/nm | cells | dofs | rows | nnz | A matrix GB | RSS upper GB | elapsed s | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 1680 | 6157 | 6237 | 2.278e+05 | 0.00514 | 2.33 | 130.8 | completed |
| 1 | 4 | 3780 | 13192 | 13272 | 4.776e+05 | 0.0108 | 2.47 | 120.9 | completed |
| 1 | 3 | 7776 | 26319 | 26399 | 9.361e+05 | 0.0211 | 2.83 | 127.4 | completed |
| 1 | 2.5 | 11760 | 39259 | 39339 | 1.385e+06 | 0.0313 | 3.24 | 121.5 | completed |
| 1 | 2 | 24570 | 80122 | 80202 | 2.791e+06 | 0.063 | 4.76 | 136.4 | completed |
| 1 | 1.5 | 54332 | 173885 | 173965 | 5.987e+06 | 0.135 | 8.84 | 180.2 | completed |
| 1 | 1 | 178500 | 559546 | 559626 | 1.902e+07 | 0.429 | 18.1 | 1167 | completed |
| 2 | 5 | 1680 | 44698 | 44778 | 4.896e+06 | 0.11 | 3.82 | 145.9 | completed |
| 2 | 4 | 3780 | 98012 | 98092 | 1.061e+07 | 0.238 | 6.33 | 142.2 | completed |
| 2 | 3 | 7776 | 198438 | 198518 | 2.132e+07 | 0.478 | 11.9 | 194.8 | completed |
| 2 | 2.5 | 11760 | 297982 | 298062 | 3.190e+07 | 0.715 | 14.8 | 327.9 | completed |
| 2 | 2 | 24570 | 615108 | 615188 | 6.545e+07 | 1.47 | 20.5 | 1666 | completed |
| 2 | 1.5 | 54332 | 1347234 | 1347314 | 1.427e+08 | 3.2 | 14.4 | 1291 | failed |

## Diagnostic vs Official 差异

| p | h/nm | R official | R diagnostic EH | T official | T diagnostic EH | note |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 0.99998 | 0.30276 | 7.56721e-06 | 5.56303e-06 | diagnostic 不作为 official |
| 1 | 4 | 0.99987 | 0.51348 | 1.22781e-05 | 1.18094e-05 | diagnostic 不作为 official |
| 1 | 3 | 0.99953 | 0.41649 | 7.29953e-06 | 7.23347e-06 | diagnostic 不作为 official |
| 1 | 2.5 | 0.99861 | 0.50705 | 4.47306e-06 | 4.30964e-06 | diagnostic 不作为 official |
| 1 | 2 | 0.99169 | 0.64056 | 2.98462e-06 | 2.82225e-06 | diagnostic 不作为 official |
| 1 | 1.5 | 0.94438 | 0.77021 | 4.26295e-05 | 4.31321e-05 | diagnostic 不作为 official |
| 1 | 1 | 0.094582 | 0.08442 | 0.42389 | 0.43922 | diagnostic 不作为 official |
| 2 | 5 | 0.089022 | 0.148 | 0.44259 | 0.34698 | diagnostic 不作为 official |
| 2 | 4 | 0.003554 | 0.014663 | 0.56192 | 0.48143 | diagnostic 不作为 official |
| 2 | 3 | 0.004613 | 0.013913 | 0.58365 | 0.52793 | diagnostic 不作为 official |
| 2 | 2.5 | 0.0027122 | 0.0086055 | 0.59282 | 0.55626 | diagnostic 不作为 official |
| 2 | 2 | 0.0013429 | 0.0042359 | 0.59921 | 0.57951 | diagnostic 不作为 official |

probe-plane E/H Fourier diagnostic 与 official DtN-port modal 仍存在显著差异，尤其粗网格或低阶下更明显。本轮所有 official `R_total/T_total` 均来自 `dtn_port_modal_amplitudes`，diagnostic 只用于观察。

## Key Results

- 新目标尺寸已按 50 x 25 x 140 nm 建模，`grating_width_y = period_y = 25 nm` 被原代码合法支持。
- 80 deg 斜入射已按 x-z 平面、phi=0、s polarization 设置，`ky=0` 且 `k dot E = 0`。
- assemble-only：p=1 完成 h=5 到 h=1；p=2 完成 h=5 到 h=1.5，p=2 h=1 在 base matrix assembled 后超时并产生约 33.4 GB swap 增量。
- direct：p=1 完成 h=5 到 h=1；p=2 完成 h=5 到 h=2，p=2 h=1.5 在 `stage4_dtn_augmented_ksp_setup` 被 signal 9 kill。
- 能量闭合：completed direct case 的 `R+T+A_volume` 均为 1 到约 1e-13 量级误差，说明 official port modal + volume absorption 口径自洽。
- 80 deg 下 R 明显不再是垂直入射旧案例那种接近零的量级；p=2 h=2 得到 R≈0.00134，p=2 h=5 粗网格 R≈0.089 说明网格/阶次敏感。

## 当前固定 Benchmark 建议

| benchmark | recommended use | reason |
| --- | --- | --- |
| p=1 h=1 direct | 低阶本机压力测试/对照 | 能完成但与 p=2 finest 不接近 |
| p=2 h=2 direct | 当前本机 official benchmark 主结果 | 本机 default direct 最细完成点，能量闭合正常 |
| p=2 h=1.5 direct failed | 本机 direct failure boundary | KSP setup signal 9，可用于估算 workstation/OOC/迭代法需求 |
| p=2 h=1 assemble timeout | 更细 direct 禁止点 | assemble-only 已超时并产生大量 swap |

## Known Issues

- p=2 h=1.5 assemble-only 的矩阵规模约 3.20 GB AIJ，但 default MUMPS direct 在 KSP setup 阶段被 kill；瓶颈不是矩阵存储本身，而是 LU fill-in / factorization setup 的额外内存峰值。
- p=2 h=1 assemble-only 已经需要约 10.31 GB AIJ 估算矩阵并出现大量 swap，不适合继续 default direct。
- 本轮没有引入迭代法，也没有强制尝试 tuned MUMPS OOC；建议后续单独开任务处理。

## Next Questions for Review

1. 是否接受 p=2 h=2 作为当前本机 official benchmark 主结果？
2. 后续是优先尝试 p=2 h=1.5 的 tuned MUMPS OOC，还是直接转向迭代法？
3. 是否需要新增 common reference plane / interface-referenced T，以便不同 domain height 的 T/A 可比？
4. 是否需要把 `direct_solve_plan.md` 的边界预测在 review 后进一步固化为 README 中的推荐运行矩阵？
