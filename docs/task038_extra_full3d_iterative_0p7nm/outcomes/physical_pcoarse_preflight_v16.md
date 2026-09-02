# V16 Q0：same-mesh physical p-coarse 数学与容量预审

## 结论

本文件是代码实现前的设计资格化，不是 Q1 数值结果。固定候选为
`same_mesh_physical_pcoarse_v1`。在声明的同时 live-set 上界内，Q0 结论为
`Q0_PASS_ELIGIBLE_FOR_Q1`，因此 `eligible_for_Q1=true`；Q1 action identity、small
solve、checkpoint correction 和任何 physical solve 仍为 `not_run`。

所有字节均为预测或已标明的历史实测锚点，不把预测写成 measured PASS。

## 冻结身份与旧证据

| 项目 | 冻结值 |
|---|---|
| Review/current commit | V16 / `c61f2f579794ac0b20bf5f99122ae83c1fc82621` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| input file SHA256 | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| normalized checkpoint input identity | `754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f` |
| physical model SHA256 | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode manifest SHA256 | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |
| checkpoint manifest / solution SHA256 | `7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139` / `00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b` |
| checkpoint | iteration `1000`, residual `0.4837947981092168`, MPI1, `173802` rows, complex128 |

当前 Git 起点为 tracked worktree clean；本次 Q0 只产生下方两份 untracked 输出，除此之外没有
tracked 或 untracked 任务改动。

V13 C1 的正定 pMG 结果仍只是辅助问题；V14 J5 仍是
`CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED`，其
`1,450,262,528 B` 只是 pass-to-controlled-stop 实测；V15 F1/F2 通过、固定 rank32
Floquet correction 因 span Gate 关闭。旧 root、checkpoint、negative 和 controlled-stop
证据不覆盖、不重分类。

用户明确授权的边界仍有效：真实 checkpoint/数值测量前、且唯一定位的
path/cache/marker/import/provenance bug，可保留旧证据并在审查、窄修和新 SHA/root
后唯一重试；identity、numerical/span、2 GB、swap 或 nonfinite 等真实 Gate 失败不得重跑。

## 唯一实现图与公式

现有 p6 physical fine operator 是 `A6`：

\[
A_6=K_{curl,6}-k_0^2M_{\epsilon,6}+T_{DtN,6}.
\]

Q1/Q2 中新增的 p3 operator 必须是同一 mesh、material tags、incidence、total-field
formulation、Floquet phase 和 ordered mode inventory 下的：

\[
A_3=K_{curl,3}-k_0^2M_{\epsilon,3}+T_{DtN,3},\qquad
A_3v\approx P_{63}^{H}A_6P_{63}v.
\]

其中 `P63` 是 p3 primal 到 p6 primal 的已有 owner transfer，`P63^H` 是 p6
dual residual 到 p3 dual residual 的 adjoint transfer。p3 action 必须复用
`_build_physical_volume_terms` 的 curl-curl 与 complex-material-mass 两项、
`FullspaceSplitVolumeAction` 的两 component sum，以及 `FullspaceDtnCarrier` 的
owner-local streaming Fourier-DtN；不组装 global p3/p6 physical AIJ、dense DtN 或
physical factor。

固定 outer/inner 流程为：

```text
S6(r6) → r6-A6 S6(r6) → r3=P63^H r6
→ solve approximately A3 e3=r3 with existing p3→p1 positive V-cycle
→ u6=S6(r6)+P63 e3 → r6-A6 u6 → S6(post residual)
```

outer 使用 right FGMRES/restart20；inner 也使用 right FGMRES/restart20。I20 只保留
一个 restart20 workspace；条件 I100 复用同一 workspace 分五个 restart20 cycle，
绝不保留 100 个向量。p6 positive Chebyshev/Jacobi pre/post、物理 RHS、材料、DtN
和后处理均不改变。

## ownership、生命周期与 staging

| 对象 | owner/复用 | 释放顺序 |
|---|---|---|
| fresh root、jit cache、7 个 child | parent 独占创建；child 只创建自己的 raw/marker | 每个 child 及 compiler descendants 退出后才启动下一个 |
| p6 setup、p3/p1 positive cycle、P63/P63^H | setup owner；physical p-cycle 只借用 setup-owned smoother、P63/P63^H 与 lower p3→p1 cycle | 先由 p-cycle owner 销毁 outer/inner KSP 与 dedicated work，再由 setup owner 销毁共享 cycle、transfer、p1 factor 与 setup |
| p6 physical action / p3 physical action / DtN carrier | physical bundle owner；carrier 只 owner-local、streaming | p6/p3 carrier 构造完成后释放 surface assembler 临时对象；solver stack 释放后由 bundle owner 销毁 action/carrier，不保留 global matrix |
| outer FGMRES | worker/KSP owner；restart20 basis | 先保存必要 scalar/recovery packet，再销毁 outer KSP 与全部 basis |
| checkpoint-1000 | 外部只读 authority；reader 只恢复 solution shard | 读入并重算 residual 后释放 reader 临时副本；不得复制或改写旧 shard |
| recovery | 仅 Q5 数值/资源通过后创建 | 确认 RSS 下降后才 recover E/H、R/T/A、A_volume 与 authority channels |

Q0 只冻结实现图，不创建上述对象。physical p-cycle 自己只拥有 dedicated work 与 inner
KSP，不侵入式复用 setup-owned upper-cycle vectors。Q1 的 production code 应进入现有通用
`src/solvers/`；benchmark 只复用现有 staged parent/watchdog，并使用一个薄的
worker/checker。checker 只能读 raw record/NPZ、用 stdlib/NumPy 独立重算，不能导入
runner、PETSc、MPI 或 DOLFINx。

每个 fresh parent 的 cold group 顺序固定为：

```text
positive-p6
→ positive-p3
→ positive-p1
→ dtn-surface
→ incident-rhs
→ physical-volume-curl
→ physical-volume-mass
```

Q1 若新增 p3 physical group，必须在该 fresh root 下重新编译并绑定新 cache，不能复用旧
J3/J4/J5 cache。

## 同时 live-set 容量账本

以下是同时存活的保守上界，不是累计分配。`N3/N6` 来自已冻结的 same-mesh
hierarchy；complex128 payload 为 `16*N`。p3 split action 的 retained 数字直接采用
现有 `FullspaceMpcFormAction` audit 的对象公式：`N3=23073`、owned
slave/constraint nnz=`2337`、每个 slave 一个 master，因此每个 component 为
`2*N3*16 + 2337*(16+16+4+4+4+4+16) = 887904 B`，两个 component 为
`1775808 B`。每次 apply 的 packed temporary 另按已实测 p6 单 component
`3564288 B` 作保守上界；curl 与 mass 顺序 apply，只计一次，不能把两个 component
同时相加。p3 streaming carrier 的公式把 mode inventory 已有的 `80` 个 ordered
modes 计一次；公式中的 `2` 是每个 mode 的 coupling/projection 两个 functionals，
不是 two sides，另加 slave-row int64。

| 项目 | 公式/来源 | 字节 | 口径 |
|---|---:|---:|---|
| V14 J5 central baseline | measured pass-to-controlled-stop anchor | 1,450,262,528 | 已包含 p6 bundle、positive hierarchy 与普通 restart20 reserve；不再重复相加 |
| V14 J4 hard calibration | measured complete P0R cold peak | 1,557,270,528 | hard 基线；同样不重复相加 |
| p6 rows / one vector | `N6=173802; 16*N6` | 2,780,832 | payload，不是 `.npy` 文件大小 |
| p3 rows / one vector | `N3=23073; 16*N3` | 369,168 | payload |
| p3 split action retained | `2*N3*16 + 2337*(16+16+4+4+4+4+16)` 每 component；`2 components` | 1,775,808 | FullspaceMpcFormAction audit公式；两 component retained |
| p3 split action packed temporary | `3564288` p6 single-component measured bound；p3不超过该 bound | 3,564,288 | curl/mass 顺序 apply，只计一次 simultaneous temporary |
| p3 streaming DtN carrier upper | `2*80*(16+8)*N3 + 2337*8` | 88,619,016 | `2` 是 coupling/projection functionals；不存 dense DtN |
| inner FGMRES restart20 | `45*V3` | 16,612,560 | 保守 45 个 p3 vector；I100 复用同一 restart20，不乘100 |
| outer FGMRES flexible delta | `21*V6` | 58,397,472 | 仅新增 flexible set；普通 restart20 已在基线 |
| dedicated physical p-cycle work | `8*V6 + 2*V3` | 22,984,992 | dedicated slots；借用 setup-owned smoother/P63/lower cycle，不重复计 baseline |
| checkpoint/recovery reserve | `2*V6` | 5,561,664 | 不复制历史 shard；只留必要 live vectors |
| **新增 live-set subtotal** | 上述七项新增对象 | **197,515,800** | simultaneous upper bound |
| central allocator/JIT reserve | fixed `64 MiB` | 67,108,864 | 预测余量，不是实测 |
| hard allocator/JIT reserve | fixed `128 MiB` | 134,217,728 | 保守预测余量，不是实测 |

因此：

```text
central = 1,450,262,528 + 197,515,800 + 67,108,864
        = 1,714,887,192 B < 1,750,000,000 B

hard-upper = 1,557,270,528 + 197,515,800 + 134,217,728
           = 1,889,004,056 B < 1,900,000,000 B
hard margin = 10,995,944 B
major_unknown = []
```

这个结论依赖的硬约束是：DtN 仍为 owner-local streaming、p3 action 不产生全局
AIJ/dense buffer、inner I100 复用 restart20、没有 persistent Z/AZ、physical p-cycle
只使用 dedicated work、以及 recovery
在 release-before-recovery 后才开始。Q1 必须实测这些对象和 process-tree RSS；本节
预测不能替代 Q1/Q2/Q5 resource Gate。由于 hard margin 仅 `10,995,944 B`，Q1
实测一旦超过 hard-upper 就关闭候选，不能用预测放宽。

## Q0 Gate 与边界

| Gate | 结果 |
|---|---|
| 唯一 `A3`、`P63/P63^H`、inner/outer apply 公式 | PASS（已冻结） |
| p3 action ownership/release 图 | PASS（由现有 split action、DtN carrier、MPC transfer 复用约束冻结） |
| central prediction | PASS，`1,714,887,192 B` |
| hard-upper prediction | PASS，`1,889,004,056 B`，margin `10,995,944 B` |
| major unknown | PASS，`[]`；p3 数字是显式 row/value 公式预测，不是 measured |
| Q1 eligibility | `eligible_for_Q1=true` |
| Q1/Q2/Q3/Q4/Q5/Q6、W0-W4、official physics | `not_run` |

下一阶段只能进入 Q1：先做 p3/p6 physical action identity 与 small MPI1/MPI2
oracle，固定 six probes、P/P^H、MPI canonical、phase、finite、slave-zero 和
resource Gate。Q0 不授权 checkpoint restore、长 Krylov、physical recovery、official
physics 或 0.7 nm PDE。
