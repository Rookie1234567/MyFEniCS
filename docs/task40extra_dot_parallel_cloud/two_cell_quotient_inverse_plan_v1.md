# Q3–Q5：两 y-cell 完整恢复逆与冻结 carrier 复用计划

**范围与结论。** 本文件为外部只读实施计划，2026-10-01 核对 canonical clean HEAD `35dd9e5c39939d14bbded98f288007aff4a08368`，未改 canonical、未导入求解项目、未做数组诊断、factor、solve、user PC 或提交。建议只恢复已审计的 C/D/H 系数，重建真实网格/MPC、体积作用和原有胞元消元/恢复缓存，再重形成 q 块比较后分解。该路线可避免重复 532-mode raw/literal 装配；当前 API 尚不能直接加载旧 spool 或注入 carrier，须先实现以下窄桥并独立审阅。全部 Q3–Q5 仍 `NOT_RUN`，不授予目标尺寸、精度、2 TB/48 h 或 production 资格。

## 1. 冻结证据与可复用对象

下文源码路径均相对 `/workspace/scratch/9c465670b46b/task40extra_cloud/repo`。Q0–Q2 的权威运行根为 `benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_two_cell_p4_phi5_audit_attempt1`（简称 `R`），`R/audit_report.json` SHA256 为 `d0bade55828b8e842f240ad3eb8b5d79d9adfdeb06976ad5be8e0a8fb2aeb37f`。该报告为 `QUOTIENT_OPERATOR_AUDIT_PASS`；本次只重读 JSON/源码及报告 SHA，未重新执行 checker 或声称所有二进制已新鲜复核。已有 worker 334 s / RSS 741 MB、checker 4842 项通过 / 10.4 s / RSS 313 MB / swap 0 的监督成绩是历史准入依据，不能当未来常驻内存。

|保存对象|准确入口|恢复用途/边界|
|---|---|---|
|四 positive-H q CSR|`R/arrays/q_{0,1,2,3}_S_{data,indices,indptr}.npy`，各描述符在 report.artifacts 与 artifact_manifest.json|形状 1884² /1960² /1960² /1960²；NNZ 436012 /454744 /454744 /455143；三数组合计 36,043,932 B。保留全部四分支，不复用 ±q 因子|
|228/304 同-live literal raw receipt|`R/raw_twist_0/raw_port_receipt.json` / `R/raw_twist_1/raw_port_receipt.json`|SHA256 `16a6e11102a91592f26f80fe943296bd0f668ff4be58236b766ddfa1a81f0bef` / `e85d03c9460641d2d273e0df600337d659dca6651724e274d877b97169fc84fe`；均为 `PASS_QUOTIENT_RAW_PORT_AUDIT_ONLY`，原文继续保留 deferred forcing/factor/output scope|
|原532与两sector的精确快照|`R/raw_global/raw_packet_manifest.json`、`R/raw_twist_{0,1}/raw_packet_manifest.json`，各 `packet_XXXX.json`|记录完整 source/discrete/JIT context、原 mode row、local/global H 与 stored C/D 稀疏对；每包数组路径/hash 在 sparse_payload。只读逐包，不集齐 raw dense vectors|
|本地 native row inventories|`R/arrays/twist_{b}_{independent_storage_rows,trace_original_rows,interior_original_rows,slave_storage_rows}.npy`|7936 independent /3616 trace /4320 interior /1004 slave；重建实际映射后逐项相等，不能把旧数组伪装为新 MPC|
|本地 H|`R/arrays/twist_{b}_original_H.npy`|228/304 个正值，必须仍为原完整 H/2；positive-H 用原 H，不能用 Hhat|
|volume/condensation 身份|report.twists[b].condensation.condensation|20 个完整 300×300 raw/oriented tensor hash、operator_cache_identity、分区与 cache audit；这些缓存没有序列化，须重建|
|原四载荷/完整场/模式控制|`benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p4_phi5_centered_attempt1`，其 `probe_report.json` SHA256 `a71c0e177394b436c9b787b62f780db19ebcdce0410a85a346dbcf4fcc42151f`|保存旧 full3D p4 results、generic/interior_only/physical/notch_supported RHS、regular/notch fields 与532逐模式输出；是独立小夹具控制，不能进入 candidate 全Ny setup|

完整物理 generator SHA256 仍为 `4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951`。两个恢复 carrier 必须分别满足以下全部身份，而非仅 C 数值 hash：

|b|assembly context|assembly mode manifest|carrier numeric|
|---|---|---|---|
|0|`8aa59251313a3e468d14bd765b6590ad396c22de1f3bc6325713625b3e88d781`|`8670b5bfd8fd0882c06aaaeb1782ebb1ba1e3d3c6510965fe67fcd962c9053d0`|`72453449ab8b758a74bd3613d237368554fa7f2cf8f3e1dcd978cf40097db930`|
|1|`7320d45bf685f80e8739b76c32cc086079883a76a4cdf71459e43a463df7014d`|`ca1b878794a0ece5dede2ec68eff1346b4035f9f5b6e1015f2dc4763e4f54018`|`b08580a66e52d07ac06fd68840d027a267f062572fc3c7200c7875f77bf25292`|

full80 carrier 的当前冻结 context 是 raw_global 包中的 `40bef5d252789a12236b19feeb5f417e053c76cbab4cab3a2252138f45b894f5`；Q0–Q2 没有另写一个新的 global literal receipt。应逐包恢复当前 532 snapshots，同时以已 hash-bound 的旧 p4 `live_component_receipt.json` 的 before/after numeric digest `199d3bb28c624672d5d263877fa00c53909a1976fd69ae3e63a77bec11910cfd` 及保存 original C/D/H/slave authority 校验内容。旧 global assembly context/manifest 继续属于旧 source，不能要求它们冒充 current snapshot 的 context/manifest；当前完整 manifest 必须由 packet context与现identity算法重算并绑定。global当前context、full/source/discrete映射相等及旧numeric控制缺一不可。

## 2. 最小恢复桥：历史系数权威与新体积计算分开绑定

1. 建议新增独立 research 模块 `src/solvers/y_orbit_qualified_snapshot.py`，提供仅只读的 manifest/packet reader 与恢复 wrapper。**不改 `RawModeSpool`**：现 `y_orbit_raw_packet_spool.py:RawModeSpool.__init__` 遇已有 manifest 必然报错；当前没有 reopen API。reader 延续其十段 offset、metadata codec、path containment、file SHA/array SHA、dtype/shape/payload 与 complete finite stream 检查，使用 `allow_pickle=False`/只读 mmap，并在任何 PETSc narrowing 前验证 int64 范围。不要通过 `__new__`、私有属性赋值、DOLFINx/PETSc 内部缓存注入绕过合同。snapshot 只保留当前包所需的 stored 段；raw 段不重新装配、不做阈值裁剪。
2. 从原 cfg 以 `build_dynamic_mode_inventory` / `build_ordered_mode_manifest` 重建 532 个原物理对象；两局部 sector 仍由 `y_orbit_quotient_context.py:build_two_cell_assembly_config/build_two_cell_quotient_context/select_inventory` 选取原对象。独立模式索引、原 key/row、局部 branch 与原顺序须完全相等，228+304=532 恰覆盖一次，不把 local cfg 的周期用于重新生成 gamma/beta/kz。
3. 用保存的 `stored_C_sparse`、`stored_D_sparse`、`local_plane_H` 建 `FullspaceDtnModeFunctional`，再通过 `fullspace_dtn_action.py:FullspaceDtnCarrier(entries, global_rows, ownership_range, slave_rows, batch_size=8, comm)` 的公共构造器规范化。D 已含一次物理共轭，恢复时不再共轭。packet 未直接保存完整 assembly mode_identity；其 `original_mode_row`、真实 mode、context、H 和 quotient mapping 足以按现 `build_fullspace_dtn_carrier_from_surface` 的 boundary/quotient identity 逻辑（当前 877–911 行）重建。复用 `_mode_identity`/`phase_gauge_descriptor`/`deep_frozen_identity` 的现算法，不改 physical coefficients，不虚构 C-hash whitelist。必须由构造器重新得到 `mode_manifest_sha256`，再用 `dtn_boundary_plane_qualification.py:carrier_numeric_identity` 与 receipt 的 before/after 全字段完全相等；一项不同即停，不能先使用后解释。
4. 恢复的 context 原文继续归属 **历史 primary port kernel**。公共 carrier 对象的 boundary/quotient metadata 应采用现 surface builder 的相同字段，另增加独立恢复 provenance（旧 run/report/receipt/packet hashes、恢复代码 SHA、`coefficients_restored=True`、`new_port_kernel_assembled=False`）。不把旧 `compiled_surface_gauss_identity` 宣称为本次新加载 JIT 的证明，也不把恢复写成新的 same-live literal PASS。
5. 重建实际 `_build_same_mesh_levels`，用 finalized public MPC arrays、geometry/tags/facets、Basix coefficient matrix、orientation、cell dofmap、cfg/ABI/explicit eta/tau/corner 对保存 context 全面核对。可复用 `y_orbit_quotient_raw_qualification.py:_actual_discrete_binding/_source_binding` 的只读验证思想；禁止调用会装配 literal forms 的 `qualify_quotient_raw_bundle` 来伪造恢复资格。原 Gauss/JIT 二进制 hash 仍可只读校验其历史文件，缺失时记录历史 provenance 无法复核并停在 restoration Gate，不自动换一个新 C hash。
6. 当前 `build_same_mesh_physical_action` 没有注入已恢复 carrier 的参数，调用它一定会先编译/装配新 ports。为保持 frozen assembly sources 字节不变，优先在新增 wrapper 中调用现 `_build_split_volume_action`、`build_fullspace_dtn_action`、`FullspacePhysicalAction`，只拼接兼容现 bundle 的元数据/所有权；不复制 UFL 或消元公式。这是项目层 wrapper，不修改 runtime internals。global80 与 local40 的 volume 都是本次实际 primary kernels，分别记录 form/UFCx/source/ABI/cache 身份。

**source-change bridge。** 新 HEAD 不等于旧 HEAD：先记录 `35dd9e5… → candidate HEAD` 每个 dependency 的 old/new 文件 SHA 和新增文件，不依靠分支名证明相同。最小路线保持旧 context.source_sha256 覆盖的物理/gauge/mesh/MPC/模式源、`p6_cell_condensed_action.py`、`hcurl_assembly_time_condensation.py`、transport/coordinate/provider 依赖字节不变，只新增恢复/逆/编排/checker/tests。新增模块不将旧 context 改写成新 hash。若必须修改被 context 绑定的 physical builder 或 gauge source，原严格 source Gate 会失败：需单独审阅具体差异与新的 coefficient authority bridge；新 primary port 装配必须做新的同-live literal 资格，不能转移旧 receipt。无法重建完整 maps/identity、旧文件不可读或 ABI 变更时，该最小路线 `BLOCKED`；明确备选为独立受监督的新 port qualification，而非默认重跑整个 Q0–Q2。

## 3. 完整逆：full RHS → 本地精确消元 → 四因子 → 全内部恢复

现 `y_orbit_two_cell_transport.py:TwoCellNativeTransport` 已用实体块实现 `P_b=R_N E_b R_2,b^-1`。primal 用 `lift_primal`，dual 用 `fold_dual=P_b^H`；坐标 extraction 用 `extract_primal`，不能用 R 的伴随代替其逆。全空间只 `collect_y_orbit_entities` 与向量/≤32列panel；局部才 `build_y_orbit_layout`。不建 candidate 全Ny S/F/Q。

增广原方程为 `[[V,C],[-D,H]] [u,alpha_full]=[f,g]`。对 K=2：本地 FE RHS 为 `P_b^H f`，本地 port RHS 为 `g[sector]/sqrt(K)`，本地 auxiliary 为 `beta_b=sqrt(K)*alpha_full[sector]`。positive-H 的 `sqrt(H_local)*beta_b=sqrt(H_full)*alpha_full`，因此现 q blocks 可以直接用。native 物理方程的有效 RHS 是 `f-C H^-1 g`；任意 nonzero g 的残差必须用这个 RHS，不能只算 f−A u。

建议新增 `src/solvers/y_orbit_two_cell_inverse.py`：

1. 持有原 full entities、两个已实际重建/检查的 local setup/bundle/transport、两个 `QuotientCondensedBundle` 与 **四个**独立 factor；明确借用/拥有关系，销毁顺序沿 `condensed.destroy()` → physical bundle → full outer。不要用 `SparseAllQFactor` 原构造器：它要求全Ny matrix、会再次完整审计+构造全Ny congruence，违反本次 setup 边界。只复用其中现 `csr_audit/integer_admission/sparse_hash`、SuperLU factor/重复/线性/true-residual policy，不新写消元数学。
2. 每个 local bundle 用 `y_orbit_quotient_condensed.py:build_quotient_condensed(..., allocation_gate)` 重建 inherited system/action。它已复用 `build_unconstrained_assembly_time_condensation(materialize_global_matrix=False, retain_local_schur_for_matrix_free=True)` 和 `build_p6_cell_condensed_action_from_carrier(..., port_coupling_mode='cached')`，保留 tiny 但非零 interior C/D support、所有 LU/recovery、完整 Hhat，不能假设 interior port 为0或 Hhat diagonal。
3. **全部 factor 之前**核对保存 row inventories、20 raw/oriented tensor identities与缓存规则，记录新 `action.cache_identity/operator_recipe`；再用 `trace_layout_coordinates`、`TwoCellBranchCoordinates`、`TwoCellBlockProvider.block(j,j)` 重新形成四 q 块，与保存块比较 norm/max ≤1e−11，同时保存本次块的 CSR hash。采用 freshly compared 块分解并绑定其 hash；不得只拿旧 qCSR 便跳过新 volume/recovery 桥。重建阶段不是重新 raw/literal Q0–Q2 audit；历史12 cross-branch qualification继续引用旧不可变证据，任何相关源/物理输入改变使它失效时应停止。
4. 对输入完整 full native f/g，先按 dual fold 写入 local **8940 storage**，所有 slave 严格0，调用 `condensed.reduce_rhs(local_f, port_rhs=local_g, rhs_is_mpc_dual=True)`。当前 API 已处理任意4320内部 RHS及 Di·Vii^-1 f_i 修正，不能只注入 trace。
5. 各 branch 得 `Q_local,j=coordinates.q_map(j)`；求解 `S_q z_q=Q_local,j^H reduced_rhs`，累加 `reduced_solution=sum_j Q_local,j z_q`。两个 branch 均参与；零 RHS 仍保留其 factor 与索引。
6. 调用 `condensed.recover_storage(reduced_solution, full_rhs=local_f, expand_trace=False)` 恢复全部 local interior，正好继承 Vii^-1 f_i、trace recovery 与 −XiB beta。提取完整7936独立 field，再累加 `sum_b transport_b.lift_primal(u_b)` 到原15872 independent/17204 storage；alpha 按原532索引写入 beta/sqrtK。返回 native storage 默认 slave0，物理输出副本才用原 MPC backsubstitution。
7. 局部使用现 `evaluate_native_residual`（已支持 nonzero port_rhs）；全局用原 full volume+冻结 full carrier 对完整 f/g/u/alpha 独立重算 augmented FE/port 与 native true residual，使用现 `augmented_residual_identity` 检查 `e_native=e_FE−C H^-1 e_p`。不从 condensed residual 推导原 residual。四 original FE loads 为 g=0；另有完整 augmented manufactured controls确保非零 g 与全部内部载荷。

## 4. Q3、Q4、Q5 的准入与验收

|阶段|先决条件与动作|必须留存的验证/停止条件|
|---|---|---|
|Q3 factor|metadata/restore/discrete/source Gate与四 freshly reformed q 块比较全过；之后单独批准 numeric 入口|逐q true residual ≤1e−10、repeated/linearity ≤1e−11、有限值，完整 native manufactured load原作用检查；所有四factor simultaneously retained；不读 factor.L/U 做统计复制；任一失败即保存真实诊断并停止|
|Q4 regular original80|full original f不因 quotient改写；generic固定 seed20261001、interior_only全部8640 interiors非零、physical原80cell incident RHS、notch_supported原真实变更两cell支持|全部17204 storage恢复、slave严格0；full original A4/augmented FE/port closure ≤1e−10；field/solution对旧 p4 ≤1e−9；532模式按自身 coefficient/operation scale ≤1e−10；非零wrap不变；另逐q任意 interior+port loads验证有效RHS/线性/重复|
|Q5 genuine notch outer|Q4通过后，新 full inverse仅作原完整80cell nonseparable notch的right PC；不重复/周期化缺口，不换outer维数|复用原 `solve_notched_fgmres` 的FGMRES/right/restart32/max128/rtol1e−11和每步原true residual；保持恰两变更cell、off-q耦合与physical非零q门；四loads全过，final A1 ports由final field重新恢复，不能用最后一次A0 PC alpha；比较旧步数/原残差/fields/532 outputs/时间/RSS，不以步数授予物理资格|

已有 `FullOriginalAction` 只要求 layout.full_rows/independent；`y_orbit_centered_evidence.py:recovered_field_and_modes` 也只用这两项，且按实际 degree选space，直接可复用。`original_packet` 额外需 `modal_norms`。新轻量 full-layout view可借用 `YOrbitEntities`，以逐实体 R/R^-1 变换后对4个y向量做显式小DFT实现 `dual_to_modal/primal_to_modal/primal_from_modal/modal_norms`，**不创建 full F/Q**；局部≤32panel验证其与保存旧full maps的作用。这是坐标/诊断接线，不另写 Maxwell/消元。`recover_p0_outputs` 当前硬编码 floquets[6]，不能直接套p4，应使用上述degree通用532-mode helper。

物理 forcing只在原80cell调用 `build_physical_rhs`，原 incident traction编译与 provenance单独记录，然后严格 dual fold；现该函数明确拒绝quotient bundle，b1不能伪造局部n0入射。完整输出继续 `prepare_boundary_plane_outputs` 的 representability Gate，逐模式保留E/H/power及boundary/global坐标，不填零补缺。

## 5. 资源政策、生命周期与未有证据

同一 fresh 受监督运行严格 MPI1/thread1、aggregate whole-tree RSS <1.5 GiB、swap0、总 worker+checker≤600 s，每次 allocation留128 MiB evidence reserve。启动前可只读验证旧 report/checker/receipt/manifest；不把旧334 s计入新run，也不因还有预算而重做旧raw/literal。

因子准入为 **当前实测 RSS + 即将额外存在的 CSR/CSC/I/O copy/workspace + remaining factor allowance +128 MiB**。factor allowance总512 MiB，第 j 个保留因子前留 `512MiB*(4−j)/4`（j为实际已保留数量，不能按q索引或twist索引误算）；已留因素在当前RSS内，不再重复加512 MiB。512 MiB是声明余量，SuperLU fill/临时workspace/allocator峰值仍unknown，whole-tree supervisor才是authority。

|生命周期|处理与资源不确定性|
|---|---|
|snapshot I/O/metadata|先manifest/descriptor/hash，再每包mmap+stored rows/values复制；FullspaceDtnCarrier会排序/规范化，计入临时第二份entry/rows/values及JSON对象；constructor返回后释放packet mmap/中间entry，不让stored view长期钉住包含十段raw的整包映射|
|full实体记录及其逆|没有fullNy CSR，但 records内真实 dense entity moment小块与懒建_inverses是常驻成本；按实际RSS与唯一backing owner统计，不能仅报向量大小|
|两local recovery bundle|每twist历史 named cache28,901,952 B+port payload4,809,504/6,295,888 B，外加carrier/layout/Python/FFCx/MPC；新run可顺序重建并保留两个bundle供重复PC，第二个构造时第一个须纳入currentRSS；不能在Q5每次apply重建|
|重建assembly与q块|每twist历史 raw tensors23,040,000 B、local Schur11,796,480 B，不同生命周期；新FFCx/JIT有额外workspace，不把这几个数字相加叫peak。reformed块一次一块保存/释放，全过后按hash重开一块转CSC分解；避免四块+四CSC+raw buffers同时驻留|
|四 retained factors|所有4个留到Q5结束；fill/time未知，旧fullNy p4 factor用时与RSS不是本路线保证；禁L/U统计副本|
|full physical/notch输出与checker|一次载荷的field/vector/mode证据写完释放；native residual消耗borrowed volume输出后才再次apply，绝不destroy borrowed Vec；checker独立进程且受相同总时间/zeroSwap政策|

**目前缺失：** 只读snapshot reader；完整mode_identity重建与public-constructor digest相等实测；new-volume/cache到旧qCSR桥；全Ny无矩阵layout view；all-fourfactor retained后的真实fill/RSS/time；任意 augmented/full RHS求逆后完整恢复证据；原physical forcing/output桥；fourloads notch outer；最终source-clean/ABI/command/independent checker证据。scalar/source/syntax contract tests可先覆盖 missing branch、dtype overflow、metadata/hash/path漂移、非法restore、phase/dual/port sign、nonzero内部RHS、cleanup；它们不能替代fresh FE门。

执行前冻结一条 staged command及具体candidate HEAD/config/ABI/允许新模块，并声明restore、rebuild/compare、factor、regular、notch、checker各阶段入口。优先扩展现 `benchmarks/run_y_orbit_two_cell_audit.py` 的监督/array/provenance编排，但其audit-only schema不可直接改判为PDE PASS；新Q3–Q5 runner/checker需独立 schema且保持旧Q0–Q2报告不变。任何恢复身份/新块/资源Gate失败都保留 `BLOCKED`/`FAILED`/`CONTROLLED_STOP`，不要默默回退昂贵装配或放松阈值。
