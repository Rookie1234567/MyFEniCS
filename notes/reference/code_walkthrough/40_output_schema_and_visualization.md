# 输出 Schema 与可视化

## 普通 2D/3D summary

必须包含 resolved config、case/stage、mesh cells/DoF、constraint 统计、solver/backend、残差、计时、RSS（可用时）、field metrics、power metrics 和 status。complex 值以 `[real,imag]` 或明确字符串序列化。

## benchmark record

| 字段组 | 关键字段 |
|---|---|
| 身份 | `benchmark_id`, `metadata.commit_sha/branch/git_dirty/command/timestamp` |
| 环境 | image、digest、host id、PETSc/DOLFINx environment file |
| 来源 | actual source command/root、canonical rerun command/root、provenance |
| 物理 | geometry/material/wavelength/angles/polarization/degree/h/MPI |
| 迭代 | profile、coarse/slab/sm2、reason、iterations |
| 可信度 | reported/condensed/full residual、qualified/deviations |
| 资源 | current/final/RTA/overall peak total RSS |
| 物理结果 | official R/T/A、closure |

## progress/parameters

`*_parameters.json` 保存启动参数，`*_progress.json` 可在中断时恢复最后 stage/iteration/RSS；最终 record 才是 Gate 输入。progress 不等于 pass。

## 场文件

2D/串行可直接写单 VTU；3D MPI 写 rank-local VTU 与 PVD。`postprocess_3d` 过滤 ghost cells，避免 ParaView 数量/积分重复。场名区分 `E_total/E_scat/E_background` 和 real/imag/abs。

## 日志

`run_log.txt` 记录阶段与错误；solver log 记录参数/残差；PETSc `-log_view` 可输出性能但不应替代项目 summary。大文本日志不塞进 canonical JSON。

## 可视化边界

图用于理解场，不用于自动 Gate。数值判定来自 JSON/CSV。`render_stage4_comsol_views.py` 只读结果生成切面；不编辑场数据。
