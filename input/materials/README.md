# Si 光学常数的唯一离线入口

canonical 文件为 [si_optical_constants_v1.json](si_optical_constants_v1.json)，ID 为 `SI_OPTICAL_CONSTANTS_USER_20260929_V1`。它永久保存原始十进制字符串和来源，不依赖聊天记忆或网络查询。

0.7／2 nm 来自2026-09-29用户直接提供并授权的数据；5／13.5 nm 来自文件中指定的冻结历史输入。来源载体是 [Task042 Review V4](../../docs/task042_neural_coarse_inverse/review_report_v4.md)，外部数据库版本、密度和测量不确定度未提供，不编造。登记四条材料不授权四波长计算。

原始标签 `0.699999988` 显式映射至 nominal `0.7`；求解仍用0.7nm，Delta/Beta不插值。仅接受登记条目和这个专用alias，其他波长报错。采用exp(-i omega t)，n=(1-Delta)+i Beta，epsilon=n*n，mu=1；air的n保持1。

Task042通过 `src.common.optical_material_table.load_si_optical_constants` 离线读取；返回实际n／epsilon与文件字节SHA256。run的resolved_config／manifest必须绑定ID、hash及所选条目，substrate、grating、背景基底和下端口使用同一个值。未来采用这些数据的其他任务须显式绑定，普通默认与既有输入不会自动改变。
