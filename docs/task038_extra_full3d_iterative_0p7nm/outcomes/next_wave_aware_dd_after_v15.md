# V15 之后的 wave-aware DD 候选

本文只是下一轮 review 的诊断设计，不是已授权实现，不是 V14 J6 PASS，也不启动第五个 PC family。DD（domain decomposition，区域分解）把大网格拆成带接口的小区域并协调接口未知量；这里的目标是让局部 Maxwell 计算看见传播波的相位，而不是把波误当成普通正定问题。

## 为什么提出、以及为什么关闭当前 rank32 correction

V15 固定的 propagating 与 near-cutoff Floquet basis 只捕获 0.002179823642496248 的残差能量，投影后 rho 为 0.9989094935766222。该真实 span Gate 结论已经封存：关闭 V15 bounded rank32 correction，不再运行同一 global projection，也不改 rank、mode、window 或权重。

| 路线 | 它表达什么 | V15 决策 |
|---|---|---|
| 固定 rank32 Floquet correction | 一个预先选定的全局波模小空间 | 已由 span Gate 关闭；不能改名重开 |
| 普通 GenEO/BDDC/HX | 主要依赖局部正定能量或通用接口模式 | 既有边界已关闭；wave-aware 路线不是换名复活 |
| wave-aware DD 候选 | 局部 matrix-free Maxwell 子域逆，加显式传播/近截止接口粗空间 | 只作为 V15 后唯一候选，尚未实现或授权 |

## 只允许的候选形状

1. 复用已经通过 positive qualification 的 same-mesh p-MG 作为局部求解基础，不改变既有 exact split volume、streaming DtN、Floquet/MPC 或物理材料。
2. 每个子域使用 matrix-free Maxwell action；接口粗空间显式由 physical canonical inventory 的 propagating 与 near-cutoff 波模及其必要梯度耦合生成。basis 不从 residual 拟合，不扫描 rank、窗口或权重。
3. 粗算子按 owner 分布，使用固定内存布局；不建立 global AIJ，不把所有子域向量或 A Z 包长期保留。
4. P 与 P^H 必须在同一 canonical entity key 上形成 adjoint；MPI owner 路由、constraint identity、输入不变和有限性都必须可审计。

这与已关闭的 rank32 诊断不同：DD 的局部逆和接口传输改变的是预条件器的空间组织，候选传播空间由子域接口物理身份决定，而不是把一次残差压缩成单个全局 correction。它也不把普通 GenEO、BDDC 或 HX 重新包装成新名字。

## 下一次 review 前必须先闭合的 Gate

| Gate | 固定要求 | 失败动作 |
|---|---|---|
| action identity | local A、DtN、MPC reduction 与 exact split action 一致；没有额外物理项 | 关闭候选 |
| interface identity | P/P^H adjoint、MPI1/MPI2 canonical owner key、slave-zero、input unchanged、finite | 关闭候选 |
| basis policy | 只用 frozen physical inventory；rank 上限和随 wavelength/interface 的增长规则预先写死 | 不允许 residual fitting 或参数扫描 |
| numerical diagnostic | 只在未来 DD 的 local/interface fixed-vector oracle 中测物理接口空间；不重跑 V15 global rank32 projection，不启动长 Krylov | 不进入 V15 bounded correction retry |
| capacity | 逐对象列 simultaneous live set、local work vectors、owner coarse storage、retained observation；central 与 hard upper 在 formal 前闭合 | 不进入 formal |
| resource | fresh cache、cold process-tree peak、swap=0、释放顺序和无 RSS accumulation | 不进入下一 review |

内存预算必须是同时存活对象的上界，而不是各阶段字节相加；需要保留 V15 的 <2 GB watchdog、swap=0 和 raw timeline 证据口径。只有这些 Gate 通过后，主线程才可在新 review、新 source SHA、新 artifact root 下决定是否开展一次独立 DD 预审；当前 V14 J6/J7/J8 仍是 not_run/locked。

## 不应继续的路线

若物理接口空间在预审中不能以固定 identity 和容量闭合，则关闭 wave-aware DD 候选，转为研究更小的局部传输或网格/波长分层；不重跑普通正定 GenEO/BDDC/HX，不重新开启 rank32 correction，也不产生 V14 official E/H/R/T/A。
