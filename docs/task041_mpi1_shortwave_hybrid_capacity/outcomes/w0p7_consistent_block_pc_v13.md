# W0.7 V13 consistent fixed BAL_H modal surrogate：实现与分阶段资格记录

**状态：V13实现已完成；A/B合同测试分批通过；registered entity-closure tiny真实FE selector已serial和MPI2分别通过；30个serial清场/服务合同节点分批通过；MPI8 native ABI-only预资格8/8通过。正式W0.7 MPI8 warm/pilot、QEP、完整场、最终五残差与physics/RTA仍未运行。** 本文记录已实施合同、实际测试边界和后续资格差额，不修改V12 raw、方程、最终五残差或物理门。

## V12基线与当前资源门

V12唯一Invocation `62c3763e266345e0b094a4f3ba3ae19c`的modal末次solve为32步、reason `-3`、relative residual `0.47290220837766356`，大于`rtol=0.001`；该值也超过近似PC拒绝线`0.1`，所以本次明确拒绝。`budget_exhausted=false`。真实状态、outer停点、46条side记录和嵌套wall口径见[summary](summary.md)。V12当时的node0 floor和单节点读数是历史资源合同。后续用户授权测试改用node0+node1合计384 GiB reserve并取消显式内存节点绑定；当前node1至少80 GiB仅是资源可用性门，不是N1页放置资格。V12负结果和原resource raw均保持原样。

## 已实现合同

策略ID：`task041_v13_consistent_fixed_balh_modal_surrogate`。实现使用同一固定平衡作用处理LDU各块；8个预定列直接进入最终Schur矩阵，其余列每列只构造一次。owner LU之后检查小系统`S_B a-g`，完整PC输出后再由原全局A modal row检查`L z_side+C a-r_modal`。两者是独立门，不以内部求解替代原方程检查。详细实现对应文件见下方。

1. **一致的固定B对象。** 对bottom/top各自创建并固定一个`FixedPhysicalBalancedActiveTraceAction`；同一对象同时用于`HybridBlockLduPreconditioner.apply`的first与delta，以及近似Schur `S_B=C-LBG`列构造/独立动作核验。B是固定BAL_H近似作用，不是`D^{-1}`。不得只在modal项使用B，而在其他LDU项继续走自适应`SideBalancedInverse.apply`。正式候选的实际side/modal KSP solve计数都必须为0；P4 owner LU调用单独记录，不混成KSP。
2. **8列只构造一次。** 保留旧`build_hybrid_action_modal_schur`默认重复构建行为。V13用独立显式分支或小helper：从sealed采样合同选定8个正/负列，直接写入最终`S_B`；剩余列各执行一次B作用后写入同一矩阵。禁止先构造sample后丢弃再构建；独立action-vs-stored-matrix验证放在单独scope计费，逐项记录列构造和验证作用次数、wall与临时存储。奇异小矩阵、错误符号和正负通道错序都必须拒绝，不允许伪逆、shift或删模态。
3. **两道不同的残差门。** owner LU求得`a`后，先检查小矩阵方程`S_B a-g`，这是LU求解门，不是完整PC门。完整PC计算出`z_side`后，另用原全局A的modal块检查`L z_side+C a-r_modal`；不得用前一门替代后一门。若`r_modal`非零按其原RHS尺度归一；若`r_modal`严格为零，使用原组成项尺度`||L z_side||+||C a||`计算后向误差，尺度也为零时仅精确零残差通过，不得用`max(norm,1)`。两门各自要求有限且误差`<=1e-10`。
4. **owner新增存储限额。** 256 MiB是指定owner上的新增模态存储预算上限，不是实测LU峰或RSS估值。分项计算最终模态矩阵、LU副本、factorization/验证临时数组、FE向量、ghost与通信buffer；来源未知或非有限的必要数组拒绝，不把矩阵/LU复制漏掉或重复计入同一项。进程树/cgroup仍按80/72/8 GiB和node0+node1合计384 GiB资源门独立准入，不预扣将来释放或把payload当RSS。
5. **outer最多一次安全重启。** 不能在活跃outer KSP或PC回调内销毁/替换KSP。只有一次完整restart32/32步窗口返回后，基于原始全局真残差证明确有restart损失，才可在外层`solve`已返回的安全边界最多切换到restart64；用可信当前`x`、同一个原始`f`及PETSc非零初值续解，保留累计iteration/wall/MatMult/side账。没有窗口证据不触发。有限停机另按两个连续16步窗口的最佳global残差及每个仍未过门的block残差判断；每项改善都必须不足10%才可收口，不复用V12的8步门。异常快照仅在iterate可信、输入完整且位于安全边界时写入，其他情况明确拒绝保存。
6. **唯一公开请求。** 复用现有`--task041-modal-solver-policy`单selector传入V13 policy，统一绑定sealed config、public argv、launch manifest、service/supervisor expected policy、worker candidate、consumer actual method与finalizer核验。普通fixed-H6/default与V12 policy不变；不新增第二个方法CLI或按W0.7身份隐式切换。

## 最小文件与调用触点

| 文件 | 触点与职责 |
|---|---|
| `src/solvers/hybrid_fem_modal_block_ldu.py` | `HybridBlockLduPreconditioner.apply`统一各LDU项使用的B；独立V13 builder按“8列最终保留+其余列一次作用”组装；owner LU后检查原Schur残差，完整PC后检查原全局modal row；outer窗口记录、安全restart与有限停止状态 |
| `benchmarks/task041_exact_side_workflow.py` | 在已注册W0.7 staged candidate建立并共享B对象，传递列缓存/owner gate/实际计数；为consumer summary保存request、candidate/setup、actual method、owner LU与原modal-row证据；不得从consumer请求自证期望 |
| `benchmarks/task041_balh_workflow.py`、`scripts/run_case.py` | 让现有单一modal solver policy selector承载V13值，default仍为原路径；config与argv一致 |
| `src/runners/task038_launcher.py`、`src/runners/task041_service.py`、`src/runners/task041_supervisor.py` | 封存request与实际worker/consumer方法比较；按launch manifest唯一runroot核summary引用，不扫描任意latest目录；missing/hash错/identity错为unknown或reject |
| `src/test/test_350_task041_balh_block_ldu.py` | tiny代数/单位列构造一次/各LDU项使用同B/side-modal KSP=0/owner LU额度/原modal row残差及零分母/一次restart保留x、f、累计账 |
| `src/test/test_351_task041_balh_public_workflow.py` | 单selector、default兼容、sealed请求至worker与consumer actual method贯通；缺失和错scope拒绝 |
| `src/test/test_352_task041_service_boundary.py` | finalizer沿manifest→唯一public summary→supervisor summary路径/SHA→consumer summary路径/SHA核验请求与实际结果；漏字段/错hash拒绝，不从consumer自报请求反推expected |

表中列出的是V13实际实现/测试触点。tiny测试证明所覆盖的代数、路由与小网格合同；不能把它外推成M400完整列成本、正式MPI8环境或整场物理资格。实现没有增加独立runner/policy框架，也没有改旧默认或W2路线。

test350的PETSc/代数fixture验证小矩阵、列构造和solver控制合同，不能单独称真实FE。另有test347 registered entity-closure tiny FE selector：degree-6、`2×2×2` cell-condensed几何，每侧6个解析模式（共12模态）；固定B/LDU、原modal row、P4 residual与借用对象生命周期的完整C断言已serial通过一次、MPI2通过一次。该fixture不是QEP模态，也不是M400/800模态或正式W0.7容量样本；MPI2合并stdout没有rank标签，所以保留为1 selector/2 rank-cases，rank-to-summary仍`not_persisted`。

## 分阶段测试与源码身份

| 组 | 范围与结果 | 环境及证据边界 |
|---|---|---|
| A | 23 selectors/45参数，跨attempt累计43 passed、2个MPI2-only serial skip | [071636Z封存的A覆盖表](../../../results/task041_v13_A_B_mpi2_review_prep_20261012T071636Z/A_serial_selector_coverage.md)及[JSON](../../../results/task041_v13_A_B_mpi2_review_prep_20261012T071636Z/A_serial_selector_coverage.json)记录当时的分批覆盖；后续B/C和源码变化按各自receipt核对，旧表不改写。不是最终19路径map一次整组通过 |
| B | 8 selectors/14参数每rank，分批覆盖 | 28 rank-cases是14个参数在两rank的执行，不是28个独立测试定义；部分合并stdout的rank归属未持久化 |
| C serial | registered entity-closure tiny FE完整selector通过一次 | 旧attempt CPU14，显式`membind=1` |
| C MPI2 | 同selector、`rc=0`、1 selector/2 rank-cases，父wall`153.515994687099 s` | 最新用户批准的default/unbound策略；两rank ABI和全组清理门通过，但summary行没有rank标签 |
| V13 serial清场/服务合同 | 两attempt共30个节点通过：首段3项，修复test351 fixture关键字后的remaining 27项 | 首attempt的setup-boundary fixture失败和原raw保留；这些mock合同不是OS/MPI8清场资格。父wall`6.377355428179726 s`与`10.62438608892262 s`各唯一计账 |
| MPI8 ABI-only | production rank qualification/native ABI 8/8通过；parent wall`2.1766278869472444 s`，不入V5 | CPU `[10,11,14,15,16,17,18,19]`，default/unbound、有效节点`[0,1]`及six-thread/native ABI checks通过；无pytest/数值worker，仅dirty-map预资格 |

最终C MPI2执行当时的V5账目为262项、SHA `64fd8d5ffc3a62aa4e49a8058e81e5701aa0a1107269c35bcae50cf1d2396ec4`；该attempt唯一费用153.515994687099秒，ABI和资源门不计账。C输出78项的SHA清单为`f9bcdc0045418fd60f21b938493a5c12bb5828375fefe851b881e61f1b1ba779`。后续两次serial合同attempt使live V5增至264项、SHA `17376a6343ac65f359f059ad632e9a305ce28a60c683164f6a16539ee6e767ce`；MPI8 ABI-only不计入V5。分组详情、serial skips、历史失败、ABI receipt及selector入口见[test summary](test_summary.md)；当前C map逐项见[源绑定receipt](../../../results/task041_v13_C_cpu_wait_retry_mpi2_attempt_20261012T142650Z/mpi2_c/source_hashes_before_after.json)。

相对044347Z冻结的19路径map，C MPI2 attempt运行时包括6个批准delta：`task041_service.py`=`c7670e4030c92ff98a2302d1725736e2141f283e374bf4facac3f3aaab31985d`、test347=`2c77d6d0e058723e54182ce7affc1cc19061e7a70e05c9c8a0ad6023d72c82a1`、test349=`c298046ec4165c4c23505384cd945d4e1158a590b1b12da048f01dd238e5585a`、test350=`070db620498aae86c9373ce3a25350141084c6aa9eaaa061df37455c88d07cca`、test351=`6654c10200a67d52d4a92a905b3b6d4d9c5eacc5e6ca75c6ad038b2e31771973`、test352=`9f87a77c487fc33e715d81a6bdd6498a5765c1d960dc865af34fbf5839667bdb`；其余13项在该运行时map相对baseline一致。A/B跨阶段有更早的test350/351/352、service和test349身份，必须引用各attempt map，不可用这组六项hash替代。本文档和其他三份文档在该运行之后更新；其文档SHA变化不等于数值源码变化，也不修改旧source receipt。

## Service/finalizer证据链与V12缺证边界

V13 service/supervisor链现由实际helper、public route和test352 finalizer合同测试覆盖：sealed `launch_manifest` → 唯一public runroot/外层summary → 被明确引用的`supervisor_summary`路径及SHA → supervisor引用的`consumer_summary`路径及SHA → source/request/candidate/setup/actual-method证据。旧V12外层`summary.json`的`task041.supervised_public_command.v1`只含command、phase result与launch manifest，不含consumer setup；V12缺setup/candidate字段按unknown/false保留，不能从请求推断实际候选。这些service/finalizer正反例由A组test351/test352提供；C组test347只覆盖固定B/LDU的小型FE、原modal row/P4残差与借用生命周期合同，不证明service链，也不替代正式pilot consumer evidence。

## 正式pilot仍需独立资格化

MPI8 ABI-only已在21路径dirty map下通过，但它没有启动worker、pytest或FE。正式W0.7 p6/h0.70/M400 MPI8 warm仍未执行。当前clean HEAD身份未知，不能把ABI-only预资格提升为正式warm资格；本轮文档更新后候选状态是`pending_rebind`。沿Review V13与现有registered route，后续独立审核仍须覆盖：

- 封存配置、public argv、launch/producer identity到真实consumer的路径与实际method证据；
- M400正式模态规模下的完整S_B列构造、owner LU新增存储与实际outer工作量；
- outer原A真残差及五项既定门、必要恢复、完整E/H和物理后处理；
- R/T/A、A_volume、衍射、physics和finalizer实际证据；
- 与正式profile匹配的fresh host/资源/CPU map、MPI8 native ABI、默认内存策略和清理身份。

正式warm的静态候选、exact public argv、producer小metadata绑定及21路径提交分组见[ignored准备包](../../../results/task041_v13_final_docs_warm_candidate_review_20261012T232650Z/README.md)。以上是既有review/pilot合同的未资格化项，不是新数值方案；本轮没有QEP或正式dispatch。node1可用内存条件只属于资源准入，不再解释为页面绑定。W5延期、W2不启动；C的serial/MPI2 tiny通过不改变V12正式warm负结果。
