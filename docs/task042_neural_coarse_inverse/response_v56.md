# Response V56：完成已有H7物理消费，独立判断h一致性与跨p分歧

本轮没有重新求解H7。其完整体吸收、固定240点、828模式、全域E/H/curl比较以及独立未凝聚原式/恢复已经完成。H7新true/native=3.939586167942246e-11，体吸收0.018135719038380065，能量差-1.249000902703301e-13。R7→H7同p7、同828模式沿z加密，散射E/H增量1.97369e-5/2.00352e-5及全部功率门通过；R6→H7跨p散射E/H差0.0340891/0.0340600，仍FAIL。高p未指定为真解，完整场准确性与原方程残差分开验收。

唯一T6已从物理零初值合法返回并保存，x轴沿V55冻结决定，32类新raw均保存/重开；原两父包没有匹配类。R6→T6同p6横向散射E/H差7.46595e-4/7.35082e-4，超过1e-4，固定点6.24562e-4也FAIL；复通道3.29229e-5、单mode功率1.53963e-7及R/T/A/A_volume增量通过。R7→T6跨p散射差约3.38%，场、复通道及功率增量仍FAIL。材料、相位弱式、内部自由度、MPC和所有828端口不变；旧H7/R6/R7/C没有重解。

直接求积是读取真实有限元场后按原吸收公式积分，避免为标量再编译大FFCx form。R7与旧定义操作差9.56523e-16，H7少量真实点新旧E/H/curl差4.17635e-15。体吸收不是1-R-T，也不是散射场积分。独立PUBLIC_BASIX_UNCONDENSED_AUDIT生成完整体向量并加全部q63端口，没有构造原全局矩阵/因子来自证；旧FFCx重运行仍not_run。

凝聚复用原既有链，先消去每个单元内部未知量，再完整恢复；没有新做邻支粗逆/端口或PC研究。H7本轮raw/factor/solve全部0。T6有限直接法确实构造全局有限authority因子，合法返回后已释放；不能称factor-free或原尺寸可扩展资格。跨支线分工以Review V54只读冻结记录为准，不操作其他工作树。

S的dat费用下界3446.328207341023s、采样树峰3420106752B、ownswap0。旧H7 raw12393.272463684902s、旧dat下界13627.054710610071s保持；14.232067284057848s只是末端solve/精化。T6、补消费、VERIFY、辅助与全部失败成本在最终费用表分列，inclusive嵌套计时不重复相加。缓存增量、研究总量和必要fresh冷N=1不同，unknown不填0，shared-workstation不声称无争用加速。

两桥接尺度s=14/135、28/135只生成布局与模式库存，没有目标mesh/向量/PDE。规则推导完整模式3060/11748，s=1为268156，不硬抄旧32060。p6/p7目标FE容量、流式DtN和恢复库存已列出，factor fill、迭代数、同时峰及48h费用unknown。原尺寸0.7nm、2TB/48h、NN20%均未资格；本批没有NN训练或NN收益。

科学source：H7原solve5e61f1acf569bf43b33bceeebcc949e1b0f1efc9；新S consumer aed40a1549e394c5c6f539a50e3aba7cfc20b6ef；T6 source0d4d2366a11bca50e2d3244e5863a34713e01904。Review18e597ba6f3193f1c54a292a258d9af8891c9c84、base ccd357885f7f9be84efe3be07868cc94f13d93fc；最终文档HEAD另见交付Git回执，不替代运行source。13项focused测试、相关Ruff/compile和3入口validate通过，无full pytest/CI或父PDE重放。GitHub精确页视觉NOT_VERIFIED。

横向h增量未过门，不能声称两个h方向都收敛；约0.0747%的横向散射差仍远小于约3.4%的跨p差，尚不能确定唯一根因。唯一下一建议是冻结R6/T6/R7/H7，用同一组预登记、Bloch兼容的连续Maxwell试验函数做共同弱平衡见证，包含端口非零函数，拆分x向/材料界面、体和DtN作用尺度；不加p8、Z8或模式，不自动实施。

完整S/T6/VERIFY已完成，科学队列冻结。完整证据见[专题结果](outcomes/saved_field_closure_target_bridge_v56.md)、[独立门与负结果](outcomes/records/gate_verdict_v56.json)、[全部费用](outcomes/records/resource_costs_final_v56.json)、[目标缺口](outcomes/records/target_gap_final_v56.json)及[交付索引](outcomes/records/delivery_index_v56.json)。本批交付后暂停，不通知隔壁、不merge、不自动打开新窗口。历史task/review/response/raw保持。

T6独立原式true/native=3.804162835310969e-11、augmented=2.263316037822323e-10、port=8.581616871847102e-13，恢复max=1.2559193728431046e-15；冻结后的数组checker同样通过正式1e-6/恢复1e-10门，all-row直接1e-10目标仍FAIL。独立VERIFY只消费已存数组，新增FE作用/factor/solve均0。

T6 dat下界8369.145540053956s（监督8348.37352103996s），采样整树峰16319598592B=15.198810577GiB、ownswap/OOC0；S峰3.185 GiB。实际最大采样间隔9.566582937957719s，不将0.5s配置称连续硬峰。新全局numeric因子1次，legacy factor=3指1次MatSolve加2次精化，不是3次numeric。收尾相对路径/manifest字段错误同轮定点修复，失败和重复元数据费用全保留，没有科学重放。
