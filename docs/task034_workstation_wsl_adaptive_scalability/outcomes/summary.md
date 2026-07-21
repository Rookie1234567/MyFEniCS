# Task034 最终成果汇总（Response V5 selective-merge candidate）

## 状态与范围

| 字段 | 结论 | 证据身份 |
|---|---|---|
| final status | `PASS_WITH_QUALIFICATIONS` | 失败和资源 stop 原样保留 |
| production mainline | S polarization | 用户批准；不重复整套 P 矩阵 |
| P capability | p2/h5 MPI8 Full3D + Hybrid M160 可计算 | capability sample，不参与 S 收敛主线 |
| Review V3 + Task35 planning addendum sync | 3a6a464156b88cc138a732110f1e22b0915c1f3b | 当前 Task34 分支 fast-forward pull；未 merge/rebase/cherry-pick origin/master |
| numerical core in Review V4 | unchanged | 未重跑 p3/h3、p4/h5、M funnel 或 MPI 重型矩阵；未执行 Task035 PDE |
| unified fact table | 40 rows / 36 columns | tracked compact fixture 在 no-artifact clean checkout 中字节级重建；空缺为 `null`，不插值 |

## Capability layering

| capability | 状态 | 边界 |
|---|---|---|
| workflow decision complete | true | Task034 每阶段有正式 decision |
| uniform benchmark | pass | Case093 固定几何 p2/p3/p4 S 主线 |
| representative MPI identity | pass | p3/h5 S；Full3D/Hybrid MPI1/8/16，MPI32 exploratory |
| graded mesh mechanism | pass | mesh/Floquet/标记机制可执行 |
| equal-accuracy graded compression | controlled negative | 三档均未通过 fixed Full3D 同误差 Gate |
| field-driven adaptivity | not qualified | 不把 raw DoF reduction 写成 qualified compression |
| common-mesh / p3 adaptive extension | not run by stop condition | critical observable failure 后停止 |
| resource model | revised engineering stress test | p2/p3/p4 场景；envelope 与 simultaneous peak 分离 |
| production 0.7 nm feasibility | unknown / not demonstrated | current-layout stress tests 均有单组件超 2 TiB |

## 表 1：全模型主表

40 行统一事实表在本 summary 中全部直接覆盖：本表 1a/1b 为 26 个固定几何主线与补充模型；表 2 为 6 个 M-funnel 记录；表 3 为 8 个 MPI identity 记录。所有入射均为 S；R00_p/T00_p 是 S 入射下 cross-polarized p 输出，不是 P 入射复跑。null 表示权威证据未提供，未插值、未跨方法补值。

### 表 1a：物理量与状态

| p/h | method | M | MPI | status | R_total | T_total | A_balance | A_volume | R00_total |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|
| p2/h5 | Full3D | null | 8 | full3d_reference_pass | 0.0890216029 | 0.442588279 | 0.468390118 | 0.468390118 | 0.0890130359 |
| p2/h5 | Hybrid | 160 | 8 | measured_shard_pass | 0.0890210691 | 0.442586743 | 0.468392188 | 0.468392188 | 0.0890118197 |
| p2/h3 | Full3D | null | 8 | full3d_reference_pass | 0.00461303141 | 0.583653357 | 0.411733611 | 0.411733611 | 0.00460127305 |
| p2/h3 | Hybrid | 160 | 8 | measured_shard_pass | 0.0046128199 | 0.58365094 | 0.41173624 | 0.41173624 | 0.0046011177 |
| p2/h2 | Full3D | null | 8 | full3d_reference_pass | 0.00134293285 | 0.599213229 | 0.399443838 | 0.399443838 | 0.00133312476 |
| p2/h2 | Hybrid | 160 | 8 | measured_shard_pass | 0.00134288473 | 0.599212676 | 0.399444439 | 0.399444439 | 0.00133309761 |
| p2/h1 | Full3D | null | 8 | not_run_by_conservative_resource_gate_after_assembly | null | null | null | null | null |
| p2/h1 | Hybrid | 160 | 8 | timeout_during_field_recovery_no_official_solution | null | null | null | null | null |
| p3/h10 | Full3D | null | 8 | full3d_reference_pass | 0.0553984905 | 0.406067867 | 0.538533643 | 0.538533643 | 0.0553826781 |
| p3/h10 | Hybrid | 160 | 8 | formal_not_pass | 0.0553988021 | 0.40606931 | 0.538531888 | 0.538531887 | 0.0553792864 |
| p3/h7.5 | Full3D | null | 8 | full3d_reference_pass | 0.00309072745 | 0.591160863 | 0.405748409 | 0.405748409 | 0.00307976819 |
| p3/h7.5 | Hybrid | 160 | 8 | measured_shard_pass | 0.00309064738 | 0.591159679 | 0.405749673 | 0.405749673 | 0.00307976491 |
| p3/h5 | Full3D | null | 8 | full3d_reference_pass | 0.00109010701 | 0.600622478 | 0.398287415 | 0.398287415 | 0.00108058337 |
| p3/h5 | Hybrid | 160 | 8 | measured_shard_pass | 0.00109009569 | 0.600622368 | 0.398287536 | 0.398287536 | 0.00108058359 |
| p3/h3 | Full3D | null | 8 | full3d_reference_pass | 0.000789467957 | 0.602514984 | 0.396695548 | 0.396695548 | 0.000780309834 |
| p3/h3 | Hybrid | 160 | 8 | measured_shard_pass | 0.000789467334 | 0.602514979 | 0.396695554 | 0.396695554 | 0.000780309829 |
| p3/h2 | Full3D | null | 8 | not_run_by_conservative_resource_gate_after_assembly | null | null | null | null | null |
| p3/h2 | Hybrid | 160 | 8 | measured_shard_pass_no_m_funnel_no_full3d_closure | 0.000764466671 | 0.602690128 | 0.396545405 | 0.396545405 | 0.000755344038 |
| p4/h10 | Full3D | null | 8 | full3d_reference_pass | 0.00188231722 | 0.59661952 | 0.401498163 | 0.401498163 | 0.00187216051 |
| p4/h10 | Hybrid | 160 | 8 | measured_shard_pass | 0.00188234769 | 0.596619395 | 0.401498258 | 0.401498258 | 0.00187215501 |
| p4/h7.5 | Full3D | null | 8 | full3d_reference_pass | 0.000802469015 | 0.602429773 | 0.396767758 | 0.396767758 | 0.000793283286 |
| p4/h7.5 | Hybrid | 160 | 8 | measured_shard_pass | 0.000802464969 | 0.602429757 | 0.396767778 | 0.396767778 | 0.000793283227 |
| p4/h5 | Full3D | null | 8 | full3d_reference_pass | 0.000766313377 | 0.602677531 | 0.396556156 | 0.396556156 | 0.000757187647 |
| p4/h5 | Hybrid | 160 | 8 | measured_shard_pass | 0.000766313235 | 0.60267753 | 0.396556157 | 0.396556157 | 0.000757187631 |
| p4/h3 | Full3D | null | 8 | not_run_by_conservative_resource_gate_after_assembly | null | null | null | null | null |
| p4/h3 | Hybrid | 160 | 8 | measured_shard_pass_no_m_funnel_no_full3d_closure | 0.00076218454 | 0.602706301 | 0.396531514 | 0.396531514 | 0.000753065135 |

### 表 1b：规模与资源

| p/h | method | M | MPI | elements | fe DoF | external aux DoF | modal unknowns | total rows | peak GiB | total s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| p2/h5 | Full3D | null | 8 | 1680 | 44698 | 80 | null | 44778 | 2.9596062 | 16.567574 |
| p2/h5 | Hybrid | 160 | 8 | 480 | 13652 | 80 | 320 | 14052 | 3.2848663 | 96.284394 |
| p2/h3 | Full3D | null | 8 | 7776 | 198438 | 80 | null | 198518 | 9.5349388 | 152.97227 |
| p2/h3 | Hybrid | 160 | 8 | 2592 | 68396 | 80 | 320 | 68796 | 4.6951599 | 164.31719 |
| p2/h2 | Full3D | null | 8 | 24570 | 615108 | 80 | null | 615188 | 32.539612 | 1235.5432 |
| p2/h2 | Hybrid | 160 | 8 | 7020 | 180696 | 80 | 320 | 181096 | 11.305332 | 461.77607 |
| p3/h10 | Full3D | null | 8 | 252 | 23073 | 80 | null | 23153 | 2.7445717 | 20.091813 |
| p3/h10 | Hybrid | 160 | 8 | 72 | 7194 | 80 | 320 | 7594 | 2.8677101 | 91.920293 |
| p3/h7.5 | Full3D | null | 8 | 720 | 63747 | 80 | null | 63827 | 4.6096954 | 52.327746 |
| p3/h7.5 | Hybrid | 160 | 8 | 288 | 26598 | 80 | 320 | 26998 | 3.61446 | 117.67073 |
| p3/h5 | Full3D | null | 8 | 1680 | 145863 | 80 | null | 145943 | 9.0400734 | 149.65782 |
| p3/h5 | Hybrid | 160 | 8 | 480 | 43614 | 80 | 320 | 44014 | 4.9082375 | 143.51496 |
| p3/h3 | Full3D | null | 8 | 7776 | 656325 | 80 | null | 656405 | 44.068672 | 1726.3617 |
| p3/h3 | Hybrid | 160 | 8 | 2592 | 223770 | 80 | 320 | 224170 | 14.271553 | 661.41003 |
| p4/h10 | Full3D | null | 8 | 252 | 53084 | 80 | null | 53164 | 5.6395607 | 115.52464 |
| p4/h10 | Hybrid | 160 | 8 | 72 | 16216 | 80 | 320 | 16616 | 3.5176163 | 136.25296 |
| p4/h7.5 | Full3D | null | 8 | 720 | 147844 | 80 | null | 147924 | 12.724396 | 345.38403 |
| p4/h7.5 | Hybrid | 160 | 8 | 288 | 61064 | 80 | 320 | 61464 | 5.9671173 | 279.37713 |
| p4/h5 | Full3D | null | 8 | 1680 | 339892 | 80 | null | 339972 | 28.888458 | 917.47044 |
| p4/h5 | Hybrid | 160 | 8 | 480 | 100520 | 80 | 320 | 100920 | 9.2059174 | 412.42189 |
| p2/h1 | Full3D | null | 8 | 178500 | 4379752 | 80 | null | 4379832 | 67.922901 | 792.95848 |
| p2/h1 | Hybrid | 160 | 8 | null | null | null | null | null | 95.878723 | 7200 |
| p3/h2 | Full3D | null | 8 | 24570 | 2047218 | 80 | null | 2047298 | 64.01495 | 1334.6453 |
| p3/h2 | Hybrid | 160 | 8 | 7020 | 595956 | 80 | 320 | 596356 | 49.641502 | 3513.8182 |
| p4/h3 | Full3D | null | 8 | 7776 | 1539948 | 80 | null | 1540028 | 80.537712 | 3035.1391 |
| p4/h3 | Hybrid | 160 | 8 | 2592 | 522136 | 80 | 320 | 522536 | 42.481407 | 3662.6851 |

Hybrid elements 来自每条 accepted evidence 的 SHA-256 绑定一次性提取，口径为 prod(bottom_local_mesh_cells) + prod(top_local_mesh_cells)；普通聚合与测试不读取 artifacts。

## 表 2：M funnel（p3/h3 与 p4/h5）

p3/h3 使用已接受的 current-source MPI8 funnel；p4/h5 保留已接受的 MPI4 formal funnel。max Δ vs prev M 是相邻 M 间 R/T/A_balance/A_volume/R00_total 的最大绝对差；首行为 baseline。

| case | MPI | M | modal | rows | R/T/A/Avol | R00 | residual | peak GiB | total s | max Δ vs prev M |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| p3/h3 | 8 | 80 | 160 | 224010 | 0.000789467335/0.602514979/0.396695554/0.396695555 | 0.00078030983 | 2.076e-11 | 12.73734 | 529.55618 | baseline |
| p3/h3 | 8 | 120 | 240 | 224090 | 0.000789467334/0.602514979/0.396695554/0.396695554 | 0.000780309829 | 6.972e-12 | 13.70872 | 567.5734 | 1.103e-09 |
| p3/h3 | 8 | 160 | 320 | 224170 | 0.000789467334/0.602514979/0.396695554/0.396695554 | 0.000780309829 | 6.718e-12 | 14.27155 | 661.41003 | 8.570e-12 |
| p4/h5 | 4 | 80 | 160 | 100760 | 0.000766313235/0.60267753/0.396556157/0.396556158 | 0.000757187631 | 5.182e-12 | 5.048573 | 558.96729 | baseline |
| p4/h5 | 4 | 120 | 240 | 100840 | 0.000766313235/0.60267753/0.396556157/0.396556157 | 0.000757187631 | 5.726e-12 | 5.497772 | 634.19357 | 1.107e-09 |
| p4/h5 | 4 | 160 | 320 | 100920 | 0.000766313235/0.60267753/0.396556157/0.396556157 | 0.000757187631 | 7.031e-12 | 5.961403 | 734.21756 | 8.713e-12 |

## 表 3：MPI identity（p3/h5 S）

R/T/A/Avol 是选定 p3/h5 同方法 baseline physics，MPI comparison 记录保存其漂移；max physical drift 是 R/T/A_balance/A_volume 对 baseline 的最大绝对漂移。Full3D 权威记录没有端到端 total，故 total 明确为 null，另列 stage4_dtn_port_assembly_and_solve；Hybrid 提供端到端 total。MPI32 仅为 exploratory，不替代 MPI16。

| method | MPI | M | rows | R/T/A/Avol | residual | peak GiB | total s | reported core s | max physical drift | identity |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| Full3D | 1 | null | 145943 | 0.00109010701/0.600622478/0.398287415/0.398287415 | 1.265e-10 | 6.339725 | null | 1050.5189 | 0.000e+00 | pass |
| Full3D | 8 | null | 145943 | 0.00109010701/0.600622478/0.398287415/0.398287415 | 8.305e-12 | 9.013885 | null | 150.51138 | 8.776e-13 | pass |
| Full3D | 16 | null | 145943 | 0.00109010701/0.600622478/0.398287415/0.398287415 | 1.143e-11 | 11.35872 | null | 72.97057 | 8.706e-13 | pass |
| Full3D | 32 | null | 145943 | 0.00109010701/0.600622478/0.398287415/0.398287415 | 6.912e-12 | 15.77257 | null | 41.948454 | 8.817e-13 | exploratory pass |
| Hybrid | 1 | 160 | 44014 | 0.00109009569/0.600622368/0.398287536/0.398287536 | 6.418e-12 | 1.244774 | 431.07164 | null | 0.000e+00 | pass |
| Hybrid | 8 | 160 | 44014 | 0.00109009569/0.600622368/0.398287536/0.398287536 | 1.164e-11 | 4.900311 | 144.6915 | null | 3.852e-13 | pass |
| Hybrid | 16 | 160 | 44014 | 0.00109009569/0.600622368/0.398287536/0.398287536 | 3.397e-12 | 7.14957 | 134.13195 | null | 1.942e-13 | pass |
| Hybrid | 32 | 160 | 44014 | 0.00109009569/0.600622368/0.398287536/0.398287536 | 3.788e-12 | 12.08782 | 201.09742 | null | 1.488e-13 | exploratory pass |

同一方法内 case/source/config/structure 一致；fields/interfaces、orders、complex amplitudes、QEP beta 与 true residual 也全部满足 identity 阈值。


## 表 4：资源 stop 与受控负结果

| case/method | measured progress | measured peak GiB | predicted upper / timeout | exact status |
|---|---|---:|---:|---|
| p2/h1 Full3D | assembly；4,379,832 rows；461,122,320 NNZ | 67.923 | factor upper 418.821 GiB | `not_run_by_conservative_resource_gate_after_assembly` |
| p2/h1 Hybrid M160 | local factors/Schur 完成；field recovery 开始 | 95.879 | 7200 s timeout | `timeout_during_field_recovery_no_official_solution` |
| p3/h2 Full3D | assembly 1334.65 s；2,047,298 rows；488,789,000 NNZ | 64.015 | factor upper 232.460 GiB | `not_run_by_conservative_resource_gate_after_assembly` |
| p3/h2 Hybrid M160 | complete shard；residual `3.613e-11` | 49.642 | 3513.82 s measured | pass only；no M funnel/closure |
| p4/h3 Full3D | assembly 3035.139050935 s；1,540,028 rows；696,091,072 NNZ | 80.537712 | factor upper 204.132 GiB | `not_run_by_conservative_resource_gate_after_assembly` |
| p4/h3 Hybrid M160 | complete shard；residual `2.924e-11` | 42.481 | 3662.69 s measured | pass only；no M funnel/closure |

三条 Full3D 的 factorization/full-solve 均 `launched=false`；upper 是预测而非 measured peak。
p2/h1 Hybrid 未触发 memory warning、swap 为 0，但没有 solver record、official R/T/A 或 true residual。

## Adaptive 与资源模型

| adaptive profile | raw DoF reduction | peak GiB | wall s | same-error result |
|---|---:|---:|---:|---|
| conservative | 1.561x | 3.964 | 112.12 | controlled negative |
| balanced | 3.172x | 3.292 | 96.63 | controlled negative |
| aggressive | 9.590x | 2.537 | 71.92 | controlled negative |

资源模型 v2.1 使用 p2/h3、p3/h3、p4/h5 三个 13.5 nm current-layout 场景。13.5 nm
simultaneous peaks 分别为 4.695/14.272/9.206 GiB；外推 peak 全为 `unknown`。0.7 nm 的
cumulative envelopes 分别为 2,014,975/6,804,671/3,008,763 GiB，但这些累计值不是同时峰值。
三个场景均存在单组件超过 2 TiB，故 current layout stress test 为负；production target-accuracy
DoF、M 和 peak 仍是 unknown。

## Review V4 工程边界

- benchmark Python inventory 覆盖 31 个变更文件，未发现 Task034 复制独立 solver；数值功能归 `src/`；
- `selective_merge_manifest.csv` 逐文件给出 action、dependency group、tests、数值变化、PDE 证据和顺序；
- `all_model_compact_fixture.json` 是 reviewed SHA-256-bound one-time extraction 形成的 40 行最小 tracked facts；metadata 区分 extraction process、fixture schema 与 output aggregator；普通聚合器只读取 tracked records，artifact path 仅作 provenance string；
- `factor_nnz` 仅表示存在时的 measured direct-factor `matrix_nnz_used`，Hybrid 或无 inventory 时为 `null`；
- `all_model_authority_audit.json` 扫描全部 40 行；唯一漂移是 p4/h3 Full3D elapsed/memory 两字段，已统一到 tracked process-tree compact authority；
- research-only adaptive/reranking/resource/Review 聚合器不作为 production API；
- p1 与完整重型 P 矩阵仍按用户批准范围排除；任何 negative 未改写为 pass。
