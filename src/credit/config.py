"""
SACRED 五维信用分体系配置
"""

# 衰减半衰期（天）
SHORT_HALF_LIFE = 30     # 短期指标：活跃度、任务量
LONG_HALF_LIFE = 90      # 长期指标：成功率、信任网络

# 冷启动
COLD_START_SCORE = 250       # 新 Agent 初始分
COLD_START_THRESHOLD = 10    # 完成N个任务后退出冷启动（保护期）
COLD_START_MAX_BOOST = 80    # 快速通道最多提80分

# 评分范围
DIMENSION_MAX = 200
TOTAL_MAX = 1000

# 严重违约
SEVERE_VIOLATION_PENALTY = 60        # 每次扣60分
SEVERE_VIOLATION_TYPES = {"seller_win", "timeout"}  # 不衰减的违约类型

# 等级阈值（从高到低）
GRADE_THRESHOLDS = [
    ("AAA", 850), ("AA", 750), ("A", 650),
    ("BBB", 550), ("BB", 450), ("B", 350),
    ("CCC", 250), ("CC", 150), ("C", 0),
]

# 查询授权
AUTHORIZATION_TTL = 3600     # 默认授权有效期1小时
AUTHORIZATION_MAX_TTL = 86400  # 最长24小时

# 数据库路径（统一使用 cryptominds.db）
# DEFAULT_DB_PATH 已废弃，统一由 UnifiedStore 管理

# API
API_HOST = "127.0.0.1"
API_PORT = 3458
