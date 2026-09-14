# V19 selective merge边界：等待审阅，未批准master合并

准确凝聚已在固定original p6/h10完成A6、完整物理和资源验证；notch被外部父监控失联中断，按最新用户指令不再恢复。以下仅为审阅依赖组，不是合并授权。

| 依赖组 | 内容 | 数值变化、依赖与验证 |
|---|---|---|
| production numerical/core | 普通默认不提升；无默认PC切换 | 固定original证据不等于任意几何/0.7nm的production资格 |
| reusable numerical/core | `hcurl_assembly_time_condensation.py`显式选项、`FullspaceSplitVolumeAction.bilinear_form`、`p4_cell_condensed_inverse.py` | 先组合完整张量再消元、MPC/非零RHS/左右端口/恢复；依赖现有carrier与LU；小fixture、U2六调用和original完整结果支持；旧默认保留 |
| reusable runner/watchdog | V18 worker、薄dispatch、既有outer stack、V18 ledger；observe_only参数与finish_pc异常保留；`scripts/run_case_in_user_service.sh` | 不加新算法；计时修复已由original第三次验证。新shell仅把原launcher交给user systemd立即执行，无timer；仅ABI/help验证，无full PDE服务资格；依赖core/profile和用户systemd |
| checker/benchmark | `check_p4_cell_condensed_v18.py`、新dat/schema和测试 | 重算control及fullspace保存证据；依赖原始schema/hash；106项最终相关测试、28项checker/ledger及original独立PASS |
| compact evidence/docs | response_v19、outcomes、compact/decision、run_index增量、progress/registry、轻量残差PNG | 保留全部负结果、费用及unknown；准确source/原始hash索引；可单独审阅，先后于对应core均可但须保持依赖说明 |
| research-only | V18 exact/BLR及original/notch显式入口 | exact控制等价且省内存、original完整通过；BLR无额外收益不提升；notch未最终资格化，用户已关闭续算 |
| do-not-merge | 大型ignored vectors/matrices/factors/timelines、工程脚本、未使用重放草稿、任何production默认切换 | 不提交大raw；不扩epsilon/rank/步数；不把未执行的恢复草稿作为已验证功能 |

建议审阅顺序：core→profile/runner→checker与测试→compact/docs。只有审查批准和用户授权后才另行合并；当前全部提交留在task39extra，不影响5nm线。完整源SHA、base、测试与fresh PDE证据见[response V19](../response_v19.md)。
