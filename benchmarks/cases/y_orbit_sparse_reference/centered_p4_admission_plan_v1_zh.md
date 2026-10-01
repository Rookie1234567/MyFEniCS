# 同80-cell centered p4：准入计划与当前接口缺口

## 决策与范围

本文件只做源码/既有JSON证据读取和字节算术；没有新代码、项目import、PDE、factor、solve或canonical写入。读取源码HEAD为`7c4410dbc55bce804d148493760d4de68acd8405`。当前centered p4被多个明确guard拒绝，**现有CLI没有可直接批准的centered p4命令**；先审查最小degree/receipt/bridge扩展，再冻结新HEAD及准确命令。

沿用同一Nx4/Ny4/Nz5、80真实三维cells、lambda0.7nm、azimuth5°、物理Si、两cell notch及全部532有序M9/N3 ports。此项只判断p增长后的三维稀疏架构和原p4残差；不是原尺寸mode/几何精度资格，也不是≤2TB/48h承诺。全局dense FE/modal矩阵与完整p4 direct均不准入；original A4使用既有独立FFCx curl+mass及已资格化live DtN action。

## 已测p2控制与不能继承的内容

| 已保存控制 | 事实 |
|---|---|
| `y_orbit_p2_phi5_centered_dense_attempt3_live/pilot_report.json` | HEAD7c4410d；report SHA256=`33415b7a1cde1001c4945cfa88b8517fc351478cf1b022b9ff9770b70dea6859`；独立checker129项；树峰633,204,736B、19.187s、swap0 |
| `y_orbit_sparse_p2_phi5_centered_live_attempt1/probe_report.json` | 同HEAD；report SHA256=`3db78e3a5aaaa550a96cefee634110b351e8c8526be29509d740f1951730d456`；checker164项；全部2048原A0列exact0差；树峰464,019,456B、15.134s、swap0 |
| p2原结构和因子前resident | 2100增广行，实际292,492 CSR entries/5,858,244B；initial-factor-policy处R0=393,674,752B；四q setup0.850s。是p2实测，不能按行比当p4预测 |
| p2内部port支持 | 8个cell真实非零Bi/Di；retained上界18,688B、scratch6,432B。不能用bubble理想论或物理incident近零内部load推断p4内部port为零 |

每个新p4 live carrier必须用其自己的Basix系数、DOF map/orientation、finalized MPC、Gauss、实际loaded-C/source/ABI完成原532项raw-before-mask/stored rank-one/action/RHS/recovery/output component门。不能继承p2 carrier receipt、context或basis。

## 实际genericity blockers与应复用的部分

| 当前源码/入口 | 已核验限制 / 最小计划 |
|---|---|
| `src/solvers/y_orbit_condensed_adapter.py::build_condensed_reference` | 已允许degree2/4且只创建请求degree；复用原Task39完整curl+mass局部消去、Bi/Di/XiB及任意内部RHS恢复，不另写Schur框架 |
| 同文件`assemble_sparse_p2_volume`、`compare_p2_saved_dense` | 故意p2-only/2048列资格工具；保留，不改成full p4 assembly/direct工具 |
| `src/solvers/dtn_boundary_plane_qualification.py::qualify_boundary_plane_bundle` | 不止assert degree2；还硬取`levels["spaces"][2]`及`floquets[2]`、固定receipt degree2。最小新增p4 profile必须选实际degree4，仍保留seed/tolerance/532 inventory与全部原门 |
| `src/solvers/y_orbit_live_boundary_contract.py::validate_live_receipt` | 固定receipt degree2；扩展后按实际请求degree及context element_degree核验，不把接受任意degree当资格；同一live对象/前后numeric digest门保持 |
| `src/solvers/y_orbit_centered_evidence.py::fixture_interior_positions` | 硬限480。p4必须从实际entity_dofs和native独立行找到8640且逐row非零；原p2期望480保留 |
| 同文件`centered_identity` | 旧a054固定p2 assembly/context hash不可用于p4；采用现有live receipt路径，保留physical generator，记录新的p4 assembly/context |
| `src/solvers/y_orbit_sparse_probe.py::run_sparse_probe` | centered guard固定p2 positive-H；centered source/solution多处无条件读取saved dense p2 RHS/direct fields。p4保留四类load与output门，但不读取尺寸不同的p2场，不作p2/p4同解比较 |
| `benchmarks/run_y_orbit_sparse_probe.py` | centered CLI、positive-H p4均拒绝；`_validate_bridge`还要求same-source RAW/global_z p2，而新控制为boundary_plane/positive-H。需要明确的新桥接合同，不静默改旧RAW负结果 |
| `benchmarks/check_y_orbit_sparse_probe.py` | centered接受式固定degree2并加载same-source dense authority；p4应独立绑定自身live receipt、四load、原action/port/field/output与全q证据，完整p4 direct明确not_run |
| `src/solvers/y_orbit_sparse_reference.py` | 已逐q streaming congruence/all-pair审计、public SciPy SuperLU、partial-factor cleanup及无L/U副本。当前constructor把审计与numeric factor串在一起；若协调方要assembly-only独立go，现接口还需明确prepare-only停点，不能宣称已有该阶段 |

## 派生尺寸、Gauss和payload（不是RSS预测）

p4 local hexahedron有300FE/192trace/108interior。完整storage=`365edges*4+296faces*24+80cells*108=17,204`；独立15,872、slaves1,332、内部8,640、active trace7,232。四q trace各1808，ports76/152/152/152，增广块1884/1960/1960/1960，总7764。完整独立FE一份dense complex128为4,030,726,144B，禁止创建。

原input没有DtN quadrature override；当前`dtn_port_3d._dtn_surface_quadrature_degree`给`2*p+max_order+6`，故p2 degree19，p4 **degree23**。默认quadrilateral tensor Gauss预期12×12=144点，但必须从实际FFCx analyzed规则/generated-C/loaded kernel证明；不能复制p2的100点或直接假定计数。

所有CSR公式用`s=16`、`i=实际index itemsize`：`bytes=(rows+1)*i+nnz*(16+i)`。PETSc dimensions/offsets在缩窄前检查，SciPy actual indices/indptr另记；SuperLU仍需signed-int32尺寸/NNZ准入，PETSc int64不使此backend自动支持更大矩阵。

| 对象 | 派生payload或前置条件 |
|---|---|
| 当前full-orbit-map admission | nnz上界1,714,176；原int32声明payload69,836,800B、workspace383,975,424B，再加128MiB reserve；这是现有粗声明，不是实测map体积 |
| full F / trace F，int32 CSR | 63,488entries/1,333,252B；28,928entries/607,492B。R/R_inverse/Q/T额外计算；不得只算F |
| degree-aware entity graph | full R每row最多entity width4/24/108，分族上界1,084,928entries；trace R上界151,808。实际完整graph/support和逆门仍须通过；现runner的40/20B声明按int32读，宽ABI必须按actual-width审查或显式拒绝 |
| class cache条件情景 | 若新metadata仍为p2测得raw16/oriented29（不能继承），原容量公式给retained24,760,944B、temporary88,255,152B（int32）；实际类数必须在raw/oriented张量分配前测量并准入 |
| 原carrier slab上界 | 每端16boundary cells，p4 native slab3876rows；C+D全部532模式的单份稀疏数组上界82,481,280B（int32），int64为98,977,536B。component cache/staging/retained的并存另计，不能当整树峰 |
| 完整Bi/Di/XiB最坏支持 | 若32个boundary cells各有本side全部266ports：retained44,160,256B/scratch5,908,392B（int32）；int64为44,194,304B/5,909,456B。实际support逐cell测量，保留端口索引宽度 |
| native condensed CSR支持上界 | volume≤80*192²*W_mpc²+7232；C+D≤2*532*1856、Hhat≤532²。W_mpc=1时总5,214,160entries，int32 104,314,260B/int64 125,201,960B；W必须来自完整finalized public map，不能假定1 |
| 四q CSR条件图上界 | 若实际每xz-cell/q支持≤152channels且port恢复未逃离审计boundary slab，则volume≤4*20*152²、C+D≤2*532*464、Hhat≤76²+3*152²，总2,417,104entries；int32 48,373,152B/int64 58,072,640B。条件需实际map/支持证明，绝非事先分配全dense q块 |
| q三角L/U scalar entry包络 | 四块总最多15,082,020个普通三角entries；它不包含SuperLU超节点padding、workspace/内部副本，不能作为后端内存保证，不访问`.L/.U`物化副本 |
| literal oracle5-state矩阵 | 每份17,204×5 complex128为1,376,320B；all-mode dense FE×FE矩阵不需要。现有16MiB payload+128MiB workspace声明须依新实际live数组审查，编译子进程纳入watchdog |

P4 full原边界slab独立FE3584，其中1728interior+1856trace；Fourier单q slab为464trace。上述带条件的较紧port界来自完整slab而非假定interior为零。实际preallocation、MPC最大展开width²、sparse-product已有graph上界及CSR三payload export gate优先于静态表；超出时停止重新审查，不删除条目/降低门。

## 准入、执行阶段与停止条件（未授权运行）

整树硬限`min(1,610,612,736B,fresh dynamic cap)`，600s、zeroSwap、MPI1/maththreads1、一次一个heavy。每步由现有watchdog/subreaper计入解释器、compiler和checker。首次numeric factor前必须`fresh R0+536,870,912B+134,217,728B<effective cap`；名义cap下R0严格小于939,524,096B。已有factor计入实测R0，后续只保留remaining factor policy，不双计原512MiB，不假设del返还RSS。512MiB是声明factor/workspace额度，fill未知且SuperLU无独立symbolic estimator。

未来顺序：新source静态/targeted gates与ABI → 如下新HEAD sparse-p2桥接 → p4 degree-only setup/map → 在同一实际carrier上完成p4 live literal oracle → 精确凝聚/Bi/Di/Hhat/trace maps与actual CSR → 全16个q-p pair的operator/covariance审计 → 仅在实测headroom准入后逐q因素化/重复线性/任意增广负载原S残差 → regular四load完整恢复 → 同两cell notch的full3D FGMRES及original A4/ports/field/output → 独立supervised checker。

generic每q激励、interior_only每个实际8640row激励、physical原incident RHS、notch_supported真实changed-cell load均保留。任意非零port loads由live oracle与逐q制造负载保留；Hhat不假定diagonal。regular使用同次逆求解的实际alpha；notch最后从原A1物理场恢复端口，不使用最后一次A0 PC的alpha。原A4/augmented FE/port门≤1e-10，operator及所有cross-q门≤1e-11；原场完整slave-zero、全部532channel及恢复状态hash保持。RTA只作诊断，不以p2/p4接近当连续精度。

身份/Gauss/模式/支持不符、headroom不足、swap、非有限数、任一原残差/线性门失败、非roundoff cross-q、600s超限均受控终止整树、保存正负原证据。P4时间/fill/实际MPC展开、Bi/Di及memory-releasing行为仍unknown；当前方案不能保证通过resource gate。

## 新HEAD的最安全桥接：保留旧dense控制，仅重跑必要sparse资格

现有same-source gate不能跨新HEAD，不能改旧report/provenance/checker里的source冒充匹配。旧7c4410d dense+sparse的完整raw/hash/watchdog证据保持不可变；新profile声明`old authority HEAD -> new executed bridge HEAD`，绑定原report/checker/provenance/所有使用数组、ABI以及完整source依赖差异清单。

新source的p2分支保持原配置/RHS/数学路径，采用旧immutable dense矩阵/解作为read-only数值权威，在新HEAD **只执行sparse-p2资格桥**：自身fresh live532 oracle、全部2048原A0列、complete interior/四load、regular+notch原残差/旧解/field/output比较和独立checker。这同时验证实际新源码行为；不用新dense矩阵或direct solve。新receipt必须明确跨HEAD身份及保持不变的physical/mesh/basis/MPC/Gauss数值合同，loaded-C/process身份按新live记录。若变化真正改变p2方程/配置/离散而不能通过完整列/观测比较，停止；不能反向放宽以沿用旧控制。

桥通过后冻结同一新HEAD用于p4。P4新的degree/basis/Gauss和assembly/context必须另资格；旧p2只证明组件实现控制，不是p4 field或物理精度权威。若仅后续文档改变HEAD，保留原run源码身份并按已审查文件hash/依赖绑定归档，不能为了文档机械重跑数值。

旧pre-centered RAW/global_z失败、positive-H same-discrete诊断和旧staging plan均保留原分类；本计划不更新它们的status。canonical writer由modalworker管理，本worker未写canonical。

## 实现候选的明确入口（数值仍未运行）

V8文档检查点为4cc0f7680fa603e5bb9222c04c8f1d22e688d902。后续最小候选沿用旧dense权威，不改旧receipt的源码身份。新p2 bridge显式增加`--cross-head-centered-authority`，固定旧7c4410d report/checker/provenance三份SHA，并记录实际old/new文件hash；六个物理装配/config/generator依赖不得改变。资格仍由自身fresh live oracle、全部2048列及四类原方程/场/逐模式比较给出。

新p4入口保持`--degree 4 --auxiliary-gauge positive-h --dtn-phase-gauge boundary_plane --live-component-oracle`，要求同一新HEAD的passed sparse-p2 report与独立checker；不传dense authority，不创建全局dense p4。p4逐模式验证另外保存原C列/D行、H、模式E/k及carrier原row/slave/ownership布局，独立checker先重算原numeric carrier digest再计算投影、耦合、边界场和功率，并完整恢复MPC。原volume作用是live FFCx保存向量权威；缺少p4 full direct比较明确登记。

示意顺序仅供源码审查，`NEW_HEAD`、`P2_BRIDGE_REPORT_SHA`在source freeze和真实checker通过后填写：

```bash
source ../complex_env_setup/activate_cloud_complex.sh
python -m benchmarks.run_y_orbit_sparse_probe --run --degree 2 --auxiliary-gauge positive-h --dtn-phase-gauge boundary_plane --live-component-oracle --cross-head-centered-authority --expected-head NEW_HEAD --dense-authority benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_phi5_centered_dense_attempt3_live/pilot_report.json --dense-authority-report-sha256 33415b7a1cde1001c4945cfa88b8517fc351478cf1b022b9ff9770b70dea6859 --run-directory benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_centered_p4_bridge_attempt1
python -m benchmarks.check_y_orbit_sparse_probe benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_centered_p4_bridge_attempt1 --expected-checker-head NEW_HEAD
python -m benchmarks.run_y_orbit_sparse_probe --run --degree 4 --auxiliary-gauge positive-h --dtn-phase-gauge boundary_plane --live-component-oracle --expected-head NEW_HEAD --bridge-report benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_centered_p4_bridge_attempt1/probe_report.json --bridge-report-sha256 P2_BRIDGE_REPORT_SHA --run-directory benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p4_phi5_centered_attempt1
python -m benchmarks.check_y_orbit_sparse_probe benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p4_phi5_centered_attempt1 --expected-checker-head NEW_HEAD
```

每条命令仍需root独立数值GO，worker和checker各由既有监督器600s/1.5GiB/zeroSwap/MPI1/thread1运行。p4不能自动随bridge启动。新增export按实际NNZ及原carrier index width准入；full-map粗声明加入实际ABI的CSR pointer开销。其余原凝聚、恢复、因子/交叉q/true residual数值阈值和普通默认不变。
