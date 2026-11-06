# 上游 v0.1.31 报表同步验证

日期：2026-11-06。上游固定来源：[v0.1.31](https://github.com/a792275829-cpu/electricity-toolbox-scripts/releases/tag/v0.1.31)，提交 `43edde1bd90149c8474e673319423f0275531fe7`。本次同步两个报表模块及其现有 GUI、服务、CLI 调用方；不采用上游无关功能或共享包重构。

## 保留的行为

保留 Windows/macOS 适配、原版 Tk 页面、现有 Rust Excel 读取优化、独立登录态与浏览器 profile、已移除的日报首页重复补录项、Windows 独立补丁更新通道。用户配置、输入工作簿、模板及已安装程序不做替换。本次源码不冒充新的 Windows 正式发行版。

## 验证结果

| 范围 | 结果 |
| --- | --- |
| 早报 `scripts/test_*.py` | 128 项通过，含 3 项完整离线 Excel → Word → 审计回读 |
| 日报 `test_market_report_*.py` | 45 项通过；开启 `TOOLBOX_REPORT_PDF_E2E=1` 实际导出并回读两份 PDF |
| 日期输入、自动文件匹配、Rust 市场载荷及编辑器冷启动 | 12 + 1 + 11 + 1 项通过 |
| `desktop/tests/python/test_service.py` | 15 项通过，真实 JSON 进程通信与任务生命周期 |
| 目录加载、报表输出锁、PDF 浏览器选择 | 各 2 项，共 6 项通过 |
| Microsoft Word 实际渲染 | 5 页 A4，逐页目视检查；无空白页，预测标题和全部 26 行同页 |

合计 **219 项针对性测试通过**。新功能测试在修改前已复现缺失功能和错误编号；额外复现并修复了完整日期匹配、全角括号、缺失上网电量、分页空白及自定义模板域/符号保护问题。`git diff --check` 通过。

合成报表按 D=2026-11-06，D-1=2026-11-05，D-2=2026-11-04 验证：上网电量 **735 万千瓦时**，其中清远 **30 万千瓦时**；日前总量 **130 万千瓦时**，含清远计划 **20 万千瓦时**；日清分表填充 **11 行**，分公司现货偏差收益 **61**、总电费 **360**；机组状态 **8 段**，三厂策略全部填入，工作簿日期告警为空。输入 Excel 文件写前写后 SHA-256 相同。

上网电量 7 个必需坐标分别以空值、无缓存公式、Excel 错误及布尔值测试（28 个子用例），均阻止错误分摊到清远；真实零值仍有效。生成器缺失 J8 时保留模板红字，并在 `onlineEnergyError` 写出具体坐标。

Word 渲染器因本机未安装 LibreOffice 而无法运行，改用本机 Microsoft Word 独立 COM 实例导出 PDF，再以 PDFium 渲染页面检查；没有关闭用户文档。PDF 与 DOCX 仅保存在 Git 忽略的本地 QA 目录。

## 可复现入口与限制

早报：从仓库根目录，用项目 `.venv` 解释器运行 `python -m unittest discover -s 每日生产经营情况汇报自动生成工具/scripts -p 'test_*.py'`，将仓库根目录加入 `PYTHONPATH`。

日报：从 `电力工具箱/` 目录，用同一解释器运行 `python -m unittest discover -s tests -p 'test_market_report_*.py'`；Windows 设置 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，`PYTHONPATH` 指向仓库根目录。实际 PDF 验证另设 `TOOLBOX_REPORT_PDF_E2E=1`，需要已安装的 Playwright Chromium。

早报接口与天气使用合成响应，未访问真实账号、上传或写入外部系统。没有 Windows 10 或 macOS 实机，本次没有重新制作安装包、公开发行附件或通过客户端安装更新。
