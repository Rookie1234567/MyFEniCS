# V13 P0 p6/h10 physical Maxwell outcome

## 结论

本次 P0 是 p6/h10、13.5 nm、MPI1、physical_rhs 的真实 physical Maxwell workflow。它在 cold setup 阶段被外部 watchdog 的 process-tree RSS hard line 受控终止，分类为 FAILED_RESOURCE_HARD_STOP / controlled termination。它不是 Krylov、PC contraction、PDE numerical 或 official-physics failure；由于没有 worker record，也没有运行 checker。

C1 positive 通过只说明预条件器在正定辅助算子上的资格。P0 才会把这个预条件器接入含波动和 streaming Fourier-DtN 的真实散射流程。本次流程在进入 bundle/setup marker、source、Krylov、recovery 之前就达到资源硬线，所以不能把 C1 结果写成 physical PASS。

## measured facts

| 项目 | 实测事实 |
|---|---|
| source / model | physical_rhs；source SHA a05e93af6edb097c1f0ebf0f65e201698db27381 |
| configuration | p6/h10、13.5 nm、MPI1、exact matrix-free Maxwell volume、streaming Fourier-DtN、selected_hierarchy=same_mesh_hcurl_pmg_v1_requalified |
| reached stage | 仅 paths_ready；没有 bundle/setup/source/solve/recovery/physics marker |
| watchdog samples / elapsed | 20,518；最后 elapsed=5167.201565908967 s |
| process-tree peak | 2,024,108,032 B |
| hard line | 2,000,000,000 B |
| first warning | 1,813,069,824 B at elapsed=5165.438371994998 s |
| strict overage | 24,108,032 B，约为 hard line 的 1.2054%；严格 FAIL，不能按“只超一点”通过 |
| process-tree swap | 0 B |
| return / stop | returncode=-15；stop_reason=process_tree_rss_limit |
| lifecycle | natural_exit=false；no_orphan=true；raw samples all_status_readable=true |
| final PID set | [1628136, 1628137, 1639353, 1639354] |

watchdog 的 compact 仍记录 watchdog poll=0.25 s、RSS limit=2,000,000,000 B、process-tree swap=0。/init.scope 与 WSL-global swap 只作为非专用环境诊断，未冒充 process-tree swap Gate。

## 未触达的数值与物理对象

没有 worker record、checkpoint、residual history、iterations、outer KSP/Krylov result、recovery packet、E/H、R/T/A、A_volume 或 diffraction channel 数值。因而 official E/H、R/T/A、A_volume、同一 12 个显著通道的 12 个 power Gate 与 12 个 complex boundary-amplitude Gate 均为 not_run_by_resource_gate；没有 direct observable-vector qualification。没有创建假的 worker record 或 checker record，也没有运行 checker。

P1 只允许在 positive hierarchy 已通过、physical 长尾满足 Review 条件后增加固定 deflation；本次尚未进入 solve，因此 P1=locked/not_run_by_resource_gate。P2 的 MPI2 physical、h5 setup-only 与 0.7 nm 更新同样为 locked/not_run_by_resource_gate。

## 受限推断

在 hard stop 前出现了两个额外 child PID，并留下一个 108,676,257-byte 的未完成 FFCx C source，没有对应的 .o/.so。这个现象与 form-JIT compiler transient 高度一致，但本次没有 child cmdline authority，不能写成已经证实的唯一根因，也不能据此修改 watchdog、阈值或复用 cache 绕过 cold Gate。

## 证据入口与哈希

ignored artifact root（原样保留）：

benchmarks/artifacts/task038_extra_full3d_same_mesh_hcurl_pmg_p0_physical_v1/a05e93af6edb097c1f0ebf0f65e201698db27381/p6-h10-mpi1/physical_rhs

root 内的 raw、compact、paths marker 和空 worker log 的事实如下：

| artifact | bytes | SHA256 |
|---|---:|---|
| watchdog.raw.jsonl | 18,722,332 | 51e8e531500e733c21f558d44be0a4d8d7a76fe9454800ebc9cb8ad06ab19566 |
| watchdog.compact.json | 2,653 | 0705e170a1835999aece82dfe43d3ff5ccd3cf98800b79a013341b54ed2955e5 |
| worker_raw/markers/paths_ready.json | 1,256 | 4f22fd62136515693ebebef4fbfe551e84e46223a0685054dcb9ad1a65108415 |
| worker.log | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

同一 watchdog compact 原字节 tracked 到 records/same_mesh_hcurl_pmg_p0_physical_v1_watchdog.json；同一 paths marker 原字节 tracked 到 records/same_mesh_hcurl_pmg_p0_physical_v1_paths_ready.json。tracked 副本分别保持 0705e170a1835999aece82dfe43d3ff5ccd3cf98800b79a013341b54ed2955e5 和 4f22fd62136515693ebebef4fbfe551e84e46223a0685054dcb9ad1a65108415。

旧 V12 evidence、C1 四源 evidence、ordinary default、master 和 0.7 nm 目录均未被改写。这个 P0 结果只说明当前 cold physical workflow 没有在 2 GB hard line 内完成 setup；不能推断 0.7 nm capacity，也不能把它重分类为数值负结果。
