# Codex 任务书

## 目标

根据 `docs/task000_review_code/review_report.md` 整理 Stage 4 验证链条，收紧 R/T 指标口径，并把 EUV 13.5 nm 与 Si 光栅复折射率写入代码配置和本轮输出记录。

## 背景

上一轮审查认为，当前 3D Maxwell / Floquet / DtN / Stage 4 框架已经基本成形，后续重点应从“继续扩功能”转为“哪些结果可以作为物理可信结论”。审查报告特别指出：

- `diffraction_3d.py` 中官方 R/T 来源说明需要统一；
- 后续 EUV 验证应固定 `lambda0 = 13.5 nm`；
- Si 光栅复折射率为 `0.999002304859 + 0.00182649365j`；
- 基座复折射率与 Si 光栅使用同一个复数；
- 不能只用 `R+T=1` 证明物理正确；
- 633 nm 或实数折射率案例只能保留为 `numerical_sanity_only`。

## 必需修改

- 明确 `diffraction_3d.py` 中 probe 后处理的官方 R/T 来源为 E/H Fourier directional fitting。
- 将 Stage 4 block grating 默认光栅材料改为 Si 复折射率。
- 给 3D 配置、summary 和运行日志增加验证角色、材料标签和吸收解释字段。
- 在有吸收基座时，将 `A_balance = 1 - R - T` 明确记录为吸收/损耗余额。
- 保留 633 nm / 实数折射率诊断入口时，明确标记为 `numerical_sanity_only`。
- 在本任务目录下生成本轮输出记录：

```text
docs/task001_stage4_validation_cleanup/outcomes/
```

## 必需验证

- `python -m compileall -q src`
- Docker 内 `python3 -m unittest discover -s src/test -p "test_*.py"`
- Docker 内 13.5 nm Stage 4A flat-layer sanity 轻量运行。
- Docker 内 13.5 nm Stage 4B zero-contrast 轻量运行。

## 验收标准

- 代码和文档不再把 E-only Fourier 描述为当前 Stage 4 probe 后处理官方 R/T。
- `parameters.json` 写明 Si 基座和 Si 光栅复折射率。
- `summary.md` 明确区分代码路径跑通、能量检查和物理 benchmark 可信性。
- `metrics.csv` 记录本轮轻量运行的 R/T、自由度、耗时和内存。
- 未提交大体积仿真结果。

## 输出要求

- 本轮 Markdown 文档使用中文。
- outcome 目录至少包含 `summary.md`、`metrics.csv`、`parameters.json`、`run_log.txt` 和 `changed_files.md`。
- 提交并推送到远程分支 `codex/20260703-stage4-validation-cleanup`。
