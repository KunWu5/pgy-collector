"""页面选择器与接口路径集中管理。

页面改版或接口变更时，只需要更新本文件，不需要在采集逻辑里逐处查找。
"""

# 搜索页：切换"搜昵称"的页签
SEARCH_TYPE_TAB = ".search-type-btn"

# 详情页：近30日/近90日时间筛选下拉框与选项
PERIOD_DROPDOWN = ".d-select-wrapper"
PERIOD_OPTION = ".d-option-name"

# 搜索结果表格中的博主头像（点击打开详情页弹窗）
DETAIL_RESULT_ROW = "tbody.d-table__body tr .head-photo"

# 搜索接口（POST，用于捕获博主基础信息）
SEARCH_API_PATH = "/api/blogger/v2"

# 详情页合作笔记指标接口（GET，用于捕获近30/90日数据）
NOTES_RATE_API_PATH = "/api/blogger/notes_rate"

# 受保护页面前缀（登录态校验）
PROTECTED_PATH_PREFIX = "/dashboard/"
