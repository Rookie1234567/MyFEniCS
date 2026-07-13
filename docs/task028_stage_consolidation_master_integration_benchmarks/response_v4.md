# Response V4：Task028 轻量元数据加固与最终合并准备

## 1. 最终状态

```text
branch = codex/20260712-task28-stage-consolidation
validated_implementation_head = da05077fc010f658f2fe01ef65a00f0723cee88c
review = review_report_v4.md
tracked_source_clean_at_validation = true
canonical_records_overwritten = no
h2_direct_or_iterative_rerun = no
new_solver_or_physics_work = no
master_merge_at_response_creation = not_yet_executed
```

用户在启动 Task29 的指令中已明确许可：完成本报告三项更正后合并 Task28 到 `master`。本响应只关闭 M1–M3，不启动 Task29 实现。

## 2. M1：`tracked_source_dirty` 强制 Gate

### 改动文件

- `benchmarks/check_benchmarks.py`
- `src/test/test_25_benchmark_contract.py`

### 精确行为

当 record 的 provenance 为：

```text
canonical_lightweight_rerun_from_frozen_case_contract
```

checker 现在强制要求：

```text
metadata.tracked_source_dirty is false
```

Gate 覆盖 Case002 的 explicit、auxiliary、comparison，以及 Case003 的 TM、TE，共 5 份轻量 canonical record。`git_dirty=true` 仍被允许，因为 ignored artifact 可以存在；未提交的受跟踪源码则会令 Gate 失败。旧的 3D reviewed/historical record 不受这条 provenance 专用规则误伤。

### 验证与证据

```text
python benchmarks/check_benchmarks.py --no-write
  PASS: 148/148

python -m unittest src.test.test_25_benchmark_contract
  PASS: 5/5
```

新增的 5 项 tracked-source-clean Gate 均观察到 `false` 并通过。限制保持不变：checker 验证保存 record 的来源元数据，不声称当前 checkout 的 ignored artifacts 为空。

## 3. M2：Candidate runner 强制真实 image digest

### 改动文件

- `benchmarks/cases/002_2d_tm_dtn_equivalence/run.sh`
- `benchmarks/cases/003_2d_te_tm_complex_absorption/run.sh`
- 两个 case 的 `README.md`
- `notes/quick_start/11_2d_dtn_floquet.md`
- `notes/quick_start/12_2d_te_tm_and_complex_material.md`
- `src/test/test_25_benchmark_contract.py`

### 精确行为

两个 runner 均改为：

```sh
: "${IMAGE_DIGEST:?Set IMAGE_DIGEST to the tested image digest}"
```

已删除 `sha256:qualified-local-image` 默认占位值。`IMAGE_NAME`、artifact root 和 candidate record 目录仍可使用安全默认值；`SOURCE_COMMIT` 与 `IMAGE_DIGEST` 都必须由调用者显式提供。相关教程和 case 命令同步增加 `IMAGE_DIGEST=sha256:<digest>`。

### 验证与证据

`test_lightweight_candidate_runners_require_image_digest` 同时保护两个 runner 必须包含 shell required-variable guard，并禁止占位 digest 回归。没有运行 candidate 生成，也没有覆盖 canonical JSON。

## 4. M3：最终实现提交上的轻量验证

验证对象：

```text
da05077fc010f658f2fe01ef65a00f0723cee88c
```

验证前：

```text
git status --short --untracked-files=no
  PASS: 无输出，受跟踪源码 clean
```

审查指定命令：

```text
python benchmarks/check_benchmarks.py --no-write
  PASS: 148/148

python -m unittest src.test.test_26_documentation_contract
  PASS: 11/11

docker run ... myfenics-stage4:task28 \
  python -m unittest src.test.test_27_main_preset_contract
  PASS: 8/8
```

补充检查：

```text
ruff check
ruff format --check
git diff --check
  PASS
```

Windows 宿主 Python 缺少 `ufl/petsc4py`，因此真实 preset parser contract 使用已资格化的 `myfenics-stage4:task28` 镜像运行；这与前几轮正式验证环境一致。用户未跟踪的 `papers/` 和 Task23 `raw_runs/` 保持原样，未进入提交。

## 5. 合并结论

```text
M1 tracked_source_dirty Gate = closed
M2 required IMAGE_DIGEST = closed
M3 final implementation head validation = closed
Task028 practical integration objective = accepted
Task028 documentation objective = accepted
Task028 benchmark objective = accepted
Task028 master merge = approved and user-authorized
```

允许合并的仍只有 `codex/20260712-task28-stage-consolidation`。历史 research branches、failed solver runners、raw runs、`papers/`、mesh/field/cache/OOC artifacts 均不进入额外合并范围。
