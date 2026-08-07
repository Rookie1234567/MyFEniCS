# Case101：Task037-extra 的 G0、G2.2、G2.3 与 G2.4 opt-in lanes

Case101 收纳四个彼此独立、显式 opt-in 的研究 lane：

| lane | 用途 | 当前边界 |
|---|---|---|
| G0 | M3a screen20 的 residual snapshot 与 contraction authority | 不产生 official RTA |
| G2.2 | primary slab14 的 full-space/trace 代数 identity | 只证明两条 action 路径一致 |
| G2.3 | primary slab14 的 full-space ILU inventory 与 retained-payload 对照 | raw consistency qualification；route 由 payload Gate 动态决定（本次为 plain full-space ILU route closed） |
| G2.4 | primary slab14 的真实 LOR edge space 与 p6 transfer build/audit | `pass_transfer_build_and_algebra_only`；factor=false；不证明 HX/V-cycle 或收敛 |

G2.2 与 G2.3 都建立在 M2c never-materialized、M3a overlap `0.125` partition、p6/h10/S、MPI1、screen20 的受限范围内。它们不会物化整个 Full3D uncondensed global `A/F`，也不会改变 ordinary defaults。G2.3 的 full-space factor 只是 inventory-only 研究对象，没有进入外层 16-slab preconditioner。

G2.4 使用同一受限 screen 范围、identity flag 与 LOR flag，明确不启用
factor-inventory flag。LOR 把每个 p6 hexa parent 细化为 lowest-order edge
网格；`T/T^H` 连接 LOR edge cochain 与 p6 full-space stored coefficients。
本轮只证明真实 slab14 的 LOR 拓扑、周期身份、可重复 action 与伴随关系可被
构造和审计，不证明 HX/V-cycle 预条件器有效，也不证明外层或物理收敛。

固定 watchdog 约束：poll `0.25` s、warning `10` GiB、terminate `14` GiB、timeout `1800` s、禁止 `--allow-swap`，因此要求 zero swap。preflight authority 与 SHA256 见 `config.json`。source SHA 必须在运行时从干净 implementation HEAD 取得，并通过 `--verified-clean-sha` 绑定；大型 raw output 只能留在 ignored `benchmarks/artifacts/`，`records/` 只保存紧凑 hash-bound JSON。

G2.3 的正式记录是 [`records/g2_slab14_fullspace_factor_inventory.json`](records/g2_slab14_fullspace_factor_inventory.json)。G2.4 的正式记录是 [`records/g2_slab14_lor_transfer.json`](records/g2_slab14_lor_transfer.json)；它绑定唯一 screen 的 raw SHA 和 corrected resource 口径。G2.5、G2.6 与 G3 尚未运行。

`test_command.txt` 保留 G0 命令，并追加 G2.3 与 G2.4 的独立命令模板。每条 heavy 命令只能在对应 clean implementation SHA 上运行一次；不要把本目录的契约文件解释为本机实测 payload 或 official RTA 结果。
