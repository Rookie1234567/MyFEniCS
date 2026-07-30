# 项目路线补充：Task035e 收口后的迭代主线

## 1. 状态更新

Task035e 已按以下状态收口：

```text
reference certification = pass
true local-h/local-p capability = pass
automatic reference-blind hp cycle = incomplete
direct selective-trace lane = closed controlled negative
accepted production hp candidate = none
ordinary default = unchanged
```

Task035e 不再继续修改 local face 数量、trace threshold、ranking 公式、Path A/B campaign 或 hidden-audit 状态机。

## 2. 对项目总体路线的修正

原路线中“Task035 adaptive hp 成功后，再进入低内存 Hybrid iterative”的依赖关系需要修正。Task035e 已证明：

- h/p、静态凝聚和目标导向 DWR 均有有效组件；
- 但在完整 59-goal 合同下，direct MUMPS + selective local trace 尚无低于 11 GiB 的合格候选；
- 继续优化局部 trace 选择不能高效解决直接分解的 factor memory。

因此，下一阶段不再等待自动 h/p 成功，而是先解决凝聚全局系统的迭代求解。

## 3. 后续固定顺序

### Phase A：Static-condensed Full3D iterative

固定资格化模型：

```text
Full3D p6/h10
assembly-time static condensation
auxiliary DtN
MPI8
S polarization
59-goal direct authority reused
```

优先研究：

- FGMRES；
- FEM trace / DtN block preconditioner；
- overlapping Schwarz/RAS local blocks；
- 可复用的低阶 H(curl) 或物理 coarse correction；
- 低 restart 与 Krylov memory；
- true residual、59-goal direct equivalence、zero swap 和 whole-job peak。

第一阶段只做 primal solve，不接 h/p controller、59 个 adjoint、反演或参数扫描。

### Phase B：Hybrid direct 59-goal qualification

在开发 Hybrid iterative 前，先固定：

```text
Hybrid static p6/h10 M120 direct
vs
Full3D p6/h10 direct
```

使用 Task035e 的同一 59-goal inventory。只有 direct Hybrid 的 modal truncation、interface E/H、R/T/A、fields 和 residual 通过，才允许进入迭代法。

### Phase C：Static-condensed Hybrid iterative

- 上下 FEM trace blocks 复用 Phase A 的 PC；
- modal/interface block 使用 block triangular 或 approximate Schur；
- 外层仍采用 FGMRES；
- 避免 replicated M²、all-mode dense multi-RHS 和不可扩展 local LU。

### Phase D：一个规模扩展点

Full3D h10 与 Hybrid h10 两条 iterative 路线通过后，最多先做一个：

```text
h7.5
或
larger M
```

用于验证内存与迭代数的增长趋势。不得同时重启 h/p controller。

## 4. h/p 的后续位置

h/p 不被否定，但从主线 blocker 改为后续叠加优化：

```text
iterative solver qualification
→ Hybrid iterative qualification
→ directional-h / variable-p reintroduction
→ wavelength continuation 13.5→5→2→1→0.7 nm
```

未来重新引入 h/p 时，必须从新的迭代 operator/PC 出发重新评估；不得把 Task035e 的 MUMPS factor-cost 模型直接搬到迭代法。

## 5. 下一任务边界

建议新任务编号：`Task035f`。

禁止同一任务同时开发：

- 新 blind controller；
- 新 local-h topology；
- 新 selective-trace ranking；
- scalable modal core；
- 0.7 nm full continuation；
- inverse solver。

优先级固定为：

```text
Full3D condensed iterative correctness
> Hybrid direct 59-goal qualification
> Hybrid condensed iterative
> one scale extension
```
