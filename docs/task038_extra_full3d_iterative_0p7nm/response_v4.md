# Task038-extra Review V4 response

本文记录 Review V4 阶段的真实边界。这里的 action 是一次矩阵自由的算子作用；setup 是为后续求解准备局部因子和粗空间数据；controlled negative 是按固定 Gate 保存的真实受控负结果，不等于算法在所有环境中永远不可行。

## 1. 身份、分支和源码

|字段|值|
|---|---|
|Review V4 start HEAD|5aaf5748fb24828c3d0d03411df9ff388b4cc2db|
|frozen master base|438caf150439343ee7c4c58ad7e02a3da812a23c|
|formal source HEAD|907fe8fb204cffa34a921c6d0cab7ff4dd4831b8|
|upstream before docs closure|5aaf5748fb24828c3d0d03411df9ff388b4cc2db|
|branch|codex/20260820-task38-extra-full3d-iterative-0p7nm|
|formal source status|clean；ahead/behind 8/0（docs closure前）|
|ABI|qualified activation，Linux WSL，complex128/int32，threads=1|

最终 docs commit 不能在本文中自引用；final delivery commit SHA 由外部交付报告给出。

## 2. N0–N4 矩阵

|阶段|结论|边界|
|---|---|---|
|N0 local spectral capacity|PASS_CONDITIONAL|固定账本闭合；仍是 preflight，不是 p6 setup 实测|
|N1 local spectral oracle|PASS|p2/p3 MPI1/MPI2 四案和 aggregate 已通过|
|N2 setup|CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE|MPI1 一次，local factor Gate 失败|
|N2 MPI2|not_run_by_gate|N2 MPI1 未通过|
|N3 coarse/contraction|not_run_by_gate|没有合格 N2 setup|
|N4 20/100/150/200|not_run_by_gate|没有进入物理迭代|
|T6-F/EH/RTA、T7–T9、full 0.7 nm|not_run_by_gate / not_authorized|无 official physics|

## 3. D2、A/B/C 与关闭边界

D2 trace-harmonic 路径此前以 p6 rank64 construction failure 受控停止（source cc8de60...，slab0 interior CG reason -3，固定500步用尽，peak 3,013,468,160 B）；没有重跑。D2 runner/checker及该 research path 属 research-only/do-not-merge。

T4 Robin transmission 只保留为历史 oracle，Candidate A 是完全冻结的 one forward+backward smoother oracle，不是独立 production claim。Candidate B 因 mixed Si-Si/Si-air interior interface缺少合格 interior modal authority，分类为 CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED；Candidate C 已按 review 关闭，保留源码和负证据，DO_NOT_RERUN/DO_NOT_OPTIMIZE/DO_NOT_MERGE。这些分类不是数学上的永久不可能判断。

## 4. N0 冻结设计与预算

N0 冻结的是固定 1-cell shared-row-overlap patch、cell-supported constrained auxiliary block、B0=curl-curl+k0^2 M_|epsilon|、tau=0、共享行 inverse-multiplicity PoU、levels=2、regional rank16、top rank32、每 patch 3 条坐标 gradient 加5条正谱方向（cap8）、最多32个 exact classes。每个 class 只有一个 deterministic hash owner；factor 为 lower-packed complex128 Cholesky，单 factor cap 6,230,448 B，总 factor cap 199,374,336 B。在线必须保留 regional Z16 与 top Z32/AZ32，不能把 regional 层在 setup 后释放来制造低内存数字。

|预算项目|值/口径|
|---|---:|
|T2 MPI1 current-self baseline|951,054,336 B，measured calibration/lower-bound，不是完整 process-tree 上界|
|baseline uncertainty reserve|central 32,000,000 B；hard 64,000,000 B|
|N0 central|1,698,919,864 B < 1,800,000,000 B|
|N0 hard upper|1,798,919,864 B < 2,000,000,000 B|
|N0 status|derived/budget conditional；不是本次 N2 measured pass|

N0 也明确禁止 global AIJ/Schur/factor、FE-sized numeric allgather、每 rank full basis replication和global direct coarse solve。N2 本次只走到 local factor build，不能把 N0 预算当作 N2 实测资格。

## 5. N1 已完成的代数证据

N1 正式四案为 p2/p3 × MPI1/MPI2，均 PASS。独立 UFL dual action relative error 为 p2 1.0014682260391434e-15、p3 1.2971226992449333e-15；MPI source/action identity relative values为 1.8605718413098607e-16 与 2.0089698816204241e-16，repeat exact。regional projector/packet 的 1.59451e-11 / 1.66085e-10 是记录的 diagnostic debt，不是 hard Gate，也没有被隐藏或写成 PASS。N1覆盖 gradient near-kernel、local modes、PoU、R/P 和 MPI identity；它不等价于 p6 N2 setup。

## 6. N2 formal 实际运行

|事实|值|
|---|---|
|case|p6/h10 MPI1，MPI1 only，一次尝试|
|source|907fe8fb204cffa34a921c6d0cab7ff4dd4831b8|
|marker|preflight → mesh_space_mpc → JIT → subdomain_inventory → local_factor_build → failure|
|failure|fixed RHS local factor solve residual 1.0426245523812324e-11 > 1.0e-11|
|excess|4.26245523812324e-13，约4.26245523812324%|
|worker marker wall|125.03350535 s|
|watchdog elapsed|126.7811168670014 s，127 samples|
|process-tree memory authority peak|1,506,271,232 B|
|process-tree swap|0 B|
|termination|worker 自行返回 rc=1；watchdog 未发 SIGTERM/SIGKILL，随后 already_exited、no orphan；natural_exit=false|

这是 CONTROLLED_NEGATIVE_LOCAL_FACTOR_SOLVE_GATE。它不是 2GB hard stop，也不是 solver/PDE contraction failure。1.506GB 是在 local_factor_build 失败前的 partial cold peak；没有 post-setup retained sample，因此不能宣称完整 setup <2GB。

## 7. 未执行的 N2/N3/N4 数值对象

最终 252 patch/class inventory、modes、regional Z16、top Z32、AZ32、E32、zero identity apply、post-setup retained measurement、MPI2 canonical setup identity均未运行。N3 五类 source/rho、online <2GB、N4 20/100/150/200、official PDE/physics也全部 not_run_by_gate。没有构造或宣称任何 official result。

## 8. 与既有证据的差异

M3a、Task37-extra fixed patch/factor evidence、T2/T3 exact action、Candidate A cold/warm-like peaks只能作为设计校准和历史边界：它们不能替代本次 p6/h10 complete-workflow process-tree测量。D2 的 3,013,468,160 B 是另一条已关闭 research path 的 construction negative；本次 N2 的 1,506,271,232 B 是 local factor build 早期峰值，二者不可相加，也不能互相冒充。

## 9. 资源与阶段口径

本次 watchdog 从完整时间线采样到 worker 自行返回 rc=1，资源证据为 measured。watchdog 未发 SIGTERM/SIGKILL，随后确认 already_exited、no orphan。它只证明失败点以前 peak 为 1,506,271,232 B 和 process-tree swap=0；post-setup retained、cold complete peak、factor/mode/Z/AZ/E 的同时存活账本均为 not measured/not run。环境的系统全局 swap 诊断值不替代 job process-tree swap authority。

## 10. 禁止项审计

已执行代码路径的 source/audit 保持无 global AIJ/Schur/factor、无 FE-sized numeric allgather、无 per-rank full-basis replication；但因为 N2 在 local factor Gate 前停止，不能把这些静态/已走路径审计扩展成未执行 regional/top/physical workflow 的 PASS。没有 N3 contraction、KSP/PDE 或 official physics 结论。

## 11. 修复、测试与证据身份

formal source 绑定窄 measurement/checker fix commit 907fe8fb204cffa34a921c6d0cab7ff4dd4831b8。源码收口测试为 27 passed, 1 skipped，test290 为 12 passed，并通过 p2 MPI1/MPI2 smoke、compileall、AST/diff-check；这些是本地非 CI 结果。正式 worker record、watchdog raw/compact、checker output的路径和 SHA见 local_spectral_setup.md及 compact JSON；原始大文件继续 ignored，不进入 Git。worker compact 的顶层 source identity回填缺口已如实记录，未篡改旧 raw。

## 12. 16项 Review V4 回答矩阵

|Review要求|回答|
|---|---|
|1 身份/HEAD|见§1；final docs commit由外部交付报告给出|
|2 N0–N4|见§2，N0 conditional PASS、N1 PASS、N2 controlled negative，其余按 Gate未运行|
|3 D2|见§3，D2 negative保留，research-only/do-not-merge|
|4 N0设计|见§4，参数和owner-only factor冻结|
|5 内存|N0是derived/budget；本次仅有partial cold peak，未得 retained/complete setup authority|
|6 历史差异|见§8，不混用不同阶段峰值|
|7 N1|四案 PASS，gradient/local modes/PoU/RP/MPI identity边界见§5|
|8 N2|MPI1在 local factor Gate失败；inventory、modes、regional/top、Z/AZ/E和post-setup未运行|
|9 N3|五 source/rho 全部not_run_by_gate|
|10 N4|20/100/150/200 全部not_run_by_gate|
|11 修复/回归|907fe8 fix；focused与本地回归见§11|
|12 forbidden audits|只对已执行路径和源码审计作陈述，未执行阶段不宣称 PASS|
|13 T6及后续|T6-F/EH/RTA、T7–T9、full0.7nm全部not_run/not_authorized|
|14 分类|measured：residual/peak/swap/termination；derived/budget：N0账本；failed：local factor Gate；controlled_negative：本轮记录；not_run：后续 setup/PDE|
|15 文件与选择性合入|本轮只新增 compact/doc四项；建议仅合入历史 evidence/docs，N2未资格化 runner/core保持 research-only，Candidate C/D2保持 do-not-merge|
|16 下一轮授权|不授权 T6-F；先 hold 本地 spectral family，review local factor Gate；不调参、不绕过 watchdog、不重跑|

## 13. Selective merge / final boundary

|组|本轮建议|
|---|---|
|compact evidence/docs|可作为受控负结果和历史边界合入|
|N2 runner/checker/core|research-only；local factor Gate 未资格化，不提升为 production default|
|D2 trace-harmonic path|research-only/do-not-merge|
|Candidate C|DO_NOT_RERUN、DO_NOT_OPTIMIZE、DO_NOT_MERGE，保留负证据|
|official physics/T6-F/T7–T9|not_run，不能合入为结果|

结论：Review V4 N2 在唯一 MPI1 setup 尝试中真实触发 local factor solve Gate，随后按 hard-stop 停止；没有伪造完整 setup、资源 PASS、contraction或物理结果。
