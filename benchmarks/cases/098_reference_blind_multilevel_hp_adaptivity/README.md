# Case098：无参考泄漏的多层 h/p 自适应

Case098 是 Task035e 的可审计入口。`config.json` 仍是严格的最终 campaign
ledger；其 schema 不能安全表达“current/p-shadow/h-shadow 已完成，但 selected
action、transition 和 candidate 尚未运行”的 partial progress，因此本批次没有
修改它的 `SCAFFOLD_NOT_RUN` / `numerical_credit_claimed=false` 语义。实际阶段
进度由独立、hash-bound 的
[`path_a_cycle0_v28_progress_checkpoint_v1.json`](records/path_a_cycle0_v28_progress_checkpoint_v1.json)
记录，不能把该 checkpoint 解释为完整 cycle 或最终精度信用。

“无参考泄漏”用通俗话说，就是负责自动改网格和阶次的程序在做决定时不能偷看
更精细网格的答案。这样最终候选的成功才来自误差估计本身，而不是事后针对答案
调参。Case098 把流程分成三个相互隔离的包：

1. `reference_certifier` 单独计算 p6/h10、p6/h7.5 和 p6/h5，并把结果封存在
   hidden-reference package；
2. `blind_controller` 只看当前解、残差、伴随以及 local p-shadow/h-shadow；
   shadow 是一次小范围的“如果升一阶或细化一次会怎样”的试算，用来决定下一步；
3. `hidden_auditor` 只在候选的源码、网格、阶次图、输出和资源记录全部冻结后，
   才打开 hidden package 做最终比较。

三层的 module path 固定写入 `config.json`。正式记录一旦不再是 `not_run`，
必须同时绑定相对路径、文件 SHA-256 和 40 位 source commit SHA；checker 还会
打开原始 JSON，核对其中的源码 SHA。缺少文件、hash 不符或源码身份不一致都会
fail closed。

## 固定合同

- 正式 reference campaign：p6/h10、p6/h7.5、p6/h5，Full3D static、direct
  MUMPS、MPI8、zero swap。这里的 static condensation 指先在每个单元内部消去
  不需要进入全局矩阵的内部自由度，从而减少全局矩阵行列。
- 固定低阶集合：top/bottom 两端口，`n=0`，`m=0,-1,...,-7`，即每端口
  `N=8`。不使用“显著功率”筛选，所以很弱的级次也不能被删掉。
- 两条盲起始路径：20/10/5 nm 与 15/7.5/3.75 nm；每条最多 6 个 cycle。
- 最终网格必须真正含 level 0/1/2、至少两个空间分离 patch、2:1 balance，
  并通过 periodic、material-interface、hanging-trace 与 MPI ownership 审计。
- 阶次固定为 p4/p5/p6；p-shadow 与 h-shadow 都必须有真实验证。
- hidden audit 必须通过 16/16 power、16/16 complex amplitude、完整传播谱、
  总量、场、残差和能量恒等式。
- Full3D 结构资源必须同时降低 rows、matrix NNZ、factor NNZ，并满足 MPI8
  同口径 `<=11.0 GiB`、zero swap。
- 只有 Full3D hidden audit 通过后才允许 Hybrid M120；Hybrid 还必须低于
  `7.544262 GiB`，优选 `<=6.4 GiB`。

## 文件

- `config.json`：当前 raw campaign ledger。状态与原始数值字段是 checker
  重算结论的唯一输入，不能只写一个 `pass=true`。
- `schema.json`：Draft 2020-12 严格 schema；每个 object 都
  `additionalProperties=false`，未知字段会被拒绝。
- `expected.json`：Task035e 固定阈值和身份合同，不包含测量结果。
- `records/`：以后只存 compact、hash-bound evidence；大 mesh、field、matrix、
  factor 和 timeline 仍进入 ignored artifact 目录。

运行：

```bash
cd /home/Projects/MyFEniCS
source scripts/activate_myfenics_wsl.sh
python -m benchmarks.task035e_case098_checker
```

当前命令应以退出码 0 报告 `evidence_valid=true`，但
`completion_pass=false`。若需要把“完整 Task035e 已完成”当作命令 Gate，可加
`--require-complete`；在当前 scaffold 上它应返回非零。证据结构有效与正式研究
完成是两个不同概念，前者绝不能被当作数值信用。

普通求解默认保持不变；Case098 的所有入口均为 opt-in。本 scaffold 不修改
ordinary default，也不把未运行项、受控资源停止或失败记录提升为 production
能力。

## 2026-07-29：Path A cycle 0 v28 离线检查点

本检查点只重放既有 v27/v28 raw artifact，没有重新运行 PDE。数值 authority
固定为
`f1ba5627f163da54fa383b43be58fd38c0da7bc9`；生成本 compact 前的最新提交
`34445a50c888bd36918929f8bd0353f4a8816075` 只属于 documentation/evidence，
不改变 numerical source identity。

```text
Path A cycle 0:
    current = pass
    p-shadow = pass
    h-shadow = pass
    cellwise_partition = offline compact replayed
    selected_action = not_run
    transition = not_run
    candidate = not_run
    cycle_advanced = false

Path B:
    no new v28 run
```

Path A 三个 MPI8 stage 的 compact 资源/结构口径如下。峰值均为 simultaneous
process-tree RSS 与同一时刻八 rank smaps PSS/USS；swap 单列。`solver RSS` 是
求解阶段峰值，`total RSS` 包含 controller/postprocess 生命周期。

| stage | leaves；p4/p5/p6 | FE DoF | rows | matrix NNZ | factor NNZ | residual | total RSS / PSS / USS (MiB) | solver RSS (MiB) | wall (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current | 160；24/136/0 | 59,264 | 20,202 | 10,798,392 | 41,217,460 | `1.373246e-12` | 8,368.988 / 6,491.735 / 6,234.652 | 7,538.484 | 239.304 |
| p-shadow | 160；15/138/7 | 62,284 | 20,564 | 11,084,868 | 43,034,248 | `1.873484e-12` | 8,345.027 / 6,955.710 / 6,847.707 | 7,832.352 | 236.323 |
| h-shadow | 181；24/157/0 | 66,434 | 22,189 | 11,821,621 | 41,744,755 | `1.671519e-12` | 10,482.977 / 9,541.340 / 9,394.934 | 7,766.582 | 395.487 |

三者均为 zero swap，residual、energy、periodic/Floquet、hanging、ownership 和
2:1 Gate 通过。h-shadow 的 whole-job RSS 为 `10.237282 GiB`，低于
`11.0 GiB` 上限约 `781.023 MiB`。完整 R00/R/T/A、phase-exclusive timeline
和 raw 文件绑定见 stage authority，不在 README 复制第二份易漂移的全量表。

59-goal endpoint DWR 对 p-shadow、h-shadow 均为 `59/59` factor-two-or-neutral，
无 opposite-sign；两个 cellwise partition 各覆盖 current 的 160 个 leaves，
并明确把 global endpoint closure 与 actual residual-adjoint cellwise
attribution 分开。离线 marking 得到：

- p-up：正式 equal-weight Dörfler marked set 为
  `r13:l0`、`r37:l0`、`r42:l1:j0`、`r42:l1:j1` 四个 canonical cells，
  无附加 closure；
- h-refine：仅为 `REFERENCE_BLIND_VERIFICATION_ONLY`，target 是
  `cell:r47:l1:i1:j0:k1`，并带一个 periodic closure
  `cell:r45:l1:i0:j0:k1`；
- preflight 建议未来若获授权先单独验证 selected-p；selected-p 与 selected-h
  没有合并，二者均未执行，也没有写 transition 或运行 candidate。

Path B 没有 v28 新运行。v27 local evidence 只允许登记为 partial：
current/p-shadow pass，h-shadow 在 `11.055027 GiB` 触发 controlled resource
stop，未形成 h evaluation/bridge，`cycle_complete=false`。

### Compact evidence 索引

- [Path A stage authority](records/path_a_cycle0_v28_stage_authority_v1.json)：
  command、ABI、MPI、raw SHA、结构、数值、资源与 phase-exclusive timing。
- [59-goal DWR](records/path_a_cycle0_v28_59goal_dwr_compact_v1.json)：
  完整 inventory、三组目标值、signed DWR、endpoint delta、effectivity 和
  cellwise/global 分离证明；不含 hidden reference。
- [cellwise marking](records/path_a_cycle0_v28_cellwise_marking_v1.json)：
  全部 p/h 候选的 topology、closure、59-goal signed contribution、成本、
  eligibility、ranking 和 marked set。
- [action preflight JSON](records/path_a_cycle0_v28_action_preflight_v1.json)
  与 [Markdown](records/path_a_cycle0_v28_action_preflight_v1.md)：冻结两个互相
  独立、尚未执行的 selected-p / selected-h component。
- [sealed reference manifest](records/task035e_sealed_reference_manifest_v1.json)：
  只提交 p6/h10、h7.5、h5 的运行身份、Gate 状态和 47 MB package 的
  path/size/SHA；package 本体、reference 数值、逐通道值、场和 error map
  均未提交。
- [Path B v27 partial authority](records/path_b_cycle0_v27_partial_authority_v1.json)：
  保留 h-shadow controlled resource stop，不冒充 cycle 完成。

所有 JSON 使用显式 canonical payload SHA，并继续绑定 ignored raw artifact 的
相对路径、字节数和 SHA-256。raw 缺失、损坏或 hash 漂移时必须 fail closed，
不得通过重跑 PDE 或人工复制 summary 数字补齐本检查点。
