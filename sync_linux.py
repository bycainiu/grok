#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
from pathlib import Path

def sync():
    # 获取脚本所在目录（假设在项目根目录 ~/grok/ 下执行）
    base_dir = Path(__file__).parent.absolute()
    
    # 路径配置
    keys_file = base_dir / "keys" / "grok.txt"
    # Docker 挂载路径通常是项目根目录下的 grok2api/data
    data_dir = base_dir / "grok2api" / "data"
    token_file = data_dir / "token.json"

    print(f"[*] 正在运行同步脚本...")
    print(f"[*] 项目根目录: {base_dir}")

    # 1. 检查数据源
    if not keys_file.exists():
        print(f"[-] 错误: 找不到账号文件 {keys_file}")
        print(f"[*] 请确保你在项目根目录下运行此脚本，或者 keys/grok.txt 确实存在")
        return

    # 2. 读取 keys
    with open(keys_file, 'r', encoding='utf-8') as f:
        tokens = [line.strip() for line in f if line.strip()]
    
    print(f"[+] 从 keys/grok.txt 读取到 {len(tokens)} 个 Token")

    # 3. 准备目标目录
    if not data_dir.exists():
        print(f"[*] 创建目录: {data_dir}")
        data_dir.mkdir(parents=True, exist_ok=True)

    # 4. 加载或初始化 token.json
    current_data = {"ssoNormal": {}, "ssoSuper": {}}
    if token_file.exists():
        try:
            with open(token_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    loaded = json.loads(content)
                    # 自动迁移旧格式 sso -> ssoNormal
                    if "sso" in loaded:
                        current_data["ssoNormal"].update(loaded["sso"])
                    if "ssoNormal" in loaded:
                        current_data["ssoNormal"].update(loaded["ssoNormal"])
                    if "ssoSuper" in loaded:
                        current_data["ssoSuper"].update(loaded["ssoSuper"])
            print(f"[*] 已同步现有 {len(current_data['ssoNormal'])} 个 ssoNormal 账号")
        except Exception as e:
            print(f"[!] 读取 token.json 失败: {e}，将重新创建")

    # 5. 合并新 Token
    new_count = 0
    now_ms = int(time.time() * 1000)
    for t in tokens:
        if t not in current_data["ssoNormal"] and t not in current_data["ssoSuper"]:
            current_data["ssoNormal"][t] = {
                "createdTime": now_ms,
                "remainingQueries": -1,
                "heavyremainingQueries": -1,
                "status": "active",
                "failedCount": 0,
                "lastFailureTime": None,
                "lastFailureReason": None,
                "tags": [],
                "note": "Initial Linux Sync"
            }
            new_count += 1

    # 6. 写入文件
    with open(token_file, 'w', encoding='utf-8') as f:
        json.dump(current_data, f, indent=2, ensure_ascii=False)

    print(f"\n[✓] 同步完成!")
    print(f"[✓] 新增账号: {new_count}")
    print(f"[✓] 当前总计 ssoNormal 账号: {len(current_data['ssoNormal'])}")
    print(f"[✓] 持久化路径: {token_file}")
    print(f"\n[*] 提示: 如果你使用 Docker 部署，请确保 docker-compose.yml 中的 volumes 已正确挂载。")

if __name__ == "__main__":
    sync()
