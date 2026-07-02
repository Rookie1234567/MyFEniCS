# 审查报告

## 总体结论

本轮 `codex/review_code` 分支本身是安全的：它没有修改核心计算代码，只新增协作留痕文件，并调整 `.gitignore` 以允许小型 `metrics.csv` 入库。因此该分支可以作为“协作流程验证分支”继续使用。

但从当前仓库整体状态看，代码已经形成了比较完整的 3D Maxwell / Floquet / DtN / Stage 4 框架；主要问题不再是“能不能跑通”，而是“哪些结果可以作为物理可信结论”。现阶段不建议继续盲目扩展功能，应先收紧验证链条。

用户补充要求：后续物理验证不再使用随意设置的实数折射率，也不再把 `lambda0 = 633 nm` 结果作为 EUV 物理结论。后续与项目目标相关的验证应锁定 `lambda0 = 13.5 nm`，并且基座与光栅材料折射率统一采用用户指定表格中的复折射率。当前上传截图在本次工具读取中没有可见文本，因此具体 `n_substrate` 与 `n_grating` 数值需要用户或 Codex 以文本形式写入下一轮任务书、`parameters.json` 和运行日志，避免再次使用临时虚构参数。

## 审查范围

- `notes/docs/CODEX_TASK_20260702_review_code.md`
- `notes/outcomes/20260702_review_code/summary.md`
- `notes/outcomes/20260702_review_code/metrics.csv`
- `notes/outcomes/20260702_review_code/parameters.json`
- `notes/outcomes/20260702_review_code/run_log.txt`
- 当前 3D 主流程相关代码与现有 notes 记录

## 主要发现

1. 协作目录结构是合理的。
   - `notes/docs/` 放任务书和审查报告。
   - `notes/outcomes/<日期>_<任务名>/` 放本轮运行记录。
   - 本轮没有提交大体积仿真结果，这是正确的。

2. 本轮分支没有新增数值验证。
   - `summary.md`、`metrics.csv` 和 `run_log.txt` 均明确说明本轮未运行 FEniCS/DOLFINx 算例。
   - 因此本轮只能验证协作流程，不能用来判断物理模型是否正确。

3. 当前 3D 代码结构已经基本成形。
   - `run_3d_cases.py` 统一调度 Stage 1 / 2A / 2B / 2C / 4A / 4B。
   - `common_3d_case_flow.py` 串联 mesh、Nedelec 空间、Floquet、DtN、求解和后处理。
   - 这套结构适合继续做逐阶段 benchmark。

4. 最大风险是物理验收标准还不够收敛。
   - 现有记录已经说明 Stage 4B p=2 路径可以组装和运行，但 EUV 下 h10/h7.5/h20 仍不能直接作为最终物理结论。
   - 当前应该优先做 flat-layer / zero-contrast / grid convergence，而不是马上相信真实 grating 的 R/T。

5. 后处理里的 R/T 来源需要进一步统一口径。
   - 代码里同时存在 E-only Fourier、E/H Fourier、net flux、modal diagnostic 等多个功率路径。
   - 当前官方指标采用 E/H Fourier，但部分说明文字仍容易让人误解为 E-only Fourier 是官方路径。
   - 这会影响后续你判断 COMSOL 对比、能量守恒和衍射级功率。

6. 求解器瓶颈已经很明确，不应再误判为边界条件错误。
   - notes 已经记录：矩阵本身没有异常变稠，主要瓶颈是 direct LU factorization fill-in 和 WSL/Docker 内存上限。
   - 后续需要把“物理验证”和“求解器容量验证”分开，不要混在一个任务里。

7. 材料与波长参数必须收紧。
   - 之前的 `lambda0 = 633 nm` 可以保留为数值 sanity 或调试用例，但不能继续作为 EUV 项目的物理验证依据。
   - 之前临时设置的实数折射率只能算算法 smoke test，不能作为真实基座/光栅 benchmark。
   - 后续 Stage 4 物理验证必须使用 `lambda0 = 13.5 nm` 和用户指定的复折射率，并在输出中明确写出材料名、`n`、`k` 或等价复数 `n_complex`。

## 必须修复

1. 明确 `diffraction_3d.py` 中官方 R/T 指标来源。
   - 统一说明：当前 `R_total/T_total` 到底来自 E/H Fourier、E-only Fourier，还是端口辅助变量。
   - 删除或修改容易误导的 note，避免 summary 中出现互相矛盾的描述。

2. 给 Stage 4 建立最小可信验证表。
   至少包括：
   - Stage 4A flat-layer sanity，`lambda0 = 13.5 nm`，使用指定基座复折射率；
   - Stage 4B zero-contrast，与同参数 Stage 4A 一致；
   - Stage 4A EUV auto_propagating，做 h 收敛；
   - Stage 4B real block 使用指定光栅复折射率，只能在前面三项稳定后再作为物理结果讨论。

3. 不要把“能量守恒 R+T=1”单独当成正确性证明。
   - 对 DtN / modal port 来说，能量守恒只能说明功率归一化和边界吸收没有明显炸掉。
   - 仍需要和 Fresnel、zero-contrast、网格收敛进行交叉验证。

4. 保持 `master` 作为稳定主线。
   - 本分支可以合并，但合并前建议先把 GitHub default branch 改回 `master`。

5. 固定 EUV 材料参数入口。
   - 在下一轮任务中，让 Codex 把 `lambda0 = 13.5 nm`、基座复折射率、光栅复折射率写入 `notes/outcomes/.../parameters.json`。
   - 如果代码中保留 633 nm 或实数折射率示例，必须明确标记为 `numerical_sanity_only`，不能混入正式 EUV validation。

## 建议的下一步 Codex 动作

下一轮不要大改算法，建议开新分支：

```text
codex/20260703-stage4-validation-cleanup
```

任务目标：整理并固定 Stage 4 的可信验证链条，且将物理参数统一到 EUV 13.5 nm。

要求：

1. 检查并统一 `diffraction_3d.py` 中官方 R/T 指标说明。
2. 将项目物理验证参数固定为：
   - `lambda0 = 13.5 nm`；
   - `n_substrate` 使用用户指定表格中的基座复折射率；
   - `n_grating` 使用用户指定表格中的光栅复折射率。
3. 生成一个新的 outcomes 目录，例如：

```text
notes/outcomes/20260703_stage4_validation_cleanup/
```

其中至少包含：

```text
summary.md
metrics.csv
parameters.json
run_log.txt
changed_files.md
```

4. 运行轻量验证，不追求大规模真实 grating：
   - `python3 -m compileall -q src`
   - `python3 -m unittest discover -s src/test -p "test_*.py"`
   - 一个 13.5 nm flat-layer sanity；
   - 一个 13.5 nm zero-contrast Stage 4B 对照。

5. 在 `summary.md` 中明确区分：
   - 代码路径是否跑通；
   - 功率是否守恒；
   - 使用的材料折射率是否为用户指定值；
   - 结果是否可作为物理 benchmark。

## 合并前验收标准

本轮 `codex/review_code` 分支：

- 可以合并，因为它只是协作结构验证，不改核心求解代码。
- 合并前建议确认 GitHub default branch 已改回 `master`。

下一轮 Stage 4 验证分支：

- 必须有可复现命令；
- 必须有 `metrics.csv`；
- 必须说明 R/T 来源；
- 必须把“路径跑通”和“物理可信”分开判断；
- 必须使用 `lambda0 = 13.5 nm`；
- 必须在 `parameters.json` 中写明基座和光栅复折射率；
- 不应把粗网格 EUV real block 结果写成最终结论。
