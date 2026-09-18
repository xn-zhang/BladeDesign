# AeroBlade 本地工作台

完整操作请见 [启动、停止、API token、远程连接与批量参数指南](docs/GETTING_STARTED.md)。该指南以仓库根目录为准；独立 ZIP 使用本页的启动路径。

本目录可独立打包运行。`web/` 为前端源码，`bridge/` 为计算服务，`docs/` 为专题文档。

```bash
python3 bridge/create_pritchard_cascade.py
bash bridge/start-local.sh
```

需要 Python 3.10+、Node.js 20+ 与 OpenCFD OpenFOAM（当前验证 v2512）。默认访问 http://127.0.0.1:8787 。连接令牌由启动脚本保存在用户私有状态目录。

详见 [服务说明](bridge/README.md)、[算例说明](docs/CASCADE.md) 和 [验证报告](docs/CASCADE_VALIDATION.md)。当前为二维流程验证，非工程精度或三维性能验证。

默认使用 [Pritchard 1985 十一参数截面模型](docs/PRITCHARD.md)，旧概念模型可显式切换。

三维探索可执行 `python3 bridge/create_pritchard_3d.py`，再在工作台选择对应模板；[首轮结果尚未通过收敛与严格几何验证](docs/THREE_D_VALIDATION.md)。

默认同时运行2个算例，工作台“计算槽位”可调整并发数。启动配置示例：`bash bridge/start-local.sh --max-parallel 2 --max-pending 16 --case-threads 1`。详见 [并行计算说明](docs/PARALLEL_CASES.md)。

前台服务按 `Ctrl+C` 停止，等待退出后执行相同命令重启。关闭网页不会停止计算。批量参数目前通过 API 提交，网页仅支持单份设计 JSON 导入。
