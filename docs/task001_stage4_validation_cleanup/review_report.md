# 审查报告

## 总体结论

我本轮审查的是远程分支：

```text
codex/20260703-stage4-validation-cleanup
```

相对 `master`，该分支目前 ahead 6 commits，包含上一轮 `review_code` 协作文档、本轮 Stage 4 validation cleanup 文档、outcomes 记录，以及若干轻量代码修改。

总体判断：本轮方向是正确的，可以作为 Stage 4 验证链条清理的第一步；但它仍然只是 `numerical_sanity_only`，不能作为正式 EUV 物理 benchmark。建议先处理少量口径问题，然后再合并到 `master`。

## 审查范围

重点阅读了：

- `notes/docs/CODEX_TASK_20260703_stage4_validation_cleanup.md`
- `notes/outcomes/20260703_stage4_validation_cleanup/summary.md`
- `notes/outcomes/20260703_stage4_validation_cleanup/metrics.csv`
- `notes/outcomes/20260703_stage4_validation_cleanup/parameters.json`
- `notes/outcomes/20260703_stage4_validation_cleanup/run_log.txt`
- `src/common/config_3d.py`
- `src/common/modes_3d.py`
- `src/runners/run_3d_cases.py`
- `src/postprocessing/diffraction_3d.py`

## 主要发现

1. 这次分支用对了。
   - 我已经明确访问的是 `codex/20260703-stage4-validation-cleanup`，不是旧的 `codex/review_code`。
   - 该分支仍然从 `master` 分出，但它包含上一轮 `review_code` 的新增文档，因为这些文件尚未进入 `master`。

2. 任务目标基本执行到位。
   - 本轮已经把 `lambda0 = 13.5 nm` 写入任务、代码默认参数和 outcomes。
   - Si 光栅复折射率已经固定为 `0.999002304859 + 0.00182649365j`。
   - 基座当前也按用户要求暂时使用同一个 Si 复折射率。

3. `numerical_sanity_only` 的标记是必要且正确的。
   - 本轮轻量算例只有 h=50 nm、p=1、zero_order。
   - Stage 4A 只有 75 DoF，Stage 4B zero-contrast 只有 144 DoF。
   - 这些结果只能说明代码路径和 zero-contrast 对照没有明显崩掉，不能说明 EUV 真实物理收敛。

4. flat-layer 与 zero-contrast 的对照结果是有价值的。
   - 两者 R/T/A 几乎完全一致。
   - 这说明 zero-contrast block 几何/tag 本身没有额外引入虚假散射。

5. lossy substrate 传播级识别的修复是合理的。
   - 对有吸收介质，`beta` 本来就是复数。
   - 不能再用 `Im(beta)≈0` 来判断是否传播，否则会把透射零级误判为非传播级。

6. 当前最大的遗留问题不是这轮代码，而是分支管理。
   - `codex/20260703-stage4-validation-cleanup` 里包含上一轮 `review_code` 的文件，说明上一轮分支可能还没有先合并进 `master`。
   - 后续应保持：一个任务分支审完后先合并到 `master`，再从最新 `master` 开下一轮分支。

## 必须修复

1. 合并前建议统一 outcomes 与代码里的“功率来源”表达。
   - 本轮 `metrics.csv` 写的是 `dtn_auxiliary_port_amplitudes`。
   - `summary.md` 同时提到 `diffraction_3d.py` 的 probe 后处理官方来源是 E/H Fourier。
   - 这两者不一定矛盾，但必须明确：Stage 4 dtn_port 求解器自身输出的 R/T 与 probe 后处理输出的 R/T 是两套来源，不能混称为一个 official R/T。

2. 合并前建议把本轮 REVIEW_REPORT 保留为最终审查文件。
   - 现在该文件已经填充，可以让 Codex 读取这个报告后做一次小修。

3. 不要删除 `master` 或当前任务分支。
   - 远程分支可以清理，但只应删除已经合并的旧任务分支。

## 建议的下一步 Codex 动作

继续在当前分支 `codex/20260703-stage4-validation-cleanup` 上小修，不要新开分支：

1. 读取本报告。
2. 在 `summary.md` 中更明确写出两类 R/T：
   - `dtn_auxiliary_port_amplitudes`：本轮轻量运行表格里的 R/T 来源；
   - `E/H Fourier directional fitting`：`diffraction_3d.py` probe 后处理的官方来源。
3. 在 `parameters.json` 中补一个字段：

```json
"power_source_note": "dtn_port summaries use dtn_auxiliary_port_amplitudes; diffraction probe postprocess uses E/H Fourier directional fitting."
```

4. 不需要新增大规模计算。
5. 修完后重新 push 当前分支。

## 合并前验收标准

本轮分支可以在以下条件满足后合并：

- `summary.md` 对 R/T 来源不再容易混淆；
- `parameters.json` 明确记录 power source note；
- `metrics.csv` 保留本轮轻量结果；
- 不提交大体积 results；
- `master` 确认为默认主线。

合并后可以删除旧任务分支，只保留：

```text
master
codex/20260703-stage4-validation-cleanup  # 如果还没合并或还要继续修
```

合并完成后，当前任务分支也可以删除。
