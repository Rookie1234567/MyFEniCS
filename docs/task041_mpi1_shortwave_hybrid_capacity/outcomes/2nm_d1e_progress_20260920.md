# Task041 2nm D1e 运行进展（D2a 冻结窗口）

本例是钨（W）、2nm、p6/h1.5、M1200、MPI8×1。Schur 是供外层迭代使用的模态耦合预条件矩阵；重复样本计划是在两侧各 8 列、每列算两遍，共 32 次，当前仅有 21/32 个样本，不能当作 formal 进度。

## 状态

截至 2026-09-20 01:19:51.480911341Z（CST 09:19:51.482977410），D1e unit
`task041-d1e-2nm-p6h1p5-m1200-mpi8.service` 仍为 `active/running`，Invocation
`1cf5e34338754dbfa80df487b322c72c`，MainPID `571560`，CPU1–8、每 rank 数学线程1。
此状态不是终态；`systemd Result=success` 不代表 solver PASS。

producer QEP 已完整保存并释放 producer scope：mode-prep wall
`29501.598348574014 s`，selected modes 为每方向1200，formal consumer QEP calls `0`。
consumer 仍在 modal/Schur 候选阶段，正式 Schur response `0/4800`；outer FGMRES
`not_started`、outer response `0`（分母不适用），RTA `not_run`。

## 21 个 modal 小 RHS 的冻结聚合

从 [`balh_side_rhs_audits.jsonl`](../../../results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z/consumer/numerical_output/balh_side_rhs_audits.jsonl)
读取 `phase=modal_schur` 的 21 行（bottom13/top8），未加载 FE 数组。文件 as-of
大小/行数/SHA 为 `63009 B`/`29`/`6ad01110ab9335f953c1064903e846fa3298d6ca7090a1f5341998dd13b2179c`。

| side | count | iterations sum / range | elapsed sum / mean (s) | elapsed range (s) | rank0 Q/A6/H6 `per_rank_accumulated_seconds` sum (s) |
|---|---:|---:|---:|---:|---:|
| bottom | 13 | 273 / 9–51 | 27977.90938461572 / 2152.1468757396706 | 899.4712390978821–5227.512858337024 | 15991.318321351893 / 8700.545055122348 / 2183.074874829501 |
| top | 8 | 197 / 11–56 | 21253.56579890987 / 2656.6957248637336 | 1155.1779964989983–6149.74191578012 | 12403.696700270288 / 6339.517980669392 / 1763.2767441337928 |

固定样本推导为
`(27977.90938461572/13 + 21253.56579890987/8) × 2400`
`= 11541222.24144817 s = 133.57896112787233 days`。
这是样本均值外推，不是 ETA；8 条 cost probe 的约115.17天 derived arithmetic 另列。21 条 modal audit 全部 `reason=2`、`explicit_true_target_reached=true`，最大 `relative_residual=0.009981656767193032 <= 0.01`；这不是最终全局残差。Q/A6/H6 是嵌套或 rank0 audit 累计量，不相加冒充 critical-path wall；`batch_size=32` 是分批，不是32路并行。

## 资源与 producer packet

冻结 memory sample 的 `sample_elapsed_seconds=142181.0448487869` 独立于报告 wall。
原始 `memory_stages.jsonl` 对应单行 byte offset `1257553500`、3535 bytes、SHA
`7e96bb667fbff3e391540a3f066a65e412c436cad6f8c3daad33fe72d690e619`；该行给出
process-tree RSS `642483105792 B`、dedicated cgroup current/peak
`647585968128/647695921152 B`、job swap `0`、global swap 基线 `8192 B`、MemAvailable
`1018492968960 B`。这是单行/括号证据，不是完整运行峰值。

selected packet 为 33 文件 `4842723531 B`，manifest 声明32个 shard，流式核验
missing/byte mismatch/SHA mismatch 全为0；manifest SHA
`7ef2ecc5587f79a123e44cacfe347356d13b36336948ade1672787c6430163d2`。producer
`mode_prep_summary` 已为 `TASK041_MODE_PREP_PACKET_READY` 且 `producer_scope_released=true`。
这里只持久化 selected mode packet，`qep_workspace_persisted=false`；producer/consumer
未来可以分别记录 source SHA，复用时分别核对物理、布局与 ABI identity，不要求两者 SHA 文本相同。

不过 `supervisor_summary.json` 当前不存在，既有
`validate_balh_producer_packet(..., require_public_supervisor_summary=True)` 因而尚未给
公共 consumer-only reuse 资格。受控结束时应保留 producer runroot、让现有 supervisor/finalizer
写完整 public summary/lifecycle/resource 证据，再按原 `--producer-packet-root` validator
复核；不伪造 summary，也不把内存中的 factor/native workspace 当成可接续 checkpoint。

完整 hash-bound 记录见 [`task041_d2a_progress_20260920.json`](records/task041_d2a_progress_20260920.json)。
