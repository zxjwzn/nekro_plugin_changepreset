from typing import Dict, List, Literal, Optional

from pydantic import Field

from nekro_agent.api.plugin import ConfigBase, NekroPlugin
from nekro_agent.core.core_utils import ExtraField

plugin = NekroPlugin(
    name="人设切换插件",
    module_name="change_preset",
    description="提供人设切换功能",
    version="0.3.2",
    author="Zaxpris",
    url="https://github.com/KroMiose/nekro-agent",
    support_adapter=["onebot_v11"],
)

class TriggerWord(ConfigBase):
    content: str = Field(..., description="触发词文本")
    is_record: bool = Field(..., description="是否记录触发词到聊天记录中")
    trigger_mode: Literal["contains", "equals"] = Field(..., description="触发模式")
    is_trigger_llm: bool = Field(..., description="是否在切换人设后一并触发LLM")
    

class PresetItem(ConfigBase):
    id: Optional[str] = Field(default=None, description="人设id")
    whitelist: Optional[List[str]] = Field(
        default=None,
        description="可见人设白名单 (人设id列表), 设置后仅白名单内人设可见",
    )
    blacklist: Optional[List[str]] = Field(default=None, description="不可见人设黑名单 (人设id列表)")
    trigger_words: Optional[List[TriggerWord]] = Field(
        default=None,
        description="人设触发词列表, 设置后会在消息中检测触发词, 触发后切换到对应人设",
    )
    preset_session_block: Optional[bool] = Field(
        default=False,
        description="人设隔离, 设置后该人设聊天记录独立",
    )

@plugin.mount_config()
class ChangePresetConfig(ConfigBase):
    PRESET_SETTINGS: Dict[str, PresetItem] = Field(
        default_factory=dict,
        description="人设设置列表",
        json_schema_extra=ExtraField(is_hidden=True).model_dump(),
    )
    TASKS: Dict[str, str] = Field(
        default_factory=dict,
        description="人设任务列表",
        json_schema_extra=ExtraField(is_hidden=True).model_dump(),
    )