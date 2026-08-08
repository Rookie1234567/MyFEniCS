# Task037b H7-H10：双侧 iterative funnel 边界

## 停止矩阵

H7-H10 依赖 H5 双侧 local inverse 先通过。本次 bottom 与 top 在同一冻结 p6/h10、M120、MPI8 配置下均未资格化，因此后续 funnel 不启动。

| 阶段 | 状态 | 直接原因 |
|---|---|---|
| H5b | `LOCAL_INVERSE_FAMILY_NEGATIVE` | bottom 1/11、top 0/11；非零 RHS 在 300 iterations 后仍为 reason=-3 |
| H5c | not_run | H5b numerical Gate 未通过 |
| H6 | not_run | H5 双侧失败触发停止 |
| H7 | not_run | 同一前置停止点 |
| H8 | not_run | 同一前置停止点 |
| H9 | not_run | 同一前置停止点 |
| H10 | not_run | 同一前置停止点 |

这里的 funnel 是任务书规定的后续逐级验证，不是已经存在的失败算法结果。不得用 H5 candidate 的内存记录或重复解一致性替代后续数值 Gate。

## 边界

H5 candidate 使用的是唯一冻结的 partition ASM + shifted ILU(0) family；本负结论不否定 Hybrid 模型、exact block action、exact block-LDU，也不证明任何未经授权的 PC 家族不可能。若后续需要恢复 H7-H10，必须新建 review，重新指定算法与 Gate；本 docs closeout 不扩大范围。

参见 [H5 local matrix evidence](local_endcap_inverse_matrix.md)、[总览](summary.md) 与 [测试汇总](test_summary.md)。

## Review V2 单侧 Gate 后的停止

V2-B bottom approximate 通过 20-step screen，V2-T top approximate 的
final/min true residual 为 0.3518371324843258。它虽从 0.428252 降到 0.351837，
仍严格高于 0.35，因此两侧不是都通过。按 Review V2 §6.3，唯一正式分类是
TOP_APPROXIMATE_SIDE_NEGATIVE。

| 后续 profile | 状态 | 原因 |
|---|---|---|
| double / max_it=20 | not_run_due_to_one_sided_gate | V2-T 严格 0.35 Gate 未通过 |
| double / max_it=100 | not_run_due_to_one_sided_gate | 同一前置停止点 |
| double / max_it=200 | not_run_due_to_one_sided_gate | 同一前置停止点 |
| full Hybrid solve、R/T/A、field、12+12、Full3D comparison | not_run | V2 bounded screen 不是 official physics |

V2-B/T 的 callback、modal Schur、factor identity、online apply count、lifecycle、no-swap
与 no-orphan 合同均通过；V2-T 的失败只属于 fixed top approximate side capacity。
因此结论是 exact matrix-free block operator pass、exact block-LDU pass、DtN Woodbury
algebra pass、bottom fixed approximate one-sided capacity pass、top fixed approximate
one-sided capacity negative；双端低内存近似逆资格未证明。

两侧 process-tree peak 都超过 6 GiB standalone resource-positive 参考线，故没有
resource-qualified candidate。T 的较高峰值包含一个 exact bottom direct factor，不能拿
它预测未来 double screen。LOR、AMS/HX、p2/p4、p-multigrid、full-space ILU 继续冻结，
不因本次 stop 重新开启。

V2-B/T 的完整 0–20 history、raw artifact 路径和 SHA 见
[V2 compact record](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v2_block_pc_screen_v1.json)。

## Review V3 双侧 fixed block-PC formal screen

V3 只运行一次冻结的双侧 approximate screen：bottom/top 均使用 whole-endcap ILU(0) 加
40-mode DtN Woodbury fixed action，外层仍是 exact matrix-free Hybrid operator。它不是
official field 或 R/T/A 求解；它回答的是两个不保留 direct factor 的近似端盖 action 是否
能在同一个 right FGMRES 中持续收缩。

| Gate | raw 结果 | 分类含义 |
|---|---|---|
| 20-step | pass，r20=0.47312934919147054 | 继续运行 |
| 60-step | pass，r60=0.11272071486850113 | 继续运行 |
| 100-step | pass，r100=0.022267181511852894 | 继续运行 |
| 200-step | pass，r200=0.0015751888272117643 | numerical pass |
| 120–200 prediction | 81 点，predicted total=469 | `<=3000`，pass |
| lifecycle / direct inventory | direct=0/0、ILU=1/1、factor 1→0 | pass |
| MPI8 resource | 6.296966552734375 GiB，`>6.0 GiB` | resource review，不能改写 numerical pass |

停止点是正常达到 max_it=200（reason=-3），不是 progressive hard stop；没有 wiring retry、
调参或第二次 numerical run。V3 的正式研究分类为
`DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW`。它仍等待下一轮 review，不自动
启动 full solve、field、R/T/A、12+12 或 Full3D comparison。

### V3 raw checkpoint table

下表直接取 hash-bound solver record 的 Review V3 checkpoint；完整 0–200 scalar history
仍保留在 raw `solver_record.json`，tracked compact record 只保存这些 17 个审查点。

| i | reported | global true | bottom true | top true | modal true | PC | bottom action | top action |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1.0000000000 | 1.0000000000 | 0.0000000000 | 1.0000000000 | 0.0000000000 | 0 | 487 | 487 |
| 1 | 0.9035588867 | 0.9035588867 | 0.9199767157 | 0.8989459516 | 5.1027006533e-15 | 1 | 489 | 489 |
| 2 | 0.8254072728 | 0.8254072728 | 0.8891214437 | 0.8167095278 | 3.9787740477e-15 | 2 | 491 | 491 |
| 5 | 0.7432234661 | 0.7432234661 | 0.7937353828 | 0.7361271450 | 3.1375849746e-15 | 5 | 497 | 497 |
| 10 | 0.6474952072 | 0.6474952072 | 0.8328767179 | 0.6316548316 | 3.0944419643e-15 | 10 | 507 | 507 |
| 20 | 0.4731293492 | 0.4731293492 | 0.7915576230 | 0.4144951476 | 2.9323935660e-15 | 20 | 527 | 527 |
| 30 | 0.3509431620 | 0.3509431620 | 0.6383629390 | 0.2614361452 | 2.8203184489e-15 | 30 | 547 | 547 |
| 40 | 0.2547124284 | 0.2547124284 | 0.4584306249 | 0.1706945895 | 2.4479476607e-15 | 40 | 567 | 567 |
| 60 | 0.1127207149 | 0.1127207149 | 0.2032001429 | 0.0666591388 | 2.6900296771e-15 | 60 | 607 | 607 |
| 80 | 0.0478583969 | 0.0478583969 | 0.0672790625 | 0.0349983452 | 3.0253300615e-15 | 80 | 647 | 647 |
| 90 | 0.0276149305 | 0.0276149305 | 0.0352600400 | 0.0211375750 | 2.8102480451e-15 | 90 | 667 | 667 |
| 100 | 0.0222671815 | 0.0222671815 | 0.0242705221 | 0.0179188417 | 1.9895321084e-15 | 100 | 687 | 687 |
| 120 | 0.0122180638 | 0.0122180638 | 0.0137107586 | 0.0097664053 | 1.8237692654e-15 | 120 | 727 | 727 |
| 150 | 0.0056879651 | 0.0056879651 | 0.0080049573 | 0.0041875336 | 1.3241490823e-15 | 150 | 787 | 787 |
| 160 | 0.0041406401 | 0.0041406401 | 0.0064708977 | 0.0028680677 | 1.5071948659e-15 | 160 | 807 | 807 |
| 180 | 0.0021352400 | 0.0021352400 | 0.0034667266 | 0.0014398014 | 1.3148561364e-15 | 180 | 847 | 847 |
| 200 | 0.0015751888 | 0.0015751888 | 0.0024392067 | 0.0010989266 | 1.3255213075e-15 | 200 | 887 | 887 |

q(10:20)=0.9691128074667947、q(40:60)=0.9600584620850824、q(160:200)=0.9761276804881517；
last20/last40 均净下降。120–200 的 log-linear fit 为 81 个 true-residual 样本，
slope=-0.026952007757600222、intercept=-1.1807285796358524、q_fit=0.9734079564339503，
predicted wall=77.27288482312974 s。

两侧 callback identity error=0、linearity error 分别为
1.965777991868971e-15/1.9934804460145754e-15、determinism=0、repeat hash 一致；K
rank=40，condition=3.0331668903694338/4.162687539173755。modal Schur 为
240×240、complex128、rank=240、condition=1845.7878710427701，matrix/LU repeat error
均为0，build apply=480/侧。online 两侧均为 487→887、increment=400、expected=400；
base ILU factor 各为1，local direct=0，nested KSP=false。

V3 process-tree RSS peak 为 6448.09375 MiB（6.296966552734375 GiB），worker RSS/PSS/USS
simultaneous sums 的最大值为 6433.4375/5335.591796875/5153.04296875 MiB；swap=0，
warning、memory/timeout/authority termination 均未触发，worker 与 process group 均正常退出、
无 orphan。相较 V2-B/T 的 7.9730224609375/8.532058715820312 GiB，V3 约低 21.0%/26.2%；
该比较是 derived 且不等价外推，因为 V2 各含一侧 direct factor。

Compact hash-bound evidence 见
[V3 record](../../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v3_double_block_pc_screen_v1.json)；
raw solver、summary、timeline、stages 和 stdout 的 SHA 见该 record。V3 仍是 research-only，
ordinary defaults unchanged，master merge 未获授权。
