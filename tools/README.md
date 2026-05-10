# CryptoMinds 验证闭环 - 快速测试指南

## 测试验证闭环

```bash
# 完整测试（包括API服务）
./tools/test_all.sh

# 仅测试验证逻辑
python tools/test_verification.py

# 测试命令行验证工具
python tools/verify_credit.py test_agent_001
```

## 验证流程

```
1. 生成测试数据（20条履约记录）
   ↓
2. 计算信用分
   ↓
3. 保存到数据库
   ↓
4. 重新读取
   ↓
5. 重新计算
   ↓
6. 对比哈希
   ↓
7. 验证通过 ✅
```

## 预期输出

```
==============================================================
测试验证闭环
==============================================================

1. 初始化存储和计算器...
2. 生成测试数据...
   生成了 20 条履约记录
3. 计算信用分...
   总分: 456.7
   等级: BB
   哈希: a1b2c3d4e5f6g7h8
4. 验证信用分...
   分数匹配: ✓
   等级匹配: ✓
   哈希匹配: ✓

✅ 验证成功！验证闭环正常工作。

==============================================================
```

## API端点测试

```bash
# 启动API服务
python src/api_server.py

# 查询信用分
curl http://localhost:3458/api/v1/credit/test_agent_001

# 获取履约记录
curl http://localhost:3458/api/v1/credit/test_agent_001/records

# 获取验证数据（一次性获取所有）
curl http://localhost:3458/api/v1/credit/test_agent_001/verify

# 使用命令行工具验证
python tools/verify_credit.py test_agent_001
```

## 故障排查

### 问题：导入错误

```bash
# 确保安装了依赖
pip install -r requirements.txt
```

### 问题：数据库锁定

```bash
# 删除测试数据库
rm -f test_cryptominds.db*
```

### 问题：端口占用

```bash
# 检查端口
lsof -i :3458

# 杀死进程
kill -9 <PID>
```

## 下一步

验证闭环测试通过后，可以：

1. 部署到生产环境
2. 开放API给外部用户
3. 开始收集真实数据
4. 准备融资材料

详细部署指南: [DEPLOYMENT.md](../docs/DEPLOYMENT.md)
