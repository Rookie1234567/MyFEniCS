# Task033 Phase C：p3/h5 目标 Hybrid 与 full3D Gate

## Phase C1 后续结论（覆盖本文件下方的历史 C0 停止状态）

review v4 批准 assembly-only；随后用户明确允许受控 p3 full solve，并允许
swap 作为可用后备。实测并未使用 swap：

```text
p3/h5 full3D direct = full3d_reference_pass
memory authority = 7.781337738 GiB
cgroup swap peak = 0
true residual = 5.441900114e-12
R/T/A = 0.001090107012 / 0.600622478293 / 0.398287414695
```

在 clean source `95921ab76e39eb1a7c5b3321b93d36939afb4075` 上只重跑
Schur-minimal M160，并绑定上述 direct NPZ；没有重复 M80、M120 或 augmented：

| 指标 | Hybrid | full3D | Hybrid − full3D |
|---|---:|---:|---:|
| R | 0.001090095685 | 0.001090107012 | `-1.133e-8` |
| T | 0.600622368221 | 0.600622478293 | `-1.101e-7` |
| A(balance) | 0.398287536094 | 0.398287414695 | `+1.214e-7` |
| A(volume) | 0.398287536096 | 0.398287414695 | `+1.214e-7` |

Hybrid true residual 为 `2.343e-12`，能量闭合误差为 `1.885e-12`，内存权威值
2.618 GiB、零 swap。10/30/60/90/110 nm 五个截面全部完成同源比较；最大
E/H 相对 L2 为 `1.100e-5 / 1.098e-4`。16 项 Gate 全过。因此 p3/h5
same-degree Hybrid/full3D 的数值闭合已完成，状态从
`HYBRID_COMPONENT_ACCEPTED_FULL3D_REFERENCE_OPEN` 更新为
`same_degree_p3_h5_hybrid_full3d_numerical_closure_pass`；Review V6 已接受。

详细轻量证据见 `records/stage3_p3_h5/full3d_reference.json` 与
`records/stage3_p3_h5/full3d_closure_summary.json`。下文保留为此前 C0/Phase C
执行历史，不能再作为当前停止状态。

## 1. 结论先行

Phase C 的准确分类是：

```text
Hybrid M80/M120/M160 component = pass
augmented vs Schur-minimal M160 = pass
p3/h5 full3D direct = not_run_by_memory_gate
same-degree full3D selected-plane E/H = unavailable
whole Phase C = not passed
```

这不是完整 Phase C 成功，也不是 Hybrid 数值失败。评审批准的五个候选都先独立做
C0；full3D 因第二内存中心和保守上界超限而没有强跑，其余四个 Hybrid 候选各自
满足 Gate，因而按顺序完成。p3/h3、p4 目标光栅、自适应和 buffer 没有启动。

## 2. 身份与执行边界

| 字段 | 值 |
|---|---|
| review authority | `review_report_v3.md` |
| 数值源码 | `b636444b693a932988b6d5d69f7e44e6a8cddb38` |
| image | `myfenics-stage4:task28` |
| image digest | `sha256:08c61b2...dd76d` |
| degree / h | p3 / 5 nm |
| wavelength | 13.5 nm |
| incidence | 10° grazing，S polarization |
| interfaces | 10 / 110 nm |
| MPI | 4 |
| source cleanliness | 运行前后完整 `git status --short --untracked-files=normal` 为空 |
| concurrency | 每次只有一个重型 case |
| swap | C0 与四个 measured run 均为 0 |
| ordinary default | unchanged |

Windows bind mount 的 CRLF 视图最初让容器内 Git 把工作树误判为 dirty；第一次 C0
因此在求解前 fail closed。随后仅用进程级 `core.autocrlf=true` 统一 Git 视图，
没有放宽 source Gate，也没有修改跟踪文件。正式 C0 与全部运行仍绑定同一 clean SHA。

Case090 证据只作为高阶 pure-3D Floquet 核心前置条件复用。审核范围明确为
`case090_pure3d_floquet_core`；Phase B 修改的
`src/coupling/modal_trace_projection.py` 被记录为与该核心组件不相交，目标 Hybrid
则在当前 SHA 上重新实测。因此这里既没有重跑 144 个 Case090 PDE，也没有把旧
Case090 当作当前 p3/h5 full3D reference。

## 3. C0 候选级内存预测

现场有效上限为 `min(13 GiB container, 12.8433 GiB host available)`：

| Gate | 现场限值 |
|---|---:|
| two-center | 10.5498 GiB |
| conservative upper | 11.7424 GiB |
| warning | 10.5498 GiB |
| controlled termination | 11.9259 GiB |

### 3.1 full3D direct

| 方法 | 中心 / 上界 |
|---|---:|
| p/h effective-resolution RSS 幂律 | 6.4446 GiB |
| p2 target NNZ → Case090 p3/p2 NNZ 比 → fill → factor payload → RSS | 15.0313 GiB |
| conservative upper | 18.0375 GiB |

第二条链预测 `130,504` 行、`34,085,833` assembled NNZ、
`513,746,598` factor NNZ 和 `11.4913 GiB` factor payload。它比第一中心悲观，
但不能因第一中心较低就丢弃。第二中心超过 `10.5498 GiB`，上界也超过
`11.7424 GiB`，所以结果是 `not_run_by_memory_gate`。

历史替代路径不足以构成安全例外：Task029 OOC 在 h5 只降低 13.744% 且依赖磁盘，
BLR 没通过残差/RTA，MPI2 的 h3 降幅也只有 15.119%。这些结果没有资格把当前
p3 direct 的 C0 veto 改成 pass。若仍使用同一缩放规则，单从预测上界反推至少需要
约 `19.73 GiB` 的有效上限；这已经超出本轮 14 GiB hard budget，必须重新评审，
或先取得经过资格化的低内存 full3D 路径。

### 3.2 Hybrid candidates

| candidate | 两中心最大值 | conservative upper | C0 |
|---|---:|---:|---|
| Schur-minimal M80 | 5.2269 GiB | 6.0110 GiB | launch eligible |
| Schur-minimal M120 | 5.2269 GiB | 6.0110 GiB | launch eligible |
| Schur-minimal M160 | 5.2269 GiB | 6.0110 GiB | launch eligible |
| augmented vs minimal M160 | 8.4356 GiB | 10.1228 GiB | launch eligible |

M80/M120 没有在缺少实测前宣称低于 M160 的折扣，而是共同继承 p3/h5/M160 的保守
上界。full3D veto 不会污染这些候选的独立准入，也不会被它们的安全性反向覆盖。

## 4. Schur-minimal M 漏斗

| M / direction | R | T | A(balance) | true residual | memory authority | max-rank total |
|---:|---:|---:|---:|---:|---:|---:|
| 80 | 0.001090095685818 | 0.600622368233025 | 0.398287536081157 | `1.905e-12` | 2.278 GiB | 63.66 s |
| 120 | 0.001090095685267 | 0.600622368221082 | 0.398287536093651 | `2.631e-12` | 2.492 GiB | 85.10 s |
| 160 | 0.001090095685264 | 0.600622368221012 | 0.398287536093723 | `2.277e-12` | 2.641 GiB | 106.98 s |

三个 watchdog 都是 `measured_shard_pass`，均未触发 warning、memory termination
或 timeout。内存权威取 simultaneous worker RSS 与 cgroup current 的最大值；三次
权威均来自 worker RSS，swap 和 pswpin/pswpout 增量均为 0。

| pair | max abs R/T/A delta | max significant order power rel. delta | max significant complex amplitude rel. delta | 结果 |
|---|---:|---:|---:|---|
| M80 → M120 | `1.249e-11` | `5.563e-9` | `4.914e-9` | mandatory + strong pass |
| M120 → M160 | `7.216e-14` | `3.676e-10` | `1.925e-10` | mandatory + strong pass |

漏斗选择 M160。M120→M160 已通过，因此评审允许的条件性 M240 没有必要，继续运行
只会增加计算量而不补充当前证据缺口。

## 5. M160 物理与接口精度

| 指标 | 值 / Gate |
|---|---:|
| `A_volume` | 0.398287536095597 |
| `R+T+A_volume-1` | `1.874e-12` |
| bottom/top E tangential relative L2 | `1.913e-8 / 2.061e-8` |
| bottom/top H tangential relative L2 | `6.914e-4 / 6.175e-4` |
| full true residual | `2.277e-12 <= 1e-9` |
| interface-E projection bottom/top/combined relative residual | `5.379e-13 / 7.175e-13 / 6.455e-13` |
| FE-modal traction equilibrium bottom/top relative residual | `3.285e-12 / 1.367e-12` |
| max right/left QEP polynomial relative residual | `1.870e-14 / 7.900e-15` |
| max biorthogonality identity error | `2.001e-7` |
| forward finite / numerical-infinity / retained modes | `320 / 0 / 160` |
| backward finite / numerical-infinity / retained modes | `320 / 0 / 160` |
| QEP shape | full `1723×1723`，reduced `1620×1620` |
| local bottom/top rows | `21,847 / 21,847` |
| local bottom/top assembled NNZ | `5,156,503 / 5,156,503` |
| dense interface square | false |

上表的代数接口和 QEP 数值直接提取自 canonical M160 原始记录
`hybrid/m160/attempt/solver_record.json`，其 SHA-256 为
`4bde1f8d3c1f56d7b1cbe81d4d1141632965b97474dcb334c301cfe4b8709c64`。
正反向的 numerical-infinity 过滤数均为 0，`first_rejected` 因而为 `null`；
这表示没有候选因数值无穷特征值被丢弃，而不是该检查缺失。actual E continuity、
actual H/traction、QEP left/right residual、biorthogonality、stable propagation、
external R/T/A、volume closure 和 selected middle-plane reconstruction 的已声明
Gate 全部通过。`selected_plane_full3d_comparison` 仍为
`None`，因为同阶 full3D 没有被 C0 允许生成；不能把“选面已重建”写成“已与
full3D 对照”。

## 6. augmented 与 Schur-minimal 锚点

| 指标 | augmented vs minimal M160 |
|---|---:|
| modal coefficients relative error | `2.801e-13` |
| bottom local solution relative error | `1.680e-13` |
| top local solution relative error | `2.279e-13` |
| interface-E projection residual delta | `2.123e-13` |
| max absolute R/T/A delta | `3.131e-14` |
| memory authority | 4.148 GiB |
| max-rank total | 114.05 s |
| dense interface square / full gather | false / false |

modal coefficients、local fields、full residual、R/T/A、单因子多 RHS 生命周期与
no-dense Gate 全部通过。该锚点证明两条 Hybrid 代数路径在当前离散上等价，不替代
Hybrid 与 full3D 的离散等价证明。

## 7. 证据与后续

tracked 轻量摘要位于
`benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage3_p3_h5/phaseC_summary.json`。
原始 watchdog、timeline、逐阶结果和 ignored aggregate 位于
`benchmarks/artifacts/cases/091/task033_phaseC_b636444/`；轻量摘要保存七个关键
文件的 SHA-256。

以下是当时 C0 停止点的历史理由，不是 Review V6 当前待办：

1. 不补跑 M240，因为截断已收敛；
2. 不跑 p3/h3、p4 或自适应，因为未获评审授权；
3. 不强跑 p3/h5 full3D，因为 C0 明确失败；
4. 当时关闭 whole Phase C 所需的 full3D reference、selected-plane E/H、
   逐阶与 R/T/A 对照，后来已按本文件顶部 Phase C1 记录完成。
