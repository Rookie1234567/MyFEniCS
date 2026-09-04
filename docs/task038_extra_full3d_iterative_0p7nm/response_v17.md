# Task038-extra Review V17 最终回应

## 当前 authority 总览

本版是 V17 M6 的最终文档收口。`NOT_QUALIFIED` 是总体状态：Q1 的窄 operator/inner 合同已经通过，Q2 的 reference correction 是真实 numerical FAIL，V17 的两个独立 oracle 都有有效证据但没有 strong signal，因此没有授权 fresh recovery 或新的 PC 实现。

| 范围 | 当前状态 | 证据语义 |
|---|---|---|
| Q1.1 | PASS | 同一 h50 网格上 p6/p3 physical action identity 通过；不是 full PDE |
| Q1.2 | PASS | p3/h50 physical inner 通过 true-residual Gate；不是 official physics |
| Q2 | `Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL` | p6/h10 checkpoint correction 的 reproduction、inner 和 rho Gate 未通过 |
| Oracle A | `EXACT_P3_COARSE_SPAN_FAIL` | evidence-valid；`rho_ref=20.97573925716883` 是真实数值失败 |
| Oracle B | `UNRESTARTED_KRYLOV_WEAK_SIGNAL` | evidence-valid；有改善但没有 strong signal |
| W0 | `W0_INTERFACE_RANK_CAPACITY_FAIL` | interface rank/同时容量 authority 未闭合 |
| Q3–Q6/W1–W4 | locked/not_run | 没有被本轮测试或实现 |
| official physics/recovery | not_run | 没有 official E/H、near-field、R/T/A 或 recovery |

“PASS”在 Q1 中只表示所定义的局部合同通过；“evidence-valid”表示记录完整、哈希和独立 checker 闭合；它们都不等于 0.7 nm full physical solve 或 continuum convergence。

## 时间顺序与保留的历史

V16 的首次 Q1 source-authority controlled stop、Q2 negative、W0 preflight 以及所有旧 raw/checker 都永久保留。随后同一任务在新 source SHA 下完成 Q1.1/Q1.2 formal PASS；V17 再以新的实现 SHA 完成 Oracle A v3 和 Oracle B v2。V17 不覆盖旧证据：Oracle A v1/v2/v3、Oracle B v1/v2、Q2 原 `checker.json` 的基础设施失败记录，以及 B 的 `checker_recheck_v2.json` checker-only recheck 都保留在各自 artifact root。

## Review V17 要求的十二项最终回答

### 1. Q1.1：A3 与 `P63^H A6 P63`

Q1.1 是同一 h50 mesh 的 p6/p3 physical action identity。MPI1 worst physical Galerkin relative 为 `4.3068152418800024e-14`（probe `curl`）；MPI2 为 `3.631160363261226e-13`（probe `curl`）。独立 pair checker 的 worst direct MPI relative 为 `1.3304006108072395e-14`（`physical_component_derived`），worst composed MPI relative 为 `3.620657472911387e-13`（`curl`）。这些是 measured identity facts，均小于冻结阈值；Q1.1 没有生成 official field。

### 2. Q1.2：p3 inner 的 MPI1/MPI2

Q1.2 固定为 p3/h50、right FGMRES、restart 20、每 20 步重算 true residual、max 5000，并使用已资格化 p3→p1 positive PC。MPI1 的 `physical_rhs` 为 `8.492309832071864e-7`/880 iterations，`random` 为 `9.452221758437722e-7`/2280；parent/worker peak 为 `1,558,450,176`/`284,377,088 B`，swap 0。MPI2 对应为 `8.456504897210137e-7`/880 和 `9.46295350977649e-7`/2280；peak 为 `1,558,446,080`/`504,700,928 B`，swap 0。MPI1 单侧 checker 与独立 pair checker（读取 MPI1/MPI2 raw）均通过；MPI2 超过 2 GB 的用户覆盖仍只适用于未来记录口径，本次 MPI2 实测未超过该线。

### 3. Q2：checkpoint reproduction、inner history、rho 与 correction

Q2 是 p6/h10 checkpoint-1000 correction，不是 full PDE。冻结 checkpoint stored explicit residual 为 `0.4837947981092168`，重算为 `0.48379479479924`，reproduction relative 为 `6.8416957056789795e-9 > 1e-11`。p3 inner 的关键 true residual history 为：iteration 0 `1.0`，20 `0.8309410237461273`，1000 `0.7830431676258411`，2000 `0.78048347154443`，4000 `0.7781984682037493`，6000 `0.7766983492676462`，8000 `0.7756091855405819`，10000 `0.7749555148382701`；最终没有达到 `1e-6`。

correction 前后 raw norms 为：`||r6||=0.6412077991519661 → ||r6_new||=1.7313562126657716`，`||r3||=0.39933395062332383 → ||r3_new||=0.309466047297697`。因此 `rho_ref=2.7001483995603124 > 0.70`，`rho3=0.774955514838267 > 0.10`。Q2 classification 是 `Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL`；parent peak `1,560,625,152 B`、worker peak `873,783,296 B`、swap 0 只说明该次运行的资源事实，不能把它写成正确 full solve。

Q2 的真实 operation ledger 为 matvec `10,999`、PC `10,000`、explicit action `501`、KSP destroy `500`；upper smoother delta 为 `0`，lower positive cycle 为 `10,000`，P63 primal/adjoint 为 `1/2`。这些计数来自 raw lifecycle，不是由公式字符串推测。

### 4. I20/I100 与 Q3

I20 和 I100 均未选择；没有进行参数扫描，也不能把“未选择”写成扫描失败。Q3 未运行。Q2 的真实 correction negative 和 V17 A/B 结果不足以授权更长的 physical PDE。

### 5. Q4 short screen

Q4 short screen 为 `not_run`。没有用未经授权的短实验替代 Q2 或 V17 oracle，也没有把缺少的结果解释为通过。

### 6. Q5 fresh physical

Q5 fresh physical 为 `not_run`。Q2 的 `1,560,625,152 B` 是 p6/h10 checkpoint correction workflow 的 parent process-tree peak，绝不能冒充 fresh full PDE 的资源或 numerical result。0.7 nm/2 TiB 上的可扩展 solve 仍未证明。

### 7. release-before-recovery 与 official recovery

Q5 的 release-before-recovery 和 official recovery 均为 `not_run`。Q2 的 `release_complete` marker 只证明该窄 reference-correction runner 完成了它自己的对象清理顺序；它不证明 official recovery 或 full PDE release contract。

### 8. scalar packet 与 official observable

已有 direct scalar packet 和 canonical physical-key packet，可支持 Q1/Q2/V17 oracle 的局部 identity 与 residual 审计；它们不能替代缺失的 official complex E/H、near-field 以及同一组 12+12 arrays。因此没有报告 official R/T/A 或其物理结论。

### 9. W0 与已关闭路线的结构差异

W0 候选是 geometry-only quartile subdomains、one-cell overlap、owner-distributed interface Schur/coarse apply，并以冻结的一阶 impedance 只做人工边界闭合；它在矩阵机制上不同于 two-slab Robin、V15 rank-32 global projection、普通 GenEO/BDDC/HX 和旧 trace-harmonic/local-spectral 路线。W0 的失败不是换名字：真实 interface rank/count 与 simultaneous byte authority 没有闭合，故 `W0_INTERFACE_RANK_CAPACITY_FAIL`，不能进入实现阶段。

V17 Oracle A/B 同样没有把 W0 或另一种 PC 偷渡进生产路径：A 是 exact p3 diagnostic assembled span，B 是 disk-backed unrestarted Krylov 对照，二者分别隔离 coarse-span 与 Krylov-memory 机制。

### 10. W0 之后的 W1–W4

W0 preflight 已被 Q2 真实失败触发，但 W0 自身因 rank/capacity major unknown 失败，所以 W1–W4 是 `locked/not_run_by_W0_gate`。W0 的矩阵公式只是 `defined；W1 identity not_run`，不应被读成已实现或已通过。

### 11. 状态标签

本回应按以下语义书写：`measured` 是 raw process/numerical observation；`derived` 是由 raw norms、counts 或 checker 公式计算；`predicted` 只用于明确标注的资源预估；`failed` 是真实 Gate 未通过；`controlled_stop` 是按合同停止；`not_run` 是没有执行；`locked` 是由上游 Gate 阻止。Oracle A 的 `status=PASS/evidence_valid=true` 只表示证据有效，mechanism classification 仍是 numerical FAIL；Oracle B 的 `status=PASS/evidence_valid=true` 与 WEAK signal 同理。

### 12. blocker 边界与总体状态

已经消除的 blocker 包括 Q1.1 surface quadrature API、Q1 action identity、p3/h50 inner lane、V17 MUMPS/ disk-backed evidence contracts，以及 Oracle B 的 checker PC-ledger 工程错误。仍有的 blocker 是：Q2 physical p-coarse correction 的 reproduction/inner/rho Gate；Oracle A fine-residual amplification；Oracle B 没有 strong signal；W0 rank/capacity authority；以及缺失 official physics/recovery。

总体结论为 `V17_Q_AND_ORACLE_LANES_CLOSED_BY_REAL_GATES / NOT_QUALIFIED`：Q1 窄合同通过，但 Q2 和 V17 mechanism Gates 不支持继续。MPI1 的 2 GB process-tree RSS 是硬线；用户明确授权 MPI2 超过 2 GB 时只记录、不因 RSS 单独关闭 Q，但 MPI2 的 numerical、finite、repeat、input-unchanged、provenance、swap 和 lifecycle 仍然是硬要求。本轮 Q2 与 Oracle A/B 都是 MPI1；没有 MPI2 Q2/A/B 证据。

## V17 Oracle A 证据摘要

Artifact root 为 [`Oracle A v3`](../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v17_oracle_a_v3/d521d85ed63535a2c9bb03e44fe9f7a5e8d394e7/mpi1)，formal source SHA `d521d85ed63535a2c9bb03e44fe9f7a5e8d394e7`。checker `status=PASS`、`evidence_valid=true`、`errors=[]`，classification `EXACT_P3_COARSE_SPAN_FAIL`，唯一 `gate_failure` 是 `rho_ref`。A1 reproduction actual/relative 为 `0.48379479479924`/`6.8416957056789795e-9`；A2 p3 residual `3.5516052364193747e-12`；A3 `rho3=4.298361509181443e-12`、`rho_ref=20.97573925716883`。A2 predicted peak `977,725,952 B`，低于 12 GB analysis preflight limit；parent overall peak `1,487,446,016 B`，swap 0。

完整 A raw/checker SHA 见 [exact p3 coarse span outcome](outcomes/exact_p3_coarse_span_v17.md)。

## V17 Oracle B 证据摘要

Artifact root 为 [`Oracle B v2`](../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v17_oracle_b_v2/3e3ad22944333439e9f4a5d71abc4c7384855dff/mpi1)，formal source SHA `3e3ad22944333439e9f4a5d71abc4c7384855dff`。原 `checker.json` 的 PC-ledger infrastructure failure 保持不变；`checker_recheck_v2.json` 从同一 raw 独立重算后 `status=PASS`、`evidence_valid=true`、`errors=[]`，classification `UNRESTARTED_KRYLOV_WEAK_SIGNAL`。`r_GMRES20(500)=0.48362582271206495`，`r_unrestarted(500)=0.19374101288500692`，ratio `0.4006010510326989`；因此不是 `<=0.1` strong signal。parent peak `1,451,954,176 B`，worker-stage peak `880,951,296 B`，swap 0；PSS 未在 B raw packet 中记录。

完整 20–500 residual history、basis/H/hash、counts 和 marker 顺序见 [unrestarted Krylov outcome](outcomes/unrestarted_krylov_v17.md)。

## M6 closeout

本轮只完成 M6 文档/证据整理，没有修改 solver、runner 或数值参数，也没有重跑 formal/heavy。下一步不是自动启动新 PC；任何未来方向都必须先获得新的 review 授权并建立独立、小规模、hash-bound 的 identity 与容量证据。
