---
layout: post
title: Wireshark抓取QQ通信流量分析实验
date: 2026-10-17
categories: 网络渗透
---

## 实验环境
操作系统：Windows
抓包工具：Wireshark
网卡：无线网卡
被测软件：QQ客户端

## 实验步骤
1. 打开Wireshark，选择无线网卡WLAN开始捕获流量；操作QQ发送消息与图片，随后停止抓包。
2. 设置显示过滤器：`udp.port == 443 or tcp.port ==443`，筛选QQ相关流量。
3. 选中捕获的数据包，查看Packet Bytes原始十六进制载荷，观察右侧ASCII字符内容。
4. 使用Wireshark查找功能，选择十六进制值，输入JPG文件头`ff d8 ff`进行搜索。


## 实验结果
1.本次捕获到的QQ流量以TCP协议（443端口，TLSv1.2）为主。QQ通信采用TCP+UDP混合模式：TCP用于图片、文件传输，提供可靠传输；UDP多用于心跳包、低延迟即时消息。本次抓包过程**没有捕获到UDP 8000数据包**。

2.QQ通信为TLS加密传输，不是明文。选中TLS数据包，查看Packet Bytes原始十六进制区域，右侧ASCII列全部是乱码字符，无法看到QQ聊天文字、图片原始内容，证明载荷被TLS加密保护。

3. 使用十六进制查找JPG图片特征码`ff d8 ff`，Wireshark提示无分组包含这些字节流。
原因：图片数据经过TLS加密后变成密文，不存在明文JPG文件头。依靠文件魔术字提取文件的方法对TLS加密流量无效，该方法仅适用于HTTP明文传输场景。

![wireshark截图]({{ site.baseurl }}/wireshark.png)

## 实验总结
新版QQ通信使用TLS加密，采用TCP与UDP混合传输。抓包仅能看到IP地址、端口等网络层信息，无法直接读取聊天内容。基于文件头部特征码的流量文件提取技术，不能提取TLS加密流量中的图片。
