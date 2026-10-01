# dot 云端组件实验复现

此目录保存有限组件证据。数值核心在 src/solvers/task40extra_reference_metric_component.py，未接入生产；benchmark 仅编排和核验。正式 runner 需要 DOLFINx/PETSc 全栈且运行完整 PDE，本实验只比较局部数值与几何计数，因此不复用 run_case 启动正式求解。

源基线 c786e87d03976a52f57d1e7f69a3c63f992afe90。原计时脚本、路径发布前版本、compact JSON 与其 hash 保留。历史 findings/provenance 中的云端路径仅描述原运行；**在仓库复现以本页命令为准**。不需要下载额外 LF，也不复制 raw 大数组。

环境为隔离的云端组件 Python 3.12，NumPy 2.5.3、SciPy 1.17.0、Basix/FFCx 0.11.0、UFL 2026.1.0。不是原 WSL/PETSc ABI 资格。依赖准备后，在本分支仓库根目录执行；python 应指向该已准备的组件环境。

```bash
export TASK40EXTRA_SOURCE_ROOT="$PWD"
export TASK40EXTRA_SOURCE_MANIFEST="$PWD/benchmarks/cases/task40extra_dot_parallel_cloud/source_manifest.json"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export TASK40EXTRA_OUTPUT_ROOT="$PWD/benchmarks/artifacts/task40extra_dot_parallel_cloud/dtn_modes"
python benchmarks/cases/task40extra_dot_parallel_cloud/dtn_modes/audit.py
python benchmarks/cases/task40extra_dot_parallel_cloud/dtn_modes/trace_quadrature.py
python benchmarks/cases/task40extra_dot_parallel_cloud/dtn_modes/audit_port_rule.py
export TASK40EXTRA_OUTPUT_ROOT="$PWD/benchmarks/artifacts/task40extra_dot_parallel_cloud/tensor_reuse"
export PYTHONPATH="$TASK40EXTRA_OUTPUT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
python benchmarks/cases/task40extra_dot_parallel_cloud/tensor_reuse/run_experiment.py
python benchmarks/cases/task40extra_dot_parallel_cloud/tensor_reuse/g1_schur_check.py
python benchmarks/cases/task40extra_dot_parallel_cloud/tensor_reuse/validate_extracted_core.py
export TASK40EXTRA_OUTPUT_ROOT="$PWD/benchmarks/artifacts/task40extra_dot_parallel_cloud/capacity"
python benchmarks/cases/task40extra_dot_parallel_cloud/capacity/exact_metric_inventory.py
```

先核对当前 baseline 数值文件仍与 source_manifest 匹配；文档后续更新不会自动使旧实验重新通过。audit.py 检查 manifest 原字节或恰多一个终端 LF；新数值修改须冻结新身份。

输出在 ignored benchmarks/artifacts，包含可再生约 36 MB 模板和约 14 MB 全模式 JSON，勿加入 Git。原 compact 中 hash 对应原历史 raw，新的复跑时间/环境可能不同，不要求新整个 raw hash 相同。portable 路径版本于 2026-10-01 在独立云端源布局运行七脚本，均 exit 0；这次仅验证可运行性，不替换历史配对性能、不授予 PDE 资格。对应摘要见 publication_checks.json。
