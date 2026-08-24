# V11 S2：p6/h10 foundation live set 资源资格

## 结论

这里的 **foundation live set** 指“完整求解所需的基础对象能否同时留在内存中”：高阶正算子、物理体积与 DtN 工作对象、低阶 LOR 矩阵、流式 transfer、工作向量以及 21 个 Krylov 基向量预留同时存活并被触页。它只回答内存生命周期和算子工作集是否成立，不代表 PDE 已收敛，也不代表任何物理结果已经通过。

S1 structural audit 已通过，S2 foundation resource audit 也已通过。因此 S3 的决策为：**PASS/PASS → 授权进入 S4 `lor_edge_geometric_mg_v1`**。本文件不表示 S4 已运行。

| 项目 | 实测事实 | Gate/解释 |
|---|---:|---|
| source | `12adebdf0e5e78de33818e97fd35cd870fef3a4e` | formal source 固定 |
| case | p6/h10/MPI1，13.5 nm | `complex128` / `int32` |
| worker samples | 659 | 外部 process-tree watchdog |
| cold peak | 983,363,584 B | `< 1,800,000,000 B`，通过 |
| external retained peak | 983,363,584 B | `<= 1,550,000,000 B`，通过 |
| headroom to 2 GB | 1,016,636,416 B | `2,000,000,000 - retained peak` |
| headroom to 1.55 GB | 566,636,416 B | `1,550,000,000 - retained peak` |
| repeated RSS growth | 0 B | `<= 32,000,000 B`，通过 |
| process-tree/rank swap | 0 B | 通过 |
| checker | `RETAINED_MEMORY_GATE_PASS` | `contract_errors=[]`, `gate_failures=[]` |

### 结构、矩阵与 reserve

| 对象 | 实测值 |
|---|---:|
| high rows / low rows | 173,802 / 173,802 |
| LOR `B_L` NNZ | 5,825,468 |
| LOR index / numeric bytes | 23,997,084 / 93,207,488 B |
| transfer retained bytes | 8,302,080 B |
| restart reserve | 21 basis + 4 auxiliary = 25 vectors |
| reserve numeric bytes | 69,520,800 B |
| known retained total | 249,126,201 B |
| unattributed remainder | 734,237,383 B |

`known retained total` 是可直接由保留数组、矩阵 payload、transfer metadata、DtN 工作量和 reserve 算出的部分；`unattributed remainder` 是外部 process-tree RSS 减去该总和，不是被遗漏后强行归零的数值。

### setup 阶段 RSS

| 阶段 | process-tree RSS | 相邻阶段增量 |
|---|---:|---:|
| start | 207,998,976 B | — |
| high mesh/space/MPC | 382,849,024 B | 174,850,048 B |
| high actions | 436,649,984 B | 53,800,960 B |
| low mesh/space/MPC | 644,374,528 B | 207,724,544 B |
| low matrix/transfer/topology/work | 939,810,816 B | 295,436,288 B |

mesh、space 和 MPC 的 C++ 对象没有可审查的独立 byte counter。上表的阶段增量是实际 process-tree 观测，`unattributed` 覆盖无法拆分的运行时/allocator/C++ 对象开销；不能把阶段增量相加后冒充对象字节数。

### 五类操作的重复身份

固定顺序为 `high_positive`、`physical_volume_dtn`、`restrict_high_to_lor`、`lor_edge_matvec`、`lift_lor_to_high`。每项真实执行 10 次，repeat index 为 0..9；所有输出 finite、输入 unchanged，10 次 digest 与 norm identity 完全一致，且没有保留 10 份向量。

| 操作 | norm | 10 次 digest |
|---|---:|---|
| `high_positive` | 294614.13313286984 | `5466647450fcafa5a659ca3c65bebb4879cdbfd4af91d95bc0b1d1924ec4a6de` |
| `physical_volume_dtn` | 272307.7081219559 | `4a9b909232d7fa81c68682ef815ec5f7c5d2cdd82c37140647c75df286a7cceb` |
| `restrict_high_to_lor` | 298222.4465525115 | `738704044a500ef801ad4d5636f7d2c24094025334a344527debae3ce393480f` |
| `lor_edge_matvec` | 28758.90365388692 | `f2e5126cafdbddef0b9ad6fdf23736b07a847570645d58067463481a00f8231e` |
| `lift_lor_to_high` | 68392.01311131215 | `0e0bb7c08be9129ce31e9e7f2b311a3080d56fdff9e82e25574542f27bac1549` |

### 禁止对象与资源口径

本次 record 明确没有构造或保留：HX/PCGAMG hierarchy、scalar node matrix、p6 exact edge factor、high-order global AIJ、global dense transfer、global direct coarse、recovery field arrays、numeric allgather。transfer 采用 owner-local streaming；工作集不是一张全局 dense transfer 矩阵。

`/init.scope` 是 non-dedicated shared cgroup。其历史共享 swap 值 `13,799,424 B` 仅作 diagnostic，不能计入本 case Gate；本案的正式 authority 是 process-tree/rank swap=0，且 `job_no_swap=true`。

## 保留的实现缺陷尝试

以下两次尝试都发生在 fixture 构造前，均不是数值 Gate，也没有被重分类为通过；ignored roots 原样保留。

| source/root | 事实 | watchdog.json SHA256 | watchdog.raw.jsonl SHA256 | worker.log SHA256 |
|---|---|---|---|---|
| `1c93fa9b7e92fc47a86ea2b8a5c2abe20f82a96d` | marker 参数冲突；RSS 61,546,496 B | `ee2876e5ca3009ee24bce24bdf88a8e7049d595a9f6bb6aeca69e6df4a9bdd91` | `2b2df3d077b6037874f82bdc0e896b9a968a1bcc1dfd09d8fbb2acfa8eac69b5` | `4f676882f0cd6c816fbf7cd6274de325dcf3897d50bb4629495124014178f295` |
| `ecaf99efa9a59915b668dd0c0d0afb314826d562` | transfer `nodes` 缺口；RSS 1,247,555,584 B | `27640a8a44ccfa08d551b623d5301e961f082c01c281c445e9953468e9a2a18c` | `1068d677b19beeeb70bed3b0d339e57eb233656775a05e1e8e2a02fb7b42d762` | `66f97ff5edfc3f9d005be2eb295769c78f8436a5d7bc5add76b1b083a2b01ff5` |

## Evidence index

以下均为本次 `12adebdf...` formal 的原始路径和哈希；大数组与时间线仍留在 ignored artifact root，不复制进 Git。

| 证据 | 路径 | SHA256 |
|---|---|---|
| worker record | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_p6h10_foundation_resource_v1.json` | `70f8f865a8943297364fdb2fdcbcbf164ceb4f56af8c48285bcca5f8af196a24` |
| independent checker | `docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/lor_p6h10_foundation_resource_v1_checker.json` | `4f6834a02948fb8d86031ce609d467889a70bef3f143cb1c2f2c1af78cc5605a` |
| watchdog compact | `benchmarks/artifacts/task038_extra_full3d_lor_p6h10_foundation_resource_v1/12adebdf0e5e78de33818e97fd35cd870fef3a4e/s2-p6-h10-mpi1/watchdog.json` | `5e5b6feeaba4e69bd0306bfd39300f6ea4c68598cc879f3af831dca1a3c11aa6` |
| watchdog raw ledger | `benchmarks/artifacts/task038_extra_full3d_lor_p6h10_foundation_resource_v1/12adebdf0e5e78de33818e97fd35cd870fef3a4e/s2-p6-h10-mpi1/watchdog.raw.jsonl` | `cc354f7142f57e210002fe5b7636e2f16528ac5d89340bd857e46b5c83282fc9` |
| apply ledger | `benchmarks/artifacts/task038_extra_full3d_lor_p6h10_foundation_resource_v1/12adebdf0e5e78de33818e97fd35cd870fef3a4e/s2-p6-h10-mpi1/worker_raw/apply_ledger.json` | `a06b176d361a8a341b1077f5b340ea8aa2a2fb1993c5a9f23b3261a4fa3698b2` |
| worker log | `benchmarks/artifacts/task038_extra_full3d_lor_p6h10_foundation_resource_v1/12adebdf0e5e78de33818e97fd35cd870fef3a4e/s2-p6-h10-mpi1/worker.log` | `e3b0c44298fc1c149afaf4c8996fb92427ae41e4649b934ca495991b7852b855` |

The worker log is empty; its SHA is nevertheless recorded as part of the evidence manifest. Marker files are under the same worker raw `markers/` directory and are bound by the record's marker sequence: `paths_ready`, `source_runtime_closed`, `fixture_built`, `reserve_built`, `apply_ledger_written`, `retained_ready`, `record_written`.

## S3 decision boundary

S1 structural PASS plus S2 resource PASS authorizes the next research stage **S4 `lor_edge_geometric_mg_v1`**. It does not authorize or claim completion of:

- S4 itself or S5;
- p6 physical Maxwell solve;
- p6/h5 qualification;
- 0.7 nm PDE or official physics results.

Any later stage must use a fresh source/root and its own numerical and resource evidence. No S4/S5 work is included in this closeout.
