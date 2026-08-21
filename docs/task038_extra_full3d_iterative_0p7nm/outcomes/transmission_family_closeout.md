# Transmission family closeout（D0）

本页关闭已经审查过的 transmission family，并把它和下一条 adaptive coarse 路线分开。这里的“action”是给一个向量计算一次离散算子作用；“smoother”是用局部子问题削弱误差；它们都不是已经完成的完整 PDE 求解。D0 没有运行 PDE、KSP、Candidate C，也没有修改 Python。

## 身份与范围

| 项目 | 值 |
|---|---|
| 当前 D0 source Git SHA | `9705e6e84a4b491a7d9fc87b20e12f1938232b07` |
| base master | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| upstream（D0 开始前） | `9705e6e84a4b491a7d9fc87b20e12f1938232b07` |
| D0 目的 | 关闭旧 transmission lane，核算 adaptive coarse 的最小内存布局 |
| 本页的执行状态 | 仅记录 preflight/设计边界；未启动 D1 或任何 heavy case |

## A/B/C 最终分类

| family | 最终分类 | 可以保留的用途 | 明确边界 |
|---|---|---|---|
| Candidate A | `ACCEPTED_NUMERICAL_CONTRACTION_FAIL` | 完全冻结的 one-forward+one-backward、两 slab smoother oracle | transmission、slab 顺序、local GMRES restart/max-it `8/8` 不变；不能写成独立 production preconditioner claim |
| Candidate B | `CLOSED_NOT_APPLICABLE_FOR_CURRENT_INTERFACE` / `CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED` | 无 | 当前 `interface_z` 是 mixed Si–Si/Si–air；已有 T3 modal authority 只覆盖 exterior top/bottom，不能推导 interior modal transmission |
| Candidate C | `CLOSED_BY_RESOURCE_AND_PROJECT_PRIORITY` | research archive；保留源码、测试、raw/compact 负证据 | `DO_NOT_RERUN`、`DO_NOT_OPTIMIZE`、`DO_NOT_MERGE`。这是本项目优先级和资源证据下的关闭，不是“数学上永远不可能” |

Candidate C 的控制停止证据仍在 [t5_sweep_candidate_c_v2.json](records/t5_sweep_candidate_c_v2.json) 和其 ignored watchdog 中：process-tree peak `12,942,209,024 B`，12 GiB hard stop `12,884,901,888 B`，swap `0 B`，return `-15`，没有 SIGKILL fallback。不得删除、重跑或以优化 JIT 的方式改变这项负证据。

## Candidate A 的冻结解释

A 只作为一个可重复的 smoother oracle：先做 slab 0→1 的 forward 局部 solve/残差传播，再做 slab 1→0 的 backward 局部 solve/残差传播，最后用当前 exact physical action 计算 closure。两 slab、owner-local restriction/prolongation、PoU/multiplicity、transmission 和 local GMRES `restart=8, max_it=8` 全部冻结，不按 source、rho 或内存改变参数。

已有 A 证据是历史 source SHA `1a4d495a4f7a78bafb389ab9b30d0b49fe7bd5be` 绑定的 compact record，不能冒充当前 D0 的新数值结果：

| source | rho / limit | closure | repeat | process-tree peak | 分类 |
|---|---:|---:|---:|---:|---|
| physical RHS | `0.8145890334049838 / 0.60` | `1.2458376041083906e-16` | `0` | `5,145,784,320 B` | numerical contraction fail |
| gradient | `0.8889127715646881 / 0.90` | `1.271047984953834e-19` | `0` | `1,323,728,896 B` | source-local pass；不等于全 source pass |

因此 A 的旧结果不能授权 R5/T6，也不能把 gradient 的资源值称为完整 PDE 内存通过。

## 为什么关闭旧 family 后需要 adaptive coarse

旧 family 主要依赖局部 slab/界面作用；它对很远的误差传播没有一个受控的全局低维修正。adaptive coarse 的含义是：从 owner-local 接口能量构造一小组固定维数的 trace-harmonic basis，用它代表跨多个 slab 的长距离误差，再用小的 coarse operator `E=Z^H A Z` 做修正。收益是用少量全局自由度补足长距离传播；代价是 basis 构造、正交化、跨 rank 的 key/owner 元数据和额外的在线 coarse action。

这条路线不改变 Maxwell 弱式、材料、Floquet MPC 或当前 exact matrix-free physical action。`Z` 是 coarse basis，`AZ` 是同一 exact action 对每个 basis 的结果；二者只按 owner-local shard 保存，不能在每个 rank 复制完整 FE basis，也不能用 FE-sized numeric allgather、global AIJ/Schur 或 growing sparse factor。

## D0 之后的停止边界

D0 只核算 `r=16/32/48/64` 的字节公式和 `64,000,000 B` metadata/work cap。D1 才能在 p2/p3 建立 trace-harmonic algebra/orientation/MPI oracle；D2 才能在 p6/h10 构造 owner-local `Z/AZ` 和 `E`；D3 才能测五类 source contraction。任何阶段越过 Review V3 Gate，均按 hard stop 保存负证据；本页不预先声称 D1–D4 通过。

