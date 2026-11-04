#!/usr/bin/env python3
"""把 subs.yaml + template.yaml 渲染成 config.yaml。

订阅清单：subs.example.yaml（入库，占位）复制为 subs.yaml（真实 token，不入库）后使用；
config.yaml 是生成产物，同样不入库。

用法:
    python3 gen.py              # 生成 config.yaml
    python3 gen.py --check      # 只做校验，不写文件

产物在三个客户端里通用（mihomo 内核 + 客户端自带的 Merge/Script 都不需要）:
    FlClash       配置 -> 本地文件 -> 导入 config.yaml
    Clash Verge   订阅 -> 新建 -> 本地 -> 导入 config.yaml
    Clash Party   配置 -> 本地文件 -> 导入 config.yaml

订阅本身由内核的 proxy-providers 刷新（interval），与客户端"更新订阅"无关，
所以一份静态文件就能长期跑；改动 subs.yaml 后才需要重新 gen.py 并重新导入。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template.yaml"
SUBS = ROOT / "subs.yaml"
OUT = ROOT / "config.yaml"

DEFAULT_EXCLUDE = "(?i)剩余|到期|过期|官网|重置|流量|套餐|折扣|客服|公告|订阅"
SPECIAL_TARGETS = {"DIRECT", "REJECT", "REJECT-DROP", "PASS", "COMPATIBLE", "GLOBAL"}


def slug(text: str) -> str:
    out = re.sub(r"[^0-9A-Za-z_-]+", "-", text).strip("-").lower()
    return out or "sub"


def dump_block(obj, indent: int) -> str:
    """把对象渲染成 yaml 片段，并整体缩进 indent 个空格（用于替换模板占位符）。"""
    text = yaml.safe_dump(
        obj, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000
    )
    pad = " " * indent
    return "".join(pad + line if line.strip() else line for line in text.splitlines(True)).rstrip("\n")


def build(cfg: dict):
    test_url = cfg.get("test-url", "https://www.gstatic.com/generate_204")
    default_exclude = cfg.get("exclude-filter", DEFAULT_EXCLUDE)
    subs = cfg.get("subs") or []
    if not subs:
        sys.exit("subs.yaml: subs 为空")

    providers, groups, refs = {}, [], []
    seen_ids, seen_names = set(), set()

    for i, sub in enumerate(subs, 1):
        url = (sub.get("url") or "").strip()
        if not url:
            sys.exit(f"subs.yaml: 第 {i} 条订阅缺少 url")
        if "REPLACE" in url:
            print(f"! subs.yaml: 第 {i} 条订阅还是占位地址，导入后这份订阅不会有节点", file=sys.stderr)
        name = str(sub.get("name") or f"订阅{i}").strip()
        pid = slug(str(sub.get("id") or name))
        if pid in seen_ids:
            sys.exit(f"subs.yaml: provider id 重复: {pid}")
        if name in seen_names:
            sys.exit(f"subs.yaml: name 重复: {name}")
        seen_ids.add(pid)
        seen_names.add(name)

        prefix = sub.get("prefix", f"[{name}] ")
        health = {
            "enable": True,
            "url": test_url,
            "interval": 300,
            "timeout": 3000,
            "lazy": True,
            "expected-status": "*",
        }
        provider = {
            "type": "http",
            "url": url,
            "path": f"./providers/{pid}.yaml",
            "interval": int(sub.get("interval", 3600)),
            "proxy": sub.get("proxy", "DIRECT"),
            "health-check": dict(health, url=sub.get("health-check-url", test_url)),
            "exclude-filter": sub.get("exclude-filter", default_exclude),
        }
        if sub.get("header"):
            provider["header"] = sub["header"]

        override = {}
        if sub.get("udp", True):
            override["udp"] = True
        if sub.get("tfo"):
            override["tfo"] = True
        if prefix:
            # 多订阅节点重名会让"聚合/地区组"串味，统一加前缀
            override["additional-prefix"] = prefix
        if sub.get("additional-suffix"):
            override["additional-suffix"] = sub["additional-suffix"]
        if sub.get("proxy-name"):
            override["proxy-name"] = sub["proxy-name"]
        if override:
            provider["override"] = override

        providers[pid] = provider

        auto, manual = f"{name} · 自动", f"{name} · 手动"
        seen_names.add(auto)
        groups += [
            {
                "name": auto,
                "type": "url-test",
                "use": [pid],
                "url": test_url,
                "interval": 300,
                "tolerance": 50,
                "timeout": 3000,
                "max-failed-times": 3,
                "lazy": True,
            },
            {"name": manual, "type": "select", "use": [pid]},
        ]
        refs += [auto, manual]

    return providers, groups, refs


def check(text: str, subs_names) -> list[str]:
    """校验渲染结果：YAML 可解析、规则目标分组存在。"""
    errors = []
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # noqa: BLE001
        return [f"YAML 解析失败: {exc}"]

    names = {g["name"] for g in doc.get("proxy-groups") or []}
    if "proxy-providers" not in doc or not doc["proxy-providers"]:
        errors.append("proxy-providers 为空")
    missing = [n for n in subs_names if not ({f"{n} · 自动", f"{n} · 手动"} & names)]
    if missing:
        errors.append(f"缺少订阅分组: {missing}")

    for rule in doc.get("rules") or []:
        parts = [p.strip() for p in str(rule).split(",")]
        if not parts or not parts[0]:
            errors.append(f"空规则: {rule!r}")
            continue
        if parts[0].upper() == "MATCH":
            target = parts[1] if len(parts) > 1 else ""
        else:
            while len(parts) > 1 and parts[-1].lower() in {"no-resolve", "src"}:
                parts.pop()
            target = parts[-1] if len(parts) > 1 else ""
        if target.upper() not in SPECIAL_TARGETS and target not in names:
            errors.append(f"规则目标分组不存在: {rule!r} -> {target!r}")

    for group in doc.get("proxy-groups") or []:
        for ref in group.get("proxies") or []:
            if isinstance(ref, str) and ref.upper() not in SPECIAL_TARGETS and ref not in names:
                errors.append(f"分组 {group['name']!r} 引用了不存在的分组 {ref!r}")

    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()

    if not SUBS.exists():
        sys.exit(f"缺少 {SUBS.name}：先执行  cp subs.example.yaml subs.yaml  再填入真实订阅")
    cfg = yaml.safe_load(SUBS.read_text(encoding="utf-8")) or {}
    providers, groups, refs = build(cfg)
    template = TEMPLATE.read_text(encoding="utf-8")

    text = (
        template.replace("# {{PROVIDERS}}", dump_block(providers, 2))
        .replace("# {{SUB_GROUPS}}", dump_block(groups, 2))
        .replace("# {{SUB_GROUP_REFS}}", dump_block(refs, 6))
    )
    if "{{" in text:
        sys.exit("模板里还有未替换的占位符")

    errors = check(text, [str(s.get("name")) for s in cfg["subs"]])
    if errors:
        print("\n".join(f"✗ {e}" for e in errors), file=sys.stderr)
        return 1
    if args.check:
        print(f"✓ 校验通过：{len(providers)} 个订阅，{len(groups)} 个订阅分组")
        return 0

    OUT.write_text(text, encoding="utf-8")
    print(f"✓ 已生成 {OUT.name}：{len(providers)} 个订阅，{len(groups)} 个订阅分组")
    print("  导入后如客户端提示 'providers' 目录不存在，首次刷新会自动创建")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
