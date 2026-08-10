# Case101：Task037b V1 iterative block solver research closeout

Case101 只是一个可审阅的 research closeout 载体，不是 active benchmark、production
candidate，也没有运行入口。它把 Review V1 的 R1–R5 raw evidence 以固定 source SHA、
artifact SHA256 和 compact record 绑定起来，便于复核负结果。

## 冻结身份

| 项目 | 值 |
|---|---|
| 物理条件 | p6/h10、modal p6/h10、M120/candidate240、MPI8、S、10° grazing、10/110 nm |
| 离散与模型 | static-condensed、full3d_uniform_cg、scalar_cg_discrete_derivative |
| authority | 与前序 H3/H4 相同的 Full3D pinned reference 与 historical preflight |
| R5 source | 2a2ef3d37514e4ab30d50209065af84c1dafd59b |
| R5 结果 | WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE |
| ordinary defaults | unchanged |
| master merge | not authorized |

compact evidence：[task037b_v1_r1_r5_research_closeout_v1.json](records/task037b_v1_r1_r5_research_closeout_v1.json)。

## 结论边界

R1 的 F/C/D/H action 分解通过；R2 的六-slab F-only 与 R3 的 whole-endcap ILU(0)
均未达到 local true-residual Gate；R4 的 exact F inverse Woodbury 与 exact A 一致，证明
公式、符号和 ownership 接线正确；R5 的 DtN-aware whole-endcap ILU(0) PC 虽然线性、
确定性、40-mode K、factor lifecycle 与独立资源 Gate 均合法，但 21 个非零 RHS 为
0/21。该负结果只关闭本任务冻结的 iterative candidate，不否定 Hybrid 模型或 Woodbury
公式，也不授权新的算法家族、扫描或生产化。

R5 official R/T/A、field 和 12+12 未运行；H6–H10 按 stop rule not_run，后续若要新
算法家族必须取得新的 review。详细逐 RHS 表见
[local endcap evidence](../../../docs/task037b_hybrid_fem_modal_iterative/outcomes/local_endcap_inverse_matrix.md)，
总回应见 [response_v2](../../../docs/task037b_hybrid_fem_modal_iterative/response_v2.md)。

## V7 后 MPI scaling diagnostic

V7 结项后另行授权的 MPI1/2/4/8 对照冻结同一 M10 Hybrid iterative candidate，只改变 MPI size；这是 research-only evidence，不是 active benchmark、production qualification、continuum/mode-count 结论，也不改变普通默认路径。

- [scaling compact](records/task037b_v6_mpi_scaling_1_2_4_8_v1.json)
- [scaling report](../../../docs/task037b_hybrid_fem_modal_iterative/outcomes/mpi_scaling_comparison.md)

四路唯一 aggregate checker `pass=true`；完整 process-tree peak、residual、traction、R/T/A、timing、authority 与 source boundary 以 compact/report 为准。MPI8 raw source 为 M10 `b291f3d`，MPI1/2/4 为 `28cbead` scaling carrier；不可简称为同 SHA 四次 formal。
