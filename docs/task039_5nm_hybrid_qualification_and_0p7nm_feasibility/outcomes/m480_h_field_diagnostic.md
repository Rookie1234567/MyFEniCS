# E6：M480 Hybrid 三路径 H 场诊断

## 1. 目的与边界

这一步把同一组重构电场用两种方式得到磁场，再与 Full3D 的离线重建结果逐点比较：
`native` 是 Hybrid 现有的本征/traction 路径，`curlE` 是对完整重构电场使用传播方程解析求
旋度，`Full3D` 是从既有 canonical finite-element shard 离线恢复的场。这样可以区分
“场后处理方式不同”和“Hybrid 场本身与 Full3D 不同”，但不能把相关性诊断升级成生产模型
资格。

最终 compare 是离线；因旧 artifact 缺少完整重建/导数 authority，本 E6 按 Review 授权
执行了一次且仅一次冻结 M480 MPI8 direct 诊断复跑。Full3D 只做离线 replay，没有新的
Full3D solve，也没有进入 E7 或改写 T3–T5 的历史记录。

## 2. 身份与输入

| 项目 | 值 |
| --- | --- |
| 分支/E6 code/static parent | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` / `af75d8c73c72cd9340191f7fb332227496e62509` |
| Hybrid formal source commit | `e6625b646ac606543d8ae095ba7ef210ea2428cd` |
| input SHA256 | `5db2607496e3fe195f719c4b217fdaae3bee7e311007e564345c0a2dff8395bc` |
| resolved config SHA256 | `21c09027cc7a9ab7c92b3a98cc1f2fa9f452e282d7327f98d54ff56bfa628a85` |
| physical model SHA256 | `db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a` |
| 冻结合同 | 5 nm, p6/h10, S, grazing 10°, phi 0°, Hybrid direct, M480, MPI8, 604 external keys |
| Hybrid raw run | `results/task039_5nm_hybrid_direct_m480/task039_5nm_hybrid_direct_p6h10_m480_mpi8__hybrid_direct__mpi8__M480/20260813T161305.428900Z` |
| Full3D replay目录 | `results/task039_review_v1_e6_h_diagnostic/full3d_canonical_replay_e6625b64` |
| 离线比较命令 | `python -m benchmarks.task039_h_field_diagnostic compare --hybrid-payload <Hybrid NPZ> --full3d-payload <Full3D NPZ> --output <comparison JSON>` |

Full3D replay 只读取 T3 canonical shard，旧五平面 identity 为 E `5.629444282611577e-15`
和 H `3.1238965408992835e-16`；因此它是合格的离线场参考，不是新的 Full3D solve。

## 3. Hybrid own authority

| Gate/量 | measured 值 | 判定 |
| --- | ---: | --- |
| full true relative residual | `9.739106890329058e-12` | `<=1e-9`, pass |
| exact traction bottom/top | `2.5683789305404366e-12 / 9.685730166363022e-12` | `<=1e-8`, pass |
| interface projection bottom/top/combined | `1.0647690104657027e-12 / 1.1795433055657498e-11 / 1.1382245902228788e-11` | `<=1e-8`, pass |
| R/T/A_balance/A_volume | `0.9094973679567948 / 0.0008705857380464786 / 0.08963204630515871 / 0.08963319109920317` | finite |
| energy closure | approximately `1.145e-6` | `<=1e-5`, pass |
| external inventory | 604 exact unique keys | pass |
| process-tree RSS/PSS/USS | `22785.6796875 / 21028.330078 / 20747.875 MiB` | measured independent peaks |
| process-tree swap | `0 MiB` | pass |
| numerical wall | `1500.0791483931243 s` | measured |

Raw authority flags remain unchanged and are reported literally: `physical_augmented_direct_pass=false`,
`official_record=false`, and sampled traction-density proxy Gate `false`. The exact variational
traction Gate above is independent and passes; the sampled proxy is not substituted for it.

## 4. Payload and sampling contract

两侧都使用 40×20 的 x/y 采样，并包含以下七个严格升序平面：
`[10, 15, 30, 60, 90, 105, 110] nm`。15 nm 和 105 nm 是相邻真实单元的中点，
不是任意 epsilon 偏移；provenance 为 `mesh_element_interior`，每侧 `element_id/slab_index=2/11`
且距离接口 5 nm。

| payload | SHA256 | metadata SHA256 | 主要内容 |
| --- | --- | --- | --- |
| Hybrid `task039_h_diagnostic_payload.npz` | `baf3791f9b0f3fbf34adfd1d0ed322e26068707b72d8bced00d80603dacd9889` | `f013eeb206e3011fb5b918854f68de769480680e790076dca08b829d00111717` | native/curlE E/H、flux、energy |
| Full3D `task039_full3d_h_diagnostic_payload.npz` | `19df097db1fa2f40f57c98449361cc20279883b8b9018196eb108278aa905da2` | `ed70b7328501b4fea6675fffa28302ded18f96f00784f01ca0e3c04914c7c7f6` | canonical replay E/H、flux、energy |

Hybrid 数组为 `complex128` 场 `(7,20,40,3)`、`float64` 坐标/标量；curlE 来源明确为
`complete_reconstructed_field_analytic_or_fe`。使用的独立公式为：

```math
H_{curlE} = \frac{1}{i k_0 \mu_r}\nabla \times E_{reconstructed}.
```

flux 是每平面 x/y 采样平均的 `0.5*Re((E x conj(H))_z)`；energy 是
`vacuum_weighted_field_energy_proxy`，不是体积分或材料吸收量。

## 5. 比较结果

比较输出：
`results/task039_review_v1_e6_h_diagnostic/hybrid_m480_e6625b64_compare_fixed/h_comparison.json`

SHA256 `a1bf836aecfe6f59a4702ec24de6fdc9801807e0bfc7f05ab5a55158e5509cb0`，完整 JSON
保留 126 个逐平面/逐分量记录，包括 reference norm、absolute/relative L2、分母、最大绝对
误差、phase-sensitive complex error 及 mandatory/strong 状态。

### 5.1 总体场误差

| 比较 | E absolute / relative L2 | H absolute / relative L2 |
| --- | ---: | ---: |
| native vs curlE | `0 / 0` | `3.379573127670069e-5 / 0.0010876471954123718` |
| curlE vs Full3D | `0.009653241872356532 / 0.0008277153668860366` | `0.00023298100764416747 / 0.007498197526364605` |
| native vs Full3D | `0.009653241872356532 / 0.0008277153668860366` | `0.00024229456804377545 / 0.007797760173875772` |

### 5.2 各平面总体 relative L2

| z (nm) | native/curlE E | native/curlE H | curlE/Full3D E | curlE/Full3D H | native/Full3D E | native/Full3D H |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 0 | `0.007546856462930465` | `2.2868741638788903e-6` | `0.0592862707563419` | `2.2868741638788903e-6` | `0.0616688298821218` |
| 15 | 0 | `0.00756479666684866` | `0.011098390992150181` | `0.02872141539917819` | `0.011098390992150181` | `0.02885849598616441` |
| 30 | 0 | `0.007822355075579117` | `1.1821093697084564e-7` | `0.058018666750252544` | `1.1821093697084564e-7` | `0.060460247187828504` |
| 60 | 0 | `0.007301979568012685` | `1.2251252014647612e-7` | `0.05761394305065237` | `1.2251252014647612e-7` | `0.05995873633947971` |
| 90 | 0 | `0.003261590397522825` | `5.9373908501065275e-8` | `0.025449132503764824` | `5.9373908501065275e-8` | `0.026506778819819256` |
| 105 | 0 | `0.0008656106060070042` | `0.001228834365486254` | `0.0033531382833542856` | `0.001228834365486254` | `0.003419223965258945` |
| 110 | 0 | `0.0005504657237062513` | `5.578165318493181e-6` | `0.004311279865295084` | `5.578165318493181e-6` | `0.0044985655596642` |

126 个 component 分母均 `near_zero_denominator=false`。三种比较的 flux/energy 每平面
mandatory/strong 均通过；最大 absolute delta 分别为：native/curlE
`1.7550593528845734e-9 / 3.369580979338441e-18`、curlE/Full3D
`4.159937795074273e-8 / 7.667745603054024e-17`、native/Full3D
`4.369245669943095e-8 / 8.006427170664139e-17`（flux / energy）。

## 6. 分类解释

机器可读结果为：

```text
diagnostic_complete=true
numeric_gate_pass=true
pass=true
classification=M480_H_DISCREPANCY_UNRESOLVED
```

`numeric_gate_pass=true` 表示本次比较使用的总体 E/H、flux 和 energy 数值阈值通过；
`M480_H_DISCREPANCY_UNRESOLVED` 表示证据不足以证明唯一因果来源，两者不矛盾。

三个特殊分支均未满足：

- 不是 `M480_H_RECOVERY_OR_POSTPROCESS_DEFECT`：native-vs-Full3D 与 curlE-vs-Full3D
  没有形成“只有 native 失败而 curlE 通过”的证据。
- 不是 `M480_H_DERIVATIVE_MODAL_TRUNCATION_NOT_CONVERGED`：两条相对 Full3D 的比较
  没有同时落入该分支的失败条件，且 native/curlE 的差异并非该分类的充分证明。
- 不是 `M480_H_GATE_CONDITIONING_REVIEW_REQUIRED`：所有 component 分母均非近零，不能
  用 conditioning 解释这些差异。

因此本阶段不声称 Full3D-qualified、production-qualified 或 Hybrid model validation；
T4 negative blocker、T5 的 `M_robust_h10=not_established` 及历史 negative records 全部保留。

## 7. 证据入口

- [Task39 summary](summary.md)
- [resource ledger](resource_ledger.md)
- [test summary](test_summary.md)
- [T5 Hybrid record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_t5_hybrid_direct_m_convergence_v1.json)

Raw run、replay payload 和 comparison JSON 位于 ignored `results/` 目录；其路径与完整 SHA
在本文件及已生成的 comparison JSON 中绑定。E6 完成后停在本阶段，不进入 E7。
