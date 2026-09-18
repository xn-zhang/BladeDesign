# 自建叶栅端到端验证（2026-09-08）

结论：二维冷态静止周期叶栅通过真实计算链路验收。三维流动及工程性能尚未验证。

## 实测结果

| 项目 | 结果 |
|---|---|
| 任务 | d2f84a8abeca48f69c717fae8545a910 |
| 环境 | Ubuntu-24.04 / OpenCFD v2512 / Python 3.12.3 / Node.js 25.9.0 |
| 模板 | cold-periodic-cascade-2d |
| 网格 | 3197 单元；二维 empty 展向；参考展宽 10 mm |
| 最大非正交角 | 26.61848° |
| 最大偏斜度 | 1.166644 |
| 检查 | checkMesh -allTopology -meshQuality：Mesh OK；周期面真实耦合 |
| 收敛 | 求解器明确报告 1276 次迭代收敛 |
| 最大最终初始残差 | 9.99609037e-06；所有方程 <1e-5 |
| 入口 / 出口质量流量 | -0.01272627768 / 0.01272627768 kg/s |
| 质量不平衡 | 按日志输出精度一致，不代表无限精度零误差 |
| 最大展向速度绝对值 | 3.857e-15 m/s |
| 压力 | 99840.1502–100204.3760 Pa |
| 温度 | 299.756598–299.988006 K |
| 叶面 y+ | 4.1836–19.5211，平均 12.9295 |

## 验证与产物

- 实际 API 管线：STL → blockMesh → snappyHexMesh → extrudeMesh → createPatch → checkMesh → rhoSimpleFoam → foamToVTK。
- 22 项测试通过；JavaScript 和启动脚本语法检查通过。
- 无头 Edge 验证连接、推荐叶片应用、任务状态和下载；无页面脚本错误。
- 网页 ZIP 下载与原件哈希一致，CRC 检查通过，包含真实 internal.vtu。
- ZIP SHA-256：3aeb703fed85d3971db0544498075da882291fbfd6d2fd174d83a3e4b80d45e5。
- 完整审计：jobs/d2f84a8abeca48f69c717fae8545a910/validation.json。
- 场数据：jobs/d2f84a8abeca48f69c717fae8545a910/case/VTK/；结果包：jobs/d2f84a8abeca48f69c717fae8545a910/results.zip。
- 工作台：http://127.0.0.1:8787。刷新页面，连接后选择二维模板并应用推荐叶片。

## 未通过和未覆盖

1. 严格 allGeometry 诊断仍报告 101 个凹单元，未通过。日志：jobs/d2f84a8abeca48f69c717fae8545a910/strict-checkMesh.log。不能宣称所有网格诊断通过。
2. 无棱柱层、一阶迎风；没有网格独立性、二阶格式、y+ 目标控制或实验对照，不能据此给出工程损失或发动机效率结论。
3. 先前三维切片任务没有通过全部稳态残差门槛；其日志和结果保留，旧模板停用。
4. 验证仅覆盖指定二维静止冷态推荐几何和默认工况；未覆盖扭转、端壁、二次流、转子、传热或高温。
5. 未安装开机自启；WSL/电脑重启后执行 bash bridge/start-local.sh。

操作与配置见 [算例说明](CASCADE.md)。令牌仅存 WSL 私有文件，未写入交付包或报告。
