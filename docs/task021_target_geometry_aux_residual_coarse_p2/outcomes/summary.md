# Outcome Summary

## 任务

Task021 在目标几何上重新验证 `DtN auxiliary residual-aware adaptive coarse correction`，重点解决 p=2 h=5 的真实残差不收敛问题。上一轮 task020 的 `default100` 算法沙盒结论只作为路线参考，本轮所有核心数据均切回 task008 目标物理模型。

## 分支

`codex/20260709-task20-wave-solver-search`

## 模型确认

| 项目 | 本轮设置 | 结论 |
|---|---:|---|
| domain | 50 x 25 x 140 nm | 已确认 |
| period | 50 x 25 nm | 已确认 |
| grating | 17 x 25 x 120 nm | 已确认 |
| substrate thickness | 10 nm | 已确认 |
| top air above grating | 10 nm | 已确认 |
| air_height | 130 nm | 已确认 |
| incident angle | theta_from_z = 80 deg, phi = 0 deg | 已确认 |
| polarization | s, E along y | 已确认 |
| material n | 0.999002304859 + 0.00182649365j | 已确认 |
| boundary | double Floquet x/y + auxiliary DtN port | 已确认 |
| auxiliary modes | top 40 + bottom 40 = 80 | 已确认 |

## 运行命令

```text
docker run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work/fenics_vector_maxwell_floquet_demo_v2_parallel ghcr.io/jorgensd/dolfinx_mpc:v0.10.5 sh -lc '. /usr/local/bin/dolfinx-complex-mode && python -m py_compile src/postprocessing/postprocess.py src/studies/run_task021_target_aux_coarse.py'

docker run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work/fenics_vector_maxwell_floquet_demo_v2_parallel ghcr.io/jorgensd/dolfinx_mpc:v0.10.5 sh -lc '. /usr/local/bin/dolfinx-complex-mode && python -m src.studies.run_task021_target_aux_coarse --only-p2 --baseline-maxiter 5 --solver-maxiter 5 --coarse-dims 1 2 --fe-methods diag --rtol 1e-6'

docker run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work/fenics_vector_maxwell_floquet_demo_v2_parallel ghcr.io/jorgensd/dolfinx_mpc:v0.10.5 sh -lc '. /usr/local/bin/dolfinx-complex-mode && python -m src.studies.run_task021_target_aux_coarse --baseline-maxiter 80 --solver-maxiter 80 --coarse-dims 1 2 4 8 16 32 40 80 --fe-methods diag spilu splu --rtol 1e-6'
```

## 资源预检

| case | p | h_nm | rows | nnz | FE dofs | aux dofs | RSS upper GB | DtN assembly s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target_p1_h5 | 1 | 5.0 | 6237 | 227751 | 6157 | 80 | 0.229 | 4.35 |
| target_p2_h5 | 2 | 5.0 | 44778 | 4896156 | 44698 | 80 | 0.693 | 27.00 |

本表为 task021 serial SciPy research runner 的进程 RSS 上界；task008 的 MPI=8 assemble-only p=2 h=5 RSS upper 约 2.80 GB，可作为并行装配资源参照。

## Baseline

| case | solver | status | true residual | gate | 说明 |
|---|---|---|---:|---|---|
| target_p1_h5 | GCROT(m,k) + Jacobi | not_converged, 80 history points | 4.520105e-5 | strong | 未达到 1e-6 production-like，但已强通过 |
| target_p2_h5 | GCROT(m,k) + Jacobi | not_converged, 80 history points | 2.025767e-1 | fail | p=2 baseline 是主要问题 |

## p=2 残差主导模式

| 排名 | local aux index | global row | side | Rayleigh order | polarization | propagating | aux residual abs | total fraction |
|---:|---:|---:|---|---|---|---|---:|---:|
| 1 | 38 | 44736 | top | (0, 0) | s | true | 5.405846e-1 | 0.391828 |
| 2 | 34 | 44732 | top | (-1, 0) | s | true | 1.138439e-3 | 8.251661e-4 |
| 3 | 39 | 44737 | top | (0, 0) | p | true | 8.740160e-4 | 6.335065e-4 |
| 4 | 37 | 44735 | top | (-1, 1) | p | true | 5.092127e-4 | 3.690889e-4 |
| 5 | 33 | 44731 | top | (-1, -1) | p | true | 4.737324e-4 | 3.433719e-4 |

结论：目标几何 p=2 h=5 的 residual-dominant auxiliary mode 不是 task020 的 default100 index `177`，而是 top side、zero-order、s polarization 的 local aux index `38`。这个模式单独占 auxiliary residual norm 约 `0.999995`，说明 selector 是稳定的，但仅修正 auxiliary 坐标不足以真正收敛。

## 方法比较

| 方法 | 最好 residual | improvement | gate | 结论 |
|---|---:|---:|---|---|
| aux-only one-shot / PC | 1.921949e-1 | 1.054x | fail | 只动 auxiliary unknown 不够 |
| diag FE response coupled PC | 1.838447e-1 | 1.102x | fail | 对角近似 FE response 太弱 |
| SPILU FE response coupled PC, m=1 | 9.865457e-7 | 2.053e5x | production-like | 最小维度生产级候选 |
| SPILU FE response coupled PC, m=2 | 9.412760e-7 | 2.152e5x | production-like | 稳定通过 |
| SPILU FE response coupled PC, m=4 | 9.134024e-7 | 2.218e5x | production-like | SPILU coupled 最低 residual |
| SPILU block Schur PC, full aux | 2.430285e-7 | 8.336e5x | production-like | 最强近似 FE-block Schur 候选 |
| exact FE-block Schur one apply | 8.155352e-12 | 2.484e10x | production-like | 上界验证，等价研究口径 block solve |
| exact FE-block Schur PC | 8.183739e-12 | 2.475e10x | production-like | 上界验证，非默认生产路径 |

核心突破：p=2 h=5 真实残差已经从 baseline `2.025767e-1` 推进到 `1e-6` 以下，最好为 `8.155352e-12`。因此 task021 的最终问题答案是：在目标模型上，该路线可以把 p=2 h=5 reduced Stage4 system 推进到 production-like gate，并为 p=2 h=2 preflight 提供依据。

## Solver-like 集成

| profile | FE solver | coarse dim | final residual | history points | elapsed s | FE factor s | FE fill nnz | 判断 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| coupled PC | SPILU drop=1e-3 fill=12 | 1 | 9.865457e-7 | 6 | 15.51 | 11.71 | 44835659 | 最小生产级候选 |
| coupled PC | SPILU drop=1e-3 fill=12 | 2 | 9.412760e-7 | 16 | 39.75 | 11.71 | 44835659 | 通过 |
| coupled PC | SPILU drop=1e-3 fill=12 | 4 | 9.134024e-7 | 40 | 86.31 | 11.71 | 44835659 | 通过但更慢 |
| block Schur PC | SPILU drop=1e-3 fill=12 | 80 | 2.430285e-7 | 2 | 0.99 | 11.71 | 44835659 | 最强近似 Schur 候选 |
| block Schur PC | exact SPLU | 80 | 8.183739e-12 | 2 | 0.11 | 9.70 | 47793239 | 研究上界 |

注意：这里的 `elapsed_s` 是 Krylov / correction 阶段耗时，不完全包含所有装配、模式映射和文档处理时间。`FE factor s` 单列记录了 FE block 因子化成本。

## Gate Decision

| case | best profile | best residual | improvement | gate | allow p2 h2 preflight |
|---|---|---:|---:|---|---|
| target_p1_h5 | baseline GCROT(m,k) + Jacobi | 4.520105e-5 |  | strong | false |
| target_p2_h5 | exact FE-block Schur one apply | 8.155352e-12 | 2.483972e10x | production-like | true |

## 必答问题

1. 是否确认使用目标模型？是，已通过代码硬检查确认 50 x 25 x 140 nm / 17 x 25 x 120 nm，period 50 x 25 nm，80 deg s polarization，80 个 DtN auxiliary modes。
2. p=1 h=5 是否 production-like？否。80 history points 后 residual 为 `4.520105e-5`，达到 strong，但未达到 `1e-6`。
3. p=2 h=5 baseline residual 是多少？`2.025767e-1`。
4. p=2 residual-dominant auxiliary modes 是哪些？首要是 top side、Rayleigh `(0,0)`、s polarization、local aux index `38`；后续弱得多的是 top `(-1,0)` s、top `(0,0)` p、top `(-1,1)` p、top `(-1,-1)` p。
5. aux-only coarse 是否达到 minimum / strong？没有。最好约 `1.921949e-1`，只改善约 `1.054x`。
6. 加入 FE response 后是否提升到 strong？是。SPILU FE response coupled PC 的 m=1/2/4 均达到 production-like；full-aux SPILU block Schur PC 达到 `2.430285e-7`。
7. solver-like integration 是否稳定？在 research runner 中稳定；SPILU m=1/2/4 和 block Schur PC 均用完整真实残差通过。但它仍是 serial SciPy prototype，不应直接宣称已经是 MPI/PETSc production 默认求解器。
8. 是否允许 p=2 h=2 preflight？允许。p=2 h=5 已 production-like，通过 task gate。
9. 是否建议合并代码？建议合并 docs；`src/postprocessing/postprocess.py` 的 PyVista 检查可合并；`src/studies/run_task021_target_aux_coarse.py` 建议作为 research runner 可选合并，不接入 production 默认路径。
10. 如果失败，失败属于哪里？本轮 p=2 h=5 没有失败。负结果说明 aux-only 和 diag FE response 失败属于 FE response / PC integration 质量不足，不是 mode selector 失败，也不是目标物理模型差异导致路线失效。

## 已知问题

1. SPILU/SPLU 路径目前在 serial SciPy runner 中验证，尚未迁移为 PETSc `PCShell` / `MatShell` / MPI-safe implementation。
2. SPILU 对 coarse dimension 有非单调性：m=1/2/4 通过，m>=8 反而失败，说明 coarse basis 需要稳定筛选或正交化/过滤。
3. exact FE-block Schur 是上界验证，不是低内存 production 策略。
4. 本轮没有输出 production R/T/A；下一步应在 converged iterative solution 上做 official R/T/A 对比。
