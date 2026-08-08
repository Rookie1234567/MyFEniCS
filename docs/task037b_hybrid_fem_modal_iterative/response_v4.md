# Task037b Review V3 response v4：双侧 fixed block-PC formal screen

## 结论

本轮对 Review V3 无算法异议。按授权只运行了一次冻结的 MPI8 double fixed-action
screen，没有 wiring retry、参数修改或第二次数值运行。

| 分类 | 结果 |
|---|---|
| numerical | pass |
| disposition | `DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW` |
| MPI8 resource | negative；process-tree peak=6.296966552734375 GiB，超过6.0 GiB |
| engineering / stretch | false / false；分别未达到5.0 / 3.77 GiB |
| official physics | field、R/T/A、A_volume、diffraction orders、12+12、Full3D comparison 全部 not_run |
| ordinary defaults | unchanged |
| master merge / production qualification | not authorized |

资源负结果没有改写 numerical pass。它表示本次双侧结构超过独立资源线，需要后续 review，
不是数学算法失败。

## 冻结身份与运行

source 为 `c7b6aa3ddaac4dbfb9f86aab8f59801330d63a16`，parent 为
`9e01280df6c241932242a75d70db27210ceed46e`，branch 为
`codex/20260807-task37b-hybrid-iterative-development`。配置保持 p6/h10、modal p6/h10、
13.5 nm、S、10°、10/110 nm、M120/candidate240、external modes/endcap=40、MPI8、
static-condensed、full3d_uniform_cg/scalar_cg_discrete_derivative、right FGMRES restart90、
rtol 1e-6、atol 0、zero initial、max_it 200。

固定 callback 的 wrapper 每次只调用一次 `HybridLocalDtnWoodburyOracle.apply`；没有
`HybridLocalDtnWoodburyLocalInverse.solve`、nested local FGMRES/KSP、fallback 或 ordinary
default 改动。Full3D 与 preflight authority 只做身份 hash 核验，没有做 Full3D comparison。

## 数值与结构证据

| Gate | raw measured/derived result |
|---|---|
| 20/60/100/200 | r=0.47312934919147054 / 0.11272071486850113 / 0.022267181511852894 / 0.0015751888272117643；全部通过 |
| q | q(10:20)=0.9691128074667947；q(40:60)=0.9600584620850824；q(160:200)=0.9761276804881517 |
| prediction | 120–200 共81点；slope=-0.026952007757600222；q_fit=0.9734079564339503；predicted total=469 |
| callback | identity=0；linearity=1.965777991868971e-15 / 1.9934804460145754e-15；determinism=0；repeat hash一致 |
| K | rank=40；condition=3.0331668903694338 / 4.162687539173755；arrays finite |
| modal Schur | 240×240、complex128、rank=240、condition=1845.7878710427701；matrix/LU repeat error=0 |
| factors | bottom/top direct=0/0、ILU=1/1；global direct=0；global A=false；F=false/false；explicit C/D=0/0 |
| online apply | 两侧 487→887，increment=400，expected=400；build apply=480/侧 |
| lifecycle | factor 1→0、released；outer context/RHS/matrix释放；worker/process group exited；no orphan |

完整 17 checkpoint 由 compact record 保存；完整 201 行 scalar history 保留在 hash-bound
raw solver record，不复制进 tracked JSON。V3 停在正常 max_it=200，PETSc reason=-3，
progressive stop cause=None。

## 资源与时间

process-tree RSS peak 为 6448.09375 MiB；worker RSS/PSS/USS simultaneous sums 最大值为
6433.4375/5335.591796875/5153.04296875 MiB；swap=0，warning、memory、timeout、authority
termination 均未触发。总耗时为 344.5687012251001 s；action/coupling、V3 setup、outer
screen、release 分别为 211.2913892850047、47.30083924799692、32.7934253399726、
0.0009031089721247554 s。

相对 V2-B/T 的 7.9730224609375/8.532058715820312 GiB，V3 约低21.0%/26.2%；V2含一侧
direct factor，故该比较不能外推双侧性能。

## 测试与停止边界

最终 serial 为 46 passed；MPI1、MPI2、MPI4 的 test239+test241+test242 均为 13 passed
per rank；Ruff check、Ruff format-check、五文件 py_compile、git diff --check 全部通过。
没有运行 full pytest、test240、额外 PDE、field、R/T/A、12+12 或 Full3D comparison，也
没有开始 H6–H10。该 response 不修改 response_v1–v3、旧 H5b/R5 事实或 Review V3。

## 证据索引

| artifact | SHA256 |
|---|---|
| [compact record](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v3_double_block_pc_screen_v1.json) | tracked hash-bound evidence |
| [solver record](../../benchmarks/artifacts/task037b/v3_double_block_pc_c7b6aa3_mpi8/solver_record.json) | `df54c36ccca35a79b61bbd3fcf4dde47222aae0574b5d7c09ded1444ec7fc3d0` |
| [summary](../../benchmarks/artifacts/task037b/v3_double_block_pc_c7b6aa3_mpi8.json) | `49343b30ec892b9f3a06b525b1535467f70b87637f5f73daf6d499a185a608fe` |
| memory stages | `47b4127b1bec86eb44012fbf0a906afd0710889d674e8d0aaa1b9ebadf9238ec` |
| memory timeline | `e6eca60fd6caf35bf9a8d29bfa23a99dc1c0422d5dfe93b73db0976082173dc1` |
| worker stdout | `5b7c57c38969540da4e49a642969e747eb84cca859b92370f05210988fa9d6bf` |

主审在下一轮 review 前未授权任何 full physics、资源调优、候选扫描或 production promotion。
