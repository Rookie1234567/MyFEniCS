# G1 factor storage 与 mixed-precision 能力收口

本轮只审计两种可能的工程收益。factor reuse 的意思是：如果两个 slab 的局部线性求解问题完全相同，可以只保留一份 factor；mixed precision 的意思是：尝试只把局部近似 factor 的数值降为 complex64，而 fine operator、右端项、外层解、true residual 和 R/T/A 仍保持 complex128。两条路线都要求先证明身份和数据类型，不能用近似相似替代证明。

## 结论

| lane | 结果 | 含义 |
|---|---|---|
| G1.1 exact factor reuse | `capability_stop_unverifiable_factor_ordering_and_values` | 7/8 只有必要条件 prefix 相同，未证明完整 exact identity；不共享 factor |
| G1.2 mixed precision | `capability_stop_global_petsc_scalar_abi` | PETSc 全局 scalar 是 complex128，complex64 输入会被存成 complex128；不做 mixed one-slab oracle |
| G1 overall | `closed_negative_capability_stop` | G1 关闭负结果；允许进入 G2.2 的 one-slab full-space identity 准备，不承诺 factor reuse 或 mixed precision |

## G1.1：唯一 M3a screen 的身份

这是唯一一次 G1.1 screen20，源码为 `bb5b4da51761ea38e852e45ced7a41b3eeae95bd`。范围固定为 p6/h10/S、`assembly_time_static_condensed`、M3a overlap0.125 partition、M2c never-materialized、MPI1、20 步 screen、poll 0.25 秒、warning 10 GiB、terminate 14 GiB、timeout 1800 秒、zero swap；本次未启用 G0 diagnostics，因此没有 residual snapshot。

| 项目 | 实测 |
|---|---:|
| watchdog | `task037_m3a_overlap0125_partition_screen_pass` |
| solver | 20 步，`DIVERGED_MAX_IT(-3)` |
| true residual i0 / i10 / i20 | `1.0 / 0.14446444295860594 / 0.04474243612765` |
| official RTA | `false`，postprocess skipped |
| global A/F | 未物化 |
| process-tree memory authority | `4.256050109863281 GiB` |
| swap | `0` |

## Factor 必要条件审计

| 指标 | 结果 | 解释 |
|---|---:|---|
| factor 数量 | 16 | slab 0–15 均有记录 |
| shifted local numeric matrix | 7 classes / 9 duplicates | 只说明 shifted local 数值矩阵相同，不说明 factor 可共享 |
| global stored factor NNZ | `91415952` | 明确指实际存储 factor 的 NNZ；本次 raw 中与旧 `global_factor_nnz` 数值相同 |
| row-ID/order + shifted prefix | 15 classes | 绝大多数 numeric duplicate 被不同 global row identity 排除 |
| 剩余必要候选 | `[7, 8]` | 两者共享 row hash、shifted matrix hash 和 prefix |
| qualified groups/count | 未形成 / 0 | material、独立 shift、ordering、factor values 尚未验证 |
| measured bytes saved | 0 | factor sharing 未实现 |

7/8 的三个 hash 是：

```text
row_ids_sha256          = 428e8c62f51e4f0a27903ec2e21412843245fa7de65655ffcdfad1c18c166d7b
shifted_matrix_sha256  = e0ff9108c190efc854669f3e9f361dcd526496652905167137660e7560fde2d7
necessary_prefix_sha256= 5dff0b6fe82aab46ff8681fe2a3aa0c87014213a7e9cffd666249b8dfdfb8611
```

完整 factor storage/value 与 ordering 的 tiny PETSc probe 得到以下 capability stop：

| API | 结果 |
|---|---|
| `PC.getFactorOrdering()` | API 不存在 |
| factored `Mat.getOrdering()` | PETSc Error 73，`Not for factored matrix` |
| `getValuesCSR/getRow/getValue/getValues/retrieveValues` | PETSc Error 73，`Not for factored matrix` |
| `convert("seqaij")` | PETSc Error 73，`Not for factored matrix` |
| `getDenseArray()` | 当前 factored object 不支持 |
| `getRowIJ()` | 空结构，不能作为可靠 factor storage |

所以不能把 `rcm` 请求字符串当作实际排序 fingerprint，也不能从 factored `Mat` 伪造 factor values hash。G1.1 状态为 `capability_stop_unverifiable_factor_ordering_and_values`；没有 factor sharing。

## G1.2：全局 PETSc scalar capability

tiny probe 使用资格化 activation，以 NumPy complex64 值写入一个 2×2 SeqAIJ，再读取 PETSc CSR；随后只执行 ILU(0) setup，不读取禁止的 factor values。

| 字段 | 结果 |
|---|---|
| NumPy 输入 dtype | `<c8`（complex64） |
| PETSc ScalarType | `numpy.complex128`，dtype `<c16` |
| PETSc IntType | `numpy.int32`，dtype `<i4` |
| SeqAIJ CSR values dtype | `<c16`（complex128） |
| ILU factor type | `seqaij`，继承全局 scalar `<c16` |

这证明当前 PETSc build 的 scalar ABI 是全局固定的：complex64 输入会在 PETSc 矩阵存储中提升为 complex128。没有复制到 Python、反复 cast、切换 PETSc ABI 或改变 solver。因而没有 one-slab mixed oracle、没有 20/100-step global screen，payload reduction 为 `not_measured/not_applicable`；fine operator、RHS、outer solution、true residual 与 R/T/A 均未改变。

## Evidence

紧凑 hash-bound record 为 `benchmarks/cases/101_task37_extra_development/records/g1_factor_storage.json`。screen raw evidence：

| 文件 | SHA256 |
|---|---|
| `task037_f3_core_audit.json` | `0a3cc1e66d3801afe4a84e9b32a6ac45603313c167e8d653c0f1c192d276bdec` |
| `watchdog_summary.json` | `afd31279f394d23193cdf7729b7373cc4cef32d50535ad0531ec62d698195b2e` |
| `run_summary.json` | `9d424cf0ad3e37bb2c64a789f8f2a5eb29e7541278928b91cea7fb7e0cd78acd` |
| `progress_3d.jsonl` | `28d5045400b23794ed2731ac281af57239ad8c9995ebb922c5124e1b4a66ce11` |
| `memory_timeline.csv` | `6218ed647333e63c80dc9117420b1bfd5ffc11084b5f9cae0b1d7661cf2093fa` |
| `worker_stdout.txt` | `f0e12554e5d33a2cd2615b671bd6c5fd851e4c7147958f35803ff373e23368c6` |

两个 tiny probe 都通过 `exec_command` 在沙箱外执行；每次都先运行
`source scripts/activate_myfenics_wsl.sh`，再用 `python_mode=inline_stdin_heredoc` 执行，
没有独立 `script_file`，命令正文也没有持久化文件。record 内完整保存了实际 4×4 和 2×2
矩阵 entries、PC 类型、ILU level、ordering 与结果，不使用描述性伪命令，也不为 probe 伪造 hash。
G0 authority/response 未修改。
