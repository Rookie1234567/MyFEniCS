# Q0–Q2 两胞元审计：独立保存证据复核

结论：固定源码 35dd9e5c39939d14bbded98f288007aff4a08368 的审计记录通过只读复核，未发现具体证据缺口。没有导入求解器、读取数值数组进行运算、重跑 checker、JIT、PDE、factor 或 solve。

核验了 1267 个冻结 Git 源文件、2222 个数组产物哈希、1064 个原始 packet JSON 描述符哈希及其两份 typed-array/十组 sparse-pair 完整绑定。当前 report/provenance/checker/ABI/supervisor 身份一致；旧 ad356715 权威保持独立，逐项 old/new source diff 与实际清单一致。独立 checker 的 4842 个唯一门全部通过。两个 raw-sector receipt 完整覆盖228/304模式，合计保留全部532物理模式、五态action/recovery、原两级cutoff及实际basis300/Gauss23/144。

四q完整CSR最大相对Frobenius差异7.62384446e-16、最大元素相对差异1.26333427e-15；每q全部3968 FE列最大误差1.11299512e-15。十二泄漏块的最大相对Frobenius量6.72959617e-16，最大元素相对量1.04620451e-15。全部532模式raw fold最大3.55113499e-15，reverse lift最大5.03477684e-15。fresh full-original action最大9.12361598e-16；两侧各4320内部行全激励的完整恢复最大2.00824000e-13。

必须保留证据来源区别：四个同twist off-block来自fresh local贡献；八个跨twist块来自immutable原S/maps，前提是完整candidate map列等价，并有两组fresh full-original action witness。不能将其描述成fresh candidate独立重组装全部十二cross blocks。

从资源采样重算，worker334.136080626s、峰值741564416B；checker10.395193904s、峰值312737792B。全部正常退出、swap0、后代进程清理完成，合计344.53127453s，满足总600s及整树1.5GiB界限。峰值为采样RSS。

Global/q factor count为0；继承的108×108 cell-interior LU已明确记录。普通默认路径保持是此前源码审查结论，本次opt-in数值审计没有替代普通默认回归测试。Q3–Q5 quotient inverse、物理forcing、notch、完整输出及目标尺寸精度/2TB/48h仍未资格化。

精确源码、ABI、报告、receipt与监督哈希、各项数值及scope见 independent_verification.json；主要核验过程见 verify_saved_evidence.py。
