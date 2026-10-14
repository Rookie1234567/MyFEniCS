# Task041 Review V14 执行回应：W0.7 V13 warm 数值门终态

## 当前结论

通俗地说，本场确实进入了注册的缩减W0.7计算：程序通过启动与资源检查，构造了把两侧模态耦合起来的小系统`S_B`（800列全部完成），并建立了owner负责的Schur子问题LU因子。这里使用固定近似作用`B`贯穿LDU各块和`S_B`列构造，使预条件器内部采用一致近似；`B`不是原方程算子`D`的准确逆。此前callback转交和SUP目录职责问题已在本次真实链中越过：workflow把factory的fresh-authority callback传给LDU builder，准备方不再预建由supervisor独占创建的SUP，真实启动后写出了launch manifest并运行public worker。

V14本批首场正式M400 warm之前，历史V13例外Invocation `cb734e0d54734b53817d157d5fe8c706`也曾实际完成800/800列和owner LU，之后在outer fresh-authority入口失败；它不是SUP冲突。SUP预创建冲突属于更早Invocation `817bc0e2a56e42feb9a8cce040c9a486`。V14批次起点V5为272项、`622067.4459419006 s`、SHA `accf760c3c25d4e89daa49da3f109ced59d6086a83971f527d61ac63a1700e8f`。`cb734...`的run manifest SHA `2bb05d80d58fd8e08ef6225e94e7f9c40a615a0ebc224e25d59dc1bbf159a564`、run summary SHA `a69fb0d467c5623e0749d7e7f4ee8a4e50e8d6040f3f5e1c9f63a24aae041fe`、consumer summary SHA `0d0e331c288b02ed2372aca70dcf03e84ac8d3e6b976782e59d89fde5f6e9b95`；其outer拒绝的首个runtime子谓词未持久化。此历史行不回写旧raw或其IMPLEMENTATION_FAILURE分类。

本场复用已资格的 producer packet，没有重新运行本征问题计算（QEP）。真实 fresh aggregate authority 通过；外层iteration 1之后某次完整预条件器（PC）apply的原始modal行相对误差检查拒绝并终止，具体apply序号未知。最终分类仍是运行记录中的 IMPLEMENTATION_FAILURE，但“某个实现缺陷”尚未由已存数据证明：失败行的绝对 RHS、残差、分母、行号、alias 及精确apply序号均未持久化。

| 阶段 | 实测结果 | 解释与边界 |
|---|---|---|
| 身份与配置 | unit task041-v14-main-warm-20261014t004907z.service；Invocation 686efe6ec9324b5bbe75a796a758d545；运行源码 HEAD f969d413bde02339b673a9636f42582a1879f657；MPI8 consumer map [0,1,13,14,15,16,17,18]；default/unbound；六个线程环境值均为1 | 模型为 W0.7、10×5 nm、p6/h0.70、M400、cell_condensed/entity_closure；复用既有 producer，当前 Invocation 的 QEP=0 |
| 旧启动问题 | callback 与真实 factory 流程接通；SUP 保持 supervisor 独占创建；本 Invocation 有 launch_manifest，且实际进入 worker | 首场 callback 漏传保留为历史；更早的 Invocation `817bc0e2a56e42feb9a8cce040c9a486` 是 SUP 预创建冲突，随后 Invocation `cb734e0d54734b53817d157d5fe8c706` 完成800列与owner LU后在outer fresh-authority失败；本场证明启动链越过这些位置，不改写旧 raw |
| 新鲜资源/authority | 初始 aggregate MemFree 863,557,566,464 B，门要求 498,216,206,336 B；node1 539,427,512,320 B，均通过。outer authority 8 rank 无错误，10 个 external gates 全真；B+delta+W=55,613,354,496 B，小于85,899,345,920 B cap | 本场不是资源拒绝；authority 请求 SHA 15c01ca21badb1676dc5df8543a2aeb9d079717e3bcbd108bfb00666641a6858 |
| worker / 同一B / 构造 | S_B 800/800列完成，owner LU ready；`v13_modal_schur_ready`记录owner rank 7、原Schur RHS residual `[1.9662845717117538e-13,1.9662845717117538e-13] <= 1e-10`、两项输入未变、factorization一次、repeat LU solve两次、residual check两次；LDU各项和modal Schur使用同一B对象 | 这是构造ready快照，不是失败PC apply的owner残差/累计计数；失败时owner LU累计求解次数未持久化 |
| 预条件器实际调用 | `modal_schur_ready`已保存快照中的modal KSP solve count=0、V13 modal KSP solve count=0；bottom/top side-inverse apply与iteration增量均0 | 这是准备完成时快照，不是失败时的全场累计计数。失败PC调用的实际计数未持久化。两个nested KSP对象被创建，但对象数不等于调用数；generic `fixed_preconditioner=false/nested_ksp=true`也不能单独证明回退 |
| outer与停止点 | iteration 1决策仍为 ITERATING；global/top/bottom/modal true relative residual分别0.8561826616833743 / 0.8560583887032607 / 0.8662175033712339 / 7.603007007147926e-14；该marker的PC apply count=1 | 这是iteration 1原方程残差快照，不是最终五残差。iteration 1之后某次PC apply的输出原modal-row门以relative=1.039223e+00 >1.0e-10拒绝；具体apply ordinal、source/target与失败行absolute量未保存 |
| 最终数值/物理 | 没有外层收敛；最终五项原方程残差、recovery、完整E/H、official R/T/A、A_volume、衍射和physics均未取得 | 不称M400实现缺陷已证实，也不称数值通过。没有权威official RTA结果 |
| 大型构造额度 | 本次为V14获批两场大型构造中的第1场；第2场未使用，但当前失败证据不足以满足启动条件 | 不自动重建、不改算法、不做参数扫描。M600与h=0.525细化依赖的M400成功条件未满足，均为not_run |

## PC modal-row 门与 tiny 诊断

权威合同保持：非零 modal RHS 使用相对误差 ||action-rhs||/||rhs||，门限1e-10；只有逐元素精确为零时，才用未约简组成项尺度的后向误差。不得把near-zero当作精确零，不用epsilon切换分母，也不改变阈值。iteration 1的modal原方程残差约7.6e-14与iteration 1之后某次PC输出行门1.039223是不同向量、不同检查位置，不能互相替代；失败PC apply的准确ordinal未保存。

| test350 tiny真实PC/owner LU/右预条件FGMRES apply | modal RHS范数 | residual范数 | 使用的scale | 结果 | 同次owner S_B证据 |
|---|---:|---:|---:|---|---|
| 第1次诊断apply（精确零支路） | 0 | 7.668949390247103e-16 | 0.9404675265097218 | relative backward error 8.15440105487558e-16，通过1e-10门 | residual 4.872072101741997e-16；relative 5.896945514369229e-16，通过 |
| 第2次诊断apply（非零、近零RHS） | 2.646487008256017e-15 | 5.299281747526413e-16 | 2.646487008256017e-15（严格按非零分支） | relative 0.20023834354730255，拒绝1e-10门 | residual 2.539848593650518e-16；relative 2.9671536616724195e-16，通过 |

这个tiny pytest报告1 passed，含义是有界捕获测试按预期运行并保存两次apply；它不是PC数值门通过。owner S_B相对误差第1次为`5.896945514369229e-16`、第2次为`2.9671536616724195e-16`，均通过owner门。tiny数据说明极小但非零RHS按现行相对门会敏感，但不能据此判断M400失败的绝对误差或根因。M400失败行的rhs_norm、residual_norm、scale、组成terms、rhs_exact_zero、行号、source/target alias与失败owner求解残差均为`not_persisted`。

首异常仍是FloatingPointError。其后异常快照在KSP/context销毁后读取borrowed side inverses，因而留下RuntimeError并丢失诊断字段；该次生快照错误不是首因，也不能用销毁后状态替代失败行数据。

## V14 启动与authority回归证据

`f969d413...`修复不只是把历史callback从workflow转交给builder：三条生产链路分别迁移LDU outer资源校验到fresh aggregate/node1 authority字段、把outer request/report/response/payload和校验错误写入rank记录并用rank0写入状态广播保持失败路径collective安全，以及让service准备与guard共享OUT/SUP绑定函数并维持SUP由真实supervisor独占创建、manifest先于轻量child。以下测试绑定各自attempt/source receipt；它们验证启动/authority合同，不替代本次M400 warm最终数值门。

| 回归范围 | 最终有效结果 | attempt/source绑定与限制 |
|---|---|---|
| Serial合同 | 三批最终有效`9+7+8=24 passed`；早期失败attempt保留，不把重试记录擦除 | 001106Z attempt SHA `04d047d99bf80efec6ac508f521b10d1842742d8fa8d78f5673dca603a09b3cf`、source map SHA `edfab602c7e3f01ca3eecd3b698343465fb17a04ec353d0bc3872a7d6afe54dd`；001733Z attempt SHA `2cba8f85a03e1e0c27e4451ff85bcf52c2c735849f59c9dec9ab16d242cf123e`、source map SHA `fac414fccc581be6639454b36a9d22009d1032cf7a3e32d69ba42d6295e40535`；002226Z attempt SHA `eae90e3edaba3ba89fd4741e6dbdaa83ec38502dd59a21130c1b5a3142cc5fee`、source map SHA `67022abaaa52b123de5f748a0cd14d456ae5bf29965cddeae56f11ac0d11f6b5`。每份map绑定当次21路径与HEAD；分批不冒充同一次运行 |
| P0：真实准备/监督启动 | test352真实`run_task041_supervised_public_command`、共享路径helper、真实supervisor及轻量OS child通过；child核launch manifest先写后spawn；SUP已存在时在spawn前拒绝 | 节点`test_task041_output_binding_and_real_supervised_child_manifest_order`及相关SUP负例在001106Z/002226Z受影响serial attempt；与早期仅静态/复制逻辑验证区分。不是大型数值worker或MPI8清场资格 |
| P1：factory callback及authority | `test_v13_candidate_helper_forwards_real_factory_callback_into_ldu_guard`在serial tail中执行真实candidate helper→factory callback→LDU guard，覆盖authority pass/refuse与错身份拒绝 | [serial attempt](../../results/task041_v14_outer_authority_serial_tail_attempt_20261014T002226Z/serial/pytest.attempt.json)、[serial source map](../../results/task041_v14_outer_authority_serial_tail_attempt_20261014T002226Z/serial/source_hashes_before_after.json)，map SHA `67022abaaa52b123de5f748a0cd14d456ae5bf29965cddeae56f11ac0d11f6b5`。该selector不在MPI2 argv中；不同于此前fake stage factory+AST转交测试 |
| MPI2 collective与factory | 两个selector、共4 rank-cases通过；准确节点为`test_v13_outer_marker_writer_real_mpi2_append_and_write_failure`与`test_v13_unmocked_builder_owner_lu_and_original_modal_row_math`，覆盖真实marker collective和真实builder/authority相关路径 | [实际argv](../../results/task041_v14_outer_authority_mpi2_attempt_20261014T002623Z/mpi2/pytest.argv.json)、[attempt](../../results/task041_v14_outer_authority_mpi2_attempt_20261014T002623Z/mpi2/pytest.attempt.json)、[stdout](../../results/task041_v14_outer_authority_mpi2_attempt_20261014T002623Z/mpi2/pytest.stdout.log)、[source map](../../results/task041_v14_outer_authority_mpi2_attempt_20261014T002623Z/mpi2/source_hashes_before_after.json)；argv SHA `d771f650305b38c33ec0ccc9a6dfaec7b91ec386ab5237b8fe3ba74f1cc9e93a`、attempt SHA `7ed5980892520e128b1ca2a7d4a3649ec525ef81cfedf437908db4a4d6d54507`、map SHA `67022abaaa52b123de5f748a0cd14d456ae5bf29965cddeae56f11ac0d11f6b5`；合并stdout不能归属rank的部分为`not_persisted` |
| Fresh MPI8 ABI | 8/8 rank通过，真实map `[0,1,13,14,15,16,17,18]`，production rank qualification、线程、默认内存、bridge与身份收口通过；未启动numerical worker/pytest | ABI attempt SHA `d57ce5e4f489c200f2fb415dd50d8725132d943e381a108b0417a2c8bbac0d2f`，输出清单SHA `7859b318184f7e2821409d697a959cf502a0745390170a8430cf0d0dbad2cc92`，运行source HEAD `f969d413bde02339b673a9636f42582a1879f657`。这是ABI资格，不是数值求解 |

此前V13 callback专测采用fake stage factory并以AST执行生产转交表达式，只能证明callback对象转交；本轮P1测试实际运行candidate helper及factory callback链。类似地，早期P0静态/文件函数检查不是本轮真实supervisor轻量child证据。serial、MPI2和MPI8各自边界与源码map不同，均不得合称同一SHA上的完整测试矩阵。

## 时间、内存与账目

| 口径 | 实测 | 使用边界 |
|---|---:|---|
| mode-prep producer wall | 1,460.4700798629783 s | 旧 producer 记录；正、负向QEP max-rank solve分别316.8529016729444 s、317.0268020199146 s |
| 本次consumer wall | 12,806.358500467148 s | consumer阶段scope |
| public嵌套phase / service parent / unit最终收费 | 12,809.970051602926 / 12,810.20820791 / 12,811.423691891 s | 这些区间嵌套或相邻，不相加；V5只按唯一Invocation收service wall |
| producer记录wall + 本次warm service wall | 14,271.893771753977 s | 只是“旧producer已测阶段 + 本次未完成warm”的组合小计，不是成功cold运行总时长；未发生的恢复、检查与official结果仍缺 |
| Consumer非重叠阶段：preflight_begin `.041663583135` → `modal_schur_build_begin` `1296.792764084181` | 1,296.751100501 s | 同一consumer marker `CLOCK_MONOTONIC`相对轴；包含到S_B开始前的setup与P4工作，不拆成没有marker支持的更细setup耗时 |
| `system_setup_stage=before_build` `1296.959448409965` → `after_all_columns` `12652.642669782974` | 11,355.683221373009 s | 同一consumer marker轴；800列构造区间，不能与内部逐列/逐rank耗时相加 |
| `after_all_columns` `12652.642669782974` → `v13_modal_schur_ready` `12748.079925443977` | 95.437255661003 s | 全列之后的独立验证、owner LU及ready检查区间 |
| `v13_modal_schur_ready` `12748.079925443977` → `outer_solve_begin` `12748.682461705059` | 0.602536261082 s | ready之后至outer开始；仍在consumer marker轴 |
| `outer_solve_begin` `12748.682461705059` → `final_cleanup_complete` `12806.358062949032` | 57.675601243973 s | outer至cleanup完成；包含iteration 1与失败清理，不是收敛求解wall |
| finalizer `post_io.phase_wall_seconds` / public-to-finalizer unit wall | 0.940788588952 / 12,811.423691891 s | finalizer post-IO有独立phase计时；unit wall从systemd单元起点计。它们与consumer marker没有共同的已保存起止点，不推算cleanup至unit结束的差值，也不与consumer/public wall相加 |
| 本次服务阶段process-tree RSS authority峰 / 专属job cgroup memory.peak | 46,615,474,176 / 43,826,028,544 B | 分别是process-tree authority与专属cgroup峰值，不能混作同一个RSS数；resource门未触发，swap authority峰0 |
| runroot workflow sampler另报峰 | process-tree RSS 46,563,233,792 B；PSS 43,485,200,384 B；USS 43,058,642,944 B | 这是workflow采样口径，和service sampler数值不完全相同；按各自scope保留，不平均 |
| V5研发累计 | 278 entries；charged_seconds=634,900.2474392491；SHA dbf7d2211ec476dd11d7fd622dbf6d014c4d0df9da9f58f63157258a52917b94 | 全历史研发/执行账本，不是本模型wall；本Invocation 12,811.423691891 s唯一追加，tiny pytest父wall4.235037796199322 s另有唯一entry |

本次峰值低于80 GiB hard cap及72 GiB warning；W=8 GiB、aggregate reserve=384 GiB合同不变。50×25 nm按对象与生命周期做条件预算如下；`M`是外部模态数，目标几何P4填充、QEP基数与并存生命周期没有目标run数据，故表中公式不能转成目标总RSS或48 h承诺。

| 对象 | 条件预算/复杂度 | 当前M400校准 | 50×25 nm缺项与边界 |
|---|---|---|---|
| P4凝聚矩阵与factor | 实际condensed rows、输入矩阵NNZ、MUMPS因子fill及workspace分列；阵列字节按实际结构与dtype取数 | M400输入凝聚矩阵：rows 64,966；bottom全rank matrix NNZ 27,929,686，top matrix NNZ 39,242,250；两者都不是MUMPS LU factor-fill NNZ，独立factor-fill计数`not_persisted`。bottom数值来自[本场factor inventory](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261014T011327.081762Z/consumer/factor_inventory.json)的`bottom_factor_calibration.nnz`（SHA `ce2f1eaed120d1f6abf5f8b440c3e1f1c6d4b6da2a628b14ea53f174e1c39262`）；producer从PETSc输入矩阵`source_matrix_inventory.local_nnz_used`汇总一次，见[`_source_matrix_inventory`](../../src/solvers/petsc_lu_stage.py#L40)和[`_task041_w0p7_bottom_factor_calibration`](../../benchmarks/task041_exact_side_workflow.py#L1931)。top值是注册输入condensed矩阵NNZ，见[`_TASK041_W0P7_PORD_NNZ_BY_STAGE`](../../benchmarks/task041_exact_side_workflow.py#L2084)及[含top matrix_identity.nnz的原progress marker](../../results/task041_v13_main_warm_exception_readonly_diagnosis_correction_20261013T160237Z/original_package_snapshot/progress_markers.json)（SHA `83d4ade694310e58962575780e006194da1fc8af060d78de39a64310e48f4443`）；历史stage peak 53,541,888,000 B不是本次峰值 | 目标网格rows/矩阵NNZ/factor fill与symbolic/numeric workspace、对象共存区间未测；须由目标真实生成/预分配结果取得，不能用元素数线性推RSS |
| QEP/TOAR与模态基 | 若冷运行，按多项式线性化阶数、`nev/ncv/mpd`、shift factor、TOAR Krylov向量及保留模态逐项计数，按各生命周期重叠求和 | 本Invocation复用qualified producer，QEP=`not_run`；旧producer mode-prep wall 1,460.4700798629783 s，其中正/负向max-rank solve 316.8529016729444/317.0268020199146 s，仅是独立历史校准 | 目标维数、shift factor fill、basis/workspace和packet对象峰值未有本次数据；冷QEP不计入本场warm wall，也不能由packet复用推算 |
| trace / DtN与模态通道 | trace自由度×通道数×复数元素大小，再计投影、ghost、通信与缓存副本；对同一共享对象按身份去重 | M400历史实际trace full rows 68,852、slave rows 4,532、active rows 64,320；[`physical_action.external_mode_count=646`](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261014T011327.081762Z/consumer/consumer_summary.json)（SHA `393f17fccd9674b0920eb0ec74e23e9c459ddd0c408a56b6520e015440f5ef75`）表示P4外部port通道数，不是内部M400模式数400，也不是`S_B`阶数`2M=800` | 目标trace维数、每方向传播通道与rank ghost/cache copies需由目标resolved几何计算；不以646或模态数简单倍乘总RSS |
| `S_B`与owner LU | `S_B`阶数为`2M`，complex128矩阵payload `16(2M)^2` B；LU副本同阶另计，另加pivot/workspace。dense factorization工作量约`O((2M)^3)` | M400时800×800矩阵payload为10,240,000 B，LU数组payload同为10,240,000 B，pivot索引3,200 B；派生owner peak 40,963,200 B，硬存储预算268,435,456 B。实测本次构造800列、11,355.683221 s，owner LU 1次factorization/2次repeat solve/2次residual check | M、owner布局、MPI通信/临时数组和同P4/trace对象生命周期未在目标测量；payload/派生peak不是RSS |
| 全列构造 | 量级约`2M × cost(B)`；每列实际action、复制、独立验证均按marker分别计量 | 本场800列已完成；marker非重叠列构造窗11,355.683221 s | 目标M、每列局部FE solve与copy成本、rank负载和stage并存对象未测；不能把本窗直接线性倍乘为目标总时间 |
| outer FGMRES | restart=`m`时右预条件FGMRES向量约`16 × N_global × (2m+1)` B，另有Hessenberg、ghost、PETSc work buffers；若按合同重启，32→条件64分别算 | 本场到iteration 1，尚无完整restart窗口；因此没有收敛/重启或终态Krylov成本 | 目标`N_global`、有效restart窗口和向量与因子同时驻留时间未知；不得由单步outer extrapolate |
| recovery / E-H / 后处理 | 至少按`16 × N_live_field`复数场payload，再加投影、traction、谱通道、输出和临时向量；只对实际重叠生命周期求和 | 本场未进入recovery、完整E/H、official R/T/A、A_volume、衍射或physics | 目标`N_live_field`、后处理缓冲与场/因子重叠均`not_measured`，不能声称50×25 nm约2 TB可行 |

每阶段仍按fresh `B_current + Δ_phase + W <= cap`检查，软件门80/72/8 GiB、aggregate reserve 384 GiB及node1资源门保持。表内没有合成出目标总RSS；也没有足以证明50×25 nm在2 TB或48 h内完成的数据。

## 证据与下一步裁决

| 主题 | 证据入口 |
|---|---|
| 正式运行身份、阶段、资源、finalizer | [supervision summary](../../results/task041_v14_main_warm_supervision_20261014T004907Z/summary.json)、[service parent](../../results/task041_v14_main_warm_supervision_20261014T004907Z/service_parent_summary.json)、[finalizer](../../results/task041_v14_main_warm_supervision_20261014T004907Z/finalizer/finalizer_summary.json)、[run summary](../../results/task041_w0p7nm_balh_hybrid_iterative_p6h0p70_m400_mpi8_cell_condensed_pilot/task041_w0p7_p6_h0p70_m400_mpi8_cell_condensed_pilot__hybrid_iterative__mpi8__M400/20261014T011327.081762Z/run_summary.json) |
| 800列/同B/owner与outer快照、失败字段缺失 | [failure closeout diagnosis](../../results/task041_v14_modal_row_failure_closeout_20261014T050244Z/diagnosis_zh.md)、[progress extract](../../results/task041_v14_modal_row_failure_closeout_20261014T050244Z/progress_extract.json)、[failure field audit](../../results/task041_v14_modal_row_failure_closeout_20261014T050244Z/failure_field_audit.json) |
| tiny两次apply原始捕获与测试 | [diagnostic JSON](../../results/task041_v14_modal_row_fgmres_serial_diag_attempt_20261014T052616Z/TASK041_V14_MODAL_ROW_DIAGNOSTIC.json)、[readout](../../results/task041_v14_modal_row_fgmres_serial_diag_attempt_20261014T052616Z/diagnostic_readout.json)、[pytest attempt](../../results/task041_v14_modal_row_fgmres_serial_diag_attempt_20261014T052616Z/serial/pytest.attempt.json) |
| 轻量中心记录与账目 | [machine record](outcomes/records/task041_v14_modal_row_terminal_20261014.json)、[live V5 ledger](../../results/task041_review_v5_cpu_numa_condensed_speed/r0_r1_20260920/r1_load_ledger_20260920.json) |

当前请求ChatGPT技术裁决的是：如何解释未保存的M400失败行，以及如何在未来已批准的诊断路径中保留门失败前的逐行输入/输出与归一化数据；并不请求本轮改变非零relative门、epsilon规则或生产PC。没有证据确认实现缺陷前，不启动第2场大型构造。M600、h细化、50×25 nm、2 TB及48 h目标均未获本场资格。
