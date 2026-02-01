"""
本地测试脚本 - 测试各个组件
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

def test_duckmail():
    """测试 DuckMail 连接"""
    print("=" * 60)
    print("测试 DuckMail 连接")
    print("=" * 60)

    from g import DuckMailClient

    client = DuckMailClient(
        base_url="https://api.duckmail.sbs",
        api_key=""
    )

    # 测试连接
    print("\n1. 测试连接...")
    result = client.test_connection()
    print(f"结果: {result}")

    if result.get("success"):
        # 获取域名列表
        print("\n2. 获取可用域名...")
        domains = client.get_available_domains()
        print(f"找到 {len(domains)} 个域名:")
        for domain in domains[:5]:
            print(f"  - {domain}")

        # 测试注册
        if domains:
            print(f"\n3. 测试注册账号 (使用域名: {domains[0]})...")
            success = client.register_account(domain=domains[0])
            print(f"注册结果: {'成功' if success else '失败'}")

            if success:
                print(f"  邮箱: {client.email}")
                print(f"  密码: {client.password}")

                # 测试登录
                print("\n4. 测试登录...")
                login_success = client.login()
                print(f"登录结果: {'成功' if login_success else '失败'}")

                if login_success:
                    print(f"  Token: {client.token[:20]}...")

                    # 测试获取邮件
                    print("\n5. 测试获取邮件...")
                    messages = client.get_messages(limit=5)
                    print(f"收到 {len(messages)} 封邮件")

                    for i, msg in enumerate(messages[:3], 1):
                        subject = msg.get("subject", "")
                        content = msg.get("text", "") or msg.get("html", "")
                        print(f"\n  邮件 {i}:")
                        print(f"    主题: {subject}")
                        print(f"    长度: {len(content)} 字符")
                        if content:
                            preview = content[:100].replace('\n', ' ')
                            print(f"    预览: {preview}...")

    print("\n" + "=" * 60)

def test_email_service():
    """测试邮箱服务"""
    print("=" * 60)
    print("测试 DuckMailEmailService")
    print("=" * 60)

    # 设置环境变量
    os.environ["DUCKMAIL_BASE_URL"] = "https://api.duckmail.sbs"
    os.environ["DUCKMAIL_API_KEY"] = ""
    os.environ["EMAIL_DOMAIN"] = "baldur.edu.kg"

    from g import DuckMailEmailService

    print("\n初始化邮箱服务...")
    service = DuckMailEmailService()

    print("\n测试创建邮箱...")
    token, email = service.create_email()

    if email:
        print(f"✅ 成功创建邮箱: {email}")
        print(f"   Token: {token[:20]}...")

        print("\n测试获取验证码（模拟）...")
        # 注意：这会实际发送验证码到邮箱
        # 需要通过其他方式获取验证码
    else:
        print("❌ 创建邮箱失败")

    print("\n" + "=" * 60)

def test_registration_flow():
    """测试完整注册流程"""
    print("=" * 60)
    print("测试完整注册流程")
    print("=" * 60)

    # 设置环境变量
    os.environ["DUCKMAIL_BASE_URL"] = "https://api.duckmail.sbs"
    os.environ["DUCKMAIL_API_KEY"] = ""
    os.environ["EMAIL_DOMAIN"] = "baldur.edu.kg"
    os.environ["CONCURRENT_THREADS"] = "1"

    print("\n注意：此测试会尝试注册真实的 x.ai 账号")
    print("仅用于调试，请勿滥用")

    confirm = input("\n是否继续？(yes/no): ")
    if confirm.lower() != "yes":
        print("已取消")
        return

    # 导入 grok 模块
    import grok

    print("\n初始化...")
    print(f"目标站点: {grok.site_url}")
    print(f"Site Key: {grok.config['site_key']}")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    print("\nGrok 本地测试工具")
    print("=" * 60)
    print("\n请选择测试项目:")
    print("1. 测试 DuckMail 连接")
    print("2. 测试 DuckMailEmailService")
    print("3. 测试完整注册流程")
    print("0. 退出")

    choice = input("\n请选择 (0-3): ")

    if choice == "1":
        test_duckmail()
    elif choice == "2":
        test_email_service()
    elif choice == "3":
        test_registration_flow()
    elif choice == "0":
        print("退出")
    else:
        print("无效选择")

    input("\n按回车键退出...")
