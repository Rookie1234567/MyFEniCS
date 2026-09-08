# Response V5：V4诊断完成，真实散射误差仍缺匹配参考

| 交付 | 结果 |
|---|---|
| 正式source | `b127546f172e46d0b217680338b4e0ea7aa39f12`，task39extra；base `2dc2e7305f10dc391a13970c6f0f0340cb87b6ee` |
| C0 | 默认strict不变；显式最多2次精化、失败前保存、局部拒绝隔离与相同拒绝RHS精确去重；首批23通过/5写包失败，修复后定向7通过；compileall/diff通过 |
| C1/C2 | 旧7响应/3identity按hash复用；M0投影110步166.845121 s，残差9.27038e-11、eta_space=0.084774901；先于物理p4 LU完成 |
| C3 | 8PC完成、4互补、10逻辑p4/12MatSolve；重建原回代1.0086968840613473e-10>1e-10，一次精化9.492574739321824e-13；原始与修正向量分存 |
| 数学结果 | 人工e上eta_G=0.092065368，range identity3.92727e-13；互补场误差剩余约0.942/0.934；真实残差LIGHT/JOINT比0.999706716/0.999674195 |
| C4 | 现有2D截面QEP不支持规定3D Bloch控制；保留相消及表示/响应数据，UNRESOLVED，无新本征平台 |
| 资源/清场 | 3936采样，RSS峰3540959232 B、cap最低8314208256 B、reserve4GiB、swap0、违规0；父进程及两个后代均清场 |
| 时间/终态 | outer保守1130.973242739 s<5400；新7200 s批账审计时1142.571742356 s；worker DIAGNOSTICS_COMPLETED_WITH_LIMITATIONS，watchdog/launch COMPLETED、exit0、cleanup无异常 |

投影用不含材料权重的L2尺子找p4最佳表示；粗修正则解实际p4方程。二者在这个人工已知误差上均较好，不支持强行认定严重p4色散/粗层失配。H6/S6虽明显减少方程残差，却只减少少量互补场误差。粗方向MR也把场误差比0.092→0.213而残差改善，这是优化目标不同，不是MR已证bug，生产公式未改。

一次p4精化闭合局部门槛，仍未使真实残差单次PC响应远离1；不能据此宣称完整p6收敛或official通过。人工e不等于实际散射误差。本轮唯一优先后续是取得同A6、同b、同1°的匹配fine参考/真实误差，再复用保存的packet定位；不追加PC、迭代或PDE。参考取得成本及迁移条件需下一review冻结。

完整原因矩阵、方法解释、各控制数值、分阶段成本、单位、selective merge依赖及局限见[中心说明](outcomes/diagnostic_completion_v4.md)和[中心JSON](outcomes/records/diagnostic_completion_v4.json)。新raw根目录、全部哈希、资源与host清场由中心JSON绑定的 `completion_audit.json` 提供；旧V3/review/response/raw及C0初次失败均未改写。最终只更新固定8份文档/索引，轻量静态检查不重新运行FE/PDE。无full repository/Ruff安装/CI通过声明。

代码与证据普通提交至task39extra并推送；精确交付HEAD、upstream与工作树状态在交付消息报告，不merge master，等待review。
