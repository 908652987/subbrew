# subbrew — Repository Guidelines

subbrew 是 mihomo（Clash.Meta）多订阅聚合配置的**生成器**，不是应用工程：根目录扁平布局、无子目录、无 CI、无测试、无依赖清单；已初始化 Git 仓库，入库的只有生成器、模板与示例订阅（`subs.example.yaml`），真实订阅 `subs.yaml` 与产物 `config.yaml` 均被 `.gitignore` 排除。产物 `config.yaml` 作为本地文件导入 FlClash / Clash Verge Rev / Clash Party 使用。

内核行为已用官方 `mihomo v1.19.33 darwin arm64` 实测验证（2026-11-04）；三个客户端自带内核分别为 Clash Verge Rev 2.5.8 → `v1.19.32`、Clash Party 2.0.4 → `v1.19.33`、FlClash 0.9.2 → `v1.19.33`（FlClash 依据其 CHANGELOG，其余为二进制 `-v` 实测）。

## Project Overview

- 输入：`subs.yaml`（真实订阅，不入库；由 `subs.example.yaml` 复制并填 token）+ `template.yaml`（DNS / TUN / 嗅探 / 分组 / 规则模板）
- 生成：`gen.py` 把订阅展开成 `proxy-providers`、每订阅 `自动/手动` 分组，并注入模板占位符，输出 `config.yaml`
- 运行期：节点与规则集**不内联**，由 mihomo 内核按 `interval` 自行刷新 `./providers/*.yaml`、`./ruleset/**`
- 另一条路径：`auto-groups.js` 粘进客户端的 Script/覆写，加载时**整体重写** `proxy-groups`

两条路径的关系：`auto-groups.js` 只重建 `proxy-groups`，不碰 `dns` / `sniffer` / `rule-providers` / `rules`。用它就必须保证 profile 本身已带这两部分（本仓库的 `config.yaml` 满足该前提），且分组名与模板一致——否则规则里的分组目标会失效。单独拿一个只有 `proxy-providers` 的裸 profile 配 JS，会得到"有分组、无分流"。

## Architecture & Data Flow

```
subs.example.yaml ──（cp）──→ subs.yaml ─┐  （真实 token，不入库）
                                         ├─ gen.py: build() ─→ 3 次字面量替换 ─→ config.yaml ─→ 客户端本地文件导入
template.yaml ───────────────────────────┘                                        （config.yaml 同样是产物，不入库）
                                        内核运行期据 config.yaml 拉取 ./providers/<id>.yaml、./ruleset/**

auto-groups.js ── 客户端加载时执行 main(config, profileName)，重建全部 proxy-groups
```

关键契约：

- `gen.py:173-206` `main()`：检查 `subs.yaml` 存在 → `build()`（`gen.py:52-133`）→ 替换占位符（缩进 2/2/6）→ 残留 `{{` 即失败 → `check()`（`gen.py:136-171`）→ 校验通过才写文件（`--check` 时只校验）
- 占位符是**列 0 的精确注释串**，改动缩进或文字会让替换失效：`# {{PROVIDERS}}`（`template.yaml:136`）、`# {{SUB_GROUP_REFS}}`（`:156`）、`# {{SUB_GROUPS}}`（`:178`）
- 生成的每订阅分组名固定为 `f"{name} · 自动"` / `f"{name} · 手动"`，`check()` 用同一公式反查；分隔符改一处不改另一处会让 `--check` 报“缺少订阅分组”
- `proxy-groups` 里 `proxies:` / `rules:` 的目标必须存在于分组名或 `SPECIAL_TARGETS`（`gen.py:35`），否则 `--check` 返回 1
- `gen.py` 只把 `subs.yaml` 的 `test-url` 用于 provider 与每订阅分组，**不会**改写模板里的 `&test_url`

## Key Directories

仓库无子目录，全部位于根目录：

| 路径 | 作用 |
|---|---|
| `gen.py` | 生成器 + 校验器；唯一第三方依赖 PyYAML |
| `template.yaml` | 手写配置主体：端口/TUN/DNS/嗅探/静态分组/rule-providers/规则 |
| `subs.example.yaml` | 订阅清单示例（只有 `REPLACE_*` 占位，入库） |
| `subs.yaml` | 真实订阅清单（含 token，**不入库**；`cp subs.example.yaml subs.yaml` 后填写，`gen.py` 只读它） |
| `config.yaml` | **生成产物**，禁止手改；重新 `gen.py` 即覆盖，含真实订阅 URL，**不入库** |
| `auto-groups.js` | 客户端运行期分组脚本，独立于生成流程 |

运行期目录 `./providers/`、`./ruleset/` 不在仓库内。路径相对内核的 HomeDir（`-d` / 客户端自己的数据目录），不存在时首次刷新自动创建。

## Development Commands

```bash
cp subs.example.yaml subs.yaml   # 首次：生成真实清单，再把 REPLACE_* 换成机场订阅 URL
python3 gen.py --check   # 只校验，不写文件（改完先跑这个）
python3 gen.py           # 覆盖生成 config.yaml
node --check auto-groups.js   # 仅语法检查；该文件不在 Node 中运行
python3 -c 'import yaml; yaml.safe_load(open("config.yaml")); print("ok")'  # 产物可解析
```

真机内核自检（可选但最有价值，改 DNS / 规则 / 分组结构后必跑）：

```bash
# 一次性准备（约 30 MB 下载；已存在可跳过）
mkdir -p /tmp/mihomo-bin /tmp/mihomo-home
curl -sSL -o /tmp/mihomo.gz \
  https://github.com/MetaCubeX/mihomo/releases/download/v1.19.33/mihomo-darwin-arm64-v1.19.33.gz
gunzip -f /tmp/mihomo.gz && mv /tmp/mihomo /tmp/mihomo-bin/ && chmod +x /tmp/mihomo-bin/mihomo

# 配置语法 / 语义自检
/tmp/mihomo-bin/mihomo -t -d /tmp/mihomo-home -f config.yaml
# 期望：configuration file ... test is successful
```

- `-t` **不会**下载 `proxy-providers`（实测 1ms 完成），也不会校验订阅可达性；它只能证明配置能被解析、分组引用自洽
- 需要验证规则集可达性 / 规则命中时，用真实内核跑起来并查 `GET /connections` 或看日志里的 `match RuleSet(x) using 组名[...]`
- 查分组构成用 `GET /proxies`（组的 `all` 字段就是最终名单）；查 provider 里的节点名用 `GET /providers/proxies`（实测 1.19.33 下 provider 节点不出现在 `/proxies` 里）
- 三端自带内核同样可 `-v` 验证版本：`"/Applications/Clash Verge.app/Contents/MacOS/verge-mihomo" -v`、`"/Applications/Clash Party.app/Contents/Resources/sidecar/mihomo" -v`
- 无 build / lint / format / test / Makefile / CI；不要臆造 `npm test`、`pytest`、`ruff`
- PyYAML 未声明版本（本机 6.0.3，Python 3.9.23；`gen.py` 有 `from __future__ import annotations`，实际兼容 3.7+），缺少时 `pip install pyyaml`
- 生成后需在客户端**重新导入** `config.yaml`；只有改 `subs.yaml` 才需要重生成（订阅本身由内核刷新）
- 命名/规则改动后的回归标准是 `python3 gen.py --check` 退出码 0 **加**上一条 `mihomo -t`

安全验证做法：把 `gen.py`、`template.yaml`、`subs.example.yaml` 复制到临时目录，`cp subs.example.yaml subs.yaml` 后再运行，避免覆盖当前 `config.yaml`。已实测：这样重生成的产物与仓库内 `config.yaml` 逐字节相同（`diff -q` 通过）；临时目录缺 `subs.yaml` 时 `gen.py` 退出 1 并提示复制命令。

## Code Conventions & Common Patterns

- 注释、docstring、CLI 提示均为中文；成功 `✓`（stdout），校验错误 `✗`（stderr），警告 `!`（stderr）
- 单次同步变换，无 async / 线程 / 网络 / 子进程
- **占位符即注释**：`gen.py` 用 `str.replace` 注入 YAML 块，再由 `dump_block()`（`gen.py:43-49`）整体缩进；`yaml.safe_dump(..., sort_keys=False, allow_unicode=True, width=1000)` 保持顺序、中文与长 URL 单行
- 顺序即语义：provider / group / rule 均按书写顺序输出，不要排序
- 命名以中文 + emoji 作为**跨文件主键**（`🎯 全局直连`、`🚀 节点选择`、`🐟 漏网之鱼`）；改名必须同步模板、规则、`gen.py` 校验、`auto-groups.js`
- 分组绑定订阅用 `use: [providerId]`；跨订阅聚合用 `include-all-providers: true` + `filter` / `exclude-filter`。这些正则是 Go RE2 方言（`(?i)`、`hong ?kong`），Python/JS 只透传不编译
- `filter` / `exclude-filter` 匹配的是**加过前缀之后的节点名**（`[A] 香港01`），前缀是最前部的固定串，不影响正则命中任何位置
- 每个 rule-provider 必须保留 `proxy: DIRECT`。`dns.respect-rules: true` 下，不带该字段时规则集下载会跟着路由走 `MATCH` → `🐟 漏网之鱼`，节点一挂规则集就永远拉不下来（实测踩到，已修）；若镜像被墙，换 `testingcf` → `gcore` 等 jsdelivr 域名，而不是改成走代理
- YAML 锚点复用：`&test_url`、`&svc_common`、`&svc_ai`、`&domestic` / `&foreign`；新增同类分组沿用锚点，不要复制粘贴
- 规则顺序固定：内网直连 → 广告 REJECT → 服务分流（专用先于通用）→ 国内直连 → gfw → `MATCH`；IP 类规则带 `no-resolve`
- 错误处理：输入错误用 `sys.exit("消息")`；校验错误汇总后返回 1；不要吞掉异常

### `subs.example.yaml` / `subs.yaml` 字段契约（`gen.py:52-133`，两份结构相同）

| 键 | 默认 | 产物 |
|---|---|---|
| `name` | `订阅{i}` | 分组名 `{name} · 自动/手动` |
| `id` | `name` 经 `slug()` | `proxy-providers.<id>`、`./providers/<id>.yaml`；必须唯一、建议 ASCII 小写 |
| `url` | 必填 | provider `url`（含 token，敏感） |
| `prefix` | `"[{name}] "` | `override.additional-prefix`；`""` 关闭 |
| `udp` | **true** | 未写即强制开 UDP；关闭需显式 `udp: false` |
| `interval` | `3600` | provider 刷新秒数，`int()` 直转 |
| `tfo` / `additional-suffix` / `proxy-name` / `header` / `proxy` / `exclude-filter` / `health-check-url` | 见 `gen.py:67-133` | 原样透传或映射到 provider 字段 |

`slug()`（`gen.py:38-40`）会把纯中文 id 归并成 `sub`，导致“provider id 重复”；给每条订阅显式 ASCII `id`。

`additional-prefix` / `additional-suffix` / `proxy-name` 已实测生效：`香港01` → `[A] 香港01`、加后缀 → `[A] 香港01 |A`；`proxy-name` 的正则替换先于前后缀执行。

### 易漂移的重复定义

改动这些值时必须全量搜索，避免只改一处：

- 测试地址：`subs.example.yaml:43`（`subs.yaml` 结构相同、同位置）、`template.yaml:163`（`&test_url`）、`auto-groups.js:19`、`gen.py` 的 `test_url` 默认值
- 地区正则：模板（`template.yaml:181-237`）与 `auto-groups.js:30-37` 两套，当前已对齐（含 `川日`、`台北`、`洛杉矶|圣何塞|西雅图`）。模板 `🌍 其他地区` 的 `exclude-filter` 必须包含上述全部关键词，否则同一节点会既进地区组又进“其他地区”；JS 侧由 `REGIONS.map(r => r.re).join("|")` 自动派生，改 `REGIONS` 即可
- `exclude-filter`：`subs.example.yaml:11`（`subs.yaml` 同位置）与 `gen.py:34` 兜底值
- rule-provider 名与 `nameserver-policy` 的 `rule-set:<name>` 键（`template.yaml:99-112`）一一对应
- `auto-groups.js:23-26` 的 `LABELS` 以 provider id 为键；改 id 会退回显示裸 id
- `auto-groups.js` 生成的组名必须与模板同名（`{name} · 自动/手动`、`♻️ 自动选择`、`🌍 其他地区` …），否则规则目标失效

## Important Files

- `gen.py:29-35`：路径与常量（`ROOT`、`TEMPLATE`、`SUBS`、`OUT`、`DEFAULT_EXCLUDE`、`SPECIAL_TARGETS`）
- `gen.py:52-133`：`build()`；`gen.py:136-171`：`check()`；`gen.py:173-206`：`main()`（开头检查 `subs.yaml` 是否存在）
- `template.yaml:7-25`：端口/模式/profile/geo；`:30-39` TUN；`:42-112` DNS（fake-ip、`respect-rules`、分流 DNS）；`:115-133` sniffer
- `template.yaml:141-311`：静态分组；`:316-492` 19 个 rule-providers；`:494-533` 28 条规则
- `config.yaml:135-193` provider 段、`:194-414` 分组、`:415-592` rule-providers、`:593-632` 规则；文件头仍写着“本文件是模板”，属生成时原样复制的注释，不要据此手改
- `auto-groups.js:50-58` `URL_TEST`；`:60-154` `main()`；`:152` 整体替换 `proxy-groups`

不要随意改的值：`mixed-port: 7890`、`allow-lan: false`、`dns.listen 0.0.0.0:1053`、`fake-ip-range 198.18.0.1/16`、`tun.enable: false`（由客户端 GUI 开关接管）、`proxy-server-nameserver` 必须使用 IP 直连的 DoH 以防解析循环、`sniffer.skip-domain`（苹果推送 / 米家发现）、每个 rule-provider 的 `proxy: DIRECT`。

`global-client-fingerprint` 在 1.19.x 已被内核移除（启动即报错提示改到节点上），不要加回去；需要统一指纹时用 provider 的 `override-expr` 给节点写 `client-fingerprint`。

## Runtime/Tooling Preferences

- Python 3（`python3`）+ PyYAML；无虚拟环境、无 lockfile，不要引入新依赖
- `auto-groups.js` 面向客户端内嵌 JS 引擎：仅 ES2015，无 `require` / `import` / `module.exports` / `fs` / 网络；入口必须是 `main(config, profileName)`，返回 config。Node 只用于 `node --check`
- 目标内核特性（`geodata-loader`、`fake-ip-filter-mode`、`nameserver-policy` 的 `rule-set:` 键、`sniffer.override-destination`、`mrs` 规则集格式、`include-all-providers`）在 1.19.32 / 1.19.33 上均可用
- 订阅必须是 **Clash 格式 YAML**。base64 / v2ray 分享链接形式的订阅无法直接喂给 `proxy-providers`，需先用 Sub-Store 或 subconverter 转换；`gen.py` 不做格式探测
- 密钥：`subs[].url`、`subs[].header` 及产物 `proxy-providers.<id>.url/header`。只写键名；真实 token 只放 `subs.yaml`（`.gitignore` 排除），入库的 `subs.example.yaml` 只保留 `REPLACE_*` 占位，`gen.py`（`build()` 里 `"REPLACE" in url` 判断）仅告警不报错。`config.yaml` 由真实清单生成、同样含 token，同样被忽略；`.gitignore` 另排运行期 `providers/`、`ruleset/`

## 客户端导入与覆盖关系

| 客户端 | 导入入口 | 入口函数 | 会覆盖配置的地方 |
|---|---|---|---|
| FlClash 0.9.2 | 配置 → 本地文件 | `main(config)`（多传参数被忽略） | TUN、端口、日志级别等 GUI 开关 |
| Clash Verge Rev 2.5.8 | 订阅 → 新建 → 本地 | `main(config, profileName)`（boa 引擎，无网络/文件 IO） | TUN、端口、**DNS 覆写开关** |
| Clash Party 2.0.4 | 配置 → 本地文件（YAML/JS 覆写） | 同上 | TUN、端口、DNS 覆写 |

- 三个客户端都会用 GUI 设置覆盖 `tun` / `mixed-port` / `mode`，所以文件里 `tun.enable: false` 是刻意的
- Verge / Party 若打开 DNS 覆写，`dns` 整段以 GUI 为准，本仓库的 fake-ip + `respect-rules` 会失效；排查 DNS 问题时先看这个开关
- 订阅刷新由内核按 `interval` 拉取，与客户端“更新订阅”按钮无关；providers 缓存落在客户端自己的数据目录（如 `~/Library/Application Support/<app>/providers/`）
- 需要"某订阅整体挂掉时自动走别的订阅"时，规则目标应指向跨订阅汇总组（`♻️ 自动选择` / `🐟 漏网之鱼` 的默认首项），指向 `{name} · 自动` 只会在这条订阅内部挑节点

## Testing & QA

无测试框架、无 fixture、无 CI。QA = 内置校验 + 内核自检 + 人工导入：

1. `python3 gen.py --check`：YAML 可解析、`proxy-providers` 非空、每订阅分组存在、规则目标与分组 `proxies` 引用可解析
2. `mihomo -t -d <临时目录> -f config.yaml`：内核侧解析与引用自洽
3. 临时目录重生成并与 `config.yaml` diff，确认改动可复现（可选，避免直接覆盖）
4. `node --check auto-groups.js`（如改了 JS）
5. 导入客户端后检查：分组是否出现、订阅是否拉到节点、`REJECT` 规则生效

已完成的实测记录（2026-11-04，`mihomo v1.19.33`）：

- `-t` 通过；19 个 rule-providers 全部从 `testingcf.jsdelivr.net` 实拉成功，0 error
- inline 假订阅验证分组构成：每订阅组只含本订阅节点、地区组跨订阅汇总、`exclude-filter` 剔除 `剩余流量` 假节点、`[A]` 前缀生效、`/providers/proxies` 返回改名后的节点
- 规则命中样例：`www.google.com → RuleSet(google) → 📢 谷歌服务`、`www.netflix.com → RuleSet(netflix) → 🎬 奈飞视频`、`www.baidu.com → RuleSet(cn) → 🎯 全局直连`、`doubleclick.net / pagead2.googlesyndication.com / hm.baidu.com → RuleSet(ads) → 🛑 广告拦截[REJECT]`
- `auto-groups.js` 用 `node` 跑 `main()`，产出的 28 个分组名与模板逐一致
- 未验证：真实机场订阅的连通性与延迟、FlClash GUI 内脚本渲染结果

`--check` **不覆盖**的盲区（改动涉及这些时需人工确认）：rule-provider 名与 DNS 策略键的对应、Go 正则合法性、端口占用、`interval` 非数字会抛 `ValueError`、模板与 `subs.yaml` 的 `test-url` 是否一致、`auto-groups.js` 与模板分组是否同名同义、provider URL 可达性。`--check` 只校验 `subs.yaml`；示例文件本身没有校验入口，改完示例需先复制再跑。

新增校验逻辑时放在 `check()`，保持“只返回错误列表、不写文件”；测试如要引入，优先用临时目录跑 `gen.py` 并断言退出码与产物文本，不要快照整份 `config.yaml`。

## 变更同步清单

| 改动 | 必须同步 |
|---|---|
| 增删订阅 | 改 `subs.yaml`（本机真实 token）；结构变更同步回 `subs.example.yaml` → `gen.py`；`auto-groups.js` 的 `LABELS` 可选 |
| 改分组名 / 新增分组 | `template.yaml` + `rules` 目标 + `auto-groups.js` 组名 + `gen.py` 校验公式 |
| 改地区正则 | 模板 `filter`、模板 `🌍 其他地区` 的 `exclude-filter`、`auto-groups.js` 的 `REGIONS` |
| 改测试地址 | `subs.yaml:43` + `subs.example.yaml:43` + `template.yaml:163` + `auto-groups.js:19` |
| 改端口 / DNS / TUN | 同时确认三个客户端的 GUI 覆盖行为，必要时更新本文件“客户端导入与覆盖关系” |
| 内核版本升级 | 重跑 `-t` 与真实内核验证，更新本文件顶部的版本记录 |
