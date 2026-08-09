# Task037-extra Response V2：Candidate H H1/H2 consolidated outcome

本文件是 Review V2 之后 Candidate H 的 consolidated authority。本轮没有运行 PDE/KSP；
正式 action-only run 生成了 ignored raw artifacts，本文件只固化其 compact/hash-bound
结论。

## 1. 总结结论

| 阶段 | 当前结论 | 语义 |
|---|---|---|
| H0 | H0_PASS | capability-only，不是数值通过 |
| H1.1 | PASS | p2/p3 tiny full-space action 与 MPI identity 通过 |
| H1.2 | CONTROLLED_STOP_TIMEOUT / H1_NOT_QUALIFIED | 1800 秒内未形成 action qualification record |
| H2 | H2_NOT_RUN_GATED_BY_H1 | 未启动 coercive block smoother |
| H3 | false | H1.2 未资格化，H3 不具备资格 |
| MPI2 / compare | not_run | H1.2 hard stop 后未启动 |
| H4 / full PDE / official RTA | not_run | 不在本轮授权范围内 |

H1.2 的 controlled stop 表示 watchdog 到达冻结 timeout 后安全终止进程组，
不是“算法失败”的数值判定，也不是通过。由于 worker 没有写出 summary，H1.2
仍是 NOT_QUALIFIED。

## 2. Review V2 五问

| 问题 | consolidated answer |
|---|---|
| 1. exact p6 action 是否成立？ | 未建立。H1.1 只在 p2/p3 tiny fixture 通过；H1.2 timeout 前没有 action record |
| 2. retained bytes / peak 是否通过？ | payload unavailable。387121152 B = 0.36053466796875 GiB 是不完整运行的 observed peak，不能作为 full process-peak Gate PASS |
| 3. exact block class 数与 refinement？ | not_run；H2 未进入 |
| 4. 四 residual contraction？ | not_run；没有 H2/H3 action 或 rho |
| 5. H3 是否有资格？ | false；H1.2 未资格化，H3 不启动 |

## 3. H1.1 tiny fixture 证据

matrix-free action 是逐单元即时计算并累加向量结果，不保存 global matrix。H1.1
只证明这个小规模 action 与 assembled authority 的代数一致性。

| 证据 | p2 | p3 |
|---|---:|---:|
| assembled-vs-MF relative error | 5.180892903724677e-16 | 8.360695796841576e-16 |
| canonical dual MPI identity error | 1.985978336928787e-16 | 3.3576744854094875e-16 |
| packet count | 224 | 720 |
| missing / extra / duplicate | 0 / 0 / 0 |

| 测试证据 | 结果 |
|---|---|
| test271 serial | 7 passed |
| test272 serial | 2 passed |
| test272 MPI2 | 两个 rank 各 2 passed |
| test276 | 3 passed |
| compileall / git diff --check | pass |
| Ruff | unavailable；未安装 |

## 4. H1.2 正式 MPI1 raw

| 身份或 Gate | 值 |
|---|---|
| branch | codex/20260806-task37-iterative-extra-development |
| source SHA | f7591aa9a2ae581d748e97ec607ea6edb51d1b14 |
| source start/end | 同一 SHA，均 clean |
| MPI | 1 |
| watchdog timeout / poll | 1800 s / 0.25 s |
| RSS hard limit | 1342177280 B = 1.25 GiB |
| strict process-tree swap | 0 |
| return code / status | 1 / controlled_stop |
| controlled stop / wall | timeout / 1801.0560716170585 s |
| termination | process group SIGTERM；sigkill_required=false |
| worker live samples | 7145 |
| authority readable | true |
| incomplete observed peak | 387121152 B = 0.36053466796875 GiB |
| worker stdout | 0 B |
| worker_summary_present | false |
| worker_qualification_pass | false |
| worker summary / run summary | 不存在 |

worker_summary_present=false；worker_qualification_pass=false 是 summary 缺失后的
机械 fail-closed 值，不是 action algorithm FAIL。

### H1.2 Gate disposition

| Gate | disposition | raw basis |
|---|---|---|
| completion/qualification within frozen 1800 s | FAIL / controlled stop | wall 1801.0560716170585 s；run_summary absent |
| action relative error / finite / deterministic | unavailable | worker summary absent |
| retained payload <=0.50 GiB | unavailable | payload 未写出 |
| MPI1/MPI2 identity | not_run / unavailable | MPI2/compare 未启动 |
| full completed-run process peak <=1.25 GiB | not qualified | 只有 incomplete observed peak 0.36053466796875 GiB |
| swap | incomplete observed 0 | worker live process-tree swap |

这里的 completion Gate 是实际失败的停止条件；action 的数值 Gate 仍是
unavailable，不能改写成 algorithm FAIL。

外层由用户启动的 watchdog 命令为：

```text
python -m benchmarks.run_task037_extra_candidate_h watchdog --run-dir benchmarks/artifacts/task037_candidate_h_h1_2_f7591aa/mpi1 --mpi-size 1
```

watchdog 内部实际执行的 worker command 为：

```text
mpiexec -n 1 /home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python -m benchmarks.run_task037_extra_candidate_h worker --run-dir benchmarks/artifacts/task037_candidate_h_h1_2_f7591aa/mpi1
```

mesh 文件已经完成；约 126 秒后 timeline 显示 RSS plateau 为 387121152 B；
同期只读 process checks 反复观察到约 110% CPU。CPU 是运行监控诊断，不是 timeline
字段。canonical export 只有在首个 source 完成 reference 与两次 candidate
apply 后才会出现，但本次没有 canonical 目录。因此只能说 mesh 已完成而首个 source
post-action canonical export 尚未完成；现有 raw 无法区分 high-order space/MPC/form
setup 与首个 source apply。不能进一步归因，也不能把 exact p6 action 判为科学失败。

四个 source 的 action error、finite/deterministic、global rows/constraints、
inventory、retained payload、canonical identity 和 manifests 均 unavailable。
不填 0、不预测。

## 5. Raw hash index

原始目录：

benchmarks/artifacts/task037_candidate_h_h1_2_f7591aa/mpi1

| raw file | SHA256 |
|---|---|
| watchdog_summary.json | 8abfc2c3554271f8ba0a16380568e75f6122d00d623706b680f7d485d5976372 |
| watchdog_timeline.jsonl | e9cbe0b7e0cca9bfe07fb41a78e13ba82fe062f5c3701a4ce82658bacf4dd886 |
| worker_stdout.txt | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| mesh/mesh_3d.h5 | 1a5f026e2544c72196d0d14bd1f34e083afe79937f2925bc825db657a4b67b16 |
| mesh/mesh_3d.xdmf | e40e1b05f3269101fe93e96416481f14bcaa64fb1df5f030381c747b484b9864 |
| mesh/mesh_3d_partition_note.txt | 0a3e481d76798fa867ac1151dee5b3899920e623606faf36f175ee670c9ed974 |

run_summary.json、四个 candidate manifests 和 canonical 目录不存在；因此没有
MPI1/MPI2 数值 identity 可报告。

## 6. H2、历史 G2 与停止边界

H2 的 coercive proxy 是给 curl-curl 体积算子加入正质量作用，使局部平滑更容易
判断；exact-class-reused block smoother 则对相同局部材料/几何类别复用同一个 block
factor，目标是减少重复存储。H2 没有运行，所以 rho、class count、factor payload、
apply/action ratio 和 determinism 全部为 not_run。原始 time-harmonic FGMRES、
official field/RTA、global matrix、per-cell/slab factors、parameter scan 也均未运行。

历史边界保持不变：G2 LOR-HX=G2_FAIL；G3 additive LOR-HX prohibited；旧 G4
sweep with failed LOR-HX prohibited；ordinary default unchanged。Candidate H 本轮
因此在 H1.2 停止，不启动 MPI2、compare、H2、H3、H4、full PDE 或 official RTA。

当前不建议 merge/master。研究实现和该受控停止的负证据只留在当前执行分支，等待
Review V2 对 H1.2 hard stop 的审阅；不把 H1.2 写成 exact p6 action PASS，也不把
timeout 写成 exact p6 action scientifically disproved。
