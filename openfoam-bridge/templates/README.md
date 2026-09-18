# 算例模板

- `cold-periodic-cascade-2d/`：当前启用的二维冷态周期叶栅，支持的参数约束见模板配置。
- `cold-periodic-cascade/`：保留的早期三维实验配置，其清单已命名为 `aeroblade-template.disabled.json`，服务不会加载。未通过收敛验证，不应用于性能结论。

这些目录只保存配置；运行时复制到 `jobs/` 后生成网格和结果。

- `pritchard-cascade-2d/`：Pritchard 1985专用二维模板，周期节距与斜置计算域按截面参数更新。

- `pritchard-cascade-3d/`：三维有限展宽端壁叶栅探索，物理展宽10 mm；配套说明见 `docs/THREE_D_PLAN.md`。
