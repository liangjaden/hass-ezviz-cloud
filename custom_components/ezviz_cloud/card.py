"""Card definitions for EZVIZ Cloud integration."""
import logging
import os
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
        with open(card_js_path, "w") as card_file:
            card_file.write(EZVIZ_CAMERA_CARD_JS)

    # 注册Lovelace资源，如果可能的话
    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection

        resources = ResourceStorageCollection(hass)
        await resources.async_initialize()

        resource_url = f"/local/{DOMAIN}/ezviz-camera-card.js"
        resource_exists = False

        for resource in resources.async_items():
            if resource["url"] == resource_url:
                resource_exists = True
                break

        if not resource_exists:
            try:
                await resources.async_create_item(
                    {
                        "url": resource_url,
                        "type": "module",
                        "res_type": "custom-card",
                    }
                )
                _LOGGER.info("已注册萤石摄像头卡片作为Lovelace资源")
            except Exception as e:
                _LOGGER.warning("无法注册萤石摄像头卡片: %s", e)
                _LOGGER.info(
                    "您需要手动添加'/local/%s/ezviz-camera-card.js' "
                    "作为Lovelace资源在您的UI设置中", DOMAIN
                )
    except (ImportError, AttributeError):
        _LOGGER.info(
            "未找到Lovelace集成或不支持自动注册。"
            "您需要手动添加'/local/%s/ezviz-camera-card.js' "
            "作为Lovelace资源在您的UI设置中", DOMAIN
        )

    return True

# 自定义卡片的JavaScript代码
EZVIZ_CAMERA_CARD_JS = """
class EzvizCameraCard extends HTMLElement {
  set hass(hass) {
    if (!this.content) {
      this.innerHTML = `
        <ha-card>
          <div class="card-header"></div>
          <div class="card-content">
            <div class="camera-wrapper">
              <img class="camera-image" />
            </div>
            <div class="controls">
              <ha-icon-button class="privacy-toggle" icon="mdi:eye"></ha-icon-button>
              <span class="privacy-status"></span>
            </div>
          </div>
          <style>
            .camera-wrapper {
              position: relative;
              width: 100%;
              height: 0;
              padding-bottom: 56.25%; /* 16:9 宽高比 */
              overflow: hidden;
              margin-bottom: 16px;
              border-radius: 4px;
            }
            .camera-image {
              position: absolute;
              top: 0;
              left: 0;
              width: 100%;
              height: 100%;
              object-fit: cover;
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
      
      this.cardHeader = this.querySelector('.card-header');
      this.cameraImage = this.querySelector('.camera-image');
      this.privacyToggle = this.querySelector('.privacy-toggle');
      this.privacyStatus = this.querySelector('.privacy-status');
      
      this.privacyToggle.addEventListener('click', () => {
        const entityId = this.config.switch_entity;
        const state = this.hass.states[entityId];
        const isOn = state.state === 'on';
        
        hass.callService('switch', isOn ? 'turn_off' : 'turn_on', {
          entity_id: entityId
        });
      });
    }
    
    const config = this.config;
    
    // Set card header
    if (config.title) {
      this.cardHeader.textContent = config.title;
    } else {
      this.cardHeader.textContent = '萤石摄像头';
    }
    
    // Update camera image
    if (config.camera_entity) {
      const cameraState = this.hass.states[config.camera_entity];
      if (cameraState) {
        this.cameraImage.src = `/api/camera_proxy/${config.camera_entity}?token=${cameraState.attributes.access_token || ''}`;
        this.cameraImage.alt = cameraState.attributes.friendly_name || '摄像头';
      }
    }
    
    // Update privacy status
    if (config.switch_entity) {
      const switchState = this.hass.states[config.switch_entity];
      if (switchState) {
        const isOn = switchState.state === 'on';
        this.privacyToggle.icon = isOn ? 'mdi:eye-off' : 'mdi:eye';
        this.privacyStatus.textContent = isOn ? '隐私模式: 开启' : '隐私模式: 关闭';
        this.privacyStatus.className = 'privacy-status ' + (isOn ? 'privacy-on' : 'privacy-off');
      }
    }
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

  static getStubConfig() {
    return {
      camera_entity: "",
      switch_entity: "",
      title: "萤石摄像头"
    };
  }
  
  static get properties() {
    return {
      hass: {},
      config: {}
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