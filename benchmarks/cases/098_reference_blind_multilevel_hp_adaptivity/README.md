# Case098：无参考泄漏的多层 h/p 自适应

Case098 是 Task035e 的可审计入口。它目前只建立数据合同、严格 schema 和
独立 checker，**没有宣称任何新的 PDE、精度或资源结果**。`config.json` 中所有
正式运行状态均为 `not_run`，因此当前分类只能是
`SCAFFOLD_NOT_RUN`，`numerical_credit_claimed=false`。

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
