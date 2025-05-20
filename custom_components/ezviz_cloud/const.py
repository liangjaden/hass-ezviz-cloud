"""Constants for the EZVIZ Cloud integration."""
DOMAIN = "ezviz_cloud"
CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"
CONF_DEVICES = "devices"
CONF_DEVICE_SN = "device_sn"
CONF_DEVICE_NAME = "device_name"
CONF_WEBHOOK_URL = "webhook_url"
CONF_PRIVACY_MODE = "privacy_mode"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_UPDATE_INTERVAL = 30

# HomeKit支持标志，设为True启用HomeKit增强功能
HOMEKIT_SUPPORT_ENABLED = True

# API超时设置
API_TIMEOUT = 10  # 秒
API_RETRY_ATTEMPTS = 3  # 最大重试次数

# 隐私状态常量
PRIVACY_ON = "on"
PRIVACY_OFF = "off"

# 服务名称
SERVICE_SET_PRIVACY = "set_privacy_mode"

# 属性
ATTR_DEVICE_SN = "device_sn"
ATTR_PRIVACY_MODE = "privacy_mode"
ATTR_LAST_UPDATE = "last_update"

# 事件
EVENT_PRIVACY_CHANGED = f"{DOMAIN}_privacy_changed"