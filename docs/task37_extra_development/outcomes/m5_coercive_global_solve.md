# M5 coercive global FGMRES 第一屏：正式结果

## 结论先行

M5 第一屏在 clean source `a3c677f0777eb858ac8b3435fec4cff92f29d9f3` 上正式通过。它测试的是固定的 coercive full-space 算子和一个不带 coarse 的右预条件 FGMRES 屏幕，不是时谐 PDE，也不是 official physics 结果。

| 项目 | 结果 |
| --- | --- |
| 分类 | `M5 FIRST_SCREEN_PASS / COERCIVE_TARGET_MET_WITHOUT_COARSE` |
| source | `a3c677f0777eb858ac8b3435fec4cff92f29d9f3` |
| scope | MPI1、p6/h10、252 cells、173,802 rows、882 local rows、9,210 constraints |
| operator | `B0 = Kcurl + k0^2 M_abs_epsilon` |
| outer solver | right FGMRES，restart=20，max_it=100，unpreconditioned norm |
| watchdog | RC0，`status=pass`，elapsed `1185.6522394389904 s` |
| checker | RC0，`status=pass`，`pass=true`，26/26 checks true |
| 75D coarse | `not_needed / not_run` |

FGMRES 是允许每次预条件作用略有不同的 Krylov 迭代法；这里的 M4Y 预条件器会随当前 residual 改变，所以使用右侧 FGMRES。`true residual` 是把当前解重新代入真实 `B0` action 后计算的 `rhs-B0*x`，不是 PETSc 内部 monitor 的替代值。checker 对三个 checkpoint 的数组逐个 mmap、重算并核对了这个量。

## True residual Gate

| checkpoint | worker reported | checker independent recompute | 固定限值 | 结论 |
| --- | ---: | ---: | ---: | --- |
| iter20 | `1.2075357244328856e-4` | `1.2075357244328856e-4` | `<=0.40` | PASS |
| iter50 | `3.1216557608039517e-6` | `3.121655760822562e-6` | 记录下降 | measured |
| iter100 | `2.9165492426098423e-9` | `2.916549231606929e-9` | `<=1e-3` | PASS |
| iter50 → iter100 | — | 严格下降 | 必须下降 | PASS |

`converged_reason=-3` 是固定 `rtol=0`、`atol=0`、`max_it=100` 屏幕达到迭代预算后的预期 `DIVERGED_ITS` 语义，不是 positive PETSc convergence。正式 PASS 依据是 checker 独立重算的 explicit true residual、资源和架构 Gate。

## 资源、action 与架构

| Gate/测量 | 实测 |
| --- | ---: |
| isolated stage peak RSS | `1,183,698,944 B` |
| online completed peak RSS | `978,083,840 B`，限值 `<1,550,000,000 B` |
| stage / online swap | `0 / 0` |
| stage / online processes | 均已 gone；online compiler descendants=`[]` |
| operator / PC / sample action count | `108 / 100 / 3` |
| total action audit | `209 = 1` fresh RHS action `+108` operator `+100` PC |
| fine space | `uncondensed_fullspace` |
| M3Y factors | 84 factors、252 cells、`525,196,562 B` retained |
| factor reuse / copy | `168 / 0` |
| mmap | read-only，真实检查通过 |
| PoU closure | `0.0` |

M3Y packed store 的 retained bytes 位于既有 `560,000,000 B` envelope 内。global matrix、global constraint matrix、static condensation、trace slab、Schur、DtN、coarse 和 PDE 均未物化；`ordinary_default=false`。stage 峰值与 online 峰值分别记录，未相加，也没有把 online 峰值称为 PDE 峰值。

固定 RHS 是 `physical-RHS-like`，定义为 physical-like primal 经 slave rows zero 后再施加一次 exact `B0` action；SHA 为：

`6f91c83e1722a07958e6d757f7aa13f88858c95ea9ff88fe9e8693629b6f2c6d`。

## 为什么不需要 75D coarse

V11 只在无 coarse 的 global solve 出现传播型平台时才允许固定 75D wave coarse。本次 iter100 true residual 已达到 `2.916549231606929e-9`，低于 `1e-8`，且从 iter20 到 iter100 持续下降，没有观察到传播型平台。因此 75D coarse 是 `not_needed/not_run`，不是“75D 已通过”。M5 第一屏不是 PDE，也不构成 official physics qualification。

M4Y 仍保持 `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`；M5 是用户 override 后开启的独立 coercive research lane，不改写 M4Y 的 checkerboard 负结果。M6/DtN、time-harmonic PDE、RTA、直接法 physics comparison 和最终 PDE `<2 GB` 目标仍 `not_run_yet/not_measured`。

## 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| raw | `benchmarks/artifacts/task037_extra_development/m5_a3c677f_run1` |
| watchdog summary | `m5_watchdog_summary.json`；`ccda2b2ab38b175f15fc40b28575ac21cf39ebd5fe492adf77eb8d4e34c242a7` |
| worker summary | `m5_worker_summary.json`；`8b26af2962183ca8bc85734cd593d67cf899022813f7c85f6069db8ba12d4556` |
| stage summary | `stage_summary.json`；`410ce5a6763e14be5c505c192509a5b8672d52e41af10a48b259a0fa51309d37` |
| m5 timeline | `m5_timeline.jsonl`；`03c06817c2f076933708c4d1d57864db21e2a0452475747fd302f630aecac39b` |
| raw evidence | watchdog `evidence_sha256=b384cfa89b934618eb9d0e8f2cceea9ca5b4f8926684f232d8e7c084471ea85b` |
| compact | `benchmarks/cases/101_task37_extra_development/records/m5_coercive_fgmres_screen.json`；`822c2d2af336395fc85fbfec99567029f29092be3413cd60da6c19beb4b901dc` |
| compact embedded evidence | `7cfb01f89d05b2f27e87d8a4c9853ad28829bc717aa01af416c074411aeb70c6` |

本 outcome 只记录本次正式第一屏，不创建 M6 outcome，不修改 M4Y/M3Y/M2 的历史 evidence；ordinary default 保持不变。
