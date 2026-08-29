# J1a exact-profile form/JIT inventory v14

这份清单只回答一个边界问题：当前 Task038 exact profile 在求解前和条件恢复阶段会请求哪些 FFCx/DOLFINx 编译对象。J1a 没有构造网格、`fem.form`、PDE 或 JIT；漏掉一个 form 会使运行时产生额外 cache miss 和编译子进程，增加 cold setup 峰值并破坏生命周期审计。

## 范围与冻结身份

| 项目 | 本轮事实 |
|---|---|
| inventory 状态 | `STATIC_INVENTORY_ONLY`；静态源码清单加 host-qualified 只读 profile probe |
| source SHA | `efc93df248e1566768dd6a8e487b61ec24b5d16c` |
| frozen input SHA | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| frozen physical model SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode manifest SHA | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| exact profile | `p6/h10/13.5nm/s/grazing1/phi0`；same physical mesh；selected hierarchy=`same_mesh_hcurl_pmg_v1_requalified` |
| J1 执行边界 | host probe 只调用 `load_and_resolve`、`simulation_config_3d_from_normalized`、`build_dynamic_mode_inventory`、`_dtn_surface_quadrature_degree`；没有 mesh、`fem.form`、JIT 或 PDE |

## Read-only profile probe

资格化 host shell 中执行的语义是：解析 `input/templates/full3d_iterative_example.dat`，从 normalized spec 构造 `SimulationConfig3D`，构造 dynamic mode inventory，再调用 `_dtn_surface_quadrature_degree(cfg, list(modes))`。probe 没有创建 mesh 或 form。

| 事实 | 实测值 |
|---|---|
| mode count | `80` |
| max mode order | `7` |
| resolved surface qdegree | `25` |
| `use_pml` | `false` |
| PML thickness | `pml_top_thickness=0.0`、`pml_bottom_thickness=0.0` |
| `pml_alpha` / outer boundary | `5.0` / `natural` |
| `divergence_penalty` | `0.0` |
| `full3d_reference_export` | `true` |
| `diffraction_compute_modal_diagnostic` | `false` |
| `visualization_degree` | `6` |

因此四个 DtN surface form 和 incident traction RHS 的 resolved qdegree 都是 `25`。physical volume 对当前 exact profile 的 active branch 是 tagged curl-plus-mass Maxwell terms；没有 PML 或 divergence-penalty 分支。`.c/.so` filesystem cache artifacts 预计保留到 formal root 结束；`.o` 是否仅为编译临时文件由 J2 实测。销毁 `fem.Form`/`Function` 不保证 dlopen module mapping 或 allocator RSS 归还；进程退出前不得声称卸载，必须以阶段 RSS 和 compiler-child teardown 实测。

## Authority 边界

只保留 J0 authority 指针：`classification=AUTHORITY_ARRAYS_MISSING`；record=`docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/direct_authority_packet_audit_v1.json`；sha256=`53b4bfc97676a41395431954b1c56013d1bf301b191cd46834e74caeffaa08b8`。V13 C1/P0 的冻结引用仍有效；本清单不把 scalar authority 或旧 profile 当作完整 field/channel authority。

## A. 求解前 form/JIT inventory

`cache/module identity` 对下列源码 inventory 均为 `not_measured_j1`。每行的 `.c/.so` 与 `.o` 生命周期均服从上面的统一实测边界；J2 才能确认文件是否跨 form 共享及 compiler child 时序。

| ID；UFL/form role | rank / 类型；degree | quadrature / coefficient identity | source；runtime consumer；precompile group；solve-critical |
|---|---|---|---|
| `p6_positive_action`；`ufl.action(same_mesh_positive_form)` | rank 1 from rank-2 bilinear；N1curl p6；compiled `dolfinx.fem.Form` | compiler default；`mu,mass` from same tagged positive construction | `fullspace_same_mesh_hcurl_pmg_setup.py:289-298`、`fullspace_mpc_action.py:23-33,73-88`；`FullspaceMpcFormAction.apply`；`positive_p6_action`；是 |
| `p6_positive_bilinear_diagonal`；same rank-2 form used as exact constrained diagonal input | rank 2；N1curl p6 | compiler default；same `mu/mass` coefficients；no unconstrained element-diagonal substitute | `fullspace_same_mesh_hcurl_pmg_global.py:145-159`、setup `:289-300`；`build_constrained_jacobi_diagonal`；`positive_p6_diagonal`；是 |
| `p3_positive_bilinear`；same-mesh curl-plus-mass | rank 2；N1curl p3 | compiler default；same mesh/tagged `mu,mass` | `fullspace_same_mesh_hcurl_pmg_global.py:113-141`、setup `:306-310`；sparse p3 assembly；`positive_sparse_levels`；是 |
| `p1_positive_bilinear`；same-mesh curl-plus-mass | rank 2；N1curl p1 | compiler default；same mesh/tagged `mu,mass` | `fullspace_same_mesh_hcurl_pmg_global.py:113-141`、setup `:312-316`；p1 sparse development oracle；`positive_sparse_levels`；是 |
| `dtn_top_x`；`inner((phase,0,0),v)*ds(z_max)` | linear rank 1；N1curl p6 | configured field or fallback；probe resolved qdegree=`25`；phase `alpha/gamma/kz` Constants；x component/top tag | `dtn_port_3d.py:1081-1125`、physical surface assemblers；top mode projection；`dtn_surface_component`；是 |
| `dtn_top_y`；`inner((0,phase,0),v)*ds(z_max)` | linear rank 1；N1curl p6 | same probe qdegree=`25`；same phase Constants；y component/top tag | `dtn_port_3d.py:1081-1125`；top mode projection；`dtn_surface_component`；是 |
| `dtn_bottom_x`；`inner((phase,0,0),v)*ds(z_min)` | linear rank 1；N1curl p6 | same probe qdegree=`25`；same phase Constants；x component/bottom tag | `dtn_port_3d.py:1081-1125`；bottom mode projection；`dtn_surface_component`；是 |
| `dtn_bottom_y`；`inner((0,phase,0),v)*ds(z_min)` | linear rank 1；N1curl p6 | same probe qdegree=`25`；same phase Constants；y component/bottom tag | `dtn_port_3d.py:1081-1125`；bottom mode projection；`dtn_surface_component`；是 |
| `incident_top_traction_rhs`；incident traction times phase on `ds(z_max)` | linear rank 1；test space N1curl p6 | same resolved qdegree=`25`；wavevector, polarization, amplitude, normal and phase | `dtn_port_3d.py:1526-1540`、physical `build_physical_rhs`；MPC RHS；`physical_incident_rhs`；是 |
| `p6_physical_volume_action`；total-field Maxwell bilinear then `ufl.action` | action rank 1 from rank-2 bilinear；N1curl p6 | compiler default；tagged air/substrate/grating curl/mass material coefficients；probe says `use_pml=false`, `divergence_penalty=0.0` | `common_3d_forms.py:23-89`、physical `:77-87`；`FullspacePhysicalAction.apply` volume part；`physical_volume_action`；是 |

四个 DtN form 虽有相似 phase，但 facet tag 与 component 的 cache identity 不能在 J1 擅自合并；J2 必须逐一核对实际 module hash。`common_3d_forms.py` 返回的 zero linear `L` 不作为 total-field physical RHS 编译；物理 RHS 是上表的 incident traction form。

## B. J7 recovery 条件 form/Expression inventory

这些对象只在 residual/resource Gate 通过、solver stack release observation 完成后才应出现。每个 active row 的 cache/module identity 是 `not_measured_j1; sharing_not_proven_until_J2`。

| ID；来源 | rank / 类型；degree | quadrature / coefficient identity | consumer；precompile group；solve-critical |
|---|---|---|---|
| `recovery_airbox_H_expression`；`postprocess_3d.py:223-225` | `fem.Expression` of `curl(E_numerical)`；DG vector degree=`cfg.visualization_degree=6` | interpolation points；无 form quadrature；recovered E、physical scaling、k0、mu_r | `save_airbox_3d_fields` 的 H export；`recovery_field_expression`；否 |
| `recovery_component_l2`；`postprocess_3d.py:_field_component_l2_metrics` | 3 个 rank-0 cell forms；输入 field 是 H(curl) N1curl p6 的 `E_numerical`，不是 DG H | compiler default；E components 与 air/substrate/grating tags；三个 component form 是否共享待 J2 | `save_airbox_3d_fields` diagnostics；`recovery_cell_integrals`；否 |
| `recovery_rta_region_volume`；`rta_3d.py:_region_volume` | rank-0 `1*dx(tag)`；每个 nonempty region 一次 | compiler default；unit integrand + cell tag | `compute_volume_absorption_3d` region metadata；`recovery_rta`；否 |
| `recovery_rta_absorbed_power`；`rta_3d.py:_region_absorbed_power` | rank-0 `0.5*k0*Im(epsilon_r)*real(inner(E_total,E_total))*dx(tag)`；每个 nonempty region 一次 | compiler default；E, epsilon/material tag, k0 | `compute_volume_absorption_3d` 的 `A_volume`/energy closure；`recovery_rta`；否 |
| `recovery_diffraction_H_expression`；`diffraction_3d.py:_h_from_curl_function` | `fem.Expression` of `curl(E_total)/(i*k0*mu_r)`；DG degree=`max(6,1)=6` | interpolation points；无 form quadrature；E_total、k0、mu_r | top/bottom E/H sampling；`recovery_diffraction_expression`；否 |

## exact profile 下不活动的 recovery 对象

`diffraction_compute_modal_diagnostic=false` 是 probe 实测值，因此 `_calibrated_amplitudes` 的逐 modal key/side H Expression 不计入 exact-profile recovery JIT inventory。它仍需在启用该配置的其他 profile 中按实际 key、side 和 cache identity 单独测量，不能在本轮合并或声称共享。

## 明确不是 UFL JIT 的动作

| 路径 | 动作 | 分类 |
|---|---|---|
| `postprocess_3d.py:187-221,236-239` | `Function.interpolate(Function or Python lambda)` | Python/DOLFINx interpolation；不是 UFL form JIT |
| `diffraction_3d.py:573-583` | mode Function callable interpolation | 普通 Function interpolation；不是 UFL `fem.Expression` |
| `postprocess_3d.py:245-339`、`rta_3d.py:201-207`、diffraction writers | VTX/PyVista/JSON/file I/O | 不产生 UFL compiler object |
| `fullspace_dtn_action.py:219-517` | carrier、modal allreduce、PETSc Python shell | owner-local numeric/action machinery；不新增 UFL form |

## J2 必须闭合的最小事实

1. 对每一行记录实际 form/Expression signature、packed coefficient/constants identity、cache module identity 以及 `.c/.o/.so` path/hash/lifecycle；相似 top/bottom/component 只有在实际 hash 相同后才能合并。
2. 记录每个 compiler child 的 PID/PPID/cmdline、stage、RSS/PSS（可读时）、swap、exit code 和 raw sample；不能只记录最终 `.so`。
3. recovery 的 JIT 对象不得在 solver stack release observation 之前创建；field E/H、R/T/A、`A_volume` 和 diffraction outputs 的完整 authority 仍受 P0 checker 的 independent physics boundary 约束，本 inventory 不把 Task037c scalar packet 当作缺失 arrays 的替代品。
