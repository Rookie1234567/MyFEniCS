# centered-boundary 完整三维 p2 参考逆资格计划（待审阅，未运行）

## 结论与当前权限

把端口相位直接放在物理边界平面上计算，能够避免很小的指数因子先被绝对稀疏阈值删除。本轮检查修正后的完整三维算子，比较两条独立求解路线：直接装配整个 p2 有限元矩阵的 dense authority，以及先准确消去每个单元内部未知量、再分解所有 y 周期块的 sparse reference。全部原三维未知量在恢复及真残差中保留；同网格非可分缺口继续由原三维 FGMRES 求解。

2026-10-01 15:54 UTC 已获实现许可，component owner 已释放 canonical/numerical slots。当前只获准最小 opt-in 实现及独立源码审阅/targeted checks；未获 PDE、factor/checker 运行许可，也不自动继续 p4。完成源码审阅、clean commit、targeted/ABI/source Gates 后，由 root 分别批准准确 dense、checker、sparse、checker 命令。

## 冻结对象与已有权威

| 对象 | 冻结内容或已测锚点 | 身份/限制 |
|---|---|---|
| 当前 component source | a0546264ae1bcc51e2aeedcac33585f4ffc04025 | read-only 设计锚点；不是将来新 runner 的运行 HEAD |
| 原 input | input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat；SHA256 6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e | 不修改 input；使用既有 pilot_config 的显式缩放配置 |
| mesh/material/forcing | 80 hexa cells；4×4×5；7/135 缩放；原 Si 常数、lambda=.7 nm、grazing1°/phi5/S | p2 离散架构 fixture，非原尺寸/continuum accuracy |
| full FE | 2394 storage、2048 independent、480 interiors、4×512 full q；condensed1568 trace+532 ports | 最终 actual count 沿既有公式复核：2048−480=1568 trace，4×392 |
| physical ports | manual m=-9..9,n=-3..3；实际 ordered(side,m,n,pol)532；q=76/152/152/152 | 每个 gamma_n/kz/polarization 保留，n=1/-3 均留 |
| 同网格 notch | 既有 box=(25,33.5,6.25,18.75,40,80)×7/135；实际2 cells | 标签及 changed native cells 必须逐字/数组对照，不重新生成另一几何 |
| component authority | boundary_plane_532_mpc_attempt4/oracle_record.json + component_qualification_a054626.json、source receipt、watchdog | literal full-MPC same-Gauss/primary coefficients、五个任意 states、RHS/recovery/output 已过；无 PDE/factor |
| measured component | new empty C/D=0/0；每 mode raw rank-one relative bound≤1.3678246951e−13；stored/raw 五状态 action defect3.2698234834e−15 | 全532贡献非空；仍保留原相对/绝对 cutoff，不能写成完全无剪裁 |
| 旧/新 DtN差异 | component 五状态旧 clipped/new action change=.03082258966421717 | sampled DtN diagnostic；不是全 Maxwell operator norm，也不是场/RTA 差异 |

既有完整 p2 tensor count 给出1568 trace，augmented2100 rows，四块468/544/544/544；运行时 actual inventory必须逐项一致。

## 物理生成器和装配表示身份：复用 boundary contract

不新建另一套平行 schema。使用既有 API：

- build_same_mesh_physical_action(levels,cfg,2,dtn_phase_gauge='boundary_plane')；普通 global_z 默认保持
- bundle.mode_sha256 / carrier.physical_generator_manifest_sha256：原物理 generator 的 ordered mode identity
- carrier.mode_manifest_sha256 / bundle.assembly_mode_manifest_sha256：centered gauge 的实际 coefficient/normalization identity
- carrier.assembly_context_sha256 / bundle.assembly_context_sha256：source、actual mesh/tag、Basix coefficient/orientation、finalized MPC、config、actual compiled Gauss、ABI 的 discrete context
- 原 H 来自 boundary-plane area*tangential_norm_sq；它与凝聚后的 Hhat 分别保存。positive-H factor congruence使用原H，不能假定 Hhat diagonal

dense 与 sparse 运行的以上 identity、configuration、native row/mesh/MPC signatures、Gauss degree/node/weight identities必须一致。new source 改动会使 source-bound assembly context 改变；不得硬称其等于 a054 component 的旧context。component reuse 必须核验参与该 context 的六份数值源码 SHA、实际 discrete config/mesh/Basix/MPC/Gauss/ABI signatures 全部不变；记录旧component source 和新运行 source，任何相关变化需要新的 component authority，不能靠文件名准入。

未来 quotient 的 global physical modes/gamma_n 应保持同一 physical generator identity，而 local mesh/area/wrap/normalization 必须有新的 assembly context/mode identity；这已转告 joint quotient owner，暂不实现。

## 最小复用和预期文件改动

| 现有文件 | 只增 opt-in 行为/检查 | 不重复实现的部分 |
|---|---|---|
| src/solvers/task40extra_y_orbit_reference.py | run_full3d_pilot 增 explicit dtn phase 参数、centered authority artifact/完整 loads/output hooks、dense allocation hooks | 原 full FFCx/MPC dense assembler、R/F/Q、YReferenceInverse、FullOriginalAction、notch FGMRES |
| src/solvers/y_orbit_sparse_probe.py | 传递 explicit boundary-plane；新同-config dense authority；四种 full FE loads 和 centered输出 | 既有 exact condensation/recovery、all-q SparseAllQFactor、original action residual、complete interior/port formulas |
| src/solvers/y_orbit_condensed_adapter.py | 原 API 预计无需 numerical 修改；仅必要的证据导出 glue | inherited P4CellCondensedInverse/assemble_condensed_ports、MPC zero-slave/native FE recovery |
| 现有 two runners/two checkers | opt-in --dtn-phase-gauge、fresh --dense-authority/path+hash；严格 receipt binding和独立 supervision | 现有 whole-tree watchdog/provenance/artifact hash；不复制新 case runner |
| 新窄共用 evidence helper（如需要） | source 中放 p2 degree-aware MPC backsubstitution与plane diagnostics glue | 使用 prepare_boundary_plane_outputs、生产 recover_auxiliary、现有 signed-power certificate，不复制功率/相位/有限元恢复公式 |
| targeted tests/case plan | gauge/oracle/config identity、missing/swapped/stale receipts、every inventory、serialization、defaults和负测试 | 旧 clipped dense/sparse source及raw失败全部保留 |

recover_p0_outputs 把space固定取6，不能直接在p2假用。应调用已有公开 finalized MPC homogenize/backsubstitution/scatter 和 lower output helpers，只保存小型 hash-bound coefficient/plane vectors。generic/interior/notch-supported loads 没有物理 incident subtraction，使用 zero incident；physical load 使用 bundle.incident_projections。

## 顺序：一项用途、两个重建流程

### C0：实施/准入

1. component owner释放 slots后，root审阅 staging diff/source freeze；canonical只集成批准文件，clean source commit
2. same-shell 激活 existing complex environment；record PETSc complex128/int32、distribution MPC版本、ABI manifest007a5f...；targeted tests/compileall/diff/source clean
3. 将当前 component 完整 receipt 与其 artifacts/watchdog/source dependencies做 path/hash/context核验，等owner完成compact后锁定精确hash；不靠root文字 PASS或adjacent文件名
4. 更换 numerical source后，先宣告新 frozen HEAD；dense/sparse/checkers保持同 source，任何 relevant fix需新source及必要重资格。禁止期间无关 docs/source 改动

### C1：fresh centered dense p2 authority（一个独立 heavy run）

- 每次重建真实 mesh、space、MPC、实际 centered carrier，不从 sparse S 或已解场合成 authority
- 原 assemble_original_dense：独立 FFCx full-MPC volume matrix + 每个实际 centered C_n H_n^-1 D_n；不是 condensed S 或 Q block 重装回来的矩阵
- upstream carrier definition复用已资格 literal same-Gauss component，明确这是volume/condensation求解路线独立性，不冒称第二次独立 boundary formula设计
- 原 action与dense A0/A1 generic及conjugate及interior-only等多 RHS比较≤1e−11
- loads：既有SEED20261001 generic全independent/allq；确定性仅480 interiors complex load（所有interior entries非零）；实际physical incident；既有真实changed-cell supported load
- direct A0/A1一次 factor 各解四 loads，立即释放全factor；保存全部 direct fields、full original residual≤1e−10、port closure、strict slave-zero及production MPC-backsubstituted full field
- 原dense all-q reference architecture/symmetry仍使用 Q^H A0 Q；4q/全部channels，native covariance、T^4/phase、R/F completeness维持原阈值
- plane aux/output对direct和candidate逐模式比较；对 physical 使用真实incident，其他 source incident0
- 与旧clipped A0的delta仅报告独立 labelled diagnostic：全部2048 columns streamed aggregate/max norms，旧/新physical RHS与解/plane-mode差异；不要求equal、不做pass line、不用旧解作centered authority。旧matrix mmap页预算单独纳入，禁止同存额外新delta dense矩阵

### C2：supervised dense checker

- 读取hash-bound A0/A1/direct/candidate、full storage/native action/volume/coupling/alpha/H/D和MPC recovery artifacts，无FFCx重装或factor
- 完整每个 expectedload/regular/notch/aux/field/mode inventory不可vacuous pass；独立重算matrix/direct/candidateresidual、original FE/port closure和模式 output差异
- receipt绑定 report+provenance+artifact manifest+source+environment+fixture+physical generator+assembly mode/context，watchdog单独source/resource gate
- dense pass+checker pass+whole-tree resource receipt才可供新的 sparse loader接收

### C3：same-config sparse positive-H p2（另一个独立 heavy run）

- 全部 mesh/space/MPC/centered carrier独立重建；严格匹配C1 config/rows/RHS/physical+assembly identities，不接受旧global_z oracle或same-source错误gauge
- 现有assemble_sparse_p2_volume + compare_p2_saved_dense逐列对全部2048新centeredA0 columns，≤32columns panel；不只random probes
- exact full elimination保留所有480 interior RHS、Bi/Di/XiB/Hhat；stream所有16(p,q) block，分别相对两对角block gating≤1e−11后才drop roundoff offblocks
- positive-H P=R_H Q_aug，primalP、dualP^H、native manufactured load P^-H f；generic/physical/interior-only/support fullFE loads不换成scaled test forcing
- 保留actualfactor six raw vectors每q共24、原S action制造载荷 residual、repeated/linearity门；有限/非有限诊断在assert前落盘
- regular四loads的完整原 centered A0 residual/全interior恢复/directfield comparison；full primal/dual translation与condensation covariance保持
- notch原 centered A1右PC FGMRES，四loads真残差/恢复/directcontrol；finalA1 ports从最终A1场恢复，不冒用PC最后A0 alpha
- physical nonzeroq>1e−12、notch实际crossq coupling>1e−8、sampled rightPC defect照旧保存且明确不是operator norm
- 每个carrier的C/D支持非空、orderedkeys532、全部γ/kz保留；绑定literal component per-mode raw-before-mask损失bounds，不将“532 slots”当作cutoff资格

### C4：supervised independent sparse checker

- 既有原 action-vector/augmented/slave-zero/all-q congruence/24rawvectors checker，增加完整新authority binding/四load/directfullfield/plane模式output核验
- 直接读取新的dense矩阵/保存directcontrol逐load重算，不只信live difference值
- 保存 full recovered storage和actual finalized MPC map，使checker可独立重算slave backsubstitution和全部场差；不把slave-zero场错称物理边界已恢复场
- output amplitudes和finite-plane E/H/power遵循已资格lower helpers；相位转换不改变primary求解。global output代表性/roundtrip/power Gate失败按现contract先保存完整packet/plane arrays/reason再保留controlled stop，不静默零填；本fixture的legacy output contract是required，因此所有此类stop阻止full qualification
- 任何failure保留新attempt，精确fail位置/数组/identity/资源；不放宽symmetry/residual/cutoff/output/预算门

## 阈值和资源

| Gate | 现有或declared policy |
|---|---|
| map/inverse/translation | 1e−12；非trivialphi5 wrap |
| original assembly/action + modal/perpair operator | 1e−11 |
| full original/native/augmented/port/factor/linearity | 1e−10 |
| full direct field difference | 1e−9 |
| component output self-consistency及permode係数尺度比较 | 1e−10；直接复用已资格的operation尺度/analytic zero限定，不新造tiny absolute floor |
| generic allq excitation | min qnorm/total qnorm≥1e−3 |
| mode output independent comparison | 全532 complexplaneamplitudes、finiteplaneE/H和signedpower；完整vectors+max/worstkey；不只sumR/T |
| whole-tree每个run/checker | sampled simultaneous parent+descendants RSS≤1.5GiB、600s、zeroSwap、MPI1/one thread；single heavy tree |
| admission | measured R0 + declared512MiB additional factor/workspace +128MiB reserve < effective cap；每allocation/account已residentfactors；未知fill不能写成有symbolic预测 |
| dense payload | 单2048²complex128矩阵67,108,864 B；2 full matrices134,217,728 B；fullLU与congruence临时逐阶段声明，不把payload称RSS |
| old/new oracle mmap | 每份67,108,864 B触页 allowance；≤32 panel额外bytes另算，删除arrays不推定allocator/RSS已释放 |
| integer width | 原wideindices/precast、CSRNNZ/indptr/DIM、PETSc.IntType实测；SuperLU signed-C-int额外拒绝overflow |

可参考旧densephi5 peak701,861,888 B/10.108s与clipped sparsepositiveH peak437,866,496 B/11.135s；centeredcomponent327,430,144 B/10.366s。新centeredC/D增加实际support，尚无新PDE/factor资源实测；上述数据不能保证准入或性能。

## 拟命令合同（参数仍需实现/审阅；不是可执行或已批准命令）

同-shell先 source ../complex_env_setup/activate_cloud_complex.sh。拟复用run_y_orbit_reference_probe增加 --dtn-phase-gauge boundary_plane --azimuth5，source为待冻结 H_NEW；dense report/hash由新loader明确传给run_y_orbit_sparse_probe的 --dense-authority 和 --dense-authority-report-sha256；后者 --degree2 --auxiliary-gauge positive-h --dtn-phase-gauge boundary_plane。两个checker都独立受1.5GiB/600s whole-tree监督，并绑定 H_NEW。

记录目录固定own ignored subtree的新attempt名字，绝不覆盖旧 y_orbit_p2_phi5、rawfailedsparse、positiveH或component attempts。实际命令需 source commit后列完整、不省略flag、分别获root numericalgo。p4仍需在centeredp2+dense/sparsecheckers全过后单独审阅/准入；two-cellquotient仅read-only后续方案，无implementation许可。

## 结果可声称和未资格项

本轮若pass只证明这个缩放full3D/p2/532模式、修正后实际离散原operator和完整非可分notch的参考inverse/recovery/输出一致性。原尺寸λ.7 accuracy、物理port截断收敛、p4/p6/大电尺寸稳定性、MPI2+/portableworkstationABI、2TB/48h、checkpoint/restart仍分别缺资格。弱Si contrast、小尺寸和弱notchperturbation必须保留。

## 审阅后明确的证据绑定

全部 required legacy global output必须通过，不能只用plane-only状态授予本fixture完整资格。对任意载荷不先假定其代表性；调用已有guarded conversion，任何控制停止保留原原因及已有效的plane诊断，并停止本轮完整资格。两checker把native solution/RHS、full matrix action、actual MPC-backsubstituted field和plane alpha逐一绑定到对应真正direct/candidate/load；actual480 Basix interior positions单独保存，强制exact support。每mode功率operation scale包含physical incident项，阈值1e−10不变。

V7组件权威只从canonical sibling目录 docs/task40extra_dot_parallel_cloud/outcomes/records/boundary_component_v7 加载资格/source/完整532ledger，分别核对SHA256 3fcc77a0.../1e1bcccc.../a1001676...，不依赖历史external绝对path。原始历史失败仍在immutable receipt/发布记录中，运行loader不重复因子/失败测试。六份component数值源码保持exact byte identity，current discrete context必须等于已资格context。
