# H2A-R1 隔离 JIT 与 fresh cache-hit 结果

本文件是 H2A 的持续 outcome。后续若获授权执行 H2A-R2，将在本文件追加，不另建 R1/R2 平行 outcome。

## 结论

H2A-R1 的目标是把昂贵的 form 编译从后续 factor/inventory 进程中隔离出来，并证明新进程能加载同一份已完成的 FFCx cache。这里的 form 编译，是把 UFL 双线性积分转换成 C/C++ 扩展并交给编译器生成可调用 kernel；它的短时峰值可能很高，但不等于已经构造了局部 factor。

| 项目 | 结论 |
|---|---|
| Review 合同 | Review V8 |
| H2A-R1 | **PASS** |
| formal 运行次数 | 2/2；attempt1 + attempt2，已用尽 R1 预算 |
| H2A-R2 | 已取得进入资格，但本轮未运行 |
| H2B/H2C/H2D/H4 | 仍 locked；未运行 |
| PDE/KSP/DtN/RTA | 未运行 |
| ordinary default | 未改变 |

隔离 JIT 的收益是让编译器、mesh、function space 和 MPC 对象不与后续在线对象长期叠加；代价是需要一次独立 staging、磁盘 cache 和额外进程启动时间。fresh hit 只证明“相同身份的 form 可以无新编译地加载”，不证明 factor、smoother、PDE 或物理结果已经通过。

## 固定范围与身份

| 字段 | 值 |
|---|---|
| source commit | `107a3ac1ea01ab0cfdd450a268789890ef76e030` |
| branch | `codex/20260806-task37-iterative-extra-development` |
| scope | p6/h10、MPI1、direct singleton |
| degree / h | 6 / 10 nm |
| JIT policy | `cffi_extra_compile_args=["-O0","-g0"]` |
| stage timeout / RSS | 3600 s / `<1,800,000,000 B` |
| hit timeout / RSS | 1800 s / `<1,750,000,000 B` |
| swap | 0 |
| R0 authority | 24 classes、nloc=882、rows=173802、constraints=9210 |

永久 full-space identity 保持冻结：

| identity | 值 |
|---|---|
| fine space | `uncondensed_fullspace` |
| fullspace global rows h10 | `173802` |
| condensation | `false` |
| global condensed Schur materialized | `false` |
| cell Schur matrix NNZ | `0` |
| slab matrix NNZ | `0` |
| static condensed operator | `false` |
| trace slab PC | `false` |
| B2/B4 local Krylov | `false` |
| fullspace patch lane | `true`；仅表示冻结候选 lane |
| interior recovery required | `false` |
| global matrix materialized | `false` |
| ordinary default changed | `false` |

阶段事实另行记录：stage 的 `jit_api_called=true`、`compile_called=true`、`compiler_probe_called=true`；hit 的 `jit_api_called=true`、`compile_called=false`、`compiler_probe_called=false`，并且 hit 只重建 mesh/space/MPC 和加载 cache，不做 class discovery、tensor tabulation 或 factorization。

## 两次正式尝试

### Attempt1：执行/来源证据失败，不是数值或资源 Gate 失败

| 项目 | 实际值 |
|---|---|
| source | `54ce2aefb151e5752d56e6aaac5a68634d7bc803` |
| 分类 | `CONTROLLED_FAIL_EXECUTION_PROVENANCE` |
| raw | [h2a_r1_54ce2ae_run1](../../../benchmarks/artifacts/task037_extra_development/h2a_r1_54ce2ae_run1) |
| stage elapsed | `23.9033112579491 s` |
| process-tree peak | `1,281,687,552 B` |
| swap | `0 B` |
| termination | `authority_unreadable` |
| hit | 未运行 |
| compact | [h2a_staged_factor_cache_attempt1.json](../../../benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache_attempt1.json) |
| compact file SHA256 | `5e755c98765c7afa5da8d71ba05461bf6258fe7a2f22a1dd56f2afaa13b86296` |
| embedded evidence SHA256 | `01cf9185dbc2501416f120187127fd1d69bfcf581ede1a845d6697b8f5533315` |

这次正式 shell 没有导出 `.git-codex` 的 `GIT_DIR/GIT_WORK_TREE`，所以 watchdog 的 source start/end 读取失败；同时短命 compiler child 的 `/proc` 状态在采样时不可读，watchdog 提前停止。它没有进入 hit，也没有产生可判断的 cache-hit 结果。该结果不是 JIT 数值错误、算法错误或 R1 内存 Gate 失败：当时使用的 stage 资源上限是 1.8 GB，实际峰值低于该上限，失败原因是来源身份和采样 authority 的执行证据不完整。

Attempt1 raw watchdog SHA 为 `ad13bb1ae51c64b08917e919806ec73662cfa95c4885dc8f3c8d139bcd9c8339`；stage progress/stdout SHA 为 `dc30d313a59dbd9c57293d246a7c308033c315c6ddbe4e2a7e912d840a895cd4`，stage timeline SHA 为 `9b56af09da1ad457d448e79ce728756b9ce85746f171817806c660b246ddc720`。这些负证据仍保留，未被 attempt2 覆盖。

### 唯一窄返修

返修只处理两个有 raw 证据支持的执行缺陷，未放宽任何资源或数值 Gate：

1. R1 专用 `_r1_inspect_source` 在调用 `inspect_tracked_source` 期间临时绑定绝对 `.git-codex` 与 work tree，`finally` 精确恢复原环境；R0 和共享 helper 未改变。
2. R1 phase loop 遇到一次不可读 process-tree sample 时写入 `transient_unreadable`，只做一次 15 ms 邻近确认。确认可读则以确认样本继续执行原 RSS/swap/time Gate；根进程正常退出则分类为 `root_exited`；仍不可读则分类为 `authority_unreadable_confirmed` 并受控终止。资源超限和 swap 仍立即按原 Gate 终止。

### Attempt2：通过

| Gate/证据 | 实际 | 限值/要求 | 状态 |
|---|---:|---:|---|
| stage completion | `28.54023524792865 s` | `<=3600 s` | PASS |
| stage process-tree peak | `1,172,946,944 B` | `<1,800,000,000 B` | PASS |
| stage swap | `0 B` | `0` | PASS |
| stage live samples | `551` | 可重算 | PASS |
| stage transient | `1`，`recovered_readable` | 必须分类 | PASS |
| stage compiler descendants | 8 | 编译期应可观测 | PASS |
| stage processes gone before hit | `true` | 必须为 true | PASS |
| hit completion | `3.4657565150409937 s` | `<=1800 s` | PASS |
| hit process-tree peak | `289,644,544 B` | `<1,750,000,000 B` | PASS |
| hit swap | `0 B` | `0` | PASS |
| hit live samples | `67` | 可重算 | PASS |
| hit transient | `0` | 无持久不可读 | PASS |
| hit compiler descendants | `0` | `0` | PASS |
| hit termination | `null` | `null` | PASS |

stage 的 transient 发生在 `curl_form_compile_started` 附近，记录的初始观测为 RSS `443,961,344 B`、swap `0`，随后确认采样恢复可读；因此没有把一次 `/proc` teardown race 错判成资源超限。两阶段 watchdog total elapsed 为 `32.024229330942035 s`。

## fresh cache-hit 证据

hit 阶段的 Form 状态为 `hit_no_new_decl_impl`；`form_jit_cache_hit=true`、`c_source_regeneration=false`、`cache_inventory_unchanged=true`，hit 的 compiler child count 为 0。stage 结束后所有 stage process 已回收，hit 才启动。

### p6 identity

| global cells | local nloc | global rows | constraints |
|---:|---:|---:|---:|
| 252 | 882 | 173802 | 9210 |

### 两个 form module 与 cache 文件

stage cold 与 hit fresh load 的 module、UFL/UFCx signature、cache 文件 path/size/mtime/SHA 完全一致。下表列出各 module 的四类文件 SHA；`.c.cached` 是 cache ready metadata，不是重新生成 C source 的证明。

| role / module | UFL/UFCx signature | `.c` SHA | `.o` SHA | `.so` SHA | `.c.cached` SHA |
|---|---|---|---|---|---|
| curl / `libffcx_forms_06c5be95446e812b0e7fd8039846a88aebdd0b55` | `4984517d077cbcb76eb9ffe85dacf15fc777f7be2a92cbad2dd537edc4d2ffa16d47b2ebc8ff13d0f5520aa81eb68f2df4ed37236b5831df72f9672a141d9961` | `b4b9576b21e2c7eff431568cf8ce08f3257b4d8a268fccb53ea3a3f23d4eebb5` | `601f8b8a408d66c4e1719b26f7f20655e56253f1807bc6b00f4c2f5dd3f601b2` | `dfd8c632eb3630efb206f23618f0469d0530f99426eb34dfac39dfd55256a1a6` | `a22d8c3dcac422cba145a7df3fef6a99ee1f99097e0cb00d31bf3455d6f432cf` |
| mass / `libffcx_forms_a64582b76588e96fbde0485693ca3c0d471f6544` | `d60c1df9a6d3a1e1761bd541cf926079c533985aea106f8b0afa5dc58326d922a084d219e1cdbfd94a7b718b4d21341dbe2fe58305f4914f54493a1e71d3f3ee` | `d1a3cf1f93b3374e9b90933db55258c08635ba2d3be5994aea8ca43c63b066d4` | `208e8c437dec5ecf7e76135b9219cf1a729b3fb125f8174b73bb40150cfab710` | `dfc99b81e7ad700c33be3cb18d66fd9953938a26b7e3085952c2f953e4a8958a` | `21c86086b76342f9c87e645df8d995d89034c72c15eec1076c27f7e3ea28fa23` |

### Fresh hit 的边界

这个结果证明了：在同一 UFL/element/scalar/options/cache 身份下，第二个 fresh process 没有新 C source、没有 compiler child，并且读取到完全不变的 cache inventory。它没有证明以下任何一项：LU factor 已构造、factor residual 已通过、constrained patch `C_c^H B_c C_c` 已实现、smoother contraction 已通过，或 PDE/KSP/field/RTA 已通过。

## Runtime 与 provenance

| 字段 | 记录 |
|---|---|
| qualified marker | `1` |
| Python | `/home/shenjh/Projects/MyFEniCS-Surrogate/.venv/bin/python` |
| PETSc | `3.19.6`，scalar `complex128`，int `int32` |
| DOLFINx / Basix | `0.10.0.post2` / `0.10.0` |
| FFCx / UFL | `0.10.1.post0` / `2025.2.1` |
| compiler | GCC `13.3.0` |
| OMP / OpenBLAS / MKL / NUMEXPR | 全部为 `1` |
| watchdog source start/end | `107a3ac1ea01ab0cfdd450a268789890ef76e030`，均 clean |
| R0 authority source | `b7eef17f10655be99f5bba072f9a547ae05f17ac`；仅作历史 R0 identity authority |

正式命令：

```bash
cd /home/shenjh/Projects/MyFEniCSx_task37_extra
export GIT_DIR="$PWD/.git-codex"
export GIT_WORK_TREE="$PWD"
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_h2 r1-watchdog --run-dir benchmarks/artifacts/task037_extra_development/h2a_r1_107a3ac_run2
python -m benchmarks.run_task037_extra_h2 r1-check --run-dir benchmarks/artifacts/task037_extra_development/h2a_r1_107a3ac_run2 --output benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache.json
```

## Evidence 索引

### Attempt2 compact 与 watchdog

| 项目 | 路径 / SHA |
|---|---|
| raw directory | [h2a_r1_107a3ac_run2](../../../benchmarks/artifacts/task037_extra_development/h2a_r1_107a3ac_run2)；ignored |
| tracked compact | [h2a_staged_factor_cache.json](../../../benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache.json) |
| compact file SHA256 | `672b036c69edfd74ee613ecc7264b0d699cb472730ebf76a048db1cb333c21ef` |
| compact embedded evidence SHA256 | `361187150b5c2ff4c76094cb99c26436d1d7c29e0709ae42608cbc9f154221cc` |
| compact status / problems | `pass` / `[]` |
| watchdog summary file SHA256 | `725eaee9349006339d50b48007376cecc63616226fc9a4fbb3bd85e721f70b66` |
| watchdog embedded evidence SHA256 | `1937f83c23be8de8d64710cc18e368675a84154f4594191300aa24c59064a297` |

### Attempt2 raw artifact hashes

| 文件 | bytes | SHA256 |
|---|---:|---|
| `stage_progress.jsonl` | 1,590 | `2cac36655ad521367d8f1af74b8308119eeeb57fcfc90e84f5020e018da7e86f` |
| `stage_stdout.txt` | 1,590 | `2cac36655ad521367d8f1af74b8308119eeeb57fcfc90e84f5020e018da7e86f` |
| `stage_summary.json` | 16,009 | `6fffc143b6205c0d4c118661396f779a037703114bc722466a1efba6ea505871` |
| `stage_timeline.jsonl` | 186,159 | `4580d60ef8f347b45658aedc1b81d726a1dd700658453a5397141278ab21f573` |
| `hit_progress.jsonl` | 1,860 | `868690f8dae47e3018abfb26c93c5a51940bc2eea2aab83165ef9b08aa84e0c1` |
| `hit_stdout.txt` | 1,860 | `868690f8dae47e3018abfb26c93c5a51940bc2eea2aab83165ef9b08aa84e0c1` |
| `hit_summary.json` | 17,838 | `e43a86341e8fc0d1eccdbbacabe68114af0fd63165d8ead6672c522087d83da4` |
| `hit_timeline.jsonl` | 21,350 | `fa781b3b3a0a4494c783dd1ffe33230812e5b44a779609a5e247fe861c2ed9b5` |

Attempt1 与 attempt2 的 raw 都在 ignored artifact 目录；tracked 只保留 compact record。attempt1 compact 被保全为 [h2a_staged_factor_cache_attempt1.json](../../../benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache_attempt1.json)，不得覆盖 attempt2 的 canonical 文件，也不得把 attempt1 的失败字段改写为通过。

## 阶段边界与下一步

H2A-R1 PASS 只表示隔离 form-JIT 和 fresh cache-hit 证据通过，授权进入 H2A-R2。R2 才能验证每个 exact class 的代表性 tensor、constrained block、exact numeric hash/dedup、LU factor、factor manifest 与实际 resident payload；R1 不等于 factor 或 smoother pass。

本轮没有运行 H2A-R2、H2B/H2C/H2D/H4、KSP、PDE、DtN、field 或 RTA。H2B/H2C/H2D/H4 继续 locked；不得把本 outcome 的 cache-hit 结果外推为 PDE 内存或物理结果。H2A-R1 的 formal 预算已经用完（2/2），后续只能按 Review V8 顺序进入获授权的 R2，不得原样再跑 R1。

## H2A-R2 受约束 factor store 正式 PASS（primary attempt #1/3）

### 这一步做什么

R1 只证明昂贵的 form 编译可以隔离，并且新的进程能从冻结 cache 命中；它还没有产生局部数值因子。R2 在同一 full-space 局部算子上加入真实的 Floquet 约束展开：稀疏的 `C_c` 把一个 cell 的完整自由度映射到独立的全局行，然后暂时计算
`C_c^H (K_curl + k0^2 M_|epsilon|) C_c`，再按 exact numeric class 复用一个 pivoted LU。相同 class 的 cell 只保留 class 引用和 gather 行，不为每个 cell 保存 dense 矩阵或 factor。

这样做的收益是可以直接审阅“约束后的局部 action、factor residual、solve residual 和真实 JSON/NumPy factor payload”；代价是需要保存 factor store，并且它仍然只覆盖局部 action/factor 证据，不等于全局 PDE、KSP、smoother 或物理场结果。

| 项目 | 实际状态 |
|---|---|
| Review 合同 | Review V8 |
| H2A-R2 | **PASS** |
| formal attempt | `#1/3`；本轮没有重跑 watchdog |
| 本轮 checker | 对既有 raw 执行两次相同的 `r2-check`；两次均 PASS 且 canonical 字节完全相同 |
| source | `da8ddbb257b0d9d510e9d711d23144f50dabd0e4`，start/end 均 clean |
| scope | p6/h10、MPI1 singleton、252 cells、`nloc=882` |
| operator | `C^H*(K_curl+k0^2*M_abs_epsilon)*C` |
| timeout / RSS | `<=7200 s` / `<1,750,000,000 B` |
| swap | `0 B` |
| R1 cache | 已通过 R1 authority 的同一 cache；命中后未重新 staging |

正式命令与本轮轻量复现命令如下；本轮对同一 raw 连续执行两次 lightweight checker，均 PASS 且 byte-identical，不启动 worker/heavy：

```bash
cd /home/shenjh/Projects/MyFEniCSx_task37_extra
export GIT_DIR="$PWD/.git-codex"
export GIT_WORK_TREE="$PWD"
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.run_task037_extra_h2 r2-watchdog \
  --run-dir benchmarks/artifacts/task037_extra_development/h2a_r2_da8ddbb_run1
python -m benchmarks.run_task037_extra_h2 r2-check \
  --run-dir benchmarks/artifacts/task037_extra_development/h2a_r2_da8ddbb_run1 \
  --output benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache.json
```

### R2 Gate 实测

| Gate / measured field | 实际值 | 限值或合同 | 状态 |
|---|---:|---:|---|
| global rows / constraints | `173802 / 9210` | 固定 authority | PASS |
| cells / local `nloc` | `252 / 882` | 固定 authority | PASS |
| exact classes | `24` | `<=32` | PASS |
| unique numeric factors / hash dedup | `16 / 8` | `<=32` | PASS |
| transformed action relative error（24 classes最大值） | `0.0` | `<=1e-11` | PASS |
| factorization residual（最大值） | `8.540193602788576e-16` | `<=1e-10` | PASS |
| representative solve residual（最大值） | `4.861914019080286e-11` | `<=1e-10` | PASS |
| factor finite / measured deterministic | `true / true` | 均须为真 | PASS |
| loaded solve deterministic | `true` | 必须为真 | PASS |
| process-tree peak | `717139968 B` | `<1,750,000,000 B` | PASS |
| swap | `0 B` | `0` | PASS |
| completion elapsed | `4658.770581231918 s` | `<=7200 s` | PASS |
| live samples / termination | `18506 / null` | 可重算、正常结束 | PASS |

Factor store 在 cold builder 阶段的 factor audit 为 `201925908 B`；正式 payload Gate 采用释放 builder 后由 loader 验证的磁盘 manifest authority，而不是用较小的 worker 自报值。manifest 绑定 JSON 和全部 NumPy 数组，loader 冷加载后给出如下闭合口径：

| retained factor + metadata 组件 | bytes |
|---|---:|
| factor values | `199148544` |
| pivots | `56448` |
| per-class sparse expansion | `508128` |
| cell reference arrays | `1781144` |
| canonical metadata / file bindings | `439548` |
| 合计 `factor_plus_metadata_bytes` | **`201933812`** |
| R2 限值 | `400000000 B` |

合计与 manifest/loader 的 verified payload 完全相等，因此该 payload Gate PASS。24 个 class 都产生了 `factor_started` 和 `factor_ready`；builder 随后释放，cold load 只加载已验证的 factor store。每个 cell 仍只有 class ID 与实际 independent global rows，没有 per-cell factor、global matrix、Schur 或 slab factor。

### R0/R1 authority 与 cache identity

| authority | 固定身份 |
|---|---|
| R0 record | [h2a_class_discovery.json](../../../benchmarks/cases/101_task37_extra_development/records/h2a_class_discovery.json)，file SHA `3024dea6ac33aa24c78a86e3f9ae7e699630320906134088f7df302b992e134d`，source `b7eef17f10655be99f5bba072f9a547ae05f17ac` |
| R1 record identity | 旧 canonical file SHA `672b036c69edfd74ee613ecc7264b0d699cb472730ebf76a048db1cb333c21ef`，embedded evidence `361187150b5c2ff4c76094cb99c26436d1d7c29e0709ae42608cbc9f154221cc`，source `107a3ac1ea01ab0cfdd450a268789890ef76e030` |
| R2 current record | [h2a_staged_factor_cache.json](../../../benchmarks/cases/101_task37_extra_development/records/h2a_staged_factor_cache.json)，file SHA `2af81d454b89d63e1a5d03916286b527112dd76da34259712e73557918516c9c`，embedded evidence `c288b8c4d5b0e2587b26c7404fb73685095bacff82ca70fcea6373356442c405` |
| R1 snapshot evidence | `c2a6512ee753adab88f715326f0b719a1bbc76af8f1e8d8c032949c3e610f3d1`；由 R2 record 自带 evidence hash 绑定 |
| R1 cache authority | `h2a_r1_107a3ac_run2/jit_cache`；R2 cache before/after unchanged，`form_jit_cache_hit=true` |
| compiler descendants | `[]`；R2 不重新编译 C source |

R2 checker 同时保留并 hash-bind 了 R0 class inventory、R1 record identity、当前 worker/watchdog summary 和 factor-store manifest；`status=pass`、`problems=[]`。canonical R2 record 内还带有自带 evidence hash 的 `r1_authority_snapshot`，其中冻结 R1 record/raw artifacts、runtime、stage/hit forms、cache inventory 与 watchdog evidence；第二次 checker 会从该 snapshot 重新验证同一 R1 authority，而不依赖已被提升的 canonical 路径。R1 的旧 raw 和 attempt1 负证据没有被覆盖；R1 record 的旧 SHA 在 R2 raw 中作为冻结 authority 保存，即使 canonical 路径现在承载 R2 record。

### 永久 full-space identity

| identity | R2 实际值 |
|---|---|
| fine space | `uncondensed_fullspace` |
| condensation | `false` |
| global matrix / global constraint matrix | `false / false` |
| global condensed Schur | `false` |
| cell Schur matrix NNZ | `0` |
| slab matrix NNZ / slab factor count | `0 / 0` |
| static condensed operator / trace slab PC | `false / false` |
| B2/B4 local Krylov | `false` |
| fullspace patch lane | `true`；仍是冻结候选 lane |
| interior recovery | `false` |
| KSP / DtN / PDE solve | `false / false / false` |
| ordinary default changed | `false` |

本次 R2 PASS 的准确含义是：在固定 MPI1 p6/h10 full-space action 上，约束展开、exact class factorization、residual、determinism、cache identity、factor artifact 和资源 Gate 均有通过的证据。它不表示已经完成 smoother contraction、global PDE/KSP、field/RTA、DtN 或 direct-method physical comparison。

### Raw evidence 索引

Raw 目录为 ignored artifact：[h2a_r2_da8ddbb_run1](../../../benchmarks/artifacts/task037_extra_development/h2a_r2_da8ddbb_run1)。关键文件 SHA 如下；factor manifest 内部另外 hash-bind 107 个 NumPy/JSON 文件条目：

| raw 文件 | SHA256 |
|---|---|
| `run_summary.json` | `fa22734a63fc5ed953a81e0ee7649c5229cca1d1fc89d0fde481488489e1c8dc` |
| `r2_watchdog_summary.json` | `f552014db609f11b7b5554ff5c82f790f002052f5323f9429cbe214e0d87a053` |
| `r2_watchdog_timeline.jsonl` | `6fd4c51580d0559cfca681fe89fe431f0ef114812ccea57330697dbea37194fd` |
| `r2_progress.jsonl` | `3f1dc478e2e3074d1adcec407ac8dbecdf96d90350569994dc8c10690edc8ca6` |
| `r2_worker_stdout.txt` | `231d51c20a3041d0729b291cb7a750739b4bfb49de7cfb5481094b0b5c806992` |
| `r2_root_pid.json` | `1946d90b37c0de187c80b41fa6bdc30920c6d11069604ffd0f7c71329e698b87` |
| `factor_store/manifest.json` | `1bac2dab37ac19dfa6ab81834327b96e251b1178e0ff652a03347bdd0fa48f98` |

### 运行边界

H2A-R2 通过后，Review V8 允许继续讨论后续阶段；本轮没有运行 H2B、H2C、H2D、H4、KSP、PDE、DtN、field 或 RTA，也没有生成 H2B 文件。不要把 `201933812 B` 的局部 factor payload 或 `717139968 B` 的 R2 action 进程树峰值外推成 PDE 内存结论。后续若要进入 H2B，仍需遵守 Review V8 的阶段授权和新的 Gate；R2 PASS 不自动等于 H2B 或物理求解通过。
