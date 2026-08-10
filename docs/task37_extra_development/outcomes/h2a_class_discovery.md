# H2A-R0 exact-class discovery 结果

## 结论

本次 H2A-R0 是“先看清楚有多少种可共享局部块”的预检查。它在不编译 form、不生成 dense cell tensor、也不做 LU factor 的前提下，根据局部几何、材料、取向以及 Floquet 约束拓扑，识别能复用同一局部块结构的 exact topological class。这样可以先估计未来 factor 的数量和内存上界；代价是本阶段只验证 class 身份和约束行数，尚未验证 factor 数值、求解动作或收缩后的逆。

| 项目 | 结果 |
|---|---|
| H2A-R0 状态 | **PASS** |
| 正式运行 | formal #1（最多 2 次预算中的第 1 次；未进行第 2 次） |
| watchdog / checker | 均仅运行一次，exit code 均为 0 |
| source SHA | b7eef17f10655be99f5bba072f9a547ae05f17ac |
| 资格结论 | 取得进入 R1 的资格；不等于 factor 或 H2B 已资格化 |

本结果是 class-discovery preflight，不是 PDE/KSP 结果，也不是某个局部 factor 已经被构造或验证的结果。旧的 H2A 资源 hard stop 负证据仍保持不变，未被本记录改写。

## 运行范围与实际测量

运行顺序固定为 p6/h10、p2/h10、p2/h5；每个 case 都先完成 mesh、未凝聚 full-space 函数空间和 Floquet MPC，再做 class discovery，随后释放 case 对象并清理拓扑缓存。没有进入 form、tensor 或 factor 阶段。

| case | degree / h | global cells | global rows | constraints | local nloc | unique classes | finite |
|---|---:|---:|---:|---:|---:|---:|---|
| p6/h10 | 6 / 10 | 252 | 173,802 | 9,210 | 882 | 24 | true |
| p2/h10 | 2 / 10 | 252 | 7,246 | 1,054 | 54 | 24 | true |
| p2/h5 | 2 / 5 | 1,680 | 44,698 | 3,898 | 54 | 32 | true |

细化关系为 32 × 252 = 8,064 < 24 × 1,680 = 40,320，因此 p2/h10 到 p2/h5 的 class 增长严格低于 cell 增长，R0 refinement Gate 通过。这个 Gate 只涉及 discovery 的 class/cell 计数，不涉及 factor 或 smoother。

## p6/h10 的 24 个 exact classes

下表中的 width、orientation、material tag 和 constraint pattern 都来自正式 worker 的 compact record。class-key SHA 和 pattern SHA 为可审阅的缩短显示；完整 64 位 SHA、完整 class inventory 以及所有 upper-bound 字段以 [tracked compact record](../../../benchmarks/cases/101_task37_extra_development/records/h2a_class_discovery.json) 为 authority。

| class id | cells | material tag | widths | orientation | pattern entries / kinds | reduced rows | class-key SHA（前 12 位） | pattern SHA（前 12 位） |
|---:|---:|---:|---|---|---|---:|---|---|
| 0 | 13 | 1 | 8.25 / 8.333333333333 / 10.0 | [0] | 162 / corner,x,y,face-x,face-y | 882 | 9792c0cca16a | 5cd1f1cd98ec |
| 1 | 13 | 1 | 8.25 / 8.333333333333 / 10.0 | [0] | 84 / x,face-x | 882 | 45e56d1aacfa | 23ca6393f217 |
| 2 | 39 | 1 | 8.25 / 8.333333333333 / 10.0 | [0] | 84 / y,face-y | 882 | e7b1af6b73c5 | 74b61822bd69 |
| 3 | 52 | 1 | 8.25 / 8.333333333333 / 10.0 | [0] | 0 / — | 882 | 5291cb077cda | 4f53cda18c2b |
| 4 | 13 | 1 | 8.25 / 8.333333333333 / 10.0 | [32769] | 84 / x,face-x | 882 | ea27a124f777 | 23ca6393f217 |
| 5 | 26 | 1 | 8.25 / 8.333333333333 / 10.0 | [32769] | 0 / — | 882 | 27ab54e93bfb | 4f53cda18c2b |
| 6 | 1 | 2 | 8.25 / 8.333333333333 / 10.0 | [0] | 0 / — | 882 | dea6d4738dc7 | 4f53cda18c2b |
| 7 | 1 | 2 | 8.25 / 8.333333333333 / 10.0 | [36873] | 84 / x,face-x | 882 | d09c287146fd | 23ca6393f217 |
| 8 | 2 | 2 | 8.25 / 8.333333333333 / 10.0 | [36873] | 0 / — | 882 | 37600c4982d6 | 4f53cda18c2b |
| 9 | 1 | 2 | 8.25 / 8.333333333333 / 10.0 | [4680] | 162 / corner,x,y,face-x,face-y | 882 | 9b44383a14bd | fb838a3681a5 |
| 10 | 1 | 2 | 8.25 / 8.333333333333 / 10.0 | [4680] | 84 / x,face-x | 882 | 97810a332037 | 12b7f51c8a02 |
| 11 | 2 | 2 | 8.25 / 8.333333333333 / 10.0 | [4680] | 84 / y,face-y | 882 | c67a5b4f37ba | bde089671257 |
| 12 | 2 | 2 | 8.25 / 8.333333333333 / 10.0 | [4680] | 0 / — | 882 | 6b12cd1ed460 | 4f53cda18c2b |
| 13 | 1 | 2 | 8.25 / 8.333333333333 / 10.0 | [576] | 84 / y,face-y | 882 | dd87ffcbde23 | 74b61822bd69 |
| 14 | 1 | 2 | 8.25 / 8.333333333333 / 10.0 | [576] | 0 / — | 882 | d4ed3eabb425 | 4f53cda18c2b |
| 15 | 2 | 1 | 8.5 / 8.333333333333 / 10.0 | [0] | 84 / y,face-y | 882 | 43f737dc56fe | 74b61822bd69 |
| 16 | 2 | 1 | 8.5 / 8.333333333333 / 10.0 | [0] | 0 / — | 882 | 9deff5faeb83 | 4f53cda18c2b |
| 17 | 2 | 1 | 8.5 / 8.333333333333 / 10.0 | [32769] | 0 / — | 882 | 5359e9f6db06 | 4f53cda18c2b |
| 18 | 2 | 2 | 8.5 / 8.333333333333 / 10.0 | [36873] | 0 / — | 882 | a31945ae8a60 | 4f53cda18c2b |
| 19 | 2 | 2 | 8.5 / 8.333333333333 / 10.0 | [4680] | 84 / y,face-y | 882 | f1857ec6ec77 | bde089671257 |
| 20 | 2 | 2 | 8.5 / 8.333333333333 / 10.0 | [4680] | 0 / — | 882 | 66df76dab8e0 | 4f53cda18c2b |
| 21 | 24 | 3 | 8.5 / 8.333333333333 / 10.0 | [0] | 84 / y,face-y | 882 | e6f1901fe212 | 74b61822bd69 |
| 22 | 24 | 3 | 8.5 / 8.333333333333 / 10.0 | [0] | 0 / — | 882 | 9d9b5d62f722 | 4f53cda18c2b |
| 23 | 24 | 3 | 8.5 / 8.333333333333 / 10.0 | [32769] | 0 / — | 882 | bcad93db8a53 | 4f53cda18c2b |

每个 p6 class 的 constrained reduced row count 都是 882；这只说明当前约束拓扑下的 reduced-row 计数与本地 nloc 相同，不表示已经生成 constrained factor。

## factor 上界预测（不是实际 retained payload）

R0 只把每个 class 的未来 one-factor payload 上界写成可审阅的预测：complex128 dense values 加 int32 pivots。由于 24 个 class 的 reduced rows 都是 882，raw local nloc² 与 constrained reduced-size 的两套数值上界恰好相同。

| 预测口径 | 每 class values | 每 class pivots | 每 class 合计 | 24 classes 合计（含 metadata） |
|---|---:|---:|---:|---:|
| raw nloc × nloc | 12,446,784 B | 3,528 B | 12,450,312 B | 298,825,403 B |
| constrained reduced size | 12,446,784 B | 3,528 B | 12,450,312 B | 298,825,403 B |

| 元数据字段 | 值 |
|---|---:|
| canonical inventory metadata bytes | 17,915 B |
| metadata basis | canonical UTF-8 class inventory |
| 24 class numeric upper bound | 298,807,488 B |
| 24 class upper bound + metadata | 298,825,403 B |
| requires numeric dedup | false；只表示预测上界未因 400 MB 预算要求额外 dedup；V8 R2 仍强制 exact numeric hash/dedup |

这些是按每个 topological class 一份 factor 的 upper-bound 估计，不是实际 retained factor bytes；本轮没有 factorization，也没有 factor finite/determinism 数值证据。因此不能把 298,825,403 B 直接写成 factor Gate PASS，也不能写成 H2B qualified。只有在后续 R1/R2 实测确认没有额外增长时，才可说该预测位于 400,000,000 B 预算内。

## 资源与生命周期测量

| 指标 | 实测值 | R0 解释 |
|---|---:|---|
| watchdog completion elapsed | 10.862848650896922 s | PASS |
| process-tree peak RSS | 314,286,080 B | < 1,000,000,000 B；通过 R0 RSS Gate |
| swap | 0 B | PASS |
| live samples | 43 | 可重算 timeline peak |
| termination | null | 未触发 controlled stop |
| 最后一个 progress marker | worker_summary_started | summary 前的最后阶段 marker |

三个 case 的 marker 顺序均为：

1. mesh_build_started / mesh_build_ready；
2. function_space_started / function_space_ready；
3. floquet_mpc_started / floquet_mpc_ready；
4. class_discovery_started / class_discovery_ready；
5. case_release_started / case_release_ready；
6. 最后为 worker_summary_started。

全程没有 form_compile、form JIT、tensor tabulation、factorization 或 factor serialization marker。case release 后清理 Floquet topology cache；这证明本次 discovery 生命周期没有把 case 级对象带入下一 case，但不替代后续 process-tree 资源测量。

## 冻结 identity 与禁止对象

| identity / inventory 项 | 记录 |
|---|---|
| fine space | uncondensed_fullspace |
| fullspace global rows（h10） | 173,802 |
| condensation | false |
| global condensed Schur materialized | false |
| cell Schur NNZ | 0 |
| slab matrix NNZ | 0 |
| static condensed operator / trace slab PC | false |
| B2/B4 local Krylov | false |
| fullspace patch lane | true |
| R0 patch/factor constructed | false |
| global matrix materialized | false |
| form JIT / tensor tabulation / factorization | false |
| interior recovery required | false |
| ordinary default changed | false |

fullspace_patch_pc_used=true 是冻结的候选 lane 身份，不表示本 R0 已经构造 patch 或 factor。由于 R0 明确没有进入 form/tensor/factor 阶段，不能把这些“未调用”字段误解为 factor 或 solver 已通过。

## Evidence 与复现身份

正式 source 为 b7eef17f10655be99f5bba072f9a547ae05f17ac，worker/watchdog 两端 source clean 且稳定。运行使用 qualified Linux ABI：qualified marker 为 1，PETSc scalar 为 complex128、PETSc integer 为 int32，四个线程变量均为 1，Python 为 /home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python。

正式 raw 目录：

    /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_development/h2a_r0_b7eef17_run1

正式 watchdog 命令：

    python -m benchmarks.run_task037_extra_h2 r0-watchdog --run-dir /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_development/h2a_r0_b7eef17_run1

正式 checker 命令：

    python -m benchmarks.run_task037_extra_h2 r0-check --run-dir /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task037_extra_development/h2a_r0_b7eef17_run1 --output /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/cases/101_task37_extra_development/records/h2a_class_discovery.json

### Compact record

| 项目 | 值 |
|---|---|
| compact 路径 | [h2a_class_discovery.json](../../../benchmarks/cases/101_task37_extra_development/records/h2a_class_discovery.json) |
| compact file SHA256 | 3024dea6ac33aa24c78a86e3f9ae7e699630320906134088f7df302b992e134d |
| embedded evidence SHA256 | 5003c13c16a93ed58957a1048d583b214a8c6381a99d4d36c284737354db0f3c |
| compact schema | task037.extra.h2a.r0.check.v1 |
| status / problems | pass / [] |

### Raw evidence hashes

以下是本次 R0 的六个主要 raw evidence 文件；raw 目录中的 mesh 文件也保留在 ignored artifacts 中，未进入 Git。

| 文件 | bytes | SHA256 |
|---|---:|---|
| r0_progress.jsonl | 7,016 | 4283eb1032d559782f61cf965344b95bd3aaace234f8f9103b698df19eebedcb |
| r0_root_pid.json | 61 | f874838cba868a4faf9dee908c2b79b055971a864197a310f832e37b260fa4b4 |
| r0_watchdog_summary.json | 3,329 | a1780f4167cbe70a74867a74bad7fbf35114ee23bd4363a485d88bb70552a8cc |
| r0_watchdog_timeline.jsonl | 11,058 | f47c9032b6047a1ccc40f6fb08ce072a52db21ce141aa11fb1e11a13212a2a69 |
| r0_worker_stdout.txt | 7,016 | 4283eb1032d559782f61cf965344b95bd3aaace234f8f9103b698df19eebedcb |
| run_summary.json | 67,289 | 4ab9216f9801d1dfd38bcdd043a14f8903c49ac675a6a3c4eea3ec7b08a1cfff |

worker summary 的 embedded evidence SHA 为 3138ef4327a8a071af575c27c952b03b930ce7430a989ce415fac239f0fddd15；watchdog summary 的 embedded evidence SHA 为 f4408e272d884289483d6a7ba812765c0cbd2129c3e2ac2f6987e2414f9264a6。compact checker 对 raw hashes、source、runtime、marker 顺序、watchdog timeline 和 worker qualification 均独立复核，最终 problems=[]。

## 验证与边界

| 验证项 | 结果 |
|---|---|
| test_289 R0 focused | 24 passed |
| test_286–test_289 focused suite | 61 passed |
| compileall | pass |
| git diff --check | pass |
| Ruff | unavailable（未安装；不声称 CI 通过） |

本轮结论是 H2A-R0 PASS，并取得进入 R1 的资格；但尚未运行 R1、R2、H2B、H2C、H2D、H4、PDE、DtN 或 RTA。H2B 及后续阶段仍锁定，不能由本次 discovery 结果自动解锁。

以下冻结结论保持不变：G2 LOR-HX 为 G2_FAIL；G3 additive LOR-HX prohibited；旧 G4 sweep with failed LOR-HX prohibited；旧 H1.2 为 CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED。H1R3 与 V7 的既有结论也不被本 outcome 改写。旧的 H2A 资源失败记录 h2_block_class_inventory 保持原样，作为负证据与本次 R0 PASS 并列保存。

当前 Review V8 已授权 R0 PASS 后自动进入 R1；R2 仅在 R1 PASS 后解锁；H2B 及后续阶段仍锁定。R0 的 upper-bound 小于 400 MB 只能说明“若实际 factor 没有额外增长，预测在预算内”；它不是 R2 Gate PASS，也不是 H2B/PDE 资格。
