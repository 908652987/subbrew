// =====================================================================
// mihomo 多订阅「自动建组」脚本（三端通用）
//
// 作用：读取配置里已有的 proxy-providers，按订阅自动生成分组，再生成
//       总聚合 / 地区 / 服务分流组。新增或删除订阅后不用改脚本、不用
//       重新生成配置，重新加载配置即可。
//
// 用法：
//   Clash Verge Rev  配置 → 新建 → Script，粘贴本文件，然后在订阅上启用
//   Clash Party      覆写 → 新建 → JavaScript（同样走 main(config)）
//   FlClash          配置 → 覆写脚本
//   三个客户端入口一致：main(config, profileName)；FlClash 只传 config，多出的参数会被忽略
//
// 注意：脚本只能改配置对象，不能联网/读写文件；订阅地址必须写在 profile 的
//       proxy-providers 里，而不是脚本里。
// =====================================================================

// 延迟测试地址
const TEST_URL = "https://www.gstatic.com/generate_204";

// 订阅显示名：key 是 proxy-providers 里的键名（provider id）
// 不写的 id 会直接用 id 作为显示名
const LABELS = {
  a: "机场A",
  b: "机场B",
  c: "机场C",
};

// 地区分组（跨订阅自动汇总，正则匹配节点名）
const REGIONS = [
  { name: "🇭🇰 香港节点", re: "(?i)香港|港|hk|hong ?kong" },
  { name: "🇹🇼 台湾节点", re: "(?i)台湾|台|tw|taiwan|台北" },
  { name: "🇯🇵 日本节点", re: "(?i)日本|jp|japan|东京|大阪|川日" },
  { name: "🇸🇬 新加坡节点", re: "(?i)新加坡|狮城|sg|singapore" },
  { name: "🇰🇷 韩国节点", re: "(?i)韩国|韩|kr|korea|首尔" },
  { name: "🇺🇸 美国节点", re: "(?i)美国|美|us|usa|united ?states|america|洛杉矶|圣何塞|西雅图" },
];

// 服务分组可选的出口（顺序即 UI 里的顺序）
const SERVICE_CHOICES = [
  "🚀 节点选择",
  "♻️ 自动选择",
  "🇺🇸 美国节点",
  "🇯🇵 日本节点",
  "🇸🇬 新加坡节点",
  "🇭🇰 香港节点",
  "DIRECT",
];

const URL_TEST = {
  type: "url-test",
  url: TEST_URL,
  interval: 300,
  tolerance: 50,
  timeout: 3000,
  "max-failed-times": 3,
  lazy: true,
};

function main(config, profileName) {
  const providers = config["proxy-providers"] || {};
  const ids = Object.keys(providers);
  if (ids.length === 0) return config; // 没有多订阅就不动配置

  // ---------- 每订阅独立分组（核心：自动跟随 providers） ----------
  const subGroups = [];
  const subGroupNames = [];
  for (const id of ids) {
    const label = LABELS[id] || id;
    const auto = label + " · 自动";
    const manual = label + " · 手动";
    subGroups.push(Object.assign({}, URL_TEST, {
      name: auto,
      use: [id],
      hidden: false,
    }));
    subGroups.push({ name: manual, type: "select", use: [id] });
    subGroupNames.push(auto, manual);
  }

  const groups = [];

  // ---------- 节点选择（总入口） ----------
  groups.push({
    name: "🚀 节点选择",
    type: "select",
    proxies: ["♻️ 自动选择", "🖱️ 手动选择"]
      .concat(REGIONS.map((r) => r.name), ["🌍 其他地区", "🎯 全局直连"])
      .concat(subGroupNames, ["DIRECT"]),
  });

  // ---------- 自动选择：所有订阅的全部节点 ----------
  groups.push(Object.assign({}, URL_TEST, {
    name: "♻️ 自动选择",
    "include-all-providers": true,
  }));

  // ---------- 手动选择：所有订阅的全部节点，手动挑一个 ----------
  groups.push({
    name: "🖱️ 手动选择",
    type: "select",
    "include-all-providers": true,
    hidden: false,
  });

  // ---------- 订阅选择：每订阅一组（自动 / 手动） ----------
  for (const group of subGroups) groups.push(group);

  // ---------- 地址选择：跨订阅自动汇总 ----------
  for (const region of REGIONS) {
    groups.push(Object.assign({}, URL_TEST, {
      name: region.name,
      "include-all-providers": true,
      filter: region.re,
    }));
  }
  groups.push({
    name: "🌍 其他地区",
    type: "select",
    "include-all-providers": true,
    "exclude-filter": REGIONS.map((r) => r.re).join("|"),
  });

  // ---------- 其他选择：服务分流 ----------
  const services = [
    "🤖 AI服务",
    "✈️ 电报消息",
    "📹 油管视频",
    "🎬 奈飞视频",
    "🎵 Spotify",
    "📢 谷歌服务",
  ];
  for (const name of services) {
    groups.push({ name: name, type: "select", proxies: SERVICE_CHOICES.slice() });
  }
  for (const name of ["🍎 苹果服务", "🪟 微软服务"]) {
    groups.push({ name: name, type: "select", proxies: ["🎯 全局直连", "🚀 节点选择"] });
  }
  for (const name of ["🐙 Github", "🎮 游戏平台"]) {
    groups.push({ name: name, type: "select", proxies: SERVICE_CHOICES.slice() });
  }
  groups.push({ name: "🛑 广告拦截", type: "select", proxies: ["REJECT", "DIRECT"] });

  // ---------- 兜底 ----------
  groups.push({
    name: "🐟 漏网之鱼",
    type: "select",
    proxies: ["🚀 节点选择", "♻️ 自动选择", "🖱️ 手动选择", "DIRECT"],
  });
  groups.push({ name: "🎯 全局直连", type: "select", proxies: ["DIRECT"] });

  config["proxy-groups"] = groups;
  return config;
}
