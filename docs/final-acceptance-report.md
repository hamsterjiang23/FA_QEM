# FA-QEM 六项 Baseline 最终验收报告

验收日期：2026-08-08  
预览纹理修订：2026-08-10
源模型：`Test_Model/curved-lantern-balustrade-final.glb`  
源模型 SHA-256：`0be9c425a2c3cc2fe7ece2a6fe4c7fa8ef44879d94403e4cdb6f849bc6f891d2`

## 1. 验收结论

本工程完成 QEM、QEM4VR、RobustLPM、ICE、STMW、CWF 六项 baseline 在同一模型上的 50%、10%、1% 三档实验，并为每档保留科研原生轨和兼容资产轨。最终审计结果为：

- 预期记录：36；实际记录：36；缺失：0；审计错误：0。
- 含有效输出的记录：28。
- 科研轨：18 个结果全部保留；其中 CWF 1% 因面数偏差超过 2% 标记为 `TARGET_UNREACHABLE`，同时保留最接近输出和完整指标。
- 资产轨：10 个 `SUCCESS`；其余 8 个因 repair 无候选通过硬约束而标记为 `REPAIR_FAILED`。
- FA-QEM 目标方法另行完成本地三档科研轨/资产轨测试，以及 Thingi10K validation/holdout 独立复现实验。

最终本地 HTML、CSV 和 JSON 报告由以下命令生成：

```powershell
uv run fa-qem-bench --config experiment.yaml report
uv run fa-qem-bench --config experiment.yaml audit
```

大体积实验资产位于被 Git 忽略的 `artifacts/`，本报告保存可审计结论、关键指标、状态和复现入口；完整资产可由已记录的配置、哈希和命令重新生成。

### 预览纹理修正与覆盖

源模型的正确 base color 已明确锁定为 `Test_Model/deliverty/textures/basecolor.png`（4096×4096，SHA-256 `4e45bf43bbf13615da2450a69945e0bbb956f767a58002ca21d52a13bad37e73`）。此前科研轨 OBJ 缺少可加载材质时，报告右栏会回退成灰色，却仍固定标为 `PBR/base color`；该标签与回退行为现已修正。

当前报告为六项 baseline 的 36 条记录和 FA-QEM 的 6 条本地记录全部生成 contact sheet，共 42/42 张，0 个渲染错误且没有灰色纹理回退：13 张读取资产内嵌 base color，6 张使用科研输出原 UV 配合上述源纹理，23 张通过最近源表面投影显示同一 base color。其中 8 张来自 `REPAIR_FAILED` 记录保留的最佳调试候选，图片标题和汇总字段均明确标为失败调试候选，不代表资产轨成功。

本次修订只改变报告预览和预览来源元数据，不改变任何简化几何、运行状态、计时、几何误差或纹理评价指标。

## 2. Baseline 状态矩阵

| 方法 | 50% 科研 / 资产 | 10% 科研 / 资产 | 1% 科研 / 资产 |
|---|---|---|---|
| QEM | `SUCCESS` / `REPAIR_FAILED` | `SUCCESS` / `REPAIR_FAILED` | `SUCCESS` / `REPAIR_FAILED` |
| QEM4VR | `SUCCESS` / `SUCCESS` | `SUCCESS` / `SUCCESS` | `SUCCESS` / `SUCCESS` |
| RobustLPM | `SUCCESS` / `SUCCESS` | `SUCCESS` / `SUCCESS` | `SUCCESS` / `SUCCESS` |
| ICE | `SUCCESS` / `SUCCESS` | `SUCCESS` / `REPAIR_FAILED` | `SUCCESS` / `REPAIR_FAILED` |
| STMW | `SUCCESS` / `SUCCESS` | `SUCCESS` / `SUCCESS` | `SUCCESS` / `SUCCESS` |
| CWF | `SUCCESS` / `REPAIR_FAILED` | `SUCCESS` / `REPAIR_FAILED` | `TARGET_UNREACHABLE` / `REPAIR_FAILED` |

状态不是经过筛选后的展示结果。失败记录同样包含输入/输出哈希、命令、环境、参数、日志、指标或 repair lineage。

## 3. 六项 Baseline 科研轨几何误差

以下指标均在单位包围盒对角线坐标中计算，使用固定随机种子、每方向 100,000 个面积采样点。`H` 为双向 sampled Hausdorff，`C` 为 mean-squared symmetric Chamfer。

| 方法 | 50% H / C | 10% H / C | 1% H / C |
|---|---:|---:|---:|
| QEM | 0.00422572 / 1.209e-9 | 0.00506778 / 1.087e-8 | 0.00626143 / 8.757e-7 |
| QEM4VR | 0.00022956 / 7.258e-10 | 0.00125901 / 3.907e-8 | 0.01426497 / 3.847e-6 |
| RobustLPM | 0.01922080 / 7.965e-6 | 0.01837818 / 8.440e-6 | 0.01906403 / 8.649e-6 |
| ICE | 0.00299278 / 6.482e-8 | 0.01059898 / 1.700e-6 | 0.02419297 / 1.785e-5 |
| STMW | 0.00023497 / 4.106e-10 | 0.00061678 / 9.586e-9 | 0.00651284 / 8.178e-7 |
| CWF | 0.00274322 / 1.501e-8 | 0.00675754 / 2.641e-7 | 0.01324665 / 6.796e-6 |

这些数值用于当前单模型、当前实现和当前采样协议的比较，不应解释为对原论文跨数据集排名的复现。

## 4. CWF 完整披露

| 比例 | 目标面数 | 实际面数 | 目标偏差 | 中位 wall time | 拓扑 | 资产轨 |
|---|---:|---:|---:|---:|---|---|
| 50% | 82,470 | 82,507 | 0.045% | 16,887 s | 3 boundary，68 non-manifold，winding inconsistent | `REPAIR_FAILED` |
| 10% | 16,494 | 16,618 | 0.752% | 5,695.5 s | 10 boundary，233 non-manifold，winding inconsistent | `REPAIR_FAILED` |
| 1% | 1,649 | 1,708 | 3.578% | 3,127.9 s | 18 boundary，150 non-manifold，winding inconsistent | `REPAIR_FAILED` |

CWF 1% 的 classification probe 用时 3,111.8 秒，低于 3,600 秒阈值，因此额外计时三次；正式 wall-time 范围为 3,124.3–3,263.3 秒。实际面数偏差为 3.578%，超过实验的 2% 容差，因此科研轨状态为 `TARGET_UNREACHABLE`。

三档原生输出均被冻结并完成几何评价。Repair 按计划运行，但没有候选同时通过开放边、非流形和绕序硬门禁，因此禁止生成伪成功的重烘焙资产。

## 5. FA-QEM 本地模型结果

FA-QEM 是论文指导的本地复现，不是作者官方代码。实现规格及所有补充假设见 [`fa-qem-implementation-spec.md`](fa-qem-implementation-spec.md)。

| 比例 | 目标 / 实际面数 | H | C | 中位 wall time | 几何拓扑 | 资产纹理 RGB L2 |
|---|---:|---:|---:|---:|---|---:|
| 50% | 82,470 / 82,470 | 0.00032294 | 2.020e-9 | 10.43 s | 单组件、封闭流形 | 0.037600 |
| 10% | 16,494 / 16,494 | 0.00150017 | 6.474e-8 | 18.05 s | 单组件、封闭流形 | 0.038501 |
| 1% | 1,649 / 1,648 | 0.01323654 | 4.581e-6 | 19.84 s | 单组件、封闭流形 | 0.045752 |

三档科研轨均未触发事后 repair。兼容资产轨使用统一 2048 纹理策略生成 base color、normal、metallic/roughness、emissive 和切线，并通过 repair 工具 v0.2.2 的外部硬门禁。

## 6. Thingi10K 独立复现

论文没有发布完整测试 ID 和足以逐项重建 Table 2 的指标缩放细节，因此本工程采用作者 Thingi10K 数据集上的固定、分层独立复现；协议见 [`thingi10k-validation-protocol.md`](thingi10k-validation-protocol.md)。

| Split | 比例 | 成功 | 平均 H | 平均 C |
|---|---:|---:|---:|---:|
| Validation | 10% | 8/8 | 0.01935191 | 9.533e-6 |
| Validation | 1% | 8/8 | 0.11360143 | 1.699e-3 |
| Untouched holdout | 10% | 8/8 | 0.02948539 | 2.250e-5 |
| Untouched holdout | 1% | 8/8 | 0.11373275 | 6.525e-4 |

验证过程发现“对所有输入使用 flip-only veto”会使原本封闭流形的本地模型在 10% 档产生 11 条非流形边。最终实现对初始流形输入保留 link-condition 和 duplicate-face 检查；已有非流形边或非流形顶点的输入使用论文的 generalized flip-only 路径。该条件化 safeguard 是明确披露的工程假设。

## 7. 最终验证

| 检查 | 结果 |
|---|---|
| 完整审计 | 36/36 records，0 missing，0 errors，28 outputs |
| WSL native build | `ninja: no work to do`，构建成功 |
| CTest | 7/7 passed |
| pytest | 26/26 passed |
| Ruff | passed |
| BasedPyright | 0 errors，0 warnings |
| QEM consistency | `SUCCESS`；100,000 samples；Hausdorff 相对差 0.000298；Chamfer 相对差 0.003249 |
| 预览完整性 | 42/42 contact sheets；0 render errors；0 gray fallbacks |
| Git | 核心源码工作树干净；`origin/main` 已同步 |

## 8. 已知限制与警告

- 外部检查器在本轮没有执行自交检测，报告中相应字段为 `not_evaluated`，不得解释为“无自交”。
- CWF 50% 在外部 CWF checkout 含 GCC 兼容补丁的状态下启动；源码版本和 dirty provenance 已写入运行记录。
- QEM4VR、STMW 和 FA-QEM 是论文指导复现；QEM、ICE、CWF、RobustLPM 使用各自官方实现或官方分发程序。
- RobustLPM 和 CWF 的外部程序/仓库保持许可证与进程隔离，没有复制进本仓库。
- `artifacts/` 中的大模型、贴图、中间 RVD 和运行日志不提交 Git；报告中的哈希用于验证本地审计包。

## 9. 复现入口

```powershell
uv run fa-qem-bench --config experiment.yaml doctor
uv run fa-qem-bench --config experiment.yaml prepare
uv run fa-qem-bench --config experiment.yaml sweep --resume --resolution 2048
uv run fa-qem-bench --config experiment.yaml report
uv run fa-qem-bench --config experiment.yaml audit
uv run python scripts/validate_qem_consistency.py
uv run pytest
```

第三方版本、URL、哈希、许可证和补丁记录在 `third_party.lock.yaml`；每次运行的完整命令和环境位于本地 `artifacts/runs/<run-id>/run.json`。
