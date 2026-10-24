---
title: 博客搭好了：Hexo + Butterfly 上线记录
date: 2026-10-24 12:00:00
updated: 2026-10-24 12:00:00
tags:
  - 博客
  - Hexo
categories:
  - 折腾记录
description: 从「只有文字的 GitHub Pages」到有主题、有侧边栏、有封面大图的博客，记录一次完整的迁移过程。
top_img: /img/post-cover-1.jpg
cover: /img/post-cover-1.jpg
---

之前我的 GitHub Pages 只有一堆纯文字——原因是 Pages 默认只把 Markdown 渲染成最朴素的 HTML，完全没有主题层。想要侧边栏、导航栏、封面图，必须换一套博客框架。

<!-- more -->

## 为什么是 Hexo + Butterfly

| 方案 | 优点 | 缺点 |
|---|---|---|
| Jekyll + Chirpy | Pages 原生支持 | 主题没 Butterfly 好看 |
| **Hexo + Butterfly** | **卡片式布局、封面大图、侧边栏齐全、中文生态好** | 需要构建步骤 |
| Hugo + PaperMod | 构建极快 | 主题不如 Butterfly 花哨 |

选 Butterfly 的理由很直接：**它默认就带首页横幅、文章卡片封面、右侧边栏、目录、深色模式**，不用自己写 CSS。

## 三张图搞懂图片放哪

```text
source/img/
├── avatar.png          # 侧边栏头像
├── index-banner.jpg    # 首页顶部大横幅
├── default-cover.jpg   # 文章默认封面
└── post-cover-1.jpg    # 单篇文章封面
```

引用的时候统一写 `/img/xxx.jpg`，**开头的斜杠不能少**。

单篇文章想换封面，改 front-matter：

```yaml
---
title: 我的文章
cover: /img/我的大图.jpg     # 首页卡片上的图
top_img: /img/我的大图.jpg   # 文章页顶部横幅
---
```

## 部署：交给 GitHub Actions

不想在本地跑 `hexo g`，所以配置了一个 workflow：推代码到 main 分支 → Actions 自动构建 → 发布到 Pages。

```yaml
on:
  push:
    branches: [main]
```

写完 Markdown，`git push` 就完事了。

## 踩坑记录

1. **Butterfly 必须装 pug 和 stylus 渲染器**，否则页面空白报渲染错误。
2. **Jekyll 主题和 Hexo 主题不通用**，别指望把 Butterfly 塞进 Jekyll。
3. **Pages 的 Source 要改成 GitHub Actions**，不然 Actions 跑完也不会发布。

## 下一步

- [ ] 换掉 `index-banner.jpg`，换成自己拍的大图
- [ ] 接一个评论系统（Giscus 或 Twikoo）
- [ ] 开数学公式支持，方便写推导
