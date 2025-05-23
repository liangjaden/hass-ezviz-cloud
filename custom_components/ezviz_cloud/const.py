"""Constants for the EZVIZ Cloud integration with HomeKit Bridge optimizations."""
DOMAIN = "ezviz_cloud"
CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"
CONF_DEVICES = "devices"
CONF_DEVICE_SN = "device_sn"
CONF_DEVICE_NAME = "device_name"
CONF_WEBHOOK_URL = "webhook_url"
CONF_PRIVACY_MODE = "privacy_mode"
CONF_UPDATE_INTERVAL = "update_interval"

# HomeKit优化的默认更新间隔
DEFAULT_UPDATE_INTERVAL = 20  # 减少到20秒以提高HomeKit响应性

# HomeKit支持标志，设为True启用HomeKit增强功能
HOMEKIT_SUPPORT_ENABLED = True

# API超时设置 - 为HomeKit优化
API_TIMEOUT = 8  # 减少到8秒，避免HomeKit超时
API_RETRY_ATTEMPTS = 2  # 减少重试次数以提高响应速度

# HomeKit特定的超时设置
HOMEKIT_COMMAND_TIMEOUT = 5  # HomeKit命令超时时间
HOMEKIT_STATE_UPDATE_DELAY = 0.3  # 状态更新延迟

# 隐私状态常量
PRIVACY_ON = "on"
PRIVACY_OFF = "off"

# 服务名称
SERVICE_SET_PRIVACY = "set_privacy_mode"

# 属性
ATTR_DEVICE_SN = "device_sn"
ATTR_PRIVACY_MODE = "privacy_mode"
ATTR_LAST_UPDATE = "last_update"
ATTR_HOMEKIT_COMPATIBLE = "homekit_compatible"

# 事件
EVENT_PRIVACY_CHANGED = f"{DOMAIN}_privacy_changed"

# HomeKit设备类型映射
HOMEKIT_DEVICE_TYPES = {
    "switch": "switch",  # 默认开关类型
    "outlet": "outlet",  # 插座类型
    "valve": "valve",    # 阀门类型（适合隐私模式）
}

# HomeKit服务特性
HOMEKIT_FEATURES = {
    "privacy_switch": {
        "device_type": "valve",  # 使用阀门类型，更适合隐私控制
        "manufacturer": "萤石",
        "service_type": "Valve",
    }
}

# 错误消息
ERROR_HOMEKIT_TIMEOUT = "homekit_timeout"
ERROR_API_UNAVAILABLE = "api_unavailable"
ERROR_DEVICE_OFFLINE = "device_offline"
ERROR_INVALID_RESPONSE = "invalid_response"

# 调试和日志
LOG_LEVEL_DEBUG = "debug"
LOG_LEVEL_INFO = "info"
LOG_LEVEL_WARNING = "warning"
LOG_LEVEL_ERROR = "error"