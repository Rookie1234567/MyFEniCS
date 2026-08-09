# Candidate H H1：full-space matrix-free action 结果

本页记录 Candidate H 的 H1 证据。matrix-free action 的通俗含义是：每个单元即时计算
局部 curl 和 mass 贡献，再写回向量，不把完整全局矩阵长期存储。它可以减少矩阵存储，
但只有在对应规模的 action、身份和资源 Gate 都完成后才算资格化。

## 1. 当前分类与身份

| 项目 | 结果 | 说明 |
|---|---|---|
| H0 | H0_PASS | 仅为 capability-only 审计，不是数值通过 |
| H1.1 | PASS | p2/p3 serial fixture，以及 MPI2 tiny identity |
| H1.2 | CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED | MPI1 正式 action-only worker 在 1800 秒超时前未写出 qualification |
| H2 | NOT_RUN / H2_NOT_RUN_GATED_BY_H1 | H1.2 未资格化，未启动 smoother |
| Candidate H 当前状态 | H1.2_CONTROLLED_STOP_TIMEOUT；H1_NOT_QUALIFIED | 不是算法 FAIL，也不是 PASS |
| G2 | G2_FAIL | 历史 LOR-HX contraction/memory 负结果保持不变 |
| G3 | prohibited | G2_FAIL 后不得启动 additive LOR-HX |
| 旧 G4 | prohibited | 不得在失败的 LOR-HX 上做 sweep、shift 或 cycle 扫描 |
| ordinary default | unchanged | Candidate H 没有接入 ordinary default |

实现身份链为：H1.1 代码审查锚点 42617e47ee4628e865cdefcfea438a5b60b5af77，
正式 H1.2 implementation SHA f7591aa9a2ae581d748e97ec607ea6edb51d1b14。
执行分支为 codex/20260806-task37-iterative-extra-development；正式 MPI1 的
source start/end 均为后一个 SHA，且均 clean。

## 2. H1.1 tiny fixture：PASS

H1.1 只证明小型 structured-hexa full-space action 的代数实现。它不等价于 p6/h10
正式测量，也不证明 H1.2 资源 Gate。

| 证据 | p2 | p3 |
|---|---:|---:|
| assembled-vs-matrix-free relative error | 5.180892903724677e-16 | 8.360695796841576e-16 |
| canonical dual MPI identity relative error | 1.985978336928787e-16 | 3.3576744854094875e-16 |
| canonical packet count | 224 | 720 |
| missing / extra / duplicate | 0 / 0 / 0 |

| focused evidence | 结果 |
|---|---|
| test271 serial | 7 passed |
| test272 serial | 2 passed |
| test272 MPI2 | 两个 rank 各 2 passed |
| test276 | 3 passed |
| compileall / git diff --check | pass |
| Ruff | unavailable；未安装依赖 |

## 3. H1.2 正式 MPI1：受控超时，未资格化

外层 watchdog 以 poll 0.25 秒、1800 秒 timeout、process-tree RSS hard limit
1.25 GiB 和 strict worker-process-tree swap 0 启动 worker。用户实际启动的外层命令为：

```text
python -m benchmarks.run_task037_extra_candidate_h watchdog --run-dir benchmarks/artifacts/task037_candidate_h_h1_2_f7591aa/mpi1 --mpi-size 1
```

watchdog 内部实际执行的 worker command 为：

```text
mpiexec -n 1 /home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python -m benchmarks.run_task037_extra_candidate_h worker --run-dir benchmarks/artifacts/task037_candidate_h_h1_2_f7591aa/mpi1
```

| measured 项目 | raw 值 |
|---|---:|
| MPI size | 1 |
| return code | 1 |
| status | controlled_stop |
| controlled stop | timeout |
| wall time | 1801.0560716170585 s |
| termination | process group SIGTERM；sigkill_required=false |
| worker live samples | 7145 |
| incomplete-run observed peak | 387121152 B = 0.36053466796875 GiB |
| hard RSS limit | 1342177280 B = 1.25 GiB |
| process-tree swap | 0 |
| resource authority readable | true |
| worker stdout | 0 B |
| worker_summary_present | false |
| worker_qualification_pass | false |
| source start/end | f7591aa9a2ae581d748e97ec607ea6edb51d1b14；均 clean |

0.36053466796875 GiB 只是受控停止前的不完整运行峰值，不能写成 process-peak
Gate PASS，也不能替代完整 worker 的 retained payload。worker 被终止前没有写出
run_summary，因此下列项目全部是 unavailable，而不是 0 或预测值。
worker_qualification_pass=false 是 summary 缺失后的机械 fail-closed 值，不是
action algorithm FAIL。

### Gate disposition

| Gate | disposition | raw basis |
|---|---|---|
| completion/qualification within frozen 1800 s | FAIL / controlled stop | wall 1801.0560716170585 s；run_summary absent |
| action relative error / finite / deterministic | unavailable | worker summary absent |
| retained payload <=0.50 GiB | unavailable | payload 未写出 |
| MPI1/MPI2 identity | not_run / unavailable | 只有 MPI1 未完成运行；MPI2/compare 未启动 |
| full completed-run process peak <=1.25 GiB | not qualified | 只有 incomplete observed peak 0.36053466796875 GiB |
| swap | incomplete observed 0 | worker live process-tree swap |

这里的 completion Gate 是实际失败的停止条件；action 的数值 Gate 仍是
unavailable，不能改写成 algorithm FAIL。

| 未形成的正式证据 | 状态 |
|---|---|
| 四个 source 的 action relative error、finite、deterministic | unavailable |
| global rows / constraint count | unavailable |
| inventory qualification | unavailable |
| retained payload local/global sum/global max | unavailable |
| canonical dual identity | unavailable |
| 四个 candidate manifests 与 canonical 目录 | unavailable |

### 阶段边界与根因边界

mesh 文件在启动后约 1 秒已经写出。timeline 约 126 秒后显示 RSS plateau 为
387121152 B；同期只读 process checks 反复观察到约 110% CPU。CPU 是运行监控
诊断，不是 timeline 字段。按 runner 的写出顺序，canonical export 只有在首个
source 完成 reference 与两次 candidate apply 后才会出现；本次没有 canonical 目录。
因此能够确定的是“mesh 已完成，但尚未完成首个 source 的 post-action canonical
export”。现有 raw 没有更细的阶段 marker，不能进一步归因到 high-order space/MPC/form
setup 还是首个 source apply；不能把这次 timeout 写成 exact p6 action 被科学否证。

## 4. Raw evidence

原始目录为：

benchmarks/artifacts/task037_candidate_h_h1_2_f7591aa/mpi1

以下 artifact 位于 ignored 目录，不应 git add：

| 文件 | SHA256 |
|---|---|
| watchdog_summary.json | 8abfc2c3554271f8ba0a16380568e75f6122d00d623706b680f7d485d5976372 |
| watchdog_timeline.jsonl | e9cbe0b7e0cca9bfe07fb41a78e13ba82fe062f5c3701a4ce82658bacf4dd886 |
| worker_stdout.txt | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| mesh/mesh_3d.h5 | 1a5f026e2544c72196d0d14bd1f34e083afe79937f2925bc825db657a4b67b16 |
| mesh/mesh_3d.xdmf | e40e1b05f3269101fe93e96416481f14bcaa64fb1df5f030381c747b484b9864 |
| mesh/mesh_3d_partition_note.txt | 0a3e481d76798fa867ac1151dee5b3899920e623606faf36f175ee670c9ed974 |

run_summary.json、四个 candidate_manifest.json 和 canonical 目录不存在。没有运行
MPI2、compare、H2、H3、H4、full PDE、official field 或 official RTA。

## 5. 停止结论

本轮分类为 H1.2_CONTROLLED_STOP_TIMEOUT / H1_NOT_QUALIFIED。当前 Candidate H
authorized campaign 在 H1.2 停止；不建议据此 merge/master，也不建议延长 timeout、
重跑 MPI1、启动 MPI2 或把未形成的 action record 补写成通过。研究实现和这次负的
受控停止证据只保留在当前执行分支，等待 review。
