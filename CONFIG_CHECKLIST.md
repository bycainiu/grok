# 配置检查清单

## 🎯 目的
确保代码在各种环境（本地、Docker、生产）中都能正常运行，避免硬编码导致的环境特定问题。

## ✅ 已修复的问题

### 1. Turnstile Solver URL 可配置
- **文件**：`grok2api/app/api/admin/register.py`
- **问题**：硬编码 `http://turnstile-solver:5072`
- **修复**：添加 `turnstile_solver_url` 配置字段
- **默认值**：
  - 本地环境：`http://127.0.0.1:5072`
  - Docker 环境：`http://turnstile-solver:5072`

### 2. DuckMail API 可配置
- **文件**：`grok2api/app/api/admin/register.py`
- **问题**：硬编码 `https://api.duckmail.sbs`
- **修复**：添加 `duckmail_base_url` 和 `duckmail_api_key` 配置字段

## ⚠️ 需要注意的配置

### 1. 环境变量加载
**当前状态**：多处调用 `load_dotenv()`
```python
# g/duckmail_client.py:9
load_dotenv()

# g/duckmail_email_service.py:17
load_dotenv()

# g/turnstile_service.py:9
load_dotenv()
```

**建议**：
- 在 `grok.py` 入口处统一加载一次即可
- 或者在每个服务中保持独立加载（当前方案，更灵活）

### 2. 旧的 EmailService
**文件**：`g/email_service.py`
**状态**：已被 `DuckMailEmailService` 替代
**建议**：可以添加废弃标注
```python
"""
邮箱服务类（已废弃）

.. deprecated::
    使用 DuckMailEmailService 替代
    保留此文件仅为兼容性考虑
"""
```

### 3. Docker Compose 环境变量优先级
**文件**：`docker-compose.yml:56`
```yaml
- TURNSTILE_SOLVER_URL=http://turnstile-solver:5072
```

**优先级**：
1. 前端配置（通过 API 设置）✅ 最高优先级
2. Docker Compose 环境变量
3. 代码默认值

**说明**：前端配置会通过环境变量传递给注册机进程，会覆盖 Docker Compose 的默认值。

### 4. 端口配置
| 服务 | 端口 | 配置位置 | 说明 |
|------|------|----------|------|
| Grok2API | 8000 | `main.py:186`, 环境变量 `PORT` | 默认 8000 |
| Turnstile Solver | 5072 | `docker-compose.yml:16`, 环境变量 | Docker 暴露端口 |
| MySQL | 3306 | `DATABASE_URL` | 可配置 |
| Redis | 6379 | `DATABASE_URL` | 可配置 |

## ✅ 正确的实践

### 1. 跨平台路径处理
```python
# ✅ 使用 pathlib.Path（自动处理路径分隔符）
from pathlib import Path
config_path = Path(__file__).parents[2] / "data" / "setting.toml"

# ❌ 不要使用字符串拼接（硬编码路径分隔符）
config_path = os.path.join(os.path.dirname(__file__), "..", "data")
```

### 2. 环境变量读取
```python
# ✅ 正确：提供默认值
solver_url = os.getenv('TURNSTILE_SOLVER_URL', 'http://127.0.0.1:5072')

# ✅ 正确：优先级处理
self.solver_url = solver_url or os.getenv('TURNSTILE_SOLVER_URL', 'http://127.0.0.1:5072')
```

### 3. 目录创建
```python
# ✅ 跨平台兼容
from pathlib import Path
Path("logs/register").mkdir(parents=True, exist_ok=True)

# ❌ Windows 特定
if not os.path.exists("logs\\register"):
    os.makedirs("logs\\register")
```

## 📋 环境配置对照表

| 环境 | TURNSTILE_SOLVER_URL | DUCKMAIL_BASE_URL | 说明 |
|------|---------------------|-------------------|------|
| **本地开发** | `http://127.0.0.1:5072` | `https://api.duckmail.sbs` | 需要本地运行 Solver |
| **Docker** | `http://turnstile-solver:5072` | `https://api.duckmail.sbs` | Docker 服务名 |
| **生产** | 实际部署的 URL | 实际部署的 URL | 根据实际情况配置 |

## 🚀 部署检查清单

### 本地开发环境
- [ ] Python 3.10+ 已安装
- [ ] 依赖已安装：`pip install -r requirements.txt`
- [ ] `.env.register` 配置文件已创建
- [ ] DuckMail API 地址正确
- [ ] 域名已选择
- [ ] **Turnstile Solver URL 设置为 `http://127.0.0.1:5072`**

### Docker 环境
- [ ] Docker 和 Docker Compose 已安装
- [ ] 镜像已构建：`docker-compose build`
- [ ] `.env.register` 已配置
- [ ] **Docker Compose 会自动设置 `TURNSTILE_SOLVER_URL=http://turnstile-solver:5072`**
- [ ] 前端配置会覆盖此默认值（如果需要自定义）

### 生产环境
- [ ] 所有环境变量已正确配置
- [ ] TURNSTILE_SOLVER_URL 指向实际部署的 Solver 服务
- [ ] DUCKMAIL_BASE_URL 指向实际的 DuckMail API
- [ ] 数据库连接正确（如果使用 MySQL/Redis）

## 🔍 常见问题排查

### 问题：连接不上 Turnstile Solver
**错误信息**：`Failed to resolve 'turnstile-solver'`
**原因**：使用了 Docker 服务名，但在本地环境运行
**解决**：在管理后台配置 `http://127.0.0.1:5072`

### 问题：端口已被占用
**错误信息**：`Address already in use`
**解决**：
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <pid> /F

# Linux/Mac
lsof -ti:8000 | xargs kill -9
```

### 问题：配置文件未生效
**检查**：
1. 配置是否保存成功
2. 注册机是否重启
3. 环境变量是否正确传递

## 📝 代码审查要点

当添加新配置时，确保：

1. **可配置性**：不要硬编码环境相关的值
2. **默认值**：提供合理的默认值
3. **文档化**：在配置界面添加说明
4. **优先级**：明确配置的优先级顺序
5. **跨平台**：使用 `pathlib.Path` 而不是字符串拼接
6. **环境变量**：使用 `os.getenv(key, default)` 提供默认值

## 🎓 最佳实践

### 1. 配置管理
```python
# ✅ 好的做法
class Service:
    def __init__(self, url=None):
        # 优先级：参数 > 环境变量 > 默认值
        self.url = url or os.getenv('SERVICE_URL', 'http://127.0.0.1:8080')

# ❌ 不好的做法
class Service:
    def __init__(self):
        self.url = 'http://localhost:8080'  # 硬编码
```

### 2. 路径处理
```python
# ✅ 好的做法
from pathlib import Path
config_file = Path(__file__).parent / "config.toml"

# ❌ 不好的做法
config_file = os.path.join(os.path.dirname(__file__), "config.toml")
```

### 3. 环境检测
```python
# ✅ 好的做法
import sys
if sys.platform == 'win32':
    # Windows 特定逻辑
    pass
else:
    # Unix/Linux/Mac 特定逻辑
    pass

# ❌ 不好的做法
# 假设所有环境都是一样的
```

---

**最后更新**：2026-02-01
**维护者**：Claude Code
**版本**：1.0
