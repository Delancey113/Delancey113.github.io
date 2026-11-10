---
title: '皮卡丘靶场实战（二）：XSS 三关与 SQL 注入三关'
date: 2026-11-09 21:30:00
updated: 2026-11-09 21:30:00
categories:
  - 网络渗透
tags:
  - XSS
  - SQL注入
  - 皮卡丘靶场
  - Web安全
  - PHP
description: 连打 Pikachu 的反射型/存储型/DOM 型 XSS 与数字型/字符型/搜索型 SQL 注入六关，并用 Source→Sink 方法统一归因、按上下文给修复。
cover: /img/index-banner.jpg
top_img: /img/index-banner.jpg
---
> 上一篇把 Pikachu 搭起来，打完了暴力破解。这一篇继续往下走，打它最经典的两类漏洞：**XSS 三关**（反射型 / 存储型 / DOM 型）和 **SQL 注入三关**（数字型 / 字符型 / 搜索型）。
>
> 六个关卡，六种 payload。但真正想写的不是 payload，而是每次 payload 能成功背后那句共同的话：**数据只是数据，只有当它被放进某个上下文时，才会变成代码。** 防护装错了上下文，等于没装。
>
> 环境不变：Kali `192.168.23.128` 上跑靶场，`http://127.0.0.1/pikachu/` 访问。整套流程不依赖外网。

---

### 目录

- [第 1 站：反射型 XSS（GET）—— 前端限制不是防护](#第-1-站：反射型-XSS（GET）——-前端限制不是防护)
- [第 2 站：存储型 XSS —— 它藏在数据库里](#第-2-站：存储型-XSS-——-它藏在数据库里)
- [第 3 站：DOM 型 XSS —— 服务器全程不知情](#第-3-站：DOM-型-XSS-——-服务器全程不知情)
- [第 4 站：SQL 注入三关 —— 从数字到 like](#第-4-站：SQL-注入三关-——-从数字到-like)
- [第 5 站：源码分析 —— 成因三层，修复四层](#第-5-站：源码分析-——-成因三层，修复四层)
- [附录](#附录)

---

## 第 1 站：反射型 XSS（GET）—— 前端限制不是防护

### 1.1 先看正常的样子

打开 `http://192.168.23.128/pikachu/vul/xss/xss_reflected_get.php`，输入 `kobe` 提交：

![输入 kobe 的正常回显](/img/pikachu-vul-01-reflected-normal.png)

页面回显 `愿你和 kobe 一样，永远年轻，永远热血沸腾！` 并配一张图。

这一步必须做。后面 payload 生效时，你要能一眼看出"多出来的东西"是哪来的。

### 1.2 撞上第一道墙：maxlength="20"

想输 `<script>alert('xss')</script>`，结果输不进去——后面一截被吞掉了。

看源码：

```html
<input class="xssr_in" type="text" maxlength="20" name="message" />
```

`maxlength="20"`，而 payload 有 **29 个字符**，只进去前 20 个（正好到 `alert('xss')` 结尾，`</script>` 全丢）。提交后不弹窗，页面还会缺一块——因为没闭合的 `<script>` 把后面一段 HTML 当成 JS 吃掉了。

**这个"失败"其实是最有价值的一步**：它说明拦你的是浏览器输入框，不是服务器。

### 1.3 绕过：不走输入框，走 URL

表单是 `method="get"`，参数本来就在 URL 上。那就直接拼 URL，绕开 maxlength：

```
http://192.168.23.128/pikachu/vul/xss/xss_reflected_get.php?message=<script>alert('xss')</script>&submit=submit
```

回车，弹窗：

![地址栏拼 payload，弹窗执行](/img/pikachu-vul-02-reflected-alert.png)

地址栏里 `<` `'` 会被浏览器自动编码成 `%3C` `%27`，但 PHP 收到后自动解码回原字符。**编码不是防护，它只是传输格式。**

### 1.4 证据：payload 被当成了标签

F12 → Elements，找到 `<p class="notice">`：

![payload 在 DOM 里是独立的 script 节点](/img/pikachu-vul-03-reflected-dom.png)

`<script>` 是**彩色的元素节点**，不是灰色的文字。这就是判定的唯一标准：

| 面板里长什么样 | 含义 |
|---|---|
| `<script>alert('xss')</script>`（元素节点，可折叠） | 被当代码解析 → **漏洞成立** |
| `&lt;script&gt;alert('xss')&lt;/script&gt;`（一串普通文字） | 被转义 → 安全 |

图里那个 `<font _mstmutation="1" _msthash="...">` 是另一个坑：**浏览器的网页翻译在改 DOM**。`_mst` 前缀是 Microsoft Translator 的标记。写报告时如果必须给"服务器原始输出"，别用 Elements，用 `view-source:` 或 F12 的 Network → Response——那才是服务器发来的字节。

### 1.5 成因

```php
$html .= "<p class='notice'>who is {$_GET['message']},i don't care!</p>";
```

`$_GET['message']` 被**直接拼接**进 HTML 字符串，然后 `echo` 出去。浏览器看到 `<script>` 就执行——它没有能力区分"这是用户输入"还是"这是页面代码"。

**反射型的特征是"一次性"**：payload 只在这一次响应里存在，不落库。攻击方式是构造一条链接发给别人，点一下才生效。刷新 = 重发请求 = 再次触发。

---

## 第 2 站：存储型 XSS —— 它藏在数据库里

### 2.1 正常留言

打开 `http://192.168.23.128/pikachu/vul/xss/xss_stored.php`，先提交一句 `hello`：

![留言板正常状态](/img/pikachu-vul-04-stored-normal.png)

这个页面用的是 `<textarea>`，**没有 maxlength**，可以随便输多长。

### 2.2 提交 payload

在 textarea 里输入：

```
<script>alert('xss')</script>
```

提交后页面重新加载留言列表，弹窗出现：

![存储型 XSS 弹窗](/img/pikachu-vul-05-stored-alert.png)

### 2.3 关键验证：它真的"存下来"了

弹窗只弹一次说明不了什么，反射型也弹。要证明"存储"，得做三件事：

1. **F5 刷新** → 又弹
2. **关掉浏览器重新打开** → 还弹
3. **换一个浏览器访问同一个 URL** → 还是弹

三条都成立，因为 payload 现在**躺在 MySQL 的 message 表里**，每次查询都会被取出来重新渲染一遍。

### 2.4 最反直觉的一幕：页面上什么都没有

这是我认为这一关最值得记的画面：

![三条留言看起来是空白的](/img/pikachu-vul-06-stored-invisible.png)

留言列表里 `hello` 看得见，后面三条**什么都没有**——只有三个"删除"链接孤零零地挂着。

不是没存进去，而是 **`<script>` 标签不产生任何可见内容**。浏览器执行它，但不画它。

所以存储型 XSS 的危险恰恰在于"看不见"：

> 一条躺在数据库里的恶意留言，在页面上看起来是空白的。管理员打开留言板，眼里什么都没有，弹窗一闪而过，或者页面悄悄把 cookie 发给了别人。**可见的字符会引起怀疑，不可见的执行不会。**

### 2.5 证据：把折叠展开

F12 → Elements，展开 `#show_message`：

![id=57/58/59 三条都是折叠的 script 元素](/img/pikachu-vul-07-stored-dom.png)

`id=56` 是 `hello`（文字直接显示），`id=57/58/59` 后面带着 `⋯` 折叠标记——里面各是一个 `<script>` 元素。

### 2.6 成因：那个"看起来做了防护"的函数

存进去之前，代码确实做了一件事：

```php
$message = escape($link, $_POST['message']);
$query = "insert into message(content,time) values('$message',now())";
```

`escape()` 定义在 `inc/mysql.inc.php`：

```php
function escape($link,$data){
    if(is_string($data)){
        return mysqli_real_escape_string($link,$data);
    }
    ...
}
```

**`mysqli_real_escape_string()` 只管 SQL 上下文。** 它转义的是 `'` `"` `\` 和空字节——这些字符在 SQL 字符串里有特殊含义。而 `<` `>` `&` 在 SQL 语法里毫无意义，所以它原样放行。

一句话说清这一关：

> **SQL 转义防的是"进数据库的那条路"，XSS 防的是"从数据库出到浏览器页面的那条路"。两个方向、两种上下文，用一个函数去管，注定漏一边。**

而且这种"半防御"比完全不防更危险——它让代码审查者看到 `escape()` 就以为"这里处理过了"，从而跳过。

---

## 第 3 站：DOM 型 XSS —— 服务器全程不知情

### 3.1 先看正常效果

`http://192.168.23.128/pikachu/vul/xss/xss_dom.php`，输入 `hello` 点 **click me!**：

![点击后生成一个链接](/img/pikachu-vul-08-dom-normal.png)

页面出现一个链接 `what do you see?`。点它没反应，因为 `href='hello'` 是个相对路径。

### 3.2 第一种 payload：闭合属性，注入事件

输入框填：

```
' onclick="alert('xss')">
```

点 **click me!**，再点生成的链接：

![点击链接触发弹窗](/img/pikachu-vul-09-dom-onclick.png)

拼接结果是：

```html
<a href='' onclick="alert('xss')">'>what do you see?</a>
```

`href` 用**单引号**包裹，payload 第一个字符就是 `'`，先把属性闭合，再塞一个 `onclick` 进去。这是"属性上下文"的逃逸。

### 3.3 第二种 payload：闭合标签，无需点击

```
'><img src=x onerror=alert('xss')>
```

点 **click me!**，**不用再点链接**，弹窗直接弹：

![图片加载失败触发 onerror](/img/pikachu-vul-10-dom-onerror.png)

```html
<a href=''><img src=x onerror=alert('xss')>'>what do you see?</a>
```

`'` 闭合 href，`>` 闭合 `<a>` 标签本身，`<img>` 成为独立元素。`src=x` 必然加载失败，触发 `onerror`——**被动执行，受害者什么都不用点**。比上一种更狠。

### 3.4 为什么说服务器"不知情"

看源码：

```javascript
function domxss(){
    var str = document.getElementById("text").value;
    document.getElementById("dom").innerHTML = "<a href='"+str+"'>what do you see?</a>";
}
```

```html
<input id="button" type="button" value="click me!" onclick="domxss()" />
```

注意 `type="button"`——**不是 `type="submit"`**。点它只执行 JS，不提交表单。整条链路在浏览器内存里跑完：

```
输入框 → JS 取值 → 拼字符串 → innerHTML 写回页面
      ↑_____________ 没有 HTTP 请求 _____________↑
```

后端那几行更能说明问题：

```php
if(isset($_GET['text'])){
    $haha = "这里是后台的处理逻辑";   // 取了个变量，然后就扔了
}
```

后端唯一做的事是把 `$_GET['text']` 赋给一个变量，然后什么都不输出。

所以这一关的性质和前两关根本不同：

| | 反射型 | 存储型 | **DOM 型** |
|---|---|---|---|
| 服务器收到 payload 吗 | 收到（GET） | 收到（POST） | **收不到** |
| WAF 能拦吗 | 能 | 能 | **不能**（看不到流量） |
| 服务器日志有痕迹吗 | 有 | 有（数据库） | **没有** |
| 刷新后还在吗 | 不在 | 在 | 不在 |

**结论：服务端怎么做防护都没用。** 加 WAF、加输入过滤、加日志审计，全部落空——因为 payload 一次都没离开过浏览器。

### 3.5 修复：只能改前端

把 `innerHTML` 换成 `textContent`：

```javascript
function domxss(){
    var str = document.getElementById("text").value;
    document.getElementById("dom").textContent = str;
}
```

在 nano 里改（`sudo nano -B` 会自动留备份）：

![改之前：innerHTML 把字符串当 HTML 解析](/img/pikachu-vul-11-dom-source.png)

保存后重放 `'><img src=x onerror=alert('xss')>`：

![修复后 payload 变成纯文字](/img/pikachu-vul-12-dom-fixed.png)

不弹窗了，页面上原样显示 `'><img src=x onerror=alert('xss')>`——**一串纯文字，没有蓝色下划线，没有图片元素**。

`textContent` 和 `innerHTML` 的差别就一句话：

> `innerHTML` 是**解析器**，会让浏览器把字符串当成 HTML 语法重新解析一遍（标签生效）；`textContent` 是**赋值器**，直接把字符塞进文本节点（标签只是字符）。

### 3.6 两个真实的坑

**坑一：改了没生效。** 第一次改的时候，我在文件里同时留下了两行：

```javascript
document.getElementById("dom").textContent = "what do you see?";   // 新加的
document.getElementById("dom").innerHTML = "<a href='"+str+"'>...";  // 原来那行还在
```

JS 逐句执行，**后一句覆盖前一句**，漏洞原封不动。排查这类问题不要只看"我有没有加防护"，要看"防护之后还有没有别的代码在写同一个地方"。在 Elements 里选中目标节点，右键 **Break on → subtree modifications**，谁改它一目了然。

**坑二：以为 `encodeURIComponent()` 就安全了。** 并不是：

```javascript
encodeURIComponent("'")     // 返回 "'"  ← 单引号根本没被编码
```

它不编码 `'` `(` `)` `!` `*`，而这里的 `href` 恰好用单引号包裹，payload 里那个 `'` 照样能闭合属性。

> URL 编码、HTML 实体编码、SQL 转义、JS 转义是**四种不同的上下文编码**，混用等于没防护。判断标准只有一个：数据最终落在哪个上下文，就用那个上下文的编码器。

---

## 第 4 站：SQL 注入三关 —— 从数字到 like

### 4.0 先建立一个方法

注入的第一步不是背 payload，是**读拼接语句**。三关全部适用这张表：

| 先回答什么 | 为什么重要 |
|---|---|
| 变量有没有被引号包裹 | 决定要不要先闭合引号 |
| 是 `=` 还是 `like` | `like` 多一层 `%`，要一起闭合 |
| 是数字还是字符串 | 数字型不用引号，字符型必须闭合 |

### 4.1 数字型：`where id=$id`

源码（`vul/sqli/sqli_id.php`）：

![源码：id=$id，两边没有引号](/img/pikachu-vul-13-sqli-int-source.png)

```php
$id=$_POST['id'];
$query="select username,email from member where id=$id";
```

`id=$id` **没有引号**——程序认定你只会输数字。

先正常查一次 `id=1`：

```bash
curl -s -d "id=1" -d "submit=1" http://127.0.0.1/pikachu/vul/sqli/sqli_id.php | grep -o "hello,[^<]*"
```

![只有一条：vince](/img/pikachu-vul-14-sqli-int-normal.png)

只有 1 条。这个"1"要记住，一会儿用来对比。

注入：把 `id` 的值换成 `1 or 1=1`：

```bash
curl -s --data-urlencode "id=1 or 1=1" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_id.php | grep -o "hello,[^<]*"
```

![一条变七条](/img/pikachu-vul-15-sqli-int-injected.png)

**1 条 → 7 条，全表泄露。**

实际执行的语句是：

```sql
select username,email from member where id=1 or 1=1
```

`1=1` 恒真，`or` 让整个条件恒真，每行都匹配。

两个操作细节：

- 前端是 `<select>` 下拉框，只有 1~6 六个选项，输不进 `1 or 1=1`。绕过方式：F12 改 `option` 的 `value`，或者干脆用 curl——**前端限制从来不是防护**。
- `submit` 的值随便填。源码只判断 `isset($_POST['submit'])`，只要这个字段存在就行，所以 `-d "submit=1"` 足够，不用发中文「查询」省掉编码麻烦。

#### 一个真实的认知错误

中途我直接在终端里敲了这句：

```
select id,email from member where username='kobe'
```

结果 zsh 报 `parse error near 'id,email'`：

![SQL 不是终端命令](/img/pikachu-vul-16-sql-as-command.png)

因为 `select` 恰好是 zsh 的内建命令（做菜单循环的），所以它不是 `command not found`，而是抱怨语法。

分清三种"输入"：

| 你输入的 | 谁接收 | 谁执行 |
|---|---|---|
| `curl ...` | 本机 zsh | zsh 调用 curl |
| `id=1 or 1=1` | 网络 → PHP | 数据库（被拼接后） |
| `select ...` | 数据库客户端 | MySQL |

**攻击者永远只输入第二层**——参数的值。SQL 语句是 PHP 自己拼的，这才是注入的本质：**你的输入混进了服务器自己写的 SQL 里。**

### 4.2 字符型：变量被单引号夹住了

源码（`vul/sqli/sqli_str.php`）：

```php
$name=$_GET['name'];
$query="select id,email from member where username='$name'";
```

| 对比 | 数字型 | 字符型 |
|---|---|---|
| 拼接 | `where id=$id` | `where username='$name'` |
| 引号 | 无 | **有，单引号** |
| 传参 | POST（`-d`） | **GET（`-G`）** |

先故意写错，看会发生什么。输入 `kobe' or 1=1`：

```bash
curl -s -G --data-urlencode "name=kobe' or 1=1" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_str.php | grep -i error
```

![Fatal error，三重信息泄露](/img/pikachu-vul-17-sqli-str-error.png)

```
Fatal error: Uncaught mysqli_sql_exception: You have an error in your SQL syntax;
... for the right syntax to use near ''' at line 1
in /var/www/html/pikachu/inc/mysql.inc.php:19
```

拼接后是 `where username='kobe' or 1=1'`——**末尾那个 `'` 落单了**。

这一行报错本身就泄露三样东西：

1. `near '''` —— 数据库回显了出错位置附近的 **SQL 片段**
2. `/var/www/html/pikachu/inc/mysql.inc.php` —— 服务器**绝对路径**
3. `Uncaught mysqli_sql_exception` —— PHP 版本与错误处理方式

> 关掉 `display_errors` 是运维底线，但它不修漏洞，只是不给攻击者递刀子。

加注释把多余的引号"吃掉"：

```bash
curl -s -G --data-urlencode "name=kobe' or 1=1 #" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_str.php | grep -o "your uid:[0-9]*"
```

![7 条](/img/pikachu-vul-18-sqli-str-7rows.png)

| 注释符 | 写法 | 注意 |
|---|---|---|
| `#` | `... #` | MySQL 特有 |
| `-- ` | `... -- 注释` | **横杠后必须有空格**，否则无效 |
| `/* */` | `/* ... */` | 块注释 |

`#` 必须交给 `--data-urlencode`（会编成 `%23`）。如果在浏览器地址栏直接输，**`#` 会被当成锚点，根本不会发给服务器**。

### 4.3 搜索型：`like '%$name%'`

源码（`vul/sqli/sqli_search.php`）：

```php
$query="select username,id,email from member where username like '%$name%'";
```

比字符型多一个 `%`——`like` 的通配符，而且它**紧贴在引号内侧**。

正常搜 `k`，拼出 `like '%k%'`，命中"包含 k"的用户：

```bash
curl -s -G --data-urlencode "name=k" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_search.php | grep -o "email is: [^<]*"
```

![2 条：kobe、kevin](/img/pikachu-vul-19-sqli-like-normal.png)

注入。**先故意不闭合 `%`**：

```bash
curl -s -G --data-urlencode "name=k' or 1=1 #" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_search.php | grep -o "email is: [^<]*"
```

结果也是 **7 条**。拼出来是：

```sql
where username like '%k' or 1=1 #%'
```

`like '%k'` 是错的（它匹配"以 k 结尾"，一个都不命中），但 `or 1=1` 恒真，照样全表。

再试规范写法 `k%' or 1=1 #`：

```bash
curl -s -G --data-urlencode "name=k%' or 1=1 #" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_search.php | grep -o "email is: [^<]*"
```

![也是 7 条](/img/pikachu-vul-20-sqli-like-7rows.png)

```sql
where username like '%k%' or 1=1 #%'      ← 第一个条件正常工作了
```

**两种写法结果一模一样。** 这就是最容易骗人的地方：`or 1=1` 是个霸道的兜底，它掩盖了前面条件的好坏。

那区别什么时候暴露？

| 利用方式 | 不闭合 `%`（`k'`） | 闭合 `%`（`k%'`） |
|---|---|---|
| `or 1=1` 拿全表 | ✅ 成功（被兜底了） | ✅ 成功 |
| `union select` | ❌ 列位置对不齐，报错 | ✅ 成功 |
| 布尔盲注（`and 1=1` / `and 1=2`） | ❌ 两次结果一样，判断不出真假 | ✅ 成功 |

所以这句比 payload 更值得记：

> **判断 payload 对不对，标准不是"出结果了没有"，而是"拼出来的 SQL 结构是否合法"。** `or 1=1` 这种暴力 payload 经常掩盖结构错误，让人误以为自己理解了。

### 4.4 彩蛋：同一个参数，两个洞

回到 `sqli_search.php` 第 34 行：

```php
$html2.="<p class='notice'>用户名中含有{$_GET['name']}的结果如下：<br />";
```

`$_GET['name']` **没做任何转义就输出到 HTML**。同一个参数上，同时挂着 SQL 注入和 XSS。

在搜索框里输入：

```
k' or 1=1 #<script>alert(1)</script>
```

弹窗：

![同一个参数同时打穿 SQL 和 XSS](/img/pikachu-vul-21-bonus-alert.png)

7 个用户全部列出：

![注入结果 7 条](/img/pikachu-vul-22-bonus-result.png)

为什么必须输在搜索框里、不能直接打地址栏？因为浏览器提交 GET 表单时会自动 URL 编码，`#` 会被编成 `%23`；地址栏直接输，`#` 会被当成锚点吞掉。

**这一张图说明的事**：一份输入进来，PHP 拿它干了两件不同的事——拼进 SQL、输出到 HTML。两个出口各自需要各自的防护，少一个就漏一个。这就是"纵深防御"为什么要按上下文分别处理，而不是"在入口过滤一下"。

---

## 第 5 站：源码分析 —— 成因三层，修复四层

这一站是这篇博客真正想写的东西。上面六个关卡，payload 各不相同，但归因的方法只有一套。

### 5.1 方法：Source → Sink

每个漏洞都能用同一句话描述：

> **一个不可信的数据（Source），沿着一条没有加固的路径，到达了一个能执行代码的地方（Sink）。**

| 找什么 | 长什么样 |
|---|---|
| **Source**：数据从哪来 | `$_GET` `$_POST` `$_COOKIE` `$_REQUEST` `location.search` `input.value` |
| **Sink**：数据去了哪 | `mysqli_query()`、`echo`、`innerHTML`、`eval()`、`system()` |

中间路径上有没有做**对应上下文的编码**——有就安全，没有就是漏洞。

### 5.2 六个洞填进同一张表

| 漏洞 | Source | Sink | 保护丢失在哪 | 上下文 |
|---|---|---|---|---|
| 反射型 XSS | `$_GET['message']` | `echo $html` | 拼接后直接 echo | HTML 文本 |
| 存储型 XSS | `$_POST['message']` | `echo $data['content']` | 入库只做 SQL 转义，**出库无 HTML 编码** | HTML 文本 |
| DOM 型 XSS | `input.value` | `innerHTML` | 前端把字符串当 HTML 解析 | HTML 片段 |
| 数字型 SQLi | `$_POST['id']` | `mysqli_query` | 变量插入**无引号**位置 | SQL 数值 |
| 字符型 SQLi | `$_GET['name']` | `mysqli_query` | 变量插入**单引号内** | SQL 字符串 |
| 搜索型 SQLi | `$_GET['name']` | `mysqli_query` | 变量插入 **`like '%...%'`** | SQL 模式串 |

特别注意最后三行里有两个 `$_GET['name']`——**同一份数据，两个不同的 Sink**。

### 5.3 三层成因

只写"因为没有过滤用户输入"，是废话，指导不了修复。合格的归因要分三层：

#### 第 1 层｜直接原因（代码级）

字符串拼接：`"... where id=$id"`、`"<p>" + str + "</p>"`。
数据被当成了**语法的一部分**，而不是语法之外的值。

#### 第 2 层｜设计原因（原则级）

没有区分「**数据**」与「**代码**」。
SQL 语句的骨架和用户输入混在同一个字符串里，数据库和浏览器都无法分辨哪个是"命令"、哪个是"内容"。防护的本质，就是**在边界上把两者彻底分开**。

#### 第 3 层｜工程原因（流程级）

看存储型那行 `escape($link, $_POST['message'])`：作者是知道要防的，但他用了一个**只管 SQL 的函数**去防 XSS。

这种"半防御"比完全不防更危险——它给代码审查者一种"这里处理过了"的错觉，安全测试时也容易被跳过。

所以真正的教训不是"他没有过滤"，而是：

> **全站没有一个统一的输出层。每个页面各写各的 `echo`，防护强度全凭个人记忆。只要漏掉一处，整站就破。**

### 5.4 修复四层

| 层 | 做什么 | 代码 |
|---|---|---|
| **① 根本（结构性）** | 让数据和语法物理分离 | `$stmt=$link->prepare("select ... where id=?"); $stmt->bind_param("i",$id);` |
| **② 输出（必须）** | 按上下文编码 | HTML：`htmlspecialchars($s, ENT_QUOTES, 'UTF-8')`；DOM：`textContent`；URL：`rawurlencode` |
| **③ 纵深（辅助）** | 输入校验白名单 | `if(!is_numeric($id)) die();` 类型、长度、格式 |
| **④ 兜底（运维）** | 降低被利用后的损失 | CSP 头、Cookie 加 `HttpOnly`、`display_errors=Off`、数据库最小权限 |

顺序不能颠倒：**②不能替代①，③不能替代②。**

输入校验只能是"降低概率"，因为黑名单永远列不全——拦了 `<script>`，还有 `<img onerror>`、`<svg onload>`、`javascript:`。这次六个关卡用的 payload，没有一个是同一个形状。

### 5.5 一句总结

> **输入是不可信的，但也是无辜的。真正危险的不是数据本身，而是数据被放进了哪个上下文。所以防护不发生在入口，而发生在出口。**

---

## 附录

### A. 实验环境

| 项目 | 值 |
|---|---|
| 靶场 | Pikachu（PHP） |
| 地址 | `http://127.0.0.1/pikachu/` |
| 运行时 | Apache 2.4 + PHP 8.4 + MariaDB |
| 浏览器 | Edge / Firefox（做 Web 题建议用无翻译的浏览器） |
| 攻击目标 | 仅限本机靶场，不涉及任何外部站点 |

### B. payload 与命令清单

**XSS**

```
# 反射型 GET
?message=<script>alert('xss')</script>&submit=submit

# 存储型（textarea 无长度限制）
<script>alert('xss')</script>

# DOM 型·属性闭合
' onclick="alert('xss')">

# DOM 型·标签闭合（无需点击）
'><img src=x onerror=alert('xss')>
```

**SQL 注入**

```bash
# 数字型
curl -s --data-urlencode "id=1 or 1=1" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_id.php | grep -o "hello,[^<]*"

# 字符型
curl -s -G --data-urlencode "name=kobe' or 1=1 #" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_str.php | grep -o "your uid:[0-9]*"

# 搜索型
curl -s -G --data-urlencode "name=k%' or 1=1 #" -d "submit=1" \
  http://127.0.0.1/pikachu/vul/sqli/sqli_search.php | grep -o "email is: [^<]*"
```

**参数说明**

| 参数 | 作用 |
|---|---|
| `-d` | POST，原样发送 |
| `--data-urlencode` | POST，自动编码（含空格、`#`、引号时必须用） |
| `-G` | 把 `-d` 的内容拼到 URL 上，变成 GET |
| `grep -o "pattern"` | 只提取匹配片段，一行打印一个，方便数数 |

### C. 踩坑记录

| 坑 | 现象 | 原因 |
|---|---|---|
| maxlength 截断 | payload 只进去一半，不弹窗 | 前端 `maxlength="20"`，payload 29 字符 |
| Edge 翻译改 DOM | Elements 里冒出 `<font _mstmutation>` | 微软翻译插件重写文本节点 |
| 改了没生效 | 修复后仍然弹窗 | `innerHTML` 在 `textContent` 之后执行，覆盖了修复 |
| SQL 当命令敲 | `zsh: parse error` | `select` 是 shell 内建命令，SQL 要交给数据库 |
| 没带 `submit` | 页面空白，什么都不返回 | 源码判断 `isset($_POST['submit'])`，缺字段直接跳过 |
| `#` 被吞 | 注释不生效，仍然报错 | URL 里 `#` 是锚点，必须编码为 `%23` |

---

*全部实验在本机隔离靶场完成。对非授权目标使用上述技术属违法行为。*
