# Windows 0.1.31 发布前验证

电力工具箱 Windows 0.1.31 发布前验证报告
日期：2026-11-06（Asia/Shanghai）

Windows 11 完整安装：660 个发行程序文件及 660 个工作区程序文件一致；15 个原版 Tk 页面、Rust 后台、实际宿主启动及正常退出通过。
源码发行预检：301 项通过，无跳过。包含日报双 PDF 导出、早报 Excel→Word 与审计回读，以及更新、并发、原生助手检查。
包内测试：{"installed-refresh.log": 26, "installed-delta-core.log": 14, "installed-update-detection-ui.log": 16, "installed-windows-update.log": 19, "installed-compat.log": 5, "installed-browser-lifetime.log": 3, "installed-morning-report.log": 128, "installed-market-report.log": 45}
包内报表使用实际安装代码及运行环境，真实 Chromium 导出打印版及手机版 PDF；Excel 源文件 SHA-256 保持不变。
Windows CI：https://github.com/QiaoZhang013/electricity-toolbox-rust-windows/actions/runs/42201300632

未修改的正式 0.1.30 更新器通过原版更新按钮执行最终生产补丁；真实安装和自动重启通过，全程禁止下载完整安装包。
0.1.30→0.1.31 补丁：2841000 字节；索引：5460 字节。
完整包：340311628 字节；SHA-256：e2d1f37cd900d7ef1c1f1abadbe3b1b7574865c49ad2c6dbca6c9747499725a8
升级保留 11 份配置/数据/登录态样本；Excel 0.125 与格式 0.00% 回读通过；运行环境复用、缓存清理、注册表及快捷方式保留。升级与自动重启耗时 92.2 秒。
0.1.28、0.1.29、0.1.30 直达补丁均从完整安装包基准实际还原并全量核对，原有升级路径保留；更新后官方卸载在隔离副本验证。
补丁目标来自未运行功能测试的干净 NSIS 安装。测试浏览器产生的空 locales 目录曾导致候选基准与原始安装不同；该候选从未发布，已隔离并从干净副本重建全部补丁，再次执行原版客户端升级和卸载验收。

边界：Windows 10/macOS 实机和真实网站业务取数/上传/WPS 写入未验证；本版只发布 Windows 安装包。公开地址与实际用户补丁更新将在发布后另行验证。
校验失败或缺少补丁路径时保留完整包回退；用户取消不触发回退。用户配置、业务文件和登录态不随程序覆盖。
