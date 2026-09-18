# 163 邮箱专用浏览器扩展：方案变更与使用

SmartMail 的网页版邮箱连接改为专用 Chrome/Edge 扩展。扩展连接操作员明确选择的已登录 163 邮箱标签页，通过 Native Messaging 与本机 SmartMail 通信。业务准备、Confirmation、重复检查、Execution Ledger 和 SQLite 存储仍由 Python 核心负责。

## 与旧方案的区别

| 方面 | 原 Playwright CLI 方案 | 当前专用扩展方案 |
| --- | --- | --- |
| 浏览器归属 | Python 启动命名会话，维护专用浏览器 profile | 使用操作员自己的浏览器，扩展明确绑定一个标签页和 document ID |
| 连接方式 | 子进程调用 `run-code`，传入整段脚本 | Manifest V3 扩展 + 版本化 Native Messaging + 本地持久命令队列 |
| 页面逻辑位置 | Python 包内的两个注入脚本 | `extensions/netease163/` 中随扩展打包的只读采集、撰写与结果判定代码 |
| 浏览器权限 | 自动化进程控制会话 | 仅 `https://mail.163.com/*`；无 cookies、debugger 或任意站点权限 |
| 附件传输 | 自动化进程把本机路径交给浏览器上传 | 本机快照校验后分块传字节；扩展再次核对 SHA-256；浏览器不接收任意文件路径 |
| 登录与切换账号 | 打开/重启受控浏览器并接管登录 | 操作员在自己的邮箱页面登录、完成验证，再主动连接；账号不匹配时拒绝操作 |
| 断线恢复 | 依赖命名会话和 CLI 结果 | 命令只交付一次；重连不重放已领取的命令；不确定发送进入 Reconciliation |
| 发送前检查 | 核心在调用适配器前检查 Confirmation | 保留原检查，并在发放单次点击许可前重新检查持久化 Confirmation 和 Execution Attempt |
| 弹窗 | 旧脚本曾自动接受原生弹窗并重试促销阻断后的提交 | 不自动接受对话框、不自动修改内容、不重复点击；不确定结果交给操作员处理和对账 |
| 验证状态 | 曾有旧浏览器通道的实邮验收 | 扩展须重新验收；旧通道的 `verified` 不继承，实际发送默认禁用 |

这次变更保留网页版邮箱作为执行渠道；不改成 SMTP/IMAP，也不把本地 Sending Plan 改成本地定时发送。

## 安装和连接（Windows，Chrome 或 Edge）

1. 按 README 建立 Python 虚拟环境并安装 `requirements.txt`。
2. 打开 `chrome://extensions` 或 `edge://extensions`，启用开发者模式，选择“加载已解压的扩展”，加载仓库的 `extensions/netease163` 目录。
3. 复制扩展管理页上的 32 位扩展 ID。也可以从扩展弹窗中复制。
4. 在仓库目录执行以下命令，将该扩展 ID 注册到明确的 SmartMail 数据目录。把示例 ID 替换为实际 ID，使用 Chrome 时将 `edge` 改为 `chrome`。

```powershell
.\.venv\Scripts\python -m smartmail.bridge --home .smartmail install --browser edge --extension-id YOUR_EXTENSION_ID
```

安装命令只写当前 Windows 用户的 Native Messaging 注册项，并在所选数据目录下生成固定路径的 Python 启动器、主机清单和启动脚本。每个浏览器的主机注册指向一个数据目录；重新安装到其他目录会切换该注册。先断开现有扩展连接，再切换目录。不要在生产数据和测试数据之间隐式复用连接。

5. 在浏览器正常登录 `https://mail.163.com`，进入邮箱主页。打开扩展，点击“连接当前邮箱”。连接状态应显示预期的邮箱地址。标签页关闭、重新加载或本机桥接断开后需要重新连接。
6. 命令行使用与安装时相同的 `--home`：

```powershell
.\.venv\Scripts\python -m smartmail.bridge --home .smartmail status
.\.venv\Scripts\python -m smartmail --home .smartmail --adapter 163-extension mailbox capabilities
.\.venv\Scripts\python -m smartmail --home .smartmail --adapter 163-extension mailbox refresh --student STUDENT_ID
```

Student 及其 Mailbox 必须事先登记。扩展连接只表示选中了该邮箱，不会创建发送授权。没有连接、连接了其他账号或无法唯一识别邮箱时，不会猜测账号继续执行。

卸载本机桥接：

```powershell
.\.venv\Scripts\python -m smartmail.bridge uninstall --browser edge
```

再从浏览器管理页移除扩展即可。卸载不删除学生数据、邮件记录、旧浏览器 profile 或执行台账。当前自动安装器只支持 Windows；其他系统需另行实现原生主机注册路径。

## 实邮验收模式

扩展的 `verified` 当前均为 `false`。只读采集在连接后可用；即时发送必须显式使用 `--enable-extension-send` 开启验收模式，并且仍要求每条内容具有有效 Confirmation。这个标志既不创建 Confirmation，也不会把能力标记为已验证。

```powershell
.\.venv\Scripts\python -m smartmail --home .smartmail confirmation review PREPARATION_ID
.\.venv\Scripts\python -m smartmail --home .smartmail confirmation confirm PREPARATION_ID
.\.venv\Scripts\python -m smartmail --home .smartmail --adapter 163-extension --enable-extension-send execution run CONFIRMATION_ID
```

上述最后一条命令会尝试真实发送，只应对已经审阅确认的验收消息执行。当前重构验证未执行任何真实邮件发送。

前端联调需要显式使用验收模式启动；普通 `npm run dev` 继续保持所有外部写入能力关闭：

```powershell
cd frontend
npm run dev:acceptance
```

该模式只打开即时发送和原生定时的能力门控，不创建 Confirmation，也不绕过执行前的内容、附件、账号、重复发送和有效期校验；Recall 仍保持关闭。

扩展实现支持可明确识别的页内撰写布局、同源可访问编辑器，以及能够证明上传完成的附件控件。弹出式撰写窗口、跨域编辑器、多个相同候选控件或未知上传状态会拒绝继续。实站布局需要通过验收确认；不能因模拟页面测试通过就宣称所有 163 布局可用。

“发送成功”必须有新的、唯一匹配的 Sent 文件夹 canonical ID，正确发送状态、精确收件人及主题和有效时间。点击、提示框或历史同名邮件本身不是 Sent。只检查最近 50 条 Sent 记录，无法证明结果时返回 Unknown Outcome。操作员处理后使用原有 `execution takeover` 和 `execution reconcile-and-continue` 流程。

## 协议与代码职责

```text
SmartMail 核心 → 163-extension adapter → 本地命令队列
                                          ↕
                                Native Messaging host
                                          ↕
                            扩展 service worker（显式选定标签页）
                                          ↕
                              隔离脚本：只读采集 / 确认后撰写
```

- 协议版本为 1，支持的固定操作为 `observe`、`submit`（即时发送）、`schedule`（原生定时放置，含附件块）、`cancel_schedule`、`recall`，以及连接、心跳/领取、按命令索引读取附件块、单次操作许可和结果回传。没有任意 JavaScript、shell、URL 或文件路径执行接口；页面侧 wmsvr 调用限定在固定的 `mbox:*` 函数白名单内。
- `extension-bridge.sqlite3` 是独立的传输数据库；`smartmail.sqlite3` 仍是业务事实和执行台账的来源。本机主机只读检查业务库，不调用启动恢复逻辑，不创建 Confirmation。
- 心跳租期为 15 秒；命令默认有效期 120 秒。连接完成后立即执行首轮拉取，空闲时以 250 ms 节拍领取命令，忙碌时保持 1 秒心跳且不领取新命令。领取是持久化的单次状态转换，重连不会重放。
- 每次发放许可前按 Confirmation 种类分别校验：`immediate`/`scheduled`/`cancellation`/`replacement`/`recall`，并检查 attempt 身份、冻结请求、有效 Confirmation、正文与附件摘要、readiness Blocker、执行暂停和已发送记录（定时另查未来精确时间和重复外部定时）。页面在点击前再次检查账号、正文、收件人、附件选择和命令期限。
- 附件总量上限为 20 MiB，使用 192 KiB 块传输；正文等命令数据上限为 512 KiB。主机发往浏览器的每帧小于 1 MiB；接收帧上限为 32 MiB。完成或本地等待结束会清理队列内的正文和附件副本，业务历史不受影响。
- 只读采集每个受支持文件夹最多 5,000 条，保留分页与详情读取覆盖信息。正文 HTML 端点、未识别的自定义文件夹均排除，不宣称整箱完整覆盖。草稿箱中 `flags.scheduleDelivery=true` 的行单独标记为 `scheduled`，与本地计划、Unknown Outcome、Sent 严格区分。
- 原生定时经 `mbox:compose`（`action=schedule`，`attrs.scheduleDate` 为北京时间 `<date>YYYY-MM-DD HH:mm:ss</date>`）放置，成功后以草稿箱复合 ID `msid:mid` 和 `scheduleDelivery` 证据标记 Externally Scheduled；取消=观察到该定时草稿移入已删除；撤回=`mbox:recallMessage`，结果单独记录且永不阻塞完成。
- native scheduling、schedule cancellation 和 Recall 仍是独立门控能力（分别由 `--enable-extension-schedule`、`--enable-extension-recall` 显式开启，默认禁用、`verified:false`）。协议与受控实站验收见 [ticket-12-validation.md](ticket-12-validation.md)；不恢复旧 Playwright 运行路径。

Native Messaging 的注册方式、stdio 帧格式和大小约束依据 [Chrome Native Messaging 文档](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)。脚本使用 [scripting API 的隔离执行环境](https://developer.chrome.com/docs/extensions/reference/api/scripting)，连接期间的 worker 生命周期依据 [Chrome service worker 文档](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle)。

## 验证

```powershell
.\.venv\Scripts\python -X utf8 -m unittest discover -s tests -v
node --test extensions/netease163/tests/commands.test.mjs
```

开发环境安装了 Playwright 和对应 Chromium 后，可以运行可选的扩展加载与模拟页面冒烟测试：

```powershell
node extensions/netease163/tests/browser-smoke.cjs
```

可用 `SMARTMAIL_PLAYWRIGHT_MODULE` 指向已安装的 Playwright 模块，`SMARTMAIL_CHROMIUM_EXECUTABLE` 指向测试浏览器。此测试使用全新的临时 profile，所有测试页面请求都由本地 fixture 响应或中止；不连接真实邮箱、不使用操作员登录信息。Playwright 仅是可选开发测试工具，不是产品运行依赖。

## 迁移

`--adapter 163-browser`、`--browser-session`、`SMARTMAIL_BROWSER_PROFILE` 和 `NetEase163Mailbox` 已移除。切换到 `163-extension` 并安装、连接扩展；旧选项会明确报错，避免悄悄沿用旧通道。

现有数据库、Source Material、Preparation、Confirmation、Sent Record 和历史观察保留。旧观察中的适配器名称是历史事实，不批量改写；原实邮验收文档标记为旧通道历史证据。无需重新导入材料。`.smartmail/browser-163` 和 `.playwright-cli` 如存在也不会在此次代码整理中被删除。
