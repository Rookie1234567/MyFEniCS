# Case104：5 nm Hybrid side inverse（active research controlled identity negative）

## 物理问题

Case104 研究在冻结 Task039 的 5 nm、1° grazing、phi=0、S polarization、p6h4、M480 和
MPI8 条件下，能否用较低内存的 iterative side inverse 替代完整 bottom/top exact side
factor。当前登记的正式证据是 V4-1 controlled identity negative：旧 exact spool 的文件和
hash 可以核对，但没有把旧 PETSc row 绑定到稳定 H(curl) 物理自由度的 canonical source-row
bridge。

## 参数说明

物理方程、材料、几何、p/h、M、external keys/order、DtN、modal Schur、global Hybrid
operator 和 ordinary defaults 均保持不变。V4-1 的 formal source 是
`9f3d6e39cb607125a773b35d9a2a9f7459c7f2dc`，checker source 是
`4b70adfb6707464aaed4309ece5bca179dd60b57`。

## PyCharm

本 case 只用于仓库内的配置、证据和轻量合同检查。需要查看结果时从仓库根目录打开本目录；
不得把 ignored full field、factor 或结果目录加入 Git。

## CLI 或测试

`test_command.txt` 只运行两个 JSON 格式检查：

```text
python -m json.tool benchmarks/cases/104_5nm_hybrid_side_factor_pc/config.json && python -m json.tool benchmarks/cases/104_5nm_hybrid_side_factor_pc/expected.json
```

它不调用 `mpiexec`、`run_3d`、watchdog、PDE 或任何 heavy solver。V5 后续的 fresh bare-F
authority 仍须按新 review 的 preflight 和独立证据执行，不能由本命令代替。

## 代码路径与理论

V4 opt-in diagnostic route 位于 `benchmarks/task040_level_a.py` 与
`benchmarks/task040_level_a_watchdog.py`，fail-closed identity helper 位于
`src/solvers/hybrid_exact_authority_compat.py`。这些路径不是 ordinary production default。
后续 canonical bridge 必须绑定 source SHA、覆盖当前 active rows、处理 orientation/Floquet
语义并通过 round-trip；不得使用跨布局 raw global-row remap。

## 当前证据

受控记录为
`records/task040_v4_1_exact_authority_compatibility_v1.json`，SHA256 为
`5ededd4bb9acfb9e4e3a403a410cecb37fb1490e7bf6056ca4644c7bfda7c36a`。其 classification 是
`EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F`，唯一 identity failure 是
`CANONICAL_SOURCE_ROW_BINDING_UNAVAILABLE`；compact record 保持为唯一轻量 V4-1 authority。

## 结果解释

V4-1 在 system、bare `F`、interface mass、PETSc Vec、factor、QEP 和 PDE 之前停止。因此
bare-F/A-side residual、trace、dual、projection、lift、FGMRES、coarse、Level B、full Hybrid
和 h3 没有数值结果。`V4-2` 至 `V4-10` 均为 `not_run_by_v4_1_identity_gate`，不是算法失败。

## 限制

```text
status                   = active_research_controlled_identity_negative
canonical                = false
production_qualified     = false
ordinary_default_changed = false
pde_run_in_v4            = false
```

Case104 不能证明 0.7 nm production 可行，也不能证明旧 vectors 数值错误。若继续 V5，应按
当前 Review V5 先完成 operator-semantics audit，再做 fresh current-layout bottom bare-F
authority；旧 raw-row remap 仍禁止，旧 source-row bridge 不再是主路线。当前 V4-2 至 V4-10
仍保持 `not_run_by_v4_1_identity_gate`，后续路线须服从新 authority 的 Gate。
