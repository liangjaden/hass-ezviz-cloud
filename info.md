# 萤石云 Home Assistant 集成插件（中国版）

这个插件允许你将萤石云设备（如摄像头）集成到 Home Assistant 中，实现远程控制和自动化功能。此版本专为中国大陆用户设计，使用官方萤石开放平台API。

## 功能特点

- 支持萤石云摄像头的集成
- 支持隐私模式（镜头遮蔽）状态查询和开关控制
- 隐私状态变更时通过企业微信机器人推送通知
- 自定义卡片组件，方便添加到 Home Assistant 仪表板
- 多语言支持（中文和英文）

## 安装方法

### 手动安装

1. 将此仓库中的 `custom_components/ezviz_cloud` 文件夹复制到你的 Home Assistant 配置目录下的 `custom_components` 文件夹中。
2. 重启 Home Assistant。
3. 在 Home Assistant 的集成页面中添加"萤石云"集成。

### HACS 安装

1. 确保你已经安装了 [HACS (Home Assistant Community Store)](https://hacs.xyz/)。
2. 在 HACS 中点击"集成"。
3. 点击右上角的三个点，然后选择"自定义存储库"。
4. 添加此仓库的 URL 作为"集成"类别的自定义存储库。
5. 点击"添加"，然后搜索"萤石云"集成并安装。
6. 重启 Home Assistant。
7. 在 Home Assistant 的集成页面中添加"萤石云"集成。

## 配置说明

### 前置准备

1. 你需要先在[萤石开放平台](https://open.ys7.com/)创建应用并获取 AppKey 和 AppSecret。
   - 注册并登录萤石开放平台
   - 在"开发者服务"中选择"我的应用"
   - 点击"创建应用"，填写必要信息
   - 创建成功后，获取应用的 AppKey 和 AppSecret

2. 如果需要使用企业微信通知功能，请先在企业微信中创建群机器人并获取 Webhook URL。
   - 在企业微信群中，点击右上角的"设置"
   - 点击"群机器人"，然后选择"添加机器人"
   - 选择"自定义"机器人，设置名称和头像
   - 创建后，获取 Webhook URL

### 集成配置流程

1. 在 Home Assistant 的配置 -> 集成页面中点击右下角的"+"按钮。
2. 搜索"萤石云"并选择。
3. 输入你的 AppKey 和 AppSecret。
4. 输入企业微信 Webhook URL（可选）。
5. 选择你要监控的设备。
6. 设置更新间隔（默认为30秒）。

## 使用说明

### 实体说明

每个萤石云设备将创建以下实体：

- **摄像头实体**：显示摄像头实时画面，实体ID格式为 `camera.设备名称`
- **隐私模式开关**：用于控制摄像头的隐私模式（镜头遮蔽），实体ID格式为 `switch.设备名称_隐私模式`
- **隐私状态传感器**：显示当前隐私模式状态，实体ID格式为 `binary_sensor.设备名称_隐私状态`

### 自定义卡片

插件提供了一个自定义卡片组件，可以在 Home Assistant 仪表板中使用：

1. 在仪表板中点击"添加卡片"。
2. 选择"自定义：萤石摄像头卡片"。
3. 配置卡片：
   - `camera_entity`: 选择摄像头实体
   - `switch_entity`: 选择隐私模式开关实体
   - `title`: 卡片标题（可选）

### 自动化示例

#### 当有人回家时关闭隐私模式

```yaml
automation:
  - alias: 有人回家时关闭隐私模式
    trigger:
      platform: state
      entity_id: person.family_member
      to: 'home'
    action:
      service: switch.turn_off
      target:
        entity_id: switch.ezviz_living_room_privacy_mode
```

#### 当所有人离开时开启隐私模式

```yaml
automation:
  - alias: 所有人离开时开启隐私模式
    trigger:
      platform: state
      entity_id: group.family
      to: 'not_home'
    action:
      service: switch.turn_on
      target:
        entity_id: switch.ezviz_living_room_privacy_mode
```

#### 隐私模式变化时发送通知

```yaml
automation:
  - alias: 隐私模式变化时通知
    trigger:
      platform: event
      event_type: ezviz_cloud_privacy_changed
    action:
      service: notify.mobile_app
      data:
        title: "萤石摄像头隐私模式变化"
        message: >
          {{ trigger.event.data.device_name }} 的隐私模式从 
          {{ trigger.event.data.old_status }} 变为 
          {{ trigger.event.data.new_status }}
```

## 服务说明

插件提供了以下服务：

### ezviz_cloud.set_privacy_mode

设置设备的隐私模式（镜头遮蔽）状态。

参数：
- `device_sn`: 设备序列号
- `privacy_mode`: 隐私模式状态，可选值：`on` 或 `off`

示例：
```yaml
service: ezviz_cloud.set_privacy_mode
data:
  device_sn: "C12345678"
  privacy_mode: "on"
```

## 故障排除

### 常见问题

1. **无法连接到萤石云**
   - 检查 AppKey 和 AppSecret 是否正确
   - 确认网络连接是否正常
   - 检查萤石云平台服务是否正常
   - 确认你的应用是否已经通过审核（新创建的应用需要等待审核）

2. **设备显示离线**
   - 确认设备在萤石云App中是否在线
   - 检查设备网络连接

3. **隐私模式控制无响应**
   - 可能是设备不支持镜头遮蔽功能
   - 尝试在萤石云App中测试此功能
   - 检查错误日志，查看 API 返回的具体错误信息

4. **企业微信通知未收到**
   - 检查Webhook URL是否正确
   - 确认企业微信机器人是否正常工作
   - 检查错误日志，查看发送通知时是否有错误

5. **权限问题**
   - 确认你的应用在萤石开放平台上已获得必要的权限
   - 默认情况下，应用需要有 "设备基础信息" 和 "设备操控" 权限

## 技术说明

本插件使用萤石开放平台API直接与萤石云服务通信，主要使用以下API：

- `/api/lapp/token/get`: 获取访问令牌
- `/api/lapp/device/list`: 获取设备列表
- `/api/lapp/device/info`: 获取设备详情
- `/api/lapp/device/scene/switch/status`: 获取镜头遮蔽状态
- `/api/lapp/device/scene/switch/set`: 设置镜头遮蔽状态
- `/api/lapp/device/capture`: 获取设备截图
- `/api/lapp/live/address/get`: 获取设备直播地址

Access Token 会自动管理、缓存和刷新，有效期为7天。

## 支持和贡献

如果你遇到任何问题或有改进建议，请在GitHub仓库中提交Issue或Pull Request。

## 许可证

本项目采用 MIT 许可证。