import os
import json
import time
from pathlib import Path

def sync_tokens():
    """
    手动将 keys/grok.txt 中的 SSO Token 同步到 grok2api/data/token.json
    """
    project_root = Path(__file__).parent
    keys_file = project_root / "keys" / "grok.txt"
    token_file = project_root / "grok2api" / "data" / "token.json"
    
    print(f"[*] 正在检查账号文件: {keys_file}")
    if not keys_file.exists():
        print(f"[-] 错误: 找不到 {keys_file}")
        return

    # 读取 keys
    tokens = []
    with open(keys_file, "r", encoding="utf-8") as f:
        for line in f:
            token = line.strip()
            if token:
                tokens.append(token)
    
    print(f"[+] 从 keys/grok.txt 读取到 {len(tokens)} 个 Token")

    # 确保 data 目录存在
    token_file.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有的 token.json
    current_data = {"ssoNormal": {}, "ssoSuper": {}}
    if token_file.exists():
        try:
            with open(token_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    loaded = json.loads(content)
                    # 兼容旧格式同步
                    if "sso" in loaded and "ssoNormal" not in loaded:
                        current_data["ssoNormal"] = loaded["sso"]
                        current_data["ssoSuper"] = loaded.get("ssoSuper", {})
                    else:
                        current_data["ssoNormal"] = loaded.get("ssoNormal", {})
                        current_data["ssoSuper"] = loaded.get("ssoSuper", {})
            print(f"[*] 已加载现有 {len(current_data['ssoNormal']) + len(current_data['ssoSuper'])} 个账号数据")
        except Exception as e:
            print(f"[!] 读取现有 token.json 失败 (可能是格式错误)，将重新创建: {e}")

    # 合并新 Token
    added_count = 0
    for token in tokens:
        # 检查是否已存在（在 normal 或 super 中）
        if token not in current_data["ssoNormal"] and token not in current_data["ssoSuper"]:
            current_data["ssoNormal"][token] = {
                "createdTime": int(time.time() * 1000),
                "remainingQueries": -1,
                "heavyremainingQueries": -1,
                "status": "active",
                "failedCount": 0,
                "lastFailureTime": None,
                "lastFailureReason": None,
                "tags": [],
                "note": "Manual Import"
            }
            added_count += 1

    # 保存
    if added_count > 0:
        with open(token_file, "w", encoding="utf-8") as f:
            json.dump(current_data, f, indent=2, ensure_ascii=False)
        print(f"[✓] 成功! 已新增 {added_count} 个账号，当前总计 {len(current_data['ssoNormal'])} 个 ssoNormal 账号")
    else:
        print("[!] 没有发现新账号，无需更新")

if __name__ == "__main__":
    sync_tokens()
