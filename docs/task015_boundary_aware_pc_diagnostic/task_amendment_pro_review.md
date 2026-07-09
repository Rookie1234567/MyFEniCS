# Task015 补充指令：从“跑 profile”改成“定位瓶颈并选择解法”

## 0. 补充目的

本补充文件用于加强 `task.md`。Task015 的目标不是再跑一组复杂 profile，而是要尽可能回答：

```text
为什么 Task014a 的 FE-AMS + aux identity 在 default100 p=1 h=5 上只把 true residual 从 3.436e-2 降到 2.147e-2？
当前停滞主要来自 FE block、DtN auxiliary、FE/aux coupling、Rayleigh/Floquet modal slow modes，还是无法区分？
```

执行 Task015 时，必须把本补充文件和 `task.md` 同时作为任务要求。

---

## 1. 先做 residual decomposition，再做新 PC

在实现任何新的 Schur 或 modal correction 前，必须先对 Task014a baseline 做残差分解。

对以下两个 profile：

```text
stage4_real_split_fgmres_jacobi
stage4_real_split_fgmres_fe_ams_aux_identity
```

计算 final true residual 的 block 分量：

```text
r = b_real - A_real x

r_FE_real
r_aux_real
r_FE_imag
r_aux_imag
```

至少输出：

```text
||r_FE_real|| / ||b||
||r_aux_real|| / ||b||
||r_FE_imag|| / ||b||
||r_aux_imag|| / ||b||
||r_FE_total|| / ||b||
||r_aux_total|| / ||b||
aux_residual_fraction = ||r_aux_total|| / ||r_total||
FE_residual_fraction = ||r_FE_total|| / ||r_total||
```

输出文件：

```text
boundary_residual_decomposition.csv
```

解释规则：

```text
如果 aux_residual_fraction 很高：优先 DtN aux / Schur correction；
如果 FE_residual_fraction 很高：优先 FE block proxy / shifted FE block；
如果 residual 主要集中在少数 modal components：优先 Rayleigh/Floquet modal deflation；
如果无法区分：不要强行宣称某方向成功。
```

---

## 2. 对 aux residual 继续做 modal decomposition

如果 `aux_residual_fraction` 不小，必须进一步把 auxiliary residual 投影到 DtN / Rayleigh/Floquet mode index 上。

输出：

```text
aux_modal_residual_decomposition.csv
```

字段至少包括：

```text
mode_id
port
diffraction_order_m
diffraction_order_n
is_propagating
is_near_cutoff
residual_norm
relative_to_total_residual
relative_to_aux_residual
```

若当前代码无法拿到 `m,n` 或 propagating/near-cutoff 标记，至少输出可用的 `mode_id`、`port` 和 residual norm，并在 notes 中说明缺失字段。

解释规则：

```text
如果少数 propagating / near-cutoff modes 占 aux residual 大头：modal deflation 优先；
如果 aux residual 分散在很多 modes：Schur / aux block preconditioner 优先；
如果 aux residual 很小：继续改 aux block 意义不大。
```

---

## 3. 把 DtN 与 Floquet 分清楚：最小 ablation 必须做

Task014a 失败可能来自 DtN，也可能来自 Floquet，也可能是二者耦合。因此 Task015 必须做最小 ablation，而不是只跑 default100 auto。

至少比较以下 reduced p=1 h=5 cases：

```text
A. default100 auto-propagating DtN auxiliary   # 当前主 case
B. default100 zero_order local Robin           # Task014a 已做过，可复用
C. default100 no_aux_or_aux_removed_if_available # 如果代码支持；否则明确说明不可用
```

如果 `C` 不可用，不要硬改 production path；只需记录：

```text
no_aux case unavailable: reason = ...
```

输出：

```text
boundary_ablation_summary.csv
```

解释规则：

```text
auto case 差、zero_order 更差：说明端口边界物理很关键，不应走 local Robin；
auto case 差、no_aux 不可比：不能直接归因于 DtN；
auto case aux residual 主导：优先 Schur/modal；
zero_order 中 FE residual 主导：FE block proxy 也需要改。
```

---

## 4. Stage B/C/D 的执行顺序改为 evidence-driven

原 `task.md` 中 Stage B、C、D 都保留，但执行顺序必须由 residual decomposition 决定：

```text
若 aux residual 主导：先做 Stage B/C；
若 modal residual 主导：先做 Stage D；
若 FE residual 主导：先做 Stage E；
若无法区分：按 B -> C -> D -> E 顺序，但每一步必须有 stop rule。
```

不要为了“覆盖任务书”而实现所有复杂 correction。优先实现最能解释 residual 的分支。

---

## 5. DtN Schur 的最低可行实现要求

Stage C 中 `S_aux_pfe ≈ A_aux - D P_FE^{-1} C` 可能成本高。允许先做低秩或抽样版本，但必须有可解释性。

推荐顺序：

```text
1. aux exact: S_aux = A_aux
2. diagonal Schur: S_aux ≈ A_aux - D diag(A_FE)^{-1} C
3. sampled P_FE-Schur: 只对 residual-dominant modes 或 propagating modes 构造 D P_FE^{-1} C columns
4. full P_FE-Schur: 仅在前面有明显正信号且成本可接受时做
```

如果 aux residual decomposition 显示只有少数 modes 主导，不要构造 full 1416 x 1416 Schur；先针对主导 modes 做 low-rank correction。

---

## 6. Rayleigh/Floquet modal correction 的最低可行实现要求

Stage D 的目标不是一次性实现完整 volume deflation。允许分两级：

```text
Level 1: auxiliary-space modal correction
  只在 aux/modal unknown 子空间做 coarse correction，验证是否能降低 aux residual。

Level 2: lifted FE+aux modal correction
  将 Rayleigh/Floquet mode lift 到 FE trace/volume，并与 aux unknown 一起组成 Z。
```

如果 Level 2 很复杂，本轮只做 Level 1 也可以，但必须明确写：

```text
modal correction level = aux-space only
not a full volume deflation
```

成功标准：

```text
aux-space modal correction 能显著降低 aux residual；
或 total true residual 比 aux identity 至少降低 10x；
若只降低 aux residual 但 total residual 不变，说明 FE block 仍是瓶颈。
```

---

## 7. FE block proxy 必须有一个“上界判断”

如果 Stage B/C/D 都失败，必须做一个小规模 FE block proxy 上界判断。不要只说“可能是 FE block 太弱”。

在 tiny10 或最小可承受 case 上比较：

```text
P_FE = same-H1 AMS positive proxy
P_FE = shifted/absorbing H(curl) proxy
P_FE = exact or near-exact FE solve on tiny10 only
```

输出：

```text
fe_proxy_upper_bound_diagnostic.csv
```

目标：

```text
如果 tiny exact FE + aux exact 仍不能明显改善，说明瓶颈主要不是 FE local inverse；
如果 tiny exact FE 显著改善，说明 same-H1 positive AMS proxy 不够，需要改 FE block PC。
```

---

## 8. 更强的 stop criteria

为了避免 Task015 变成无边界开发，加入以下硬停止条件：

```text
1. baseline reproduction 不一致且无法解释：停止。
2. residual decomposition 显示 FE residual 占比 > 90%，且 aux/modal correction 无法影响 total residual：停止 Schur/modal，转 FE proxy。
3. aux exact、Schur_diag、modal_aux_space 三者均不能把 true residual 降到 1e-2 以下：停止本轮，不做组合测试。
4. 任一 profile 比 aux identity 更差 3 倍以上且无法解释：不继续该方向。
5. 任何 correction 需要提交大型 matrix dumps 或侵入 direct/BLR production path：停止。
```

---

## 9. 更强的 success criteria

Task015 不以“有一点改善”为成功。

成功分级：

```text
A: true residual <= 1e-6，或相对 aux identity 改善 >= 100x；允许建议进入 reduced p=2 h=5。
B: 相对 aux identity 改善 >= 10x，且 residual <= 1e-3；允许继续强化该方向。
C: 改善 2x-10x；只算弱正信号，不允许进入 p=2。
D: 改善 <2x 或变差；该方向停止。
```

当前 aux identity baseline：

```text
true residual = 2.1465559540488233e-2
```

因此：

```text
B 档至少需要降到约 2e-3 或更低；
A 档需要约 2e-4 或更低，最好 <= 1e-6。
```

---

## 10. summary.md 必须增加最终判断表

除原 task 要求外，summary 必须增加：

```text
## Bottleneck Attribution
```

表格：

```text
candidate_bottleneck,evidence_for,evidence_against,confidence,next_action
DtN aux block,...
FE/aux Schur coupling,...
Rayleigh/Floquet modal slow modes,...
FE block proxy,...
unknown/mixed,...
```

最后必须写一句：

```text
Most likely bottleneck: ...
Recommended Task016: ...
```

不能只输出“需要继续研究”。
