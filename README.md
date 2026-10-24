# Hexo + Butterfly 博客

一套开箱即用的博客：顶部导航栏、右侧边栏、首页大横幅、文章封面大图、目录、深色模式、本地搜索、RSS。

---

## 一、必须先改的 4 处

| 文件 | 改什么 | 说明 |
|---|---|---|
| `_config.yml` | `url: https://yourname.github.io` | 换成你的 Pages 地址 |
| `_config.yml` | `title` / `author` | 站点名和作者 |
| `_config.butterfly.yml` | `social:` 里的 GitHub、邮箱链接 | 侧边栏下的图标 |
| `_config.butterfly.yml` | `card_author.button.link` | 「关注我」按钮跳转地址 |

> 如果仓库名不是 `用户名.github.io`，`url` 要写成 `https://用户名.github.io/仓库名`，同时 `_config.yml` 的 `root` 改成 `/仓库名/`。

---

## 二、本地预览

```bash
npm install
npx hexo server      # 打开 http://localhost:4000
```

改配置后如果页面没变化，先 `npx hexo clean` 再重新生成。

### 关于依赖：Hexo 8 的变化（重要）

Hexo 8 把渲染器和生成器从核心里拆了出来，`npm install hexo` **不会**自动带上它们。
本项目的 `package.json` 已经列全了，直接 `npm install` 即可，但你要知道缺了哪个会出什么症状：

| 缺失的包 | 症状 |
|---|---|
| `hexo-renderer-marked` | 文章完全不生成，`public/posts/` 是空的 |
| `hexo-generator-index` | 没有 `index.html`，网站打不开 |
| `hexo-generator-archive` / `category` / `tag` | 归档/分类/标签页 404 |
| `hexo-server` | `hexo server` 命令不存在，只打印 Usage |
| `hexo-renderer-pug` / `stylus` | Butterfly 报渲染错误，页面空白 |

另外 `package.json` 里必须有这个字段，否则 Hexo 不加载任何插件、只剩下 `help/init/version` 三个命令：

```json
"hexo": { "version": "8.1.2" }
```

---

## 三、写文章

### 方法 1：用脚手架（推荐）

```bash
npx hexo new post "文章标题"
```

会在 `source/_posts/` 生成 md 文件，**front-matter 里已经带好 `cover` 和 `top_img` 字段**，你只要把图片路径改成自己的图。

### 方法 2：直接新建 md

放在 `source/_posts/`，头部必须写成这样：

```yaml
---
title: 文章标题
date: 2026-10-24 12:00:00
tags:
  - 标签1
categories:
  - 分类名
description: 首页卡片上显示的摘要
cover: /img/我的大图.jpg      # 首页卡片封面
top_img: /img/我的大图.jpg    # 文章页顶部横幅
---
```

正文里想让首页只显示摘要，在合适位置插入 `<!-- more -->`。

---

## 四、图片放哪里（重点）

**所有图片统一放 `source/img/` 目录：**

```text
source/img/
├── avatar.png          # 侧边栏头像
├── favicon.png         # 浏览器标签图标
├── index-banner.jpg    # 首页顶部大横幅（建议 1920×1080）
├── default-cover.jpg   # 文章没配封面时的默认图
├── post-cover-1.jpg    # 示例文章封面
└── post-cover-2.jpg    # 示例文章封面
```

引用规则：

- 配置里写 `/img/xxx.jpg`，**开头的 `/` 不能漏**
- 换自己的图：**保持文件名不变直接覆盖**最省事，不用改任何配置
- 想用新文件名，改两个地方：文章 front-matter 的 `cover` / `top_img`，或 `_config.butterfly.yml` 里的 `index_img` / `default_top_img`

各个位置对应哪张图：

| 页面位置 | 由谁决定 | 优先级 |
|---|---|---|
| 首页顶部大横幅 | `index_img` | 固定 |
| 文章卡片封面 | 文章的 `cover` → `cover.default_cover` | 文章优先 |
| 文章页顶部横幅 | 文章的 `top_img` → `default_top_img` | 文章优先 |
| 归档/标签/分类页横幅 | `archive_img` / `tag_img` / `category_img` | 固定 |

> 图片建议先压缩：横幅宽度 1920 足够，封面 1000 宽足够。GitHub Pages 单文件别超过 5MB。

---

## 五、部署到 GitHub Pages

### 第一次部署

1. 在 GitHub 建仓库，把本目录所有文件推上去（**注意：`node_modules/` 和 `public/` 已在 `.gitignore` 里，不要提交**）
2. 打开仓库 → **Settings → Pages → Build and deployment**
3. **Source 选 `GitHub Actions`**（⚠️ 不是 `Deploy from a branch`，选错 Actions 跑完也不会发布）
4. 推一次代码，等 Actions 跑完（约 1–2 分钟），绿色对勾后访问 `https://用户名.github.io`

### 日常更新

```bash
git add .
git commit -m "新文章"
git push
```

Actions 自动构建发布，不用在本地跑 `hexo g`。

---

## 六、可选增强

### 开评论（推荐 Giscus，免费且基于 GitHub Discussions）

1. 仓库开启 Discussions 功能
2. 到 https://giscus.app 配置，拿到 `repo` 和 `repo-id`
3. 改 `_config.butterfly.yml`：

```yaml
comments:
  enable: true
  use: Giscus
```

并在同文件底部加：

```yaml
giscus:
  repo:
  repo_id:
  category:
  category_id:
  mapping: pathname
  light_theme: light
  dark_theme: dark
```

### 开数学公式（写推导必备）

默认 Markdown 渲染器会把 `\\` 吃掉，需要换渲染器：

```bash
npm uninstall hexo-renderer-marked
npm install hexo-renderer-kramed
npx hexo clean
```

然后改 `_config.butterfly.yml`：

```yaml
mathjax:
  enable: true
  per_page: true      # 只在写了 mathjax: true 的文章里加载
```

文章 front-matter 加一行 `mathjax: true` 即可。

### 换主题色

`_config.butterfly.yml` 里 `theme_color.enable: true`，然后在下面的 `theme_color` 列表里填色值。

---

## 七、目录结构

```text
├── _config.yml               站点配置（改 url/title/author）
├── _config.butterfly.yml     主题配置（导航/侧边栏/封面都在这）
├── package.json              依赖
├── scaffolds/                文章模板
├── source/
│   ├── _posts/               文章放这里
│   ├── about/index.md        关于页
│   ├── tags/categories/link  标签/分类/友链页
│   └── img/                  所有图片
└── .github/workflows/deploy.yml   自动部署
```

---

## 八、常见问题

**`hexo generate` 只打印 Usage: hexo &lt;command&gt;** → `package.json` 缺少 `"hexo": { "version": "..." }` 字段，加上即可。

**页面空白 / 报 render 错误** → 没装 pug 或 stylus 渲染器：
```bash
npm install hexo-renderer-pug hexo-renderer-stylus
```

**改了配置没生效** → `npx hexo clean && npx hexo generate`

**封面图裂了** → 检查路径有没有开头的 `/`，以及文件是不是真的在 `source/img/` 下

**归档页显示 No title** → 归档页 md 文件缺少 `type: archives`，检查一下 `source/` 下各目录的 index.md

**Actions 报 npm ci 错误** → 本地 `npm install` 后要把 `package-lock.json` 一起提交
