# Task032 本地迁移记录

## 1. 结论

```text
status = PASS
task031_merge_sha = dae03170b0cdd87f2d72769aea7ce04e32acce2b
old_local_project = C:\Users\admin\Desktop\Code\fenics_vector_maxwell_floquet_demo_v2_parallel
new_local_project = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
remote = https://github.com/Rookie1234567/MyFEniCS
task032_branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
```

Task031 已按 `review_report_v2.md` 通过显式 merge commit 合入远程 `master`。Task032 新目录来自该 merge 后的 clean `origin/master`；旧目录没有切换分支、提交或复制 `.git`。

## 2. 旧目录迁移前快照

```text
branch = codex/20260714-task31-compact-pc-memory-optimization
HEAD = 2021a893a9a988e52769fe971f61b4150d2f570a
origin = https://github.com/Rookie1234567/MyFEniCS
git status --short:
  ?? docs/task023_petsc_mpi_fe_response_pc/outcomes/raw_runs/
  ?? papers/
```

这两个未跟踪目录在迁移前已经存在，未提交、未删除、未复制到新库。旧 `papers/` 中的 14 份 PDF 保留为只读参考材料；Task032 需要时从旧路径读取。

## 3. Task031 clean master merge

远程刷新后发现初始 `origin/master` 仍为：

```text
b7e0d14cab31e5bad0119f4541c76e278378419c
```

Task031 远程分支 tip 为：

```text
2021a893a9a988e52769fe971f61b4150d2f570a
```

在独立临时 clean clone 中确认 `origin/master` 是 Task031 tip 的祖先后，以显式 merge commit 合并：

```text
merge = dae03170b0cdd87f2d72769aea7ce04e32acce2b
parents = b7e0d14cab31e5bad0119f4541c76e278378419c 2021a893a9a988e52769fe971f61b4150d2f570a
subject = merge: close Task31 memory optimization
```

合并后轻量验收：

```text
documentation + Task031 contracts = 21 passed
benchmark checker = 258/258 passed
compileall = PASS
git diff --check = PASS
```

push 后重新 fetch，确认远程 `master` 与本地 merge SHA 完全一致，且包含 Task031 Review V2、Case070、Task032 任务书、Hybrid 理论和 iterative solver ports。

## 4. 新目录和分支

新目录从更新后的远程库 clean clone：

```text
folder = C:\Users\admin\Desktop\Code\fenics_v3_hybrid_FEM_modal
clone HEAD = dae03170b0cdd87f2d72769aea7ce04e32acce2b
origin/master = dae03170b0cdd87f2d72769aea7ce04e32acce2b
initial git status --short = empty
```

随后由 Codex 创建并推送：

```text
branch = codex/20260714-task32-hybrid-fem-modal-direct-baseline
upstream = origin/codex/20260714-task32-hybrid-fem-modal-direct-baseline
```

## 5. 旧目录保护和路径检查

迁移后复核旧目录仍为原 Task031 分支和原 HEAD，两个既有未跟踪目录保持不变。新库没有复制旧缓存、结果、虚拟环境或 benchmark heavy artifacts。

对 `src/**/*.py` 与 `benchmarks/**/*.py|*.sh` 扫描：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel = no source hits
C:\Users\admin\Desktop\Code = no source hits
```

正式运行均使用仓库相对路径和显式 `--results-root`。重型 smoke 输出位于 ignored 的 `benchmarks/artifacts/task032_phase0/`。
