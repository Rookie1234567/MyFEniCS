# V11-0 继承审计：exact response 与 full Hybrid 基线

## 1. 范围与身份

本文件是 Review V11 的 V11-0 docs-only inherited audit。它只核对既有 hash-bound 记录、任务书和只读环境快照，不修改 solver、runner、JSON 数值记录、ordinary defaults 或 ignored raw；本轮没有运行测试、MPI、PDE、algebra、TSQR/SVD、top pilot、producer 或 formal。

审计时间：2026-08-22T00:57:17+00:00 UTC。写入前工作树 clean；本轮唯一产物是本 Markdown，随后由 V11-0 独立 docs-only commit 提交。

| 项目 | 结果 |
|---|---|
| 分支 | codex/20260812-task39-5nm-hybrid-0p7nm-feasibility |
| V11-0 audit base HEAD | 6b58076b859c713850a0cf8eda89ede7febf3dbf |
| upstream | 同名远端分支，指向 6b58076b859c713850a0cf8eda89ede7febf3dbf |
| ahead/behind | 0/0 |
| Review V11 中的 reviewed HEAD | b4d4759e3cff670c2cc420146a5130fe957ad79b；这是 review 编写时的旧审阅基线，不是本次 audit base |
| Review V11 | docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/review_report_v11.md |
| Review V11 SHA256 | d2e5550933df45fa3e85d13ac4df726c43dec3cae76d4510d4efa71a794b5797 |
| master | 未触碰；未创建新分支或 worktree |
| 本轮修改范围 | 仅本文件；无 Python、测试、阈值或 raw 修改 |

6b58076b 是先对同名 upstream fetch --prune 后以 merge --ff-only 得到的目标 SHA；没有 merge commit、rebase 或 force 操作。

## 2. 既有记录与来源链

下表只引用既有 compact evidence、tracked record 或 ignored run root；raw 没有被复制进 Git。

| 层级 | 记录或来源 | 身份与 hash-bound 结果 |
|---|---|---|
| V7 full-side authority | benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v7_exact_side_full_formal_v1.json | SHA256 412610be438423e893c6886bf617132b3cb5f0241937243e3cd1fb1303104bd2；来源 9e31ecf189081afcb8ca27b0374ec89af0094e2d |
| V7 outcome | docs/task039_5nm_hybrid_qualification_and_0p7nm_feasibility/outcomes/v7_exact_side_limit.md | SHA256 c2949060d5b152f904c504e85478ff1531bcc3157e62a2403010e37e91e8b289 |
| V10 compact authority | benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v10_side_response_packet_v1.json | schema task039.v10.side_response_packet.v1；SHA256 4094beac26b90baf349c8849d0f155c53ed268668e94614cac0e770cf4a58781 |
| V10 full producer | results/task039_v10_h4_side_response_packet_full_producer_mpi8_dbc5e9bf | producer source dbc5e9bfdf9ad0520881caa168c7a27316d50f10；manifest SHA256 1f4e8acaf278bde0d0d14a2a096335049ee988cdbc1b406bca4197918ff64a0e |
| V10 status-independent recheck | results/task039_v10_h4_side_response_packet_full_recheck_5efc715a/recheck.json | record SHA256 a6691e7b1cf72449a533da9689cdc901d468f39975d70f60450c49b933cb92ac；recheck source 5efc715a81049abcac94233ece51594b3b773d3c；15/15 checks true；原 parent status contract_mismatch 与 reason identity_factor_packet_or_gate_mismatch 原样保留 |
| V10 compression | results/task039_v10_h4_side_response_packet_compression_mpi8_30b40d43 | compression source 30b40d4303a1da90769557aee8d0f493c784591f；worker 236.720152 s、parent 约 239.730152 s、process-tree peak 15.4776763916 GiB、swap0、factor/KSP0；execution/resource/lifecycle pass，但泛化 negative |
| frozen old holdout carrier | benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v6_port_modal_bottom_component_v1.json | SHA256 00c8b889d75b7fa0b77a6563d4ffe708a07d00f23133dec06b5929e4cabe3368；producer 7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f；catalog SHA256 a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384 |

旧 holdout catalog 的规则是 sorted relative path、byte count 和 file SHA256 行的 SHA256；覆盖 8 个 producer ranks、6 个 labels 和 96 个 response artifacts。V10 复用的 exact spool 是 results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output；selected/exact spool manifest SHA256 为 2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067。

V10 full producer 还绑定 input SHA256 4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811、physical model SHA256 8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c、resolved config SHA256 f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883。factor identity 是 bottom、research exact-side LU、factor-only storage；profile/scope 是 task039.v10.h4.side_response_packet.full_producer.v1。

## 3. 物理、输入与完整 workflow baseline

| 项目 | 继承身份或结果 |
|---|---|
| 物理 | 5 nm、1 degree grazing、phi=0、S polarization |
| formal 离散 | p6/h4、Hybrid iterative M480、MPI8 |
| official input | input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat |
| matched direct baseline | 93.377006531 GiB |
| 当前 best full iterative workflow | 80.025856018 GiB；1 outer iteration；相对 direct RSS saving 14.298113646% |
| V7 measured setup-only peak | 81.056903839 GiB |
| V7 setup advancement line | 84.039305878 GiB 是 Gate/advancement line，不是 measured peak |

full iterative 是完整 workflow authority；V10 producer、pilot 和 compression peak 是 component/sequential evidence，不能冒充完整 workflow saving，也不能把阶段峰值相加。

## 4. Fresh host probe 与 ABI 口径

资格化 activation 没有重新测量成功：source scripts/activate_myfenics_wsl.sh 在当前会话报告 Qualified WSL temporary directory /tmp is unavailable。下表把 fresh host 只读值与 inherited qualified identity 分开；没有把 activation 失败写成 ABI 通过。

| 项目 | fresh V11-0 probe | 口径 |
|---|---|---|
| MemAvailable | 240648232960 B | 当前 host 只读值，不是 formal process-tree peak |
| swap | total 34359738368 B，used 0 B | 当前 host 只读值 |
| /home/Projects/MyFEniCS 可用磁盘 | 815081861120 B | df 当前值 |
| CPU count | nproc 48 | 当前 host 只读值 |
| OMP/MKL/OpenBLAS threads | 当前均未设置 | 未据此推断 formal worker thread 数 |
| qualified activation | not_remeasured | /tmp 不可用；未安装依赖、未修改 activation、未启动 MPI/PDE |
| MPI/scalar | inherited formal identity 为 MPI8 / complex128 | 来自 hash-bound V10 records，不是本轮 fresh ABI probe |
| PETSc IntType | not_available | 本轮未启动 qualified Python |
| formal thread setting | not_recorded | 不能把当前 unset 环境变量冒充正式线程证据 |

本轮没有 pytest、MPI2/4/8、PDE、solver import 或 heavy process，因此没有新增测试计数或 fresh PETSc ABI 结论。

## 5. 阶段内存与 V11 resource Gate

V10 packet evidence 中可比较的 process-tree RSS peak 为：full producer 50.7548675537 GiB（54497624064 B）、成功 16-column pilot producer 43.20536804199219 GiB、full compression consumer 15.4776763916 GiB、成功 pilot consumer 1.649871826171875 GiB。它们属于不同顺序阶段；PSS/USS 在这些 compact records 中未测。

三进程或多阶段的 observed maximum 是 50.7548675537 GiB，即四个阶段峰值取最大值而不是求和。该值不能替代完整 V7 workflow 的 80.025856018 GiB，也不能与 direct 的 93.377006531 GiB 相减来宣称 V11 component saving。

Review V11 后续定义 producer 进程树峰值不超过 60 GiB、factor-free consumer 进程树峰值不超过 79 GiB、swap 为零、producer/consumer 不重叠、payload 不超过 16 GiB、wall 不超过 21600 s。full physics workflow 继续使用 V7 的 residual、field、RTA 和 finite Gate。这些是后续 Gate 定义，不是 V11-0 新运行结果。

## 6. 继承结论与负结果边界

- V7 exact-side full formal 是当前完整 workflow 的 best available discrete reference：资源低于 matched direct，但保留两侧 full factors，不能外推为 0.7 nm solver。
- V10 exact response producer/recheck 在 provenance、residual、payload、factor lifecycle 和资源上通过；它是 research-only response authority，不是 side inverse 或 production default。
- V10 compression 的执行、资源和生命周期通过，但 rank512 effective rank 为 478，holdout indices 0、1、480、481 仍约 0.9673，因此 generalization/compressibility negative，production promotion 不允许。
- V9 combined-action output 曾有 historical controlled numerical failure；V10 A/B、scatter 和 current combined action 均 finite，因果首次阶段未建立。
- V10 四个 pilot wiring/lifecycle failures 和后续 compression producer-SHA 漏传 failure 均保留在现有 compact evidence；它们是 implementation evidence，不与数值负结果混称。

## 7. V11-0 Gate、后续阶段与禁止项

V11-0 只完成继承审计和 docs-only commit，没有宣称 V11-1 或后续阶段通过。以下项目均 not_run：

| 后续路线 | V11-0 状态与边界 |
|---|---|
| V11-1 bottom response algebra | not_run；本轮未做 block algebra 或新 action |
| V11-2 closed-set compression | not_run；本轮未做 TSQR/SVD |
| V11-3 top pilot / producer | not_run |
| V11-4 top/both/full response | not_run |
| V11-5、V11-6、V11-7 后续 formal 或 response | not_run |
| bottom producer 重跑、V10 replay、full Hybrid/direct/exact-side | 禁止，未运行 |
| selected packet、QEP、global direct factor、generic ILU/BLR scan | 禁止，未运行 |
| 0.7 nm PDE/full formal | 禁止，未运行 |

ordinary defaults、master、历史 raw/negative records 均未改。后续阶段必须继续绑定同一 source/input/physical identity，并分开报告 producer、consumer 与完整 workflow 的内存口径；不能把本审计的 inherited values 当成新 formal 结果。

## 8. 审计限制

1. fresh host 的 MemAvailable、swap、磁盘和 CPU 已测；qualified ABI、PETSc IntType、fresh MPI/threads 因 /tmp activation blocker 标为 not_remeasured 或 not_available，没有安装依赖或修改环境。
2. V10 compact 对 packet stages 的 process-tree RSS 有 hash-bound 数值；PSS/USS 和本轮 fresh process-tree sample 未测。
3. raw results 仍在 ignored roots；本文件只绑定 tracked records、manifest/config hashes 和既有 outcome，不复制或修改 raw artifact。
4. V11-0 没有新的数值、资源或物理结论；本阶段 Gate 是身份完整、继承边界清楚、禁止项未启动。后续阶段必须重新提供自己的 raw、source SHA、资源和 true-residual evidence。

## 9. V10 producer 与 shared packet 的强绑定

V10 bottom full producer 是 component evidence，不是完整 workflow 结果：

| producer 字段 | 继承实测值 |
|---|---|
| process-tree peak | 50.7548675537 GiB，即 54497624064 B |
| payload | 2034244800 B |
| maximum true residual | 1.52248376596e-10 |
| factor lifecycle | ready 1，cleanup 后 0 |
| swap | 0 |
| measured total wall | 4390.176657371572 s |
| classification | exact response producer component pass；research-only，不是 side inverse |

V10 绑定的 shared selected-mode/exact-spool packet root 是 results/task039_v5_h4_mumps_blr_side_component_mpi8_7e5d9b57_1e3/numerical_output，manifest SHA256 是 2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067。V10 full packet output root 是 results/task039_v10_h4_side_response_packet_full_packet_dbc5e9bf，producer manifest SHA256 是 1f4e8acaf278bde0d0d14a2a096335049ee988cdbc1b406bca4197918ff64a0e。两者身份不能被新阶段静默替换。

## 10. Qualified snapshot、tier 和阶段解锁

fresh qualified activation 在本轮标为 not_remeasured，直接原因是 /tmp unavailable。最近的 hash-bound V10 qualified snapshot 记录的环境身份为：qualified activation、qualified interpreter、PETSc scalar complex128、PETSc Int32、OpenMPI 4.1.6、MPI8、thread setting 1。它是继承快照，不是本轮重新测量；本轮只读 fresh host 的 MemAvailable、swap 和 disk 值仍按第 4 节记录。

完整 workflow 与 component 的内存层级必须分开。当前权威序列是 direct 93.377006531 GiB、best full workflow 80.025856018 GiB；Review 的后续 saving tiers 为 74.701605225 GiB、65.363904572 GiB、56.026203919 GiB、46.688503266 GiB。workflow peak 的定义是 bottom producer、top producer、consumer 三者 process-tree peak 的最大值，不是三者相加；V11 后续 factor-free consumer hard stop 为 79 GiB。V10 bottom producer 的 50.7548675537 GiB 只能作为 component envelope。

V11 的阶段解锁顺序是：bottom algebra Gate 失败即收口；bottom 通过后才允许 top pilot；top pilot 通过后才允许 full；top factor ready 1 且 cleanup 后 0 才允许 consumer；五个 mandatory residual 与 resource Gate 都通过后才允许 recovery/physics。V11-0 尚未解锁其中任何执行阶段。

## 11. V11-0 完整禁止项

本阶段明确禁止：bottom producer 重跑、direct/V7 exact-side 重跑、J1-alone、SN2、普通 ILU/BLR/sweep 扫描、Full3D heavy、0.7 nm PDE、并发 heavy、任何新分支或 worktree、master 修改、物理条件修改、M480 修改、阈值修改、符号或困难列修改、raw artifact 提交，以及把历史 component peak 或 inherited Gate 写成新的 formal 通过。
