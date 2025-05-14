"""Card definitions for EZVIZ Cloud integration."""
import logging
import os
import aiofiles
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_cards(hass: HomeAssistant):
    """Set up custom cards for the EZVIZ integration."""
    # 确保自定义卡片目录存在
    cards_dir = Path(hass.config.path("www", DOMAIN))
    cards_dir.mkdir(parents=True, exist_ok=True)

    # 复制卡片文件
    card_js_path = cards_dir / "ezviz-camera-card.js"
    if not card_js_path.exists():
        try:
            # 使用同步方式写入文件，避免可能的异步问题
            with open(card_js_path, "w", encoding='utf-8') as card_file:
                card_file.write(EZVIZ_CAMERA_CARD_JS)

            _LOGGER.debug("Created camera card file at %s", card_js_path)
        except Exception as e:
            _LOGGER.error("Failed to create camera card file: %s", e)

    # 注册Lovelace资源
    try:
        # 在Home Assistant 2021.7之后，需要通过资源存储系统注册
        try:
            from homeassistant.components.lovelace import resources
            from homeassistant.components.lovelace.resources import ResourceStorageCollection

            # 获取资源存储集合
            resource_collection = ResourceStorageCollection(hass)
            await resource_collection.async_initialize()

            # 设置资源URL和类型
            resource_url = f"/local/{DOMAIN}/ezviz-camera-card.js"
            resource_exists = False

            # 检查资源是否已经存在
            for resource in resource_collection.async_items():
                if resource["url"] == resource_url:
                    resource_exists = True
                    break

            # 如果资源不存在，创建它
            if not resource_exists:
                try:
                    await resource_collection.async_create_item({
                        "url": resource_url,
                        "type": "module",
                        "res_type": "custom-card",
                    })
                    _LOGGER.info("已注册萤石摄像头卡片作为Lovelace资源")
                except Exception as e:
                    _LOGGER.warning("无法注册Lovelace资源: %s", e)
        except (ImportError, AttributeError, ValueError) as e:
            _LOGGER.warning("无法使用资源存储系统注册Lovelace资源: %s", e)
            _LOGGER.info("您可能需要手动添加资源: /local/%s/ezviz-camera-card.js", DOMAIN)
    except Exception as e:
        _LOGGER.warning("注册Lovelace资源时出错: %s", e)
        _LOGGER.info(
            "您需要手动添加'/local/%s/ezviz-camera-card.js' "
            "作为Lovelace资源在您的UI设置中", DOMAIN
        )

    return True

# 自定义卡片的JavaScript代码
EZVIZ_CAMERA_CARD_JS = """
class EzvizCameraCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.content = false;
    this._initialized = false;
    this._updateInterval = null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.content) {
      this.initialSetup();
    }
    
    this.updateCard();
  }
  
  initialSetup() {
    this.shadowRoot.innerHTML = `
      <ha-card>
        <div class="card-header"></div>
        <div class="card-content">
          <div class="camera-wrapper">
            <img class="camera-image" />
            <div class="camera-loading"><ha-circular-progress active></ha-circular-progress></div>
          </div>
          <div class="controls">
            <ha-icon-button class="privacy-toggle"></ha-icon-button>
            <span class="privacy-status"></span>
          </div>
        </div>
        <style>
          ha-card {
            position: relative;
            overflow: hidden;
            box-sizing: border-box;
          }
          .card-header {
            font-size: 1.2em;
            font-weight: 500;
            padding: 16px 16px 0;
            color: var(--primary-text-color);
          }
          .card-content {
            padding: 16px;
          }
          .camera-wrapper {
            position: relative;
            width: 100%;
            height: 0;
            padding-bottom: 56.25%; /* 16:9 宽高比 */
            overflow: hidden;
            margin-bottom: 16px;
            border-radius: 4px;
            background-color: #202020;
          }
          .camera-image {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            cursor: pointer;
          }
          .camera-loading {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background-color: rgba(0, 0, 0, 0.6);
          }
          .camera-loading.hidden {
            display: none;
          }
          .controls {
            display: flex;
            align-items: center;
            justify-content: space-between;
          }
          .privacy-status {
            font-size: 14px;
            color: var(--secondary-text-color);
          }
          .privacy-on {
            color: var(--error-color);
          }
          .privacy-off {
            color: var(--success-color);
          }
        </style>
      </ha-card>
    `;
    
    this.content = true;
    
    this.cardHeader = this.shadowRoot.querySelector('.card-header');
    this.cameraImage = this.shadowRoot.querySelector('.camera-image');
    this.cameraLoading = this.shadowRoot.querySelector('.camera-loading');
    this.privacyToggle = this.shadowRoot.querySelector('.privacy-toggle');
    this.privacyStatus = this.shadowRoot.querySelector('.privacy-status');
    
    // 点击切换隐私模式
    this.privacyToggle.addEventListener('click', () => {
      if (!this._hass || !this.config) return;
      
      const entityId = this.config.switch_entity;
      const state = this._hass.states[entityId];
      const isOn = state.state === 'on';
      
      this._hass.callService('switch', isOn ? 'turn_off' : 'turn_on', {
        entity_id: entityId
      });
    });
    
    // 点击图像打开摄像头流
    this.cameraImage.addEventListener('click', () => {
      if (!this._hass || !this.config) return;
      
      this._showCameraDialog();
    });
  }
  
  updateCard() {
    if (!this._hass || !this.config) return;
    
    // 设置卡片标题
    if (this.config.title) {
      this.cardHeader.textContent = this.config.title;
    } else if (this.config.camera_entity) {
      const cameraState = this._hass.states[this.config.camera_entity];
      this.cardHeader.textContent = cameraState?.attributes?.friendly_name || '萤石摄像头';
    } else {
      this.cardHeader.textContent = '萤石摄像头';
    }
    
    // 更新摄像头图像
    if (this.config.camera_entity) {
      const cameraState = this._hass.states[this.config.camera_entity];
      if (cameraState) {
        // 如果还没有初始化，设置自动刷新
        if (!this._initialized) {
          this._setupAutoRefresh();
          this._initialized = true;
        }
        
        // 设置图像源
        this._updateCameraImage();
      }
    }
    
    // 更新隐私状态
    if (this.config.switch_entity) {
      const switchState = this._hass.states[this.config.switch_entity];
      if (switchState) {
        const isOn = switchState.state === 'on';
        this.privacyToggle.icon = isOn ? 'mdi:eye-off' : 'mdi:eye';
        this.privacyStatus.textContent = isOn ? '隐私模式: 开启' : '隐私模式: 关闭';
        this.privacyStatus.className = 'privacy-status ' + (isOn ? 'privacy-on' : 'privacy-off');
      }
    }
  }
  
  _setupAutoRefresh() {
    // 清除可能存在的旧定时器
    if (this._updateInterval) {
      clearInterval(this._updateInterval);
    }
    
    // 设置新的定时器，每30秒更新一次图像
    this._updateInterval = setInterval(() => {
      this._updateCameraImage();
    }, 30000);
  }
  
  _updateCameraImage() {
    if (!this._hass || !this.config || !this.config.camera_entity) return;
    
    const cameraState = this._hass.states[this.config.camera_entity];
    if (!cameraState) return;
    
    // 显示加载动画
    this.cameraLoading.classList.remove('hidden');
    
    // 构建带有时间戳的URL以避免缓存
    const timestamp = new Date().getTime();
    const entityId = this.config.camera_entity;
    const accessToken = cameraState.attributes.access_token || '';
    
    // 设置图像URL
    const imageUrl = `/api/camera_proxy/${entityId}?token=${accessToken}&ts=${timestamp}`;
    
    // 创建新图像对象以确保加载完成后再显示
    const newImage = new Image();
    newImage.onload = () => {
      this.cameraImage.src = imageUrl;
      this.cameraLoading.classList.add('hidden');
    };
    newImage.onerror = () => {
      this.cameraLoading.classList.add('hidden');
      console.error('Failed to load camera image');
    };
    newImage.src = imageUrl;
  }
  
  _showCameraDialog() {
    const event = new Event('hass-more-info', {
      bubbles: true,
      composed: true,
    });
    event.detail = {
      entityId: this.config.camera_entity,
    };
    this.dispatchEvent(event);
  }
  
  setConfig(config) {
    if (!config.camera_entity) {
      throw new Error('您需要定义摄像头实体');
    }
    if (!config.switch_entity) {
      throw new Error('您需要定义隐私控制开关实体');
    }
    
    this.config = config;
  }
  
  getCardSize() {
    return 4;
  }

  disconnectedCallback() {
    // 清除定时器
    if (this._updateInterval) {
      clearInterval(this._updateInterval);
      this._updateInterval = null;
    }
  }
  
  static getStubConfig() {
    return {
      camera_entity: "",
      switch_entity: "",
      title: "萤石摄像头"
    };
  }
}

customElements.define('ezviz-camera-card', EzvizCameraCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ezviz-camera-card",
  name: "萤石摄像头卡片",
  description: "一个带有隐私控制的萤石摄像头卡片"
});
"""