# Review V16 Q1：physical p-coarse source-authority 收口

## 结论

Q0 已通过；Q1 核心已实现并提交为 research/unqualified scaffold，但固定六 probe
formal 不具备合法 source authority。

| 阶段 | 结果 |
|---|---|
| Q0 | PASS；Q0 reference commit 12252290c3d9ec51713094f08c335f24ce172a5b |
| Q1 | CONTROLLED_STOP_PREMEASUREMENT_PROVENANCE / NOT_QUALIFIED |
| 原因 | V16 要求 p6/h50 的 R3 probe，唯一旧 R3 authority 是 p6/h10 |
| Q2–Q6 | not_run |
| W0–W4 | not_run_by_trigger_not_met |
| official physics | not_run |

source authority 是带完整 mesh、物理、mode 和 canonical-key 身份、能证明 probe
代表指定问题的输入；不能靠改文件名、重新 hash 或跨网格猜测得到。本轮只做
元数据和源码语义核对，未读取 checkpoint 数值、未构造 mesh/JIT/MPI 对象。

## 实现与冻结边界

| 项目 | 值 |
|---|---|
| Q1 clean core | 6edf5f5c1255185052a2a5d5fb8dd422f3238f04 |
| branch | codex/20260820-task38-extra-full3d-iterative-0p7nm |
| core 内容 | physical p-coarse、fixed restart20 FGMRES support、test343 |
| 状态 | implementation-only；未提升 ordinary default 或 production |

六 probe 为 random、gradient、curl、checkerboard、physical_component_derived、
r3_long_tail_derived。P/P^H、physical action、linearity、repeat、finite、slave-zero、
canonical MPI 和 Galerkin Gate 均未运行。

## 旧 R3 authority

| 字段 | 只读事实 |
|---|---|
| tracked compact | outcomes/records/lor_edge_geometric_mg_r3_route_b_v2.json |
| compact SHA256 | 4c3f9f23f22bc9e20cef8992d99db86f8eda159951b78b016685214bbc274b68 |
| case | p6-h10-mpi1，degree=6，h=10 nm，MPI1，Route B，levels=[6,2,1] |
| full rows / active dual packets | 173802 / 164592；9210 slave rows excluded |
| canonical role | full_fe_dual；sha256(canonical-key-json-v1) |
| R3 source SHA | 2c8fca90c7300b85b30021081868b699c0b306d2 |
| input / physical / mode SHA | 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41 / 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f / dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| ignored manifest | benchmarks/artifacts/task038_extra_full3d_iterative_t5_authority_v2/r3_2c8fca90/mpi1/raw/canonical/residual.manifest.json |
| manifest SHA256 | 62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce |

这是 p6/h10 的 local canonical dual 与 p6→p2→p1 interlevel evidence；不定义
h10→h50 full-FE dual restriction/projection。

## 已有 h50 facts

| 对象 | 事实 |
|---|---|
| 当前 F1 p3/h50 | mesh=[4,4,3]，degree=3，full rows=4641，slaves=465，active full_fe_dual packets=4176，full_fe primal packets=4641 |
| 当前 F1 evidence | benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/f1_floquet_wave_small_oracle_v5/fb1b4be71d230b77eff431a7e3dd77eb3a69ba69/mpi1/record.json |
| 旧 T2 p3/h50 | mesh=[1,1,3]，rows=3018；不同旧几何，不能替代当前 authority |
| p6/h50 | 无 tracked 或已资格化 record；rows/key inventory 未建立 |

## reconstruct 的 fail-closed 边界

src/solvers/hcurl_canonical_vector_dolfinx.py 中，_canonical_packet_map（约
698 行）对错误 role、空 packets 和 duplicate canonical key 直接失败；
reconstruct_canonical_full_fe_dual_vector（1040 行起）对缺失 entity/cell/full-FE
key 直接失败（1123、1163、1190–1193），MPI1 对 unexpected extra key 直接失败
（1194–1198）。它没有跨 mesh 插值、投影或物理身份转换能力。

因此 same-mesh P63/P63^H、旧 LOR/interlevel transfer、PETSc row 重排或重新 hash
都不是 R3 authority 修复。没有发现经过资格化的 h10→h50 full-FE dual map。

## 历史与阶段决定

V13 positive、V14 J5 的 CONTROLLED_STOP_USER_NUMERICAL_STAGNATION、V15
F1/F2 通过与 F3 span 失败、以及全部历史 negative 均原样保留。用户明确允许
真实 checkpoint/数值测量前唯一定位的 path/cache/marker/import/provenance bug
窄修后用新 SHA/root 重试；真实 identity、numerical、span、2 GB、swap、nonfinite
Gate 不得重跑。本次是缺少新的 h50 source 定义/映射数学合同，不是局部代码 bug。

Q1 六 probe formal 不可启动，Q2–Q6 not_run。按 V16 文字，W0 只由真实数学、
数值或资源 Gate 关闭 Q 后触发；本次没有该类 Gate，因此 W0–W4
not_run_by_trigger_not_met。下一步需由主线程选择：提供合法 h50 R3 source
定义/映射并继续 Q1，或明确授权把该 blocker 视为 Q 关闭并进入 W0。
