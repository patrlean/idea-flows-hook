# Idea Flows Hook

让 Idea 看板随着 Codex 对话里的实际进展更新。

[English](README.md) · [测试](https://github.com/patrlean/idea-flows-hook/actions/workflows/test.yml) · MIT

你主动指定要跟踪的项目后，当前 Codex Agent 会在每轮结束前记录一句有依据的进展。Stop hook 将事件保存在本机；配置 webhook 后，也可以发送到你自己的看板。无需额外模型服务或 API Key。

## 状态如何判断

| 状态 | 含义 | 变更依据 |
| --- | --- | --- |
| `idea` | 构思 | 当前对话内容 |
| `research` | 调研 | 已开展的调研、发现和待验证问题 |
| `dev` | 开发中 | 实际实现进展或用户指定 |
| `live` | 已上线 | 部署成功、验证过的网址和事实依据 |
| `discarded` | 已归档 / 已丢弃 | 用户本轮明确归档的原话 |

多久没动都不会自动归档。一般讨论应保留已有状态。脚本检查字段和原话，部署结果仍由当前 Agent 根据工具结果判断，并非脚本独立验证。

尚未开始实现、正在查论文、做竞品分析、需求调查或可行性验证时使用 `research`，摘要写清发现和待验证问题，事实依据不能为空。调研报告写完不等于上线；已开发或已上线的项目偶尔查资料，也不会因此自动退回调研。自建 webhook 接收端需要接受这五种状态；现有本地数据库无需迁移。

## 安装

需要 **Python 3.9+**，命令名为 `python3`，以及支持原生插件 hooks 的 Codex。附带的 hook 命令面向 macOS / Linux；Python 核心也通过 Windows CI 测试，但这个版本未提供 Windows 的 hook 命令配置。

```sh
codex plugin marketplace add patrlean/idea-flows-hook
```

在插件目录选择 **Idea Flows Tools**（`idea-flows-tools`），安装 **Idea Flows**（`idea-flows`）。没有出现时重启桌面应用。点插件的 **Set up** 指定项目目录，再到 Codex 的 `/hooks` 界面审阅并信任命令。在已登记的项目里开始新一轮对话，确认原生 hook 是否触发。

这是通过 Git marketplace 手动安装的插件，尚未上架通用插件目录。安装机制见 [OpenAI 官方文档](https://developers.openai.com/plugins/build/plugins)。插件已自带 hooks，不要再重复安装全局 hooks。

从 0.1.x 更新：运行 `codex plugin marketplace upgrade idea-flows-tools` 刷新来源，再在插件目录更新 Idea Flows。hook 命令和配置路径保持一致；使用自建接收端时，先让它接受 `research`，再发送调研事件。

插件名称是 **Idea Flows**。安装命令中的 `patrlean` 是 GitHub 仓库所有者，不属于插件名；插件名无需包含个人姓名。每个安装者配置自己的项目清单及可选 webhook。

## 手动配置

```sh
git clone https://github.com/patrlean/idea-flows-hook.git
cd idea-flows-hook
python3 scripts/idea_flows.py init
python3 scripts/idea_flows.py enroll --id my-project --name '我的项目' --cwd /项目的绝对路径
```

`init` 输出配置位置，不覆盖已有配置。登记目录及其子目录中的所有对话都会参与同步；嵌套项目取最近的已登记父目录。不会扫描其他聊天，目前也不支持单独按聊天筛选。从配置的 `projects` 中移除项目即可停止跟踪。

默认配置在 `~/.config/idea-flows/config.json`，遵循 `XDG_CONFIG_HOME`。运行数据优先使用 Codex 提供的 `PLUGIN_DATA`，否则写到 `~/.local/share/idea-flows`。支持环境变量 `IDEA_FLOWS_CONFIG`、`IDEA_FLOWS_DATA_DIR`，或在子命令**之前**传 `--config`、`--data-dir`。Agent 收到的记录命令会带上实际路径，避免执行环境不同导致写错地方。

## 发送到站点

默认只在本地记录。参考 [配置示例](examples/config.example.json)，在配置中添加：

```json
"webhook": {
  "url": "https://your-dashboard.example/api/sync",
  "headers_env": {"Authorization": "IDEA_FLOWS_AUTHORIZATION"}
}
```

在 **Codex 进程的环境**中设置 `IDEA_FLOWS_AUTHORIZATION`，值按接收端要求包含 `Bearer ` 等前缀。普通方式打开的桌面应用可能不继承终端 export 的变量；更改启动环境后需要重启 Codex。配置只保存变量名，不保存凭据值。其他认证请求头也可以同样映射。

仅允许 HTTPS 和用于本机测试的 loopback HTTP，不跟随重定向。收到 2xx 即视为成功。失败事件保存在 SQLite，后续已登记项目的 Stop 或手动 `flush` 会重试，每次最多三个。接收端必须按 `eventId` 去重，并根据 `observedAt` 避免旧事件覆盖新状态。网络中断可能造成重复投递。

**后来启用 webhook 会发送此前本地保留的事件。** 不希望发送历史摘要时，先检查或移除本地数据库。

```sh
python3 scripts/idea_flows.py --data-dir /插件实际使用的数据目录 status
python3 scripts/idea_flows.py --data-dir /插件实际使用的数据目录 flush
```

完整事件格式和接收端规则见 [英文说明](README.md#event-contract)。`discarded` 对应归档；`threadId` 是 Codex 聊天标识，不是通用网页链接。手动选择的看板状态应由接收端保护，只有新的部署依据或用户明确指令才能覆盖。

本仓库只包含 hook 和事件协议，需要自行提供看板和接收端，不附带托管站点或云账户。

## 数据与运行行为

- 当前用户输入会暂存在本地，用于校验归档原话；Stop 完成后删除上下文行。中断的轮次可能留下上下文。SQLite 删除行不等于安全擦除，彻底清理需移除本地数据库。
- 长期事件包含项目 ID、聊天 ID、时间、进展和依据。Agent 会被要求去除敏感信息，但接入公开接收端前仍应检查摘要。
- 默认缺少记录时，Stop 让 Agent **再继续一次**，可能消耗额外 Codex 用量。配置 `"require_record": false` 可关闭。
- 并发写入使用事务，重复事件不会重复更新本地状态；旧轮次晚结束也不会覆盖较新状态。接收端需要做同样处理。
- 卸载在 Codex 插件界面完成，本地配置和历史会保留，可按需另行删除。脚本不修改 hook 信任记录。

## 测试

```sh
python3 -m unittest discover -s tests -v
```

覆盖指定目录、嵌套项目、空格路径、状态依据、Stop 继续次数、并发写入、去重、重试和认证头处理。CI 配置 Python 3.9 / 3.13，运行在 Linux、macOS、Windows。脚本测试不等于已经验证某个 Codex 安装的原生 hook 自动触发，安装后应单独确认。
