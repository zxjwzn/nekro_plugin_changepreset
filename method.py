from typing import Any, Dict, Optional, Union

from nekro_agent.api.core import logger
from nekro_agent.api.plugin import SandboxMethodType
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.core.config import config
from nekro_agent.models.db_chat_channel import DBChatChannel, DefaultPreset
from nekro_agent.models.db_chat_message import DBChatMessage
from nekro_agent.models.db_preset import DBPreset
from nekro_agent.models.db_user import DBUser
from nekro_agent.schemas.chat_message import ChatMessage
from nekro_agent.schemas.signal import MsgSignal
from nekro_agent.services.config_service import ConfigService
from nekro_agent.services.message_service import message_service

from .plugin import ChangePresetConfig, PresetItem, TriggerWord, plugin


async def sync_all_presets_to_config() -> None:
    """
    同步所有人设到配置中，为新人设创建空的配置映射
    """
    config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
    try:
        # 获取所有现有人设
        all_presets = await DBPreset.all()
        
        # 检查并添加缺失的人设配置
        for preset in all_presets:
            preset_id_str = str(preset.id)
            if preset_id_str not in config_obj.PRESET_SETTINGS:
                # 为新人设创建空的配置
                config_obj.PRESET_SETTINGS[preset_id_str] = PresetItem(id=preset_id_str)
                logger.info(f"为人设 {preset.name} (ID: {preset_id_str}) 创建了空配置")
        
        # 检查默认人设配置
        if "default" not in config_obj.PRESET_SETTINGS:
            config_obj.PRESET_SETTINGS["default"] = PresetItem(id="default")
            logger.info("为默认人设创建了空配置")
        
        plugin.save_config(config_obj)
        logger.info("已同步所有人设到配置中")
    except Exception as e:
        logger.error(f"同步人设配置失败: {e}")

@plugin.mount_init_method()
async def init_plugin():
    await sync_all_presets_to_config()

@plugin.mount_prompt_inject_method(name="change_preset_prompt_inject")
async def change_preset_prompt_inject(_ctx: AgentCtx) -> str:
    """
    构造提示词时会执行此方法来动态构建prompt
    """
    await sync_all_presets_to_config()
    result_parts = []
    
    # 获取插件配置
    config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
    
    ######注入任务提示######
    try:
        # 检查当前会话是否有任务
        tasks = config_obj.TASKS
        current_task = tasks.get(_ctx.chat_key)
        if current_task:
            result_parts.append(f"提示:当你认为以下信息已完成或不再需要时请使用ignore_task忽略\n当前任务: {current_task}")
    except Exception as e:
        logger.error(f"获取任务信息失败: {e}")
    
    ######注入可用人设######
    try:
        # 获取当前会话的聊天频道
        channel = await DBChatChannel.get_or_none(chat_key=_ctx.chat_key)
        if not channel:
            return "\n".join(result_parts) if result_parts else ""
        
        # 获取当前会话使用的人设
        current_preset: Union[DBPreset, DefaultPreset] = await channel.get_preset()
        
        preset_settings = config_obj.PRESET_SETTINGS
        
        
        # 获取当前人设的配置
        if isinstance(current_preset, DefaultPreset):
            current_preset_id = "default"
        else:
            current_preset_id = str(current_preset.id)
        if current_preset_id not in preset_settings:
            return "\n".join(result_parts) if result_parts else ""
        
        current_preset_config = preset_settings[current_preset_id]
        whitelist = current_preset_config.whitelist
        blacklist = current_preset_config.blacklist
        
        # 获取所有人设
        all_presets = await DBPreset.all()
        
        # 过滤人设列表
        available_presets = []
        for preset in all_presets:
            preset_id_str = str(preset.id)
            
            # 如果设置了白名单，只显示白名单内的人设
            if whitelist is not None and preset_id_str not in whitelist:
                continue
            
            # 如果设置了黑名单，排除黑名单内的人设
            if blacklist is not None and preset_id_str in blacklist:
                continue
            
            available_presets.append(preset)
        
        # 构建人设列表字符串
        preset_list = []
        
        # 添加当前人设信息
        if isinstance(current_preset, DefaultPreset):
            preset_list.append(f"当前人设: ID:None - {current_preset.name}")
        else:
            preset_list.append(f"当前人设: ID:{current_preset.id} - {current_preset.name}")
        
        preset_list.append("")  # 添加空行分隔
        
        # 添加默认人设选项
        preset_list.append(f"ID:None - {config.AI_CHAT_PRESET_NAME}:默认人设")
        
        # 添加可用的人设
        if available_presets:
            for preset in available_presets:
                preset_info = f"ID:{preset.id} - {preset.name}"
                if preset.description:
                    preset_info += f": {preset.description}"
                preset_list.append(preset_info)
        
        # 如果有人设列表（包括默认人设），添加到结果中
        if preset_list:
            result_parts.append("可切换的人设列表:\n" + "\n".join(preset_list))
        
    except Exception as e:
        logger.error(f"获取人设列表失败: {e}")
    
    return "\n\n".join(result_parts) if result_parts else ""
    
@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="人设切换",
    description="当需要切换到另一个人设来完成特定任务时使用。",
)
async def change_preset(_ctx: AgentCtx, chat_key: str, preset_id: Optional[int], message_text: str):
    """
    人设切换

    Args:
        chat_key: 会话ID
        preset_id: 目标人设的ID,传入None时获取默认人设
        message_text: 对切换后的人设发送的消息或任务指令 例如:呜呜呜人家现在正在被欺负,请帮我教训他

    Returns:
        str: 操作结果信息
    """
    try:
        # 获取聊天频道
        channel = await DBChatChannel.get_or_none(chat_key=chat_key)
        if not channel:
            return
        
        preset = await channel.get_preset()
        # 获取插件配置并创建任务
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        if isinstance(preset, DefaultPreset):
            # 直接修改配置对象中的任务
            config_obj.TASKS[chat_key] = f"名为{preset.name}的人设\nID: None，向你留下了以下消息: {message_text} \n请完成消息内的所有任务要求并在之后切换回原人设"
        else:
            config_obj.TASKS[chat_key] = f"名为{preset.name}的人设\nID: {preset.id}，向你留下了以下消息: {message_text} \n请完成消息内的所有任务要求并在之后切换回原人设"

        if preset_id is None:
            channel.preset_id = None  # type: ignore  # 在数据库模型中允许为null
        else:
            channel.preset_id = preset_id
        await channel.save()

        #通过system触发下一轮消息
        await message_service.push_system_message(
            chat_key=chat_key,
            agent_messages=f"人设切换成功，已切换到人设ID: {preset_id}",
            trigger_agent=True,
        )

    except Exception as e:
        logger.error(f"人设切换失败: {e}")
        return
    else:
        return

@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="忽略任务",
    description="删除当前会话的任务，使其不再在提示中显示",
)
async def ignore_task(_ctx: AgentCtx, chat_key: str):
    """
    忽略/删除任务
    当你认为原人设交代的任务已完成且没有必要切换回原人设时，可以调用此方法以忽略提示
    Args:
        chat_key: 会话ID，必须是当前会话的ID

    Returns:
        None
    """
    try:
        # 验证chat_key是否为当前会话
        if chat_key != _ctx.chat_key:
            return
        
        # 获取插件配置
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        # 检查任务是否存在
        if chat_key not in config_obj.TASKS:
            return
        
        # 删除任务
        del config_obj.TASKS[chat_key]
        
    except Exception as e:
        logger.error(f"删除任务失败: {e}")
        return
    else:
        return

@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="获取详细人设信息",
    description="获取详细人设信息",
)
async def get_preset_info(_ctx: AgentCtx, preset_id: Optional[int]) -> str:
    """
    获取人设内容
    当change_preset_prompt_inject内的人设描述模糊,无法知晓其具体身份时,可以调用此方法获取人设内容
    Args:
        preset_id: 人设ID,传入None时获取默认人设

    Returns:
        str: 人设具体内容
    """
    if not preset_id:
        return f"人设:{config.AI_CHAT_PRESET_NAME}\n具体内容:{config.AI_CHAT_PRESET_SETTING}"
    preset = await DBPreset.get_or_none(id=preset_id)
    if not preset:
        return "人设不存在"
    return f"人设:{preset.name}\n具体内容:{preset.content}"

@plugin.mount_on_user_message()
async def on_message(_ctx: AgentCtx, chatmessage: ChatMessage) -> MsgSignal:
    """处理消息"""
    try:
        # 获取插件配置
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        
        preset_settings = config_obj.PRESET_SETTINGS
        
        if not preset_settings:
            return MsgSignal.CONTINUE  # 如果没有人设配置，继续处理消息
            
        # 获取消息文本内容
        message_text = chatmessage.content_text

        # 遍历所有人设配置，检查触发词
        for preset_id_str, preset_config in preset_settings.items():
            trigger_words = preset_config.trigger_words
            if not trigger_words:
                continue
                
            # 检查消息中是否包含任何触发词
            message_lower = message_text.lower()
            for trigger_word in trigger_words:
                content = trigger_word.content
                trigger_mode = trigger_word.trigger_mode
                is_record = trigger_word.is_record
                is_trigger_llm = trigger_word.is_trigger_llm
                
                # 根据触发模式检查是否匹配
                is_matched = False
                if trigger_mode == "contains":
                    is_matched = content.lower() in message_lower
                elif trigger_mode == "equals":
                    is_matched = content.lower() == message_lower
                
                if is_matched:
                    # 找到触发词，执行人设切换
                    logger.info(f"检测到触发词 '{content}'，准备切换到人设 {preset_id_str}")
                    
                    # 获取聊天频道
                    channel = await DBChatChannel.get_or_none(chat_key=_ctx.chat_key)
                    if not channel:
                        logger.error(f"未找到聊天频道: {_ctx.chat_key}")
                        return MsgSignal.CONTINUE
                    
                    # 获取当前人设
                    current_preset = await channel.get_preset()
                    
                    # 将preset_id_str转换为int（如果不是"default"）
                    try:
                        if preset_id_str == "default":
                            target_preset_id = None
                        else:
                            target_preset_id = int(preset_id_str)
                    except ValueError:
                        logger.error(f"无效的人设ID: {preset_id_str}")
                        return MsgSignal.CONTINUE
                    
                    target_preset = await channel.get_preset()

                    #验证目标人设是否存在
                    if target_preset_id is not None:
                        target_preset = await DBPreset.get_or_none(id=target_preset_id)
                        if not target_preset:
                            logger.error(f"无效的人设ID: {target_preset_id}")
                            return MsgSignal.CONTINUE

                    # 切换人设
                    if target_preset_id is None:
                        channel.preset_id = None  # type: ignore  # 数据库允许为null
                    else:
                        channel.preset_id = target_preset_id

                    await channel.save()

                    #获取切换后人设
                    target_preset = await channel.get_preset()

                    if target_preset == current_preset:
                        logger.info(f"人设切换失败: 目标人设与当前人设相同 ({current_preset.name})")
                        return MsgSignal.CONTINUE

                    # 发送系统消息
                    if is_trigger_llm:
                        await message_service.push_system_message(
                            chat_key=_ctx.chat_key,
                            agent_messages="",
                            trigger_agent=True,
                        )
                    else:
                        # 如果不触发LLM，则发送系统消息提示
                        await message_service.push_system_message(
                            chat_key=_ctx.chat_key,
                            agent_messages="",
                            trigger_agent=False,
                        )  

                    if is_record:
                        # 记录触发词到聊天记录中
                        return MsgSignal.BLOCK_TRIGGER
                    
                    return MsgSignal.BLOCK_ALL
                    
    except Exception as e:
        logger.error(f"消息处理失败: {e}")
        return MsgSignal.CONTINUE  # 继续处理消息，默认行为
    return MsgSignal.CONTINUE

@plugin.mount_on_channel_reset()
async def reset_methods(_ctx: AgentCtx):
    """重置插件方法"""
    config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
    try:
        config_obj.TASKS[_ctx.chat_key] = ""  # 清空当前会话任务
    except Exception as e:
        logger.error(f"重置插件方法失败: {e}")

@plugin.mount_cleanup_method()
async def clean_up():
    """清理插件"""