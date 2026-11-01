---
title: 从零开始用 curl 做一次完整的内网渗透实验
date: 2026-11-01 14:30:00
updated: 2026-11-01 14:30:00
categories:
  - 网络渗透
tags:
  - curl
  - HTTP
  - 渗透测试
  - Metasploitable
description: 以 curl 为主线，走完环境确认、HTTP 报文分析、请求改造、资产发现、服务识别、Web 探测与会话分析的完整流程。
cover: /img/index-banner.jpg
top_img: /img/index-banner.jpg
---

> 课程作业记录：以 curl 为主线，走完"环境确认 → HTTP 报文分析 → 请求改造 → 资产发现 → 服务识别 → Web 探测 → 会话分析"的完整流程。
>


---

## 一、实验环境

| 角色 | 系统 | 地址 | 说明 |
| --- | --- | --- | --- |
| 宿主机 | Windows 11 | — | 运行 VMware，仅用于写文档 |
| 攻击机 | Kali Linux | 192.168.23.128 | VMware NAT（vmnet8） |
| 靶机 | Metasploitable 2 | 192.168.23.129 | 靶机 |

### 1.1 网卡

```bash
ip a
```

![ip a 查看网卡](/img/curl-02-ip-a.png)

`eth0` 拿到 `inet 192.168.23.128/24`，`scope global dynamic` 说明是 DHCP 分配的，**重启后可能变**。所以每次实验前都要重新查一次地址。

`/24` 的意思是前 24 位固定，最后一位可变 —— 相当于一条街道 `192.168.23.0/24`，能住 254 户。

### 1.2 路由

```bash
ip route
```

![ip route 查看路由](/img/curl-03-ip-route.png)

```
default via 192.168.23.2 dev eth0 proto dhcp src 192.168.23.128 metric 100
192.168.23.0/24 dev eth0 proto kernel scope link src 192.168.23.128 metric 100
```

- **`default via`**：凡不在这条街上的目标，一律交给 `.2`（NAT 网关）绕出去
- **`scope link`**：这条街上的地址直接从 `eth0` 送过去，**不需要经过网关**



完整拓扑：

| 地址 | 是谁 |
| --- | --- |
| 192.168.23.1 | 宿主机虚拟网卡 |
| 192.168.23.2 | NAT 网关 |
| 192.168.23.254 | DHCP 服务器 |
| 192.168.23.128 | 我的 Kali |
| 192.168.23.129 | 靶机 |


---

## 二、确认 curl 可用

```bash
curl --version
```

![curl 版本信息](/img/curl-01-version.png)

关键信息：

```
curl 8.20.0 (x86_64-pc-linux-gnu) libcurl/8.20.0 OpenSSL/3.6.2 ...
Protocols: ... http https ... ftp ldap mqtt rtsp ... ws wss
Features: alt-svc AsynchDNS brotli ... HTTP2 HTTP3 HTTPS-proxy ...
```


1. **TLS 后端是 OpenSSL**。同一份 curl 在 Windows 上走的是 Schannel，两者 TLS 指纹不同。
2. **`Protocols` 里有 20 多种协议**，不只有 HTTP —— `ftp`、`ldap`、`mqtt`、`ws` 都在。
3. **`Features` 里有 HTTP3**，说明这个版本支持 QUIC。

---

## 三、发出第一个请求

```bash
curl http://httpbin.org/get
```

![httpbin 回显](/img/curl-04-httpbin-get.png)

```json
{
  "headers": {
    "Accept": "*/*",
    "Host": "httpbin.org",
    "User-Agent": "curl/8.20.0"
  },
  "origin": "111.55.***.***",
  "url": "http://httpbin.org/get"
}
```

- `origin` 是公网出口 IP —— `192.168.23.128` 是内网地址，出不了门，由 NAT 网关替换
- `User-Agent` 暴露了"我是 curl 脚本"，这是最基础的指纹
- **只有 3 个请求头**，而真实浏览器有十几个

---

## 四、用 `-v` 看见真正的报文

```bash
curl -v http://httpbin.org/get
```

![verbose 报文](/img/curl-07-verbose.png)

curl 用三种前缀标记信息来源：

| 前缀 | 含义 |
| --- | --- |
| `*` | curl 自己的调试信息（DNS、TCP、TLS） |
| `>` | 我发出去的 |
| `<` | 服务器返回的 |

一次完整的 HTTP/1.1 交互：

```
*   Trying 18.227.178.96:80...
* Established connection to httpbin.org (18.227.178.96 port 80) from 192.168.23.128 port 38456
> GET /get HTTP/1.1              ← 请求行
> Host: httpbin.org              ← 请求头
> User-Agent: curl/8.20.0
> Accept: */*
>                                ← 空行！请求头结束
< HTTP/1.1 200 OK                ← 状态行
< content-type: application/json ← 响应头
<                                ← 空行！之后是响应体
{ ... }                          ← 响应体
```

**空行是所有 HTTP 报文的分水岭。** 头在上面，体在下面。

`from 192.168.23.128 port 38456` —— 源端口是系统随机分配的临时端口。一条 TCP 连接由**四元组**唯一确定：源 IP、源端口、目标 IP、目标端口。这也是"改源端口绕过出口防火墙"这类技巧的原理。

输出末尾还有一行：

![verbose 结尾](/img/curl-08-verbose-end.png)

```
* Connection #0 to host httpbin.org:80 left intact
```

`left intact` 说明连接**没有被关闭** —— 这就是 **keep-alive**。HTTP/1.1 默认开启，所以响应头里反而看不到 `Connection: keep-alive`，只有服务端想主动断开时才写 `Connection: close`。

---

## 五、改造请求：把自己伪装成浏览器

### 5.1 改 User-Agent

```bash
curl -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36" http://httpbin.org/get
```

![UA 伪装](/img/curl-05-ua-spoof.png)

返回的 `User-Agent` 变成 Chrome。

### 5.2 一次性塞进多个请求头

```bash
curl -H "User-Agent: Mozilla/5.0 ... Chrome/141.0.0.0 Safari/537.36" \
     -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
     -H "Accept-Language: zh-CN,zh;q=0.9" \
     -H "Referer: https://www.baidu.com/" \
     http://httpbin.org/get
```

![多请求头](/img/curl-06-multi-headers.png)


---

## 六、HTTPS：TLS 到底做了什么

```bash
curl -v https://httpbin.org/get
```

完整输出如下（`origin` 已打码，其他原样）：

```console
$ curl -v https://httpbin.org/get
*   Trying 16.58.42.220:443...
* Host httpbin.org:443 was resolved.
* IPv6: (none)
* IPv4: 16.58.42.220, 3.137.48.32, 18.227.178.96
*   Trying 3.137.48.32:443...
* ALPN: curl offers h2,http/1.1
* TLSv1.3 (OUT), TLS handshake, Client hello (1):
* SSL Trust Anchors:
*   CAfile: /etc/ssl/certs/ca-certificates.crt
*   CApath: /etc/ssl/certs
* TLSv1.3 (IN), TLS handshake, Server hello (2):
* TLSv1.3 (IN), TLS change cipher, Change cipher spec (1):
* TLSv1.3 (IN), TLS handshake, Encrypted Extensions (8):
* TLSv1.3 (IN), TLS handshake, Certificate (11):
* TLSv1.3 (IN), TLS handshake, CERT verify (15):
* TLSv1.3 (IN), TLS handshake, Finished (20):
* TLSv1.3 (OUT), TLS change cipher, Change cipher spec (1):
* TLSv1.3 (OUT), TLS handshake, Finished (20):
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384 / x25519 / id-ecPublicKey
* ALPN: server accepted h2
* Server certificate:
*   subject: CN=httpbin.hbin.postmanlabs.com
*   start date: Oct 28 18:55:57 2026 GMT
*   expire date: Jan 26 18:55:56 2027 GMT
*   issuer: C=US; O=Let's Encrypt; CN=YE1
*   Certificate level 0: Public key type EC/prime256v1 (256/128 Bits/secBits), signed using ecdsa-with-SHA384
*   Certificate level 1: Public key type EC/secp384r1 (384/192 Bits/secBits), signed using ecdsa-with-SHA384
*   Certificate level 2: Public key type EC/secp384r1 (384/192 Bits/secBits), signed using ecdsa-with-SHA384
*   Certificate level 3: Public key type EC/secp384r1 (384/192 Bits/secBits), signed using ecdsa-with-SHA384
*   subjectAltName: "httpbin.org" matches cert's "httpbin.org"
* OpenSSL verify result: 0
* SSL certificate verified via OpenSSL.
* Established connection to httpbin.org (16.58.42.220 port 443) from 192.168.23.128 port 49156
* using HTTP/2
* [HTTP/2] [1] OPENED stream for https://httpbin.org/get
* [HTTP/2] [1] [:method: GET]
* [HTTP/2] [1] [:scheme: https]
* [HTTP/2] [1] [:authority: httpbin.org]
* [HTTP/2] [1] [:path: /get]
* [HTTP/2] [1] [user-agent: curl/8.20.0]
* [HTTP/2] [1] [accept: */*]
> GET /get HTTP/2
> Host: httpbin.org
> User-Agent: curl/8.20.0
> Accept: */*
>
* Request completely sent off
< HTTP/2 200
< access-control-allow-credentials: true
< access-control-allow-origin: *
< access-control-expose-headers: Retry-After, RateLimit, RateLimit-Policy
< content-length: 201
< content-type: application/json
< x-content-type-options: nosniff
< date: Sat, 31 Oct 2026 06:51:29 GMT
<
{
  "args": {},
  "headers": {
    "Accept": "*/*",
    "Host": "httpbin.org",
    "User-Agent": "curl/8.20.0"
  },
  "method": "GET",
  "origin": "111.55.***.***",
  "url": "https://httpbin.org/get"
}
* Connection #0 to host httpbin.org:443 left intact
```

它把一次 HTTPS 请求拆成了三层：**TCP 连接 → TLS 握手 → HTTP 报文**。三种前缀就是三层的分界：

| 前缀 | 谁在说话 |
| --- | --- |
| `*` | curl 自己（DNS 解析、TCP 连接、TLS 握手） |
| `>` | 我发出去的（请求行 + 请求头） |
| `<` | 服务器回的（状态行 + 响应头） |

`From 192.168.23.128 port 49156` ：**源端口 49156 是随机的，目标端口 443 是固定的**。一条 TCP 连接由源 IP、源端口、目标 IP、目标端口这四元组唯一确定。有些出口防火墙只放行 53 或 80，把源端口伪装成 53 偶尔能混过去 —— 这就是"端口绕过"的由来。

### 6.1 协商阶段

```
* ALPN: curl offers h2,http/1.1              ← 我提议
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384 / x25519 / id-ecPublicKey
* ALPN: server accepted h2                    ← 服务器选一个
```

| 协商结果 | 作用 |
| --- | --- |
| `TLSv1.3` | 协议版本。1.3 里握手大部分内容在 ServerHello 之后就加密了 |
| `TLS_AES_256_GCM_SHA384` | 加密套件：AES-256-GCM 加密 + SHA384 哈希 |
| `x25519` | 密钥交换（椭圆曲线 DH），用完作废 |
| `h2`（ALPN） | 应用层协议 —— 所以后面全变成 HTTP/2 |

`ALPN` 是"提议 → 答复"的完整协商：我提两个，服务器选一个。握手消息后面的数字是类型编号：`1`=ClientHello、`2`=ServerHello、`8`=EncryptedExtensions、`11`=Certificate、`20`=Finished。**ClientHello 和 ServerHello 是明文，之后全部加密** —— 所以 TLS 1.3 抓包看不到证书内容。

### 6.2 证书校验：HTTPS 的真正意义

```
*   subject: CN=httpbin.hbin.postmanlabs.com
*   issuer: C=US; O=Let's Encrypt; CN=YE1
*   start date: Oct 28 2026    expire date: Jan 26 2027
*   subjectAltName: "httpbin.org" matches cert's "httpbin.org"
* OpenSSL verify result: 0
```

**反直觉的地方**：证书 `subject` 是 `httpbin.hbin.postmanlabs.com`，我访问的是 `httpbin.org`，名字不一样却通过了 —— 因为现代客户端**只看 `subjectAltName`（SAN），不看 CN**，CN 早已废弃。

`OpenSSL verify result: 0`，0 就是通过。非 0 都是错误码：

| 码 | 含义 |
| --- | --- |
| 0 | 通过 |
| 10 | 证书已过期 |
| 18 | 自签名证书 |
| 20 | 找不到本地 CA（证书链不全） |
| 62 | 主机名与证书不匹配 |

**证书还是情报来源**：这张证书泄露了主域名 `postmanlabs.com`。所有证书签发记录都公开存档在证书透明度（CT）日志里，去 `crt.sh` 搜一个域名，就能挖出它全部历史子域名 —— 这是子域名枚举最省力的一招。

### 6.3 curl 为什么相信这张证书？

```
* SSL Trust Anchors:
*   CAfile: /etc/ssl/certs/ca-certificates.crt
```

这个文件里存着几百个**受信任的根 CA**。curl 拿到证书链后，从 `Certificate level 0` 一级级往上追，追到最后一级，看它是否在这份名单里。

追到了 → `verify result: 0`；追不到 → `error 20: unable to get local issuer certificate`。

所以"信任"不是天生的，是**由这份名单决定的**：

- 删掉这个文件，所有 HTTPS 立刻失败
- `--cacert` 可以指定自己的名单（Burp Suite 解密 HTTPS 就靠这个）
- `-k` 干脆跳过整个校验

### 6.4 亲手验证证书校验拦住了什么

```bash
curl https://expired.badssl.com/
```

返回的终端原文：

```console
$ curl https://expired.badssl.com/
curl: (60) SSL certificate OpenSSL verify result: certificate has expired (10)
More details here: https://curl.se/docs/sslcerts.html

curl failed to verify the legitimacy of the server and therefore could not
establish a secure connection to it. To learn more about this situation and
how to fix it, please visit the webpage mentioned above.
```

**两个数字要分清**：

| 数字 | 来源 | 含义 |
| --- | --- | --- |
| `(60)` | curl 的错误码 | SSL 证书问题 |
| `(10)` | OpenSSL 的校验码 | 证书已过期 |

注意 **`could not establish a secure connection`** —— 连接根本没建立，一个字节的网页内容都没拿到。这是**硬失败**，不是警告。


```bash
curl https://expired.badssl.com/; echo "退出码: $?"
```

`$?` 是上一条命令的退出码。`0` 成功，非 0 失败。常用的五个：

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 6 | 域名解析失败 |
| 7 | 连接失败 |
| 28 | 超时 |
| 60 | 证书问题 |

批量扫描时没工夫人工看输出，全靠退出码判断。

```bash
curl -k https://self-signed.badssl.com/
```

![忽略证书](/img/curl-09-insecure.png)

`-k` = `--insecure`，跳过校验，立刻拿到 HTML（badssl 故意做成红底警告页，`<style>body { background: red; }</style>`）。

**关键认识：证书校验是客户端自愿的行为，服务器根本不管你验不验。** 你不验，对面是谁都行。

---

## 七、实战：先找目标

### 7.1 存活主机扫描

```bash
sudo nmap -sn 192.168.23.0/24
```

![资产发现](/img/curl-10-host-discovery.png)

```
Nmap scan report for 192.168.23.1
MAC Address: 00:50:56:C0:00:08 (VMware)
Nmap scan report for 192.168.23.2
MAC Address: 00:50:56:E4:26:7E (VMware)
Nmap scan report for 192.168.23.129
MAC Address: 00:0C:29:5B:DF:FA (VMware)
Nmap scan report for 192.168.23.254
MAC Address: 00:50:56:EA:83:1B (VMware)
Nmap scan report for 192.168.23.128
Nmap done: 256 IP addresses (5 hosts up) scanned in 3.00 seconds
```

**MAC 前缀就能分辨"设施"和"靶子"**：

| OUI | 用途 |
| --- | --- |
| `00:50:56` | VMware 分配给**宿主侧虚拟设备**（虚拟网卡、NAT、DHCP） |
| `00:0C:29` | VMware 分配给**虚拟机本身** |

所以 `.1`（虚拟网卡）、`.2`（NAT 网关）、`.254`（DHCP）都是设施，`00:0C:29` 开头的 `.129` 是真正可以打的靶机。

这个技巧在内网里通用：不同厂商的 OUI 不同，能快速区分打印机、摄像头、服务器。

### 7.2 端口与服务识别

```bash
sudo nmap -sS -sV -T4 192.168.23.129
```

![端口扫描（上）](/img/curl-11-portscan-a.png)

![端口扫描（下）](/img/curl-12-portscan-b.png)

```
Not shown: 977 closed tcp ports (reset)
PORT     STATE SERVICE     VERSION
21/tcp   open  ftp         vsftpd 2.3.4
22/tcp   open  ssh         OpenSSH 4.7p1 Debian 8ubuntu1
23/tcp   open  telnet      Linux telnetd
25/tcp   open  smtp        Postfix smtpd
53/tcp   open  domain      ISC BIND 9.4.2
80/tcp   open  http        Apache httpd 2.2.8 ((Ubuntu) DAV/2)
111/tcp  open  rpcbind
139/tcp  open  netbios-ssn Samba smbd 3.X - 4.X
445/tcp  open  netbios-ssn Samba smbd 3.X - 4.X
512/tcp  open  exec        netkit-rsh rexecd
514/tcp  open  tcpwrapped
1099/tcp open  java-rmi    GNU Classpath grmiregistry
1524/tcp open  bindshell   Metasploitable root shell
2049/tcp open  nfs
3306/tcp open  mysql       MySQL 5.0.51a-3ubuntu5
5432/tcp open  postgresql  PostgreSQL DB 8.3.0 - 8.3.7
5900/tcp open  vnc         VNC (protocol 3.3)
6667/tcp open  irc         UnrealIRCd
8180/tcp open  http        Apache Tomcat/Coyote JSP engine 1.1

Service Info: Hosts: metasploitable.localdomain, irc.Metasploitable.LAN
```

三个判读要点：

**1. `(reset)` 说明没有防火墙。** 关闭的端口主动回 RST，是"我不收"。如果是 `filtered`，说明包被中途丢弃 —— 那才是有防火墙。

**2. 版本清一色 2008 年。** Apache 2.2.8、MySQL 5.0.51a、PostgreSQL 8.3。判断标准：软件版本比较老的"服务器"，一定是靶场。

**3. `Service Info` 直接交代了主机名。** 一台正常服务器不会把 `metasploitable.localdomain` 一字不差地写在 banner 里。这是最典型的信息泄露 —— 我什么都没做，只是扫了一下端口。

另外 `tcpwrapped` 是 nmap 的专属标记：TCP 握手成功但立刻被关闭，通常是 `tcp_wrappers` 拦截。

---

## 八、curl 上场：摸 Web 服务

nmap 是"猜"（发特征包比对指纹库），curl 是"直接问" —— 更准。

### 8.1 只看响应头

```bash
curl -I http://192.168.23.129/
```

![响应头](/img/curl-13-response-header.png)

```
HTTP/1.1 200 OK
Date: Tue, 27 Oct 2026 00:51:58 GMT
Server: Apache/2.2.8 (Ubuntu) DAV/2
X-Powered-By: PHP/5.2.4-2ubuntu5.10
Content-Type: text/html
```

**两个泄露头**：

- `Server: Apache/2.2.8 (Ubuntu) DAV/2` —— Web 服务器版本 + 模块
- `X-Powered-By: PHP/5.2.4-2ubuntu5.10` —— **脚本语言版本，精确到补丁级**，比 Server 更危险

对比 httpbin：那个站**故意把 `Server` 头删掉了**。这就是"响应头脱敏"存在的原因。

**还注意到这里没有 `Content-Length`、`ETag`、`Last-Modified`。** 因为首页是 PHP 动态生成的，长度事先不知道。静态文件才会带这三个头 —— **看有没有 `Content-Length` 就能判断静态资源还是动态页面**。

另外 `Date` 显示靶机时钟慢了 4 天。服务器时间在真实渗透里能帮着判断设备状态和时区。

### 8.2 看首页内容

```bash
curl http://192.168.23.129/
```

![靶机首页](/img/curl-14-target-home.png)

```html
Warning: Never expose this VM to an untrusted network!
Contact: msfdev[at]metasploit.com
Login with msfadmin/msfadmin to get started

<ul>
<li><a href="/twiki/">TWiki</a></li>
<li><a href="/phpMyAdmin/">phpMyAdmin</a></li>
<li><a href="/mutillidae/">Mutillidae</a></li>
<li><a href="/dvwa/">DVWA</a></li>
<li><a href="/dav/">WebDAV</a></li>
</ul>
```

**默认口令直接印在首页。** 靶场故意的，目的是降低练习门槛。真实环境里对应的场景是：测试账号忘删、`/backup/` 目录没清、`phpinfo.php` 忘了删。

那 5 个链接就是**攻击面** —— 浏览器里看是漂亮网页，curl 里看是 5 个待探测路径。

**curl 的本质在这里体现得很清楚：它不渲染，它给你原始字节。** 那个 ASCII art 在浏览器里是图案，在 curl 里是一堆空格和竖线。

### 8.3 批量探测（目录扫描雏形）

```bash
for p in twiki phpMyAdmin mutillidae dvwa dav; do
  printf "%s -> " "$p"
  curl -s -o /dev/null -w "%{http_code}\n" http://192.168.23.129/$p/
done
```

![目录批量探测](/img/curl-15-dir-probe.png)

```
twiki -> 200
phpMyAdmin -> 200
mutillidae -> 200
dvwa -> 302
dav -> 200
```

三个参数是关键：

| 参数 | 作用 |
| --- | --- |
| `-s` | 静默，不显示进度条（写脚本必加，最好用 `-sS` 保留错误） |
| `-o /dev/null` | 把响应体丢进黑洞，只要状态码 |
| `-w "%{http_code}\n"` | 请求结束后只打印状态码 |

`-w` 常用变量：`%{http_code}` 状态码、`%{time_total}` 耗时、`%{size_download}` 字节数、`%{url_effective}` 最终 URL、`%{num_redirects}` 跳转次数。

### 8.4 对照组：为什么必须测一个不存在的路径

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://192.168.23.129/thispagedoesnotexist
```

![404 对照组](/img/curl-16-404-control.png)

```
404
```

### 8.5 状态码判读

| 码 | 含义 | 渗透里的意思 |
| --- | --- | --- |
| 200 | 正常 | 路径存在 |
| 301/302 | 跳转 | 路径存在但搬家了，看 `Location` |
| 401 | 需要认证 | **有东西，但锁着** |
| 403 | 禁止访问 | **有东西，但你没权限** —— 可试绕过 |
| 404 | 不存在 | 没有 |
| 500 | 服务器错误 | 参数可能有问题，值得细看 |

**403 和 401 比 200 更值得关注。** 200 是"给你看"，403 是"有宝贝但不给你看"。

---

## 九、重定向与 HTTP 方法探测

### 9.1 `302` 和 curl 的性格

```bash
curl -i http://192.168.23.129/dvwa/
```

![DVWA 响应头](/img/curl-17-dvwa-header.png)

```
HTTP/1.1 302 Found
Expires: Thu, 19 Nov 1981 08:52:00 GMT
Cache-Control: no-store, no-cache, must-revalidate, post-check=0, pre-check=0
Pragma: no-cache
Set-Cookie: PHPSESSID=d7df0a01b98500242a92225d25b8e5a3; path=/
Set-Cookie: security=high
Location: login.php
Content-Length: 0
```

**`Expires: 1981`** 不是服务器疯了，是 PHP `session_start()` 的经典行为 —— 发一个早就过期的日期强制不缓存。加上 `post-check=0, pre-check=0` 这种非标准字段，**不用看 `X-Powered-By` 也能断定后端是 PHP**。这就是指纹识别：不靠猜，靠特征组合。

**`Location: login.php`** 是相对路径，相对于当前目录 `/dvwa/`，实际是 `/dvwa/login.php`。写脚本解析跳转时必须处理相对路径。

**curl 默认不跟随重定向。** 浏览器会自动跟，curl 只告诉你"对方给了 302"。这是 curl 的性格 —— 它不替你做决定，只把事实给你看。

```bash
curl -L -o /dev/null -w "最终URL: %{url_effective}  状态码: %{http_code}  跳转次数: %{num_redirects}\n" http://192.168.23.129/dvwa/
```

`-L` 跟随，`%{url_effective}` 看最终落点。**坑**：`-L` 默认最多跟 50 次，恶意站点可以做无限重定向拖死你，生产脚本要加 `--max-redirs 5`。

### 9.2 用 OPTIONS 问它允许哪些方法

`dav -> 200` 说明有 WebDAV。WebDAV 支持文件上传，光看状态码看不出来，得直接问：

```bash
curl -i -X OPTIONS http://192.168.23.129/dav/
```

看 `Allow` 头：

```
Allow: GET,HEAD,POST,DELETE,OPTIONS,PUT
```

**如果 `Allow` 里有 `PUT`，说明这个目录可能允许直接上传文件** —— 上传一个 PHP 文件就可能拿到服务器权限。这是 WebDAV 配置不当导致的高危漏洞，真实环境里非常常见。

`OPTIONS` 是标准 HTTP 方法，只问不做，任何合规扫描都会发。

---

## 十、会话与 Cookie

### 10.1 会话 ID 是什么

```
Set-Cookie: PHPSESSID=d7df0a01b98500242a92225d25b8e5a3; path=/
```

服务器不记得你，它只记得"持有这个 ID 的人来过"。**谁拿到这个字符串，谁就是你。** 这也是 XSS 偷 cookie 能直接接管账号的原因。

### 10.2 一存一发

| 参数 | 方向 | 作用 |
| --- | --- | --- |
| `-c 文件` | 服务器 → 我 | 把 Set-Cookie 保存到文件 |
| `-b 文件` / `-b "k=v"` | 我 → 服务器 | 把 cookie 带进请求 |

```bash
curl -sS -c cookies.txt -o /dev/null http://192.168.23.129/dvwa/
```

![写入 cookie 文件](/img/curl-18-cookie-save.png)

```bash
cat cookies.txt
```

![cookie 文件内容](/img/curl-19-cookie-file.png)

```
192.168.23.129  FALSE  /dvwa  FALSE  0  security   high
192.168.23.129  FALSE  /      FALSE  0  PHPSESSID  2bf17f96614f29d9aec63e96c4ab368a
```

这是 **Netscape cookie 格式**，7 列制表符分隔：域、是否含子域、**路径**、是否仅 HTTPS、过期时间（`0` = 会话）、名字、值。

**第 3 列最容易踩坑**：

- `security` 的路径是 `/dvwa` → **只有访问 `/dvwa` 下才发送**
- `PHPSESSID` 的路径是 `/` → 全站发送

所以 `curl http://192.168.23.129/` 时，`security` **根本不会被带上**。

### 10.3 验证会话保持

```bash
curl -sS -b cookies.txt -i http://192.168.23.129/dvwa/
```

![会话保持](/img/curl-20-session-keep.png)

响应里**一条 `Set-Cookie` 都没有**。

服务器看到熟悉的 `PHPSESSID`，知道是老访客，不需要新建会话，也就不需要再发一次。

**判断标准：没有 `Set-Cookie` = 认出来了；有新的 `PHPSESSID` = 没认出来。**

### 10.4 改一个 cookie，看服务器信不信

```bash
curl -sS -b "security=low" -i http://192.168.23.129/dvwa/
```

![改 cookie 后的响应](/img/curl-21-cookie-mod.png)

```
Set-Cookie: PHPSESSID=34b4aa6a971a17900d1dcf2efae47677; path=/
Location: login.php
```

两个观察：

**1. `PHPSESSID` 变了。** 因为这次只发了 `security=low`，没带 `PHPSESSID`，服务器把我当新访客，开了新会话。这正好反证了上一条的判断标准。

**2. 服务器没有把 `security` 改回 `high`。**

第一次请求（完全不带 cookie）时，服务器主动下发了 `Set-Cookie: security=high` —— 说明默认值是 high。而这次我带了 `security=low`，它**一句话没说，直接接受了**。

**它没有纠正我，说明安全等级由客户端说了算。**

这就是"把安全控制放在客户端"的现实版本。DVWA 有 low/medium/high/impossible 四档防护，等级存在 cookie 里，改为 low 即降低防护。真实系统里的对应物：前端校验、隐藏字段里的权限标记、localStorage 里的角色 —— 全都可以被绕过。

**用"服务器有没有纠正我"来判断它信不信客户端**，这个思路比背漏洞名字有用得多。


## 十一、总结：curl 在渗透流程里的位置

```
信息收集 ──────→ 服务识别 ──────→ 漏洞验证 ──────→ 后渗透
  nmap -sn          nmap -sV          curl -i          其他工具
  MAC 判读          Server 头          curl -X
  同网段判断        X-Powered-By       curl -b
                                      curl -d
```

curl 的真正价值不是"能发请求"，而是**它让每一个字节都可见、可改**：

- **可见**：`-v` 看到请求行、请求头、空行、响应体；浏览器把这些全藏起来了
- **可改**：`-H` 改任意请求头、`-b` 改任意 cookie、`-X` 换任意方法、`-d` 提交任意数据

浏览器替你做了太多决定（自动跟随跳转、自动带 cookie、自动校验证书、自动加一堆头），**而渗透需要的恰恰是"不做任何决定"**。

这就是为什么学渗透的第一个工具是 curl，而不是 Burp Suite —— Burp 的每一个功能，底层都是一条 HTTP 报文，而 curl 让你直接摸到它。

---

## 附：截图清单

| 编号 | 文件 | 对应命令 |
| --- | --- | --- |
| 01-01 | `curl-01-version.png` | `curl --version` |
| 01-02 | `curl-02-ip-a.png` | `ip a` |
| 01-03 | `curl-03-ip-route.png` | `ip route` |
| 01-04 | `curl-04-httpbin-get.png` | `curl http://httpbin.org/get` |
| 02-01 | `curl-05-ua-spoof.png` | `curl -H "User-Agent: ..."` |
| 02-02 | `curl-06-multi-headers.png` | 多 `-H` |
| 02-03 | `curl-07-verbose.png` | `curl -v http://...` |
| 02-04 | `curl-08-verbose-end.png` | `curl -v` 末尾 |
| 02-05 | `curl-09-insecure.png` | `curl -k https://self-signed.badssl.com/` |
| 03-01 | `curl-10-host-discovery.png` | `nmap -sn` |
| 03-02/03 | `curl-11-portscan-a.png`、`curl-12-portscan-b.png` | `nmap -sS -sV -T4` |
| 03-04 | `curl-13-response-header.png` | `curl -I` |
| 03-05 | `curl-14-target-home.png` | `curl http://靶机/` |
| 03-06 | `curl-15-dir-probe.png` | `for` 循环 + `-w` |
| 03-07 | `curl-16-404-control.png` | 404 对照组 |
| 03-08 | `curl-17-dvwa-header.png` | `curl -i /dvwa/` |
| 03-09/10 | `curl-18-cookie-save.png`、`curl-19-cookie-file.png` | `-c` + `cat` |
| 03-11 | `curl-20-session-keep.png` | `-b cookies.txt` |
| 03-12 | `curl-21-cookie-mod.png` | `-b "security=low"` |


---

## 参考

- curl 官方文档：https://curl.se/docs/
- curl 证书与退出码：https://curl.se/docs/sslcerts.html
- Metasploitable 2：https://docs.rapid7.com/metasploit/metasploitable-2/
- nmap 手册：https://nmap.org/book/man.html
