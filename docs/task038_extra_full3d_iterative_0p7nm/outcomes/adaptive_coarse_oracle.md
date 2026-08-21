# D1 trace-harmonic coarse oracle

## 结论

D1 在真实 p2/p3 Full3D 两-slab fixture 上通过。它验证的是一个可审查的
trace-harmonic（界面谐波）粗空间 oracle：把体内自由度固定为界面 trace 后，
用辅助能量定义最小能量延拓，再检查界面算子、延拓、广义特征问题和 MPI
分区是否保持同一物理身份。它不是 p6/h10 production coarse solve，也没有
运行 PDE、KSP 或 process-tree 资源资格化。

| 项目 | 结果 |
|---|---|
| D0 source commit | `79b33f86b22ba33a610c1167fe0c2287dc3d7b54` |
| D1 implementation commit | `a650aae08957736eedf7b6c4842cce15c73da708` |
| provenance narrow-fix / formal source SHA | `ddf7801af3285a35ee1a53c728d552a15e8d6983` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| profile / mesh | `adaptive_trace_harmonic_two_level_v1`, p2/p3, h=50 nm |
| formal cases | p2-MPI1, p2-MPI2, p3-MPI1, p3-MPI2 |
| individual / aggregate | 4 PASS / aggregate PASS |
| process-tree peak | `not_measured` |
| D2/D3/D4 | `not_run` |
| Candidate C / transmission family | closed; no source or negative evidence changed |

## 1. 这项 oracle 在检查什么

`B_i` 是第 `i` 个 z-slab 的固定辅助体能量：

\[
B_i(u,v)=\int_{\Omega_i}\mu_r^{-1}\,\mathrm{curl}(u)\cdot
\overline{\mathrm{curl}(v)}\,dx
+k_0^2\int_{\Omega_i}|\epsilon_r(x)|,u\cdot\overline v\,dx .
\]

`M_Γ` 是真实界面 facet 上的切向质量形式
`∫Γ u_t·conj(v_t) dS`。它把界面上的向量值看成需要传递的数据。两者的
作用不是替代 Maxwell 物理算子，而是为粗空间选择提供稳定的离散度量。

对一个给定的界面 trace，harmonic extension 会固定 trace，只解 slab 内部
自由度的 `B_i` 最小能量延拓；外部 shell 行不被误当成内部未知量。随后以
延拓矩阵 `H` 构造

\[
K=H^H B_i H,\qquad Kq=\lambda M_\Gamma q .
\]

最小的 16 个广义特征向量按升序、确定性相位保存。D1 的 restriction/prolongation
沿用已资格化的 owner-active-row 单位权 Euclidean adjoint；它只搬运数据，
不是新的物理权重层。

记录中的 `source` 是 primal `full_fe` canonical coefficient。`B_i` 和 `M_Γ`
的 action 是 finalized MPC 后的 `full_fe_dual` residual；两种角色不能混用，
否则会把 primal 系数误解释为物理 covector。

## 2. 四个正式记录

四个 record 均绑定同一 clean source SHA，manifest 逐 shard hash-bound；每个
individual checker 都从 raw packet/NPZ 重算 Gate。MPI2 的 assembled serial algebra
按合同为 `not_run`，其边界是
`distributed_action_identity_only; serial assembled algebra is MPI1-only`。

| case | compact record SHA-256 | individual check SHA-256 | rank-max RSS / swap |
|---|---|---|---:|
| p2-MPI1 | `dc8f1531a50098c318e628ad7782180a6f729d3f58c356cf370d62bfdaa1a398` | `bc1334cbf72901a4a4c851744a878816899b18014254a597907b7938fbe5d60a` | 216,186,880 B / 0 B |
| p2-MPI2 | `e9f60ef093d2d73794e5306d366c1246ef2f8b98c037df00242e69d4685e15b0` | `3f83cecc3f076b6bbad9c52962e36f928511b4b669cb5a7bd745a58366136dd8` | 114,843,648 B / 0 B |
| p3-MPI1 | `7f9aec18c6b04b888fef5e9f231efdd15ee480ef3a2b81d65f6d2c75d21b1810` | `0f0169fb9df91bfea53e2fd2a8d47bc7fb5a34341a4b1ca9d403103114e4b672` | 1,046,962,176 B / 0 B |
| p3-MPI2 | `59d4e0a548e33108a748797251f8571b27ee1b590a85447b12aaa9553a8c5963` | `a31a0dec994090d5ebf74d4c89b3aa60b2404494cac323dd708839eda1f0fb17` | 120,438,784 B / 0 B |

RSS 是 runner 记录的 rank-max current self RSS，swap 是每个进程的 `/proc/self/status`
`VmSwap`；二者都不是 process-tree peak。四个 compact record 位于
[`records/`](records/)；aggregate checker 位于 ignored raw 根目录，SHA-256 为
`3a948b02fdd627758ff96fb6523001defe7099f8cbe8168228cd9a8953e39680`。

## 3. Serial assembled algebra 结果

这些 dense assembled 数据只用于小 p2/p3 oracle。它们证明公式、分块和特征问题
在小 fixture 上闭合，不是允许把同一 dense 方法搬到 p6/h10 的授权。

| degree / slab | B Hermitian defect | MΓ Hermitian defect | K Hermitian defect | eigen residual | mass norm error | rank / repeat |
|---|---:|---:|---:|---:|---:|---|
| p2 / 0 | 5.7047e-17 | 5.4648e-17 | 9.8466e-17 | 3.2214e-15 | 5.3841e-15 | 16 / exact |
| p2 / 1 | 5.9316e-17 | 5.4648e-17 | 1.5201e-16 | 2.3299e-15 | 5.3493e-15 | 16 / exact |
| p3 / 0 | 7.5664e-17 | 5.7418e-17 | 3.7545e-16 | 9.5109e-15 | 5.2356e-15 | 16 / exact |
| p3 / 1 | 7.2254e-17 | 5.7418e-17 | 4.7034e-16 | 8.1657e-15 | 5.3794e-15 | 16 / exact |

四个 slab 的 eigen ordering 均为 ascending，harmonic extension relative error 和
repeat error 均为 0；R/P adjoint relative error 均为 0。所有 serial checks finite，
`K=H^H B H` relation error 均为 0。

## 4. Canonical packet 与 MPI identity

| degree | source packets / role | 每 slab B、MΓ action/repeat packets / role | MPI1/MPI2 topology digest |
|---|---:|---:|---|
| p2 | 988 / `full_fe` primal | 768 each / `full_fe_dual` | `8a325f1de93fbe250235b4a89280007f6bb51a51d9deda80f0698344633f9afa` |
| p3 | 3018 / `full_fe` primal | 2538 each / `full_fe_dual` | `1c60a381f4b5e807328bc5f7c82622f4bff535a1bc260ba0d8fed3046bf97512` |

每个 action/repeat manifest 的 missing、extra、duplicate 均为 0；每个 MPI pair
的 key count 相同。aggregate 从 MPI1/MPI2 raw shard 重新读取并得到以下 relative L2，
限值均为 `1e-12`：

| degree | source | slab0 B | slab0 MΓ | slab1 B | slab1 MΓ |
|---|---:|---:|---:|---:|---:|
| p2 | 4.6246e-17 | 3.9119e-16 | 9.2168e-16 | 2.3280e-16 | 9.2168e-16 |
| p3 | 6.3473e-17 | 2.5007e-16 | 3.2746e-16 | 2.1450e-16 | 3.2746e-16 |

这证明的是同一物理 canonical key 下的分布式 action identity，不是把数值向量
numeric allgather 到每个 rank。生产 audit 中 `global_numeric_allgather=false`，
没有 global AIJ、global Schur、dense interface matrix 或 growing factor。

## 5. Raw evidence 路径与边界

| case | raw/check 路径 |
|---|---|
| p2-MPI1 | `benchmarks/artifacts/task038_extra_full3d_iterative_d1_formal_v1/ddf7801_p2_mpi1_attempt2/` |
| p2-MPI2 | `benchmarks/artifacts/task038_extra_full3d_iterative_d1_formal_v1/ddf7801_p2_mpi2_attempt1/` |
| p3-MPI1 | `benchmarks/artifacts/task038_extra_full3d_iterative_d1_formal_v1/ddf7801_p3_mpi1_attempt1/` |
| p3-MPI2 | `benchmarks/artifacts/task038_extra_full3d_iterative_d1_formal_v1/ddf7801_p3_mpi2_attempt1/` |

raw mesh、NPZ、canonical shards、checker JSON 和 staged compact copies 均留在 ignored
artifact 目录；Git 只保存轻量 compact record。D1 没有测 process-tree peak，不能把
上述 rank RSS 当成完整工作流内存资格。

## 6. 启动层事件与后续边界

以下三件事都发生在数值计算之前，不属于 D1 formal numerical failure：

1. sandbox 中 MPI singleton 触发已知 PMIx listener socket 隔离；正式运行改用同一
   qualified activation 的受控 non-sandbox 路径。
2. 标准 venv `bin/python` 是系统解释器 symlink，旧的 resolved executable 判断错误地
   拒绝了它；窄修已在 `ddf7801af3285a35ee1a53c728d552a15e8d6983` 修复，并记录 lexical
   executable 与 resolved qualified bin。
3. 首次直接脚本调用未把仓库根加入 module search path，触发
   `ModuleNotFoundError: No module named 'src'`；它只留下空 raw 目录，目录被保留且未计入
   数值尝试。纠正为 `python -m benchmarks.run_task038_full3d_adaptive_coarse` 后才进入
   正式数值。

D1 的结论是 PASS，但只覆盖小 p2/p3 fixture 和 MPI1/MPI2 distributed action identity。
D2、D3、D4 仍为 `not_run`；Candidate C 和 transmission family 的 closed/research
archive 状态不变。本文件不授权 p6/h10 coarse build，也不把 D1 dense algebra 当成
production coarse implementation。
