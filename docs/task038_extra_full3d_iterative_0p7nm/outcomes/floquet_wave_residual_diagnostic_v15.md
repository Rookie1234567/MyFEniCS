# V15 Floquet 波模残差诊断收口

本文记录 Review V15 的可核查结果。这里的“诊断”是用固定的物理波模子空间解释残差；它不等于重新求解 PDE，也不产生 official 物理量。所有结果区分为实测、预测和未运行。

## 结论总表

| 阶段 | 结果 | 边界 |
|---|---|---|
| F0 设计与容量预审 | PASS（预测） | central 1,555,934,144 B；未宣称正式资源实测 |
| F1 small p3/h50，MPI1/MPI2 | F1_REAL_SMALL_ORACLE_PASS | canonical modal/PC 及 owner/MPC identity 通过 |
| F2 checkpoint-1000 residual 重算 | PASS | identity/algebra 通过，不是完整 PDE solve PASS |
| F3 固定 rank 32 波模投影 | FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE | algebra/resource 通过；span Gate 失败 |
| J5 full physical workflow | CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED | V14 用户控制停止，不是 fixed-cap 失败 |

F3 的固定 32 个预选模式只捕获残差能量的 0.2179823642496248%，投影后相对残差仍为 0.9989094935766222。因此该物理子空间没有解释本次 plateau 的主要部分；按合同关闭 correction，不启动 KSP、recovery 或 official physics。

## F0 固定身份与容量

| 项目 | frozen authority |
|---|---|
| 80-mode manifest SHA256 | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| fixed selector SHA256 | 7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3 |
| checkpoint manifest / solution SHA256 | 7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139 / 00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b |
| predicted complete central live set | 1,555,934,144 B |
| contract hard upper used for pre-audit | <1,800,000,000 B |

容量数值是 F0 的对象账本预测，不是 F3 formal 的 process-tree measured PASS。F3 formal 使用既有 fresh-cache、七个顺序 child 和 parent watchdog；不把累计分配量当作同时峰值。

## F1 small oracle

F1 使用 source SHA fb1b4be71d230b77eff431a7e3dd77eb3a69ba69，在 p3/h50、MPI1 和 MPI2 上运行同一真实 small runner。正式 artifact root 为：

    /home/shenjh/Projects/MyFEniCSx_task37_extra/benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/f1_floquet_wave_small_oracle_v5/fb1b4be71d230b77eff431a7e3dd77eb3a69ba69

profile 为 p3/h50/13.5nm/s/grazing1/phi0；real operator oracle 使用首个固定模式 mode_index=38、mode_key=[38,"top",0,0,"s"]。selector identity 覆盖 exact 32 indices，但这不表示 32 个模式都分别运行了 real MPI oracle。F1 raw 记录 modal_rhs_apply_count=4、pmg_apply_count=4，PMG 为 same_mesh_hcurl_pmg_v1、levels=[3,1]。

| 观测 | MPI identity / Gate |
|---|---:|
| modal canonical dual | 3.7455782853640207e-16 <= 1e-12 |
| PC canonical full-primal output | 8.520822093979077e-16 <= 1e-10 |
| modal repeat / linearity | 0 / 0 |
| PC repeat / input unchanged | 0 / 0 |
| PC linearity max | 3.614539850452157e-16 |
| P/P^H adjoint，MPI1 / MPI2 | 1.9465463728177503e-15 / 7.26427252913998e-15 <= 1e-11 |
| finite、slave-zero、owner-local、canonical keys | PASS |

selector 的固定 indices 是 [38,39,72,73,76,77,32,33,36,37,40,41,0,1,42,43,46,47,2,3,6,7,74,75,34,35,66,67,70,71,26,27]，但 real operator oracle 只使用首个固定模式 38。测试中的 synthetic QR 只表示阈值 <=1e-12 的 focused oracle PASS，不冒充 formal scalar。

compact evidence 见 [F1 small oracle compact record](records/floquet_wave_small_oracle_v15.json)。原始 record、四数组 NPZ 和 checker 的绝对路径及 SHA 都在该 JSON 中；大数组不复制到 Git。

## V15 formal artifact v3：F2 与 F3

V15 formal artifact v3 root 为：

    benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/f2_f3_floquet_wave_cold_staged_v3/c85ec1aab8548e02e8b47cfdcfb03b5c4df377f6

parent natural exit 为 0，33 个 marker 到 parent_complete，七个 precompile group 均 rc=0，11 个 module，solver cache unchanged 且无 recompile，diagnostic natural exit 为 0，全部进程消失。process JSONL 有 100656 samples，window 6245.343577229 s；authoritative RSS peak 1,447,358,464 B，swap 0，status 全部可读，warning=false，compiler peak=2。PSS 最高 1,417,525,248 B，但 7 个 transient precompile 退出样本的 PSS 不可读；PSS 仅作诊断，资源 Gate 采用完整 RSS。

| F2/F3 原始事实 | 数值 |
|---|---:|
| checkpoint iteration / stored residual | 1000 / 0.4837947981092168 |
| recomputed residual / relative difference | 0.48379479810921644 / 6.884466486395685e-16 <= 1e-11 |
| F2 identity、x/b unchanged、finite、slave-zero | PASS |
| F2 exact residual action count | 1 |
| accepted rank | 32 |
| condition ratio | 0.05087665596047715 |
| Q orthogonality | 1.4263744029917661e-13 |
| QR reconstruction | 2.4622854394555095e-16 |
| projection repeat | 2.7273607083155513e-16 |
| PC / exact action / modal RHS counts | 32 / 32 / 32 |
| captured energy（checker 重算） | 0.002179823642496248，要求 >= 0.90 |
| rho（checker 重算） | 0.9989094935766222，要求 <= 0.31622776601683794 |
| ideal projected true residual | 0.4832672167742815，要求 <= 0.153 |

F2 是同一 checkpoint 上的 identity/algebra residual reproduction PASS，不是 physical solve PASS。F3 的 rank、condition、orthogonality、QR、重复性、计数和资源均通过；只有 projection span Gate 失败，故最终分类固定为 FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE。独立 checker JSON 保持原样，见 [V15 checkpoint checker output](records/floquet_wave_checkpoint1000_v15.json)。

### F2 identity authority

| identity | exact SHA256 |
|---|---|
| checkpoint normalized input identity | 754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f |
| operator identity | bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3 |
| physical model identity | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| mode manifest identity | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| input file SHA256（独立于 normalized identity） | 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41 |

该表明确区分 template 文件本身的 SHA 与 checkpoint reader 使用的 normalized input identity；二者不能混称。

## V15 formal artifact v1/v2 pre-F2 execution failures 与次数边界

下列 pre-F2 失败原样保留，不修改其 raw status/classification：

| root | 事实 | 证据 |
|---|---|---|
| f2_f3_floquet_wave_cold_staged_v1/87b71b346580f57926b6dbd87e6ee1a408380bea | authority_unreadable 的 /proc transient-exit race，未进入 F2/F3 | parent 7833cf725d15626c72170a3591435684965aaa0f35f7d0d03b44c2986c534ab6；process b8c1628400276df7a3105af3afe8c65dac7eed5d3c85d866541df17a8ad95c6b；marker 8129248d43036dfa3462e37e338eff20ec2ad8d2a0d3651e68bfad5e7f8c9305 |
| f2_f3_floquet_wave_cold_staged_v2/7adaea8fa8bb17488f094a55b3f777b88e2b7f99 | ModuleNotFoundError: benchmarks.run_task038_full3d_jit_p6_positive，未进入 F2/F3；RSS 1,580,867,584 B，swap 0 | parent af587557dd7e5c070d955b44fd8a78c56261390a42974b0245ab3432ccf53f88；process ecce7ec5471d80056cff926c2ca491cebfa76f6e64ac854e6319282df669c26c；marker 483d10f4fd23a9b726e6ccb68bbcb52e561a1234dfe3a4689488e5ccb387f806；stderr c781c19f5fcf8e511801dee5133f2519c39b41c238cbfe39526b91fb1f416690 |

完整 SHA 已在本表列出，raw 留在各 V15 artifact root。这些是发生在真实 checkpoint/数值测量之前的唯一可定位代码、path、marker 或 provenance 问题；按用户明确授权，不计正式数值次数，但不改写旧证据。

## 未运行项与证据边界

| 项目 | 状态 |
|---|---|
| fixed rank32 correction、KSP、corrected screen | not_run_by_span_gate |
| recovery、official E/H、R/T/A、A_volume、12+12 channels | not_run_by_span_gate |
| MPI2、h5、full 0.7 nm | not_run_by_span_gate |
| J6/J7/J8 | not_run；J7/J8 locked |

J0 的 AUTHORITY_ARRAYS_MISSING 仍有效。V13 四类 same_mesh_hcurl_pmg_v1_requalified positive qualification 保留，但不能提升为 standalone physical Maxwell production qualification。V14 J5 的 [J5 compact evidence](records/j5_full_cold_staged_v3_controlled_stop_v14.json) 仍标记为 CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED；这不是 fixed-cap 20000-step failure，也不是完整 workflow memory PASS。

## 原始证据索引

| 类别 | root / compact |
|---|---|
| V15 formal artifact v3 parent | f2_f3_floquet_wave_cold_staged_v3/c85ec1aab8548e02e8b47cfdcfb03b5c4df377f6 |
| V15 formal artifact v3 parent SHA256 | ae7576e117534fcc5b24b1f08c95907549be830b3fae63ce66b12b5ccf751077 |
| V15 formal artifact v3 worker / process / marker / vectors SHA256 | 5505201592066ffbca7ec4a1e666ad769bfa758b6597841f11b90d5c16c78af2 / 30147d07c62fccf0c721586e5e10a2528434d8a51afc020a0232bffca8feafa9 / 7c42c46a0250b3479bcd6bac788e244465ef70b223964ad08dbdf27835a180d7 / 839a97e48740cd6c8fc9e3fbbe3634b9eccc342b07ded9bfeda27310ea41e789 |
| V15 formal artifact v3 cache before/after | 6e901145be8a8afa2f71a789eb9211c81fe0fa8b11dedee9bbaf29b5cfa77eca / 6e901145be8a8afa2f71a789eb9211c81fe0fa8b11dedee9bbaf29b5cfa77eca |
| checker result | [F3 checker result](records/floquet_wave_checkpoint1000_v15.json) |

V14 response 的 J5 raw JSONL 为 1,020,808,306 B；它仍只以 hash-bound compact 形式进入文档，不追踪原始 1.02 GB 文件。
