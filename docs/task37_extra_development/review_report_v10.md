# Review V10：canonical congruence bounded audit

本文件是 H2B-P1 数值停止后的新监督合同。它定义一条全新的、有限的 C 路线，不是旧 P1 campaign 的重跑，也不放宽任何既有 Gate。

## 合同身份

| 字段 | 固定值 |
|---|---|
| `working_branch` | `codex/20260806-task37-iterative-extra-development` |
| `reviewed_handoff` | `response_v9.md` |
| reviewed `HEAD` | `66074140c129bb4d7b64e5a654f4833e6b6a08f4` |
| upstream | `codex/20260806-task37-iterative-extra-development` |

## 0. 读者先看：这条路线要解决什么

P1 为 84 个局部 neighborhood 逐一生成 row-complete patch。即使两个 patch 只是“同一个算子换了行号或 Floquet 相位”，逐字节 SHA 也会把它们当成不同矩阵并重复 factor。C 路线先证明这种“换坐标”关系确实存在，再只 factor 每个代表 patch。

这里的证明不是看结果猜一个变换，也不是把近似相似的矩阵合并。它只接受由有限元行拓扑、Basix orientation、MPC/Floquet 系数和材料/operator identity 明确产生的 permutation 加单位模相位；无法严格构造就 fail closed。

## 1. 已冻结的历史边界

| 阶段/结论 | 冻结状态 | 解释 |
|---|---|---|
| G2 LOR-HX | `G2_FAIL` | 历史 LOR-HX contraction/memory 负结果保留，不重新打开 |
| G3 additive LOR-HX | `prohibited` | 不得在 G2_FAIL 后重跑 |
| old G4 sweep | `prohibited` | 不得在失败 LOR-HX 上做 shift/cycle/smoother 扫描 |
| H1R3.0R / H1R3.1 / H1R3.2 | `PASS` | 只保留既有 full-space action/identity/scaling 证据 |
| V8 fixed-unit H2B | `FAIL_NUMERIC / NOT_QUALIFIED` | 旧 symmetric fixed-unit 结果不是 PDE 通过 |
| V9 H2B-S0 | `PASS` evidence、`s0_direction_gate_pass=false` | 三组合方向 Gate 均未通过，路线进入 P |
| V9 H2B-P0 | `PASS / QUALIFIED` | 仅代表性 central row-complete patch 通过 |
| V9 H2B-P1 | `CONTROLLED_STOP_UNIQUE_FACTOR_LIMIT / NOT_QUALIFIED` | neighborhood 32 触发第 33 个 unique numeric factor |
| V9 P1 预算 | `1 campaign + 1 execution-fix` 已耗尽 | 数值/容量负结果不得以 execution-fix 名义重跑 |
| H2B-K | `locked_by_P1` | 只有 C2 完成后才可返回 V9 H2B-K |
| H2D / full-space matrix-free DtN | `locked_by_H2B-K` | C2/K 之前不得启动 |
| H4 time-harmonic PDE | `locked_by_H2D` | H2D 之前不得启动 |
| official field/RTA | `locked_by_H4 full solve + true residual/physics Gate` | 未收敛前不得输出 official R/T/A |

旧 P1 raw、v1/v2/v3 compact、P0/S0/R2 evidence 必须永久保留。C 不得覆盖它们，也不得把 C 的任何中间结果写入旧文件。

## 2. 授权与最终目标

用户于 2026-08-12 再次明确授权：针对具体执行问题持续定位、窄修并在 Gate 通过后推进直至目标。该授权不覆盖数值负结果，不放宽数值、物理、RSS、swap 或 provenance Gate；不得把数值/容量负结果包装成 execution-fix 后重复运行。

最终目标仍是：

| 目标 | 必须实测 |
|---|---|
| MPI | `MPI1` |
| full PDE process-tree RSS | 严格 `<2,000,000,000 B` |
| swap | `0` |
| 数值可信度 | full true residual、direct-authority physics comparison、field/RTA Gate 全部闭合 |

C2 之前不得启动 H2B-K、H2D、H4、PDE、field 或 RTA。C1/C2 的结果必须区分 `measured`、`derived`、`predicted`、`not_run` 和 `controlled_stop`。

## 3. C 路线总览

唯一新路线名称为 **C：canonical congruence**：

```text
C0 metadata carrier/tests
    -> C1 84-neighborhood patch-only orbit audit（不得 factor）
    -> C2 representative-factor/transformed-solve（仅 C1 全 PASS）
    -> V9 H2B-K（仅 C2 全 PASS）
    -> V9 H2D
    -> V9 H4/PDE/field/RTA
```

C0 是实现和纯测试阶段，不是 formal campaign。C1 只做 metadata/orbit/patch/action audit；C2 才允许 factor representative。C1 或 C2 的 numeric/congruence negative 不得重跑；只有实际代码、JIT 或 telemetry execution defect 才能使用各自批准的一个 execution-fix rerun。

## 4. C0：metadata carrier 与最小测试

### 4.1 允许复用的输入

复用现有：

- `discover_h2b_p1_neighborhoods` 和 `stream_h2b_p1_neighborhood`；
- 已冻结并已资格化的 H2A-R2 expansion/factor authority；
- `H2AR2CellExpansion` 的 CSR offsets、column indices、complex coefficients；
- 真实 `PhaseIndependentConstraintBlock`、Floquet phase 和 MPC source/masters；
- 现有 Basix/DOLFINx orientation helper；orientation 只能施加一次。

不得把 absolute global row、owner、cell ordinal 或 coordinate 写入 canonical key。global row 只可在当次 temporary gather/scatter 中使用。

### 4.2 canonical row token

每个 patch row 必须生成 metadata-only token，至少包括：

1. central cell slot；
2. 每个 touching cell 到 central patch 的 local incidence；
3. class key、constraint pattern、expansion pattern、numeric class authority；
4. orientation、material、operator identity；
5. 该 row 的 CSR expansion columns/coefficients；
6. 真实 Floquet/MPC phase 与 entity-transform provenance。

token 不得读取 patch matrix 数值来拟合，不得 nearest matching、tolerance clustering、结果驱动枚举，不得引入通用图同构/registry/framework。若 token 不能形成唯一、确定性的 row correspondence，直接 fail closed。

### 4.3 unitary monomial T

对 neighborhood `j` 与代表 `rep`，只允许生成：

```math
T_j = P_j D_j,
```

其中 `P_j` 是由 canonical row token 得到的 882×882 permutation，`D_j` 是由 orientation sign、Floquet/MPC phase 或严格验证的 coefficient ratio 得到的对角 unit-modulus phase。应用约定固定为：

```math
B_j = T_j^H B_{mathrm{rep}} T_j.
```

对于 `B_j x_j=b_j`，代表 factor 的 solve 只能按下式使用：

```math
x_j = T_j^H\,\operatorname{solve}(B_{\mathrm{rep}}, T_j b_j).
```

`P_j` 必须是 bijection；每个 phase 必须 finite；必须满足：

```math
\max_i\bigl||d_i|-1\bigr| \le 1\mathrm{e}{-14},
```

```math
\lVert T_j^H T_j-I\rVert \le 1\mathrm{e}{-14}.
```

identity/source metadata 与 T SHA 必须 deterministic。若真实 Basix orientation 需要非-monomial 混合，C 路线直接返回 `MONOMIAL_TRANSFORM_NOT_PROVEN`；不得偷偷扩大成 dense learned transform。

### 4.4 C0 focused contract

必须覆盖：

- row renumbering 不改变 token/key/T SHA；
- global row、cell enumeration 改变但 metadata 等价时得到 byte-identical T；
- MPC phase/orientation 只施加一次；
- 非一一映射、非 unit-modulus phase、不同 material/operator/incidence 均 fail closed；
- 无 patch matrix、factor、global matrix、Schur、slab 或 per-cell tensor retained；
- ordinary/default path 完全不变。

## 5. C1：84-neighborhood patch-only orbit audit

### 5.1 前置顺序

1. fresh process 验证 R0/R1/R2/P0 authority、source/checker identity、B0 form/cache hit 和 cache unchanged；
2. fresh discovery 必须闭合 `252 cells / 24 classes / 84 neighborhoods / 173802 rows / 882 nloc / 9210 constraints`；
3. 先仅由 C0 metadata 形成 candidate orbit；
4. 若 candidate representative count `>32`，立即写结构化 controlled stop，不构造任何 factor；
5. candidate count `<=32` 后才逐 orbit/member 流式生成 patch 做完整 audit。

### 5.2 patch 与 action audit

按 canonical orbit/ID 顺序生成全部 84 个 882×882 patch。每个 member 至少重复生成一次；同一 member 两次 matrix SHA 必须逐位相同。每次最多保留：

```text
representative patch + current patch + comparison workspace = 3 dense patches
```

禁止保留 84 个矩阵；C1 不调用 `factorize_h2b_p0_patch`、不调用 `H2BP1FactorLedger.accept`、不写 factor store。

完整矩阵 congruence Gate：

```math
\frac{\lVert B_j-T_j^H B_{\mathrm{rep}}T_j\rVert_F}
     {\lVert B_j\rVert_F}
\le 1\mathrm{e}{-11}.
```

所有矩阵、T、重复 SHA、Hermitian/finite 结果必须 deterministic。固定的两个 complex Rademacher vectors（同时作为 C1 probes 与 C2 RHS）使用 `numpy.random.default_rng(20260812)`，每个实部/虚部取 `±1/sqrt(2)`，不得扫描或按结果改变 seed。

对每个 neighborhood，使用这两个固定 probe 分别检查：

1. patch action；
2. embed 到 full-space 后调用 exact B0，再 restrict 回 patch。

两者相对 closure 均必须 `<=1e-11`。probe closure 是 operator binding；完整 882×882 congruence residual 仍是 orbit Gate，不能用少量 probe 替代矩阵 Gate。

若 C1 任一 member 的 T、congruence、action closure、determinism、authority 或资源 Gate 失败，状态必须是结构化 C1 negative/controlled stop，不能进入 C2。

### 5.3 C1 资源与预算

| 项目 | 固定 Gate |
|---|---:|
| retained orbit metadata | `<=16,777,216 B` |
| predicted live set | `<1,450,000,000 B` |
| completed process-tree peak | `<1,500,000,000 B` |
| watchdog controlled-stop threshold | `1,480,000,000 B` |
| swap | `0` |
| timeout | `1800 s` |
| MPI/config | `MPI1`, `p6/h10` |

C1 提议预算为 `1 formal + 1 execution-fix`。execution-fix 仅适用于代码/JIT/telemetry defect；congruence、factor-count 或其他 numeric negative 不得重跑。

## 6. C2：representative factor 与 transformed solve

C2 只有在 C1 全部 84 个 member、T、congruence、action、determinism、resource 和 authority Gate 全 PASS 后才能启动。

### 6.1 数值路径

- 只 factor 每个 orbit representative；member 不单独 factor；
- representative factor count `<=32`；
- 每个 neighborhood 按固定顺序用 C1 同一 `default_rng(20260812)` 和同一 `±1/sqrt(2)` 生成规则得到的两个固定 complex RHS 验证 transformed solve，不另选 seed 或生成规则；
- solve 采用第 4.3 节的 `T_j` 约定；
- representative factorization residual `<=1e-10`；
- transformed solve residual `<=1e-10`；
- 所有 values/pivots/solve/action/determinism 字段 finite；
- exact SHA 只用于证据和重复性，不进行 tolerance-based factor merging。

### 6.2 retained 与在线 Gate

| 项目 | 固定 Gate |
|---|---:|
| representative factor count | `<=32` |
| factor + metadata | `<=500,000,000 B` |
| predicted live set | `<1,700,000,000 B` |
| completed process-tree peak | `<1,700,000,000 B` |
| swap | `0` |
| forbidden materialization | no per-cell factor/dense tensor/global matrix/global constraint matrix/Schur/slab factor |
| default | ordinary/default unchanged |

C2 提议预算为 `1 formal + 1 execution-fix`，数值负结果不得重跑。C2 全 PASS 才能返回 V9 H2B-K；K 的 normalized two-level FGMRES、75D coarse、true residual、RSS 和 swap Gate 全部保持 V9 原值，不在 C 中修改。C2 任一 factor、solve、payload 或 resource numeric Gate 失败，都关闭 block-factor lane并进入 `M0 review only`，不得停在可继续 factor 的状态。

### 6.3 C2 资源账本

当前已审计 P1 账本给出 Stage A `1,326,006,476 B`、Stage B `1,562,565,932 B`。最大 32 个 factor arrays 为：

```math
32\times 12,450,312 = 398,409,984\ \mathrm{B}.
```

C2 worker 必须把 T/compare workspace 单独计入，不得把已有 P1 预测直接冒充 C2 measured。orbit patch 最大 3 dense workspace 的规划上界为 `37,340,352 B`；由此得到的 `1,599,906,284 B` 只是 preflight planning upper bound，不能替代 watchdog 的实际 process-tree peak。

## 7. raw、compact、checker 与 evidence 命名

新证据只能使用：

```text
raw:     benchmarks/artifacts/task037_extra_development/h2b_canonical_orbit_<source7>_runN
C1:      benchmarks/cases/101_task37_extra_development/records/h2b_canonical_orbit_audit_v1.json
C2:      benchmarks/cases/101_task37_extra_development/records/h2b_canonical_orbit_factor_v1.json
outcome: docs/task37_extra_development/outcomes/h2b_canonical_congruence.md
summary: docs/task37_extra_development/response_v10.md
```

本轮只提交本合同 `review_report_v10.md`；不创建 outcome/response/record。

checker 必须从 raw summary、progress、timeline、manifest 和 `.npy` 文件独立重算：

- source 与 checker SHA 分开记录并分别验证 clean provenance；
- 84/252/24 mapping 与 digest；
- 每个 row token、P、D、T SHA、unitary Gate、congruence/action closure；
- repeated matrix/T SHA；
- representative factor count、factor quality、retained payload 和 live-set components；
- watchdog RSS/swap/termination/process cleanup；
- materialization identity 与 ordinary default；
- missing key、NaN、状态篡改或 raw artifact/hash 缺失必须 fail closed。

checker 不得重做 factorization来“补证据”，也不得给 missing field 默认值。旧 P1 evidence 永久保留，C1/C2 不覆盖它。

## 8. C0/C1/C2 失败后的 M0 边界

若 C0 或 C1 失败，full-space block-factor lane 维持关闭；若 C2 任一 factor、solve、payload 或 resource numeric Gate 失败，同样关闭该 lane。两种情况都只允许进入 `M0 matrix-free p4/p6 transfer feasibility` 的后续审阅。V10 第一执行边界只允许静态/轻量 M0 设计与 fixture，不得直接运行 coercive solve 或 PDE。

M0 只可复用：

- `fullspace_matrix_free_hcurl.py` 的 exact full-space action 边界；
- 现有 Basix p4/p6 reference transfer 的 cell-local interpolation metadata；
- `hcurl_rank_one_mpc_action.py` 的 MPC-aware action 约定。

M0 禁止：

- PETSc global transfer AIJ；
- `CondensedGalerkinCoarse`；
- LOR-HX/LOR-H1 hierarchy；
- global matrix、static condensation、trace slab、slab factor；
- B2/B4 local Krylov；
- parameter/overlap/level scan；
- 在没有新 review 前实现或运行 GMG/PDE。

仓库现有 `hcurl_multilevel.py` 的 NonmatchingTransfer 会生成 PETSc AIJ transfer，`CondensedGalerkinCoarse` 会做显式 Galerkin/condensed matrix products；它们只能作为历史接口参考，不能直接满足 M0 合同。G2 LOR-HX 已 `G2_FAIL`，不得 reopening。`static_modal_coarse_basis.py` 只有 research-only basis/action foundation，没有现成 qualified coarse PC。

## 9. 硬禁项

- 不得创建新分支、PR、merge、rebase、cherry-pick 或 force push；不得修改 master/default；
- 不得原样重跑旧 P1；
- 不得以 execution-fix 名义重跑 numeric/congruence/factor-count negative；
- 不得重开 LOR-HX；
- 不得 global matrix、static condensation、trace slab、B2/B4 local Krylov；
- 不得在 C2/H2B-K/H2D 完成前启动 PDE、field 或 RTA；
- 不得把未收敛 residual 的 field/RTA 写成 official result；
- 不得把 predicted memory 写成 measured peak；
- 不得把 C1 patch audit 写成 factor/PDE PASS。

## 10. 给执行方的简化指令

1. 先在当前 extra 分支做 C0 carrier 与 pure tests；只新增 C 路线文件，不改普通 default。
2. C0 focused tests/静态 Gate 通过后自动进入 C1，按新 raw 名称运行一次 patch-only orbit audit；先形成 metadata candidate orbit，`>32` 立即 controlled stop，不 factor。
3. 只有 C1 全 PASS 才可运行一次 C2 representative factor/transformed-solve；任何 numeric/congruence negative 立即停止，不重跑。
4. C2 全 PASS 才返回 V9 H2B-K；K/H2D/H4/PDE 继续使用原 Gate。
5. 所有 raw/compact/source/checker SHA 分开绑定；旧 P1 evidence 不覆盖、不改写。

```text
               C0 carrier/tests
                      |
              metadata candidate orbits
                      |
             reps > 32 ? ---- yes --> C1 controlled stop -> M0 review only
                no
                |
        C1 all 84 patch/action/congruence PASS ?
             |                         |
            no                         yes
            |                          |
     block-factor closed          C2 factor representatives
     -> M0 review only                    |
                                  C2 all Gates PASS ?
                                    |             |
                                   no             yes
                                   |              |
                              block-factor closed
                              -> M0 review only   return V9 H2B-K
```
