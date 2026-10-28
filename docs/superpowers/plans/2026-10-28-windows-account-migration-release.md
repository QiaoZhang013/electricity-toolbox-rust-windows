# Windows 账号迁移及 0.1.25 发布计划

> 使用 executing-plans 顺序执行；账号授权由用户完成，不读取或记录凭据。

**目标：** 将本地 development 完整历史与 Windows 0.1.25 正式版发布到本次 GitHub CLI 授权确认的新账号。

**实现：** 沿用原 Tk 界面、Rust 宿主及 Windows 完整安装包更新通道，仅调整仓库地址、版本、发行文档与入口。main 保持下载页和 Actions，完整源码维护在 development。

**约束：** 不覆盖已发布标签或附件；保留配置、登录态及业务数据；不得将这些数据或构建产物提交到 Git。旧客户端仍指向旧账号，因此新下载页明确说明需手动安装迁移版一次。

**用户最新交付要求：** 从 Windows 直接发布到新账号。浏览器登录与 CLI 授权分别核对，新账号须通过 GitHub CLI 的正常设备授权取得；安装包不得残留旧 Windows 更新地址。

**已核对的目标：** GitHub API 返回账号 QiaoZhang013，仓库列表为空。新公共仓库使用 QiaoZhang013/electricity-toolbox-rust-windows。

## 任务与验收

- [x] 用户完成设备授权；回读 API 用户名，确认新账号及目标仓库状态。若仓库已存在，先确认属于当前项目，不能覆盖不相关内容。
- [ ] 将 desktop/python/windows_update.py、README.md、packaging/github-downloads/README.md 及三个代理 workflow 中的 Windows 仓库改为已核对的新账号，保留 macOS 原通道。
- [ ] 通过 packaging/tauri/version.py 设置 0.1.25，合并未发布日志，补充账号迁移、箭头 80% 和日报首页去重说明。
- [ ] 验证新仓库链接和更新器的可信来源校验；运行 Windows 更新、WPS、清远导出及网页速度相关回归。
- [ ] 创建公共发行仓库，上传 development 与下载页 main，设置 main 为默认分支并核对远端提交。保留既有 Git 历史与标签。
- [ ] 使用既有干净导出规则刷新发行载荷，构建 Windows x64 宿主和 NSIS；生成 ASCII SHA-256 文件，核对版本、载荷摘要和文件大小。
- [ ] 在独立目录实际从旧版安装升级到 0.1.25，回读数据、配置、WPS 冷启动、清远工作簿和 500kV 80% 速度；准确记录未完成的验证。
- [ ] 创建草稿 Release，上传安装包和摘要，核对 GitHub 附件摘要后正式发布；新通道更新器实查公开 Release，下载页直链回读通过后交付。

## 重点复核

- 旧账号 URL 不得遗留在新 Windows 下载或更新路径，旧 macOS 通道不能被误改。
- 更新器必须拒绝外部仓库的安装包，继续执行大小和 SHA-256 校验。
- main 的代理 workflow 必须调用新仓库 development，并保留手动构建入口。
- 不得把旧 0.1.24 本地安装包作为此次发行包，它不含 WPS 和清远修复。
- 安装验证只使用独立副本；完整点击到重启的流程只有真实运行后才可声称通过。
