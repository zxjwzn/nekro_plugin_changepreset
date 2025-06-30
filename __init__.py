from typing import Any, Dict

from nekro_agent.api import core
from nekro_agent.api.core import logger
from nekro_agent.api.plugin import ConfigBase, NekroPlugin, SandboxMethodType
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.models.db_chat_channel import DBChatChannel
from nekro_agent.models.db_preset import DBPreset
from nekro_agent.services.message_service import message_service

plugin = NekroPlugin(
    name="人设切换插件",
    module_name="change_preset",
    description="提供人设切换功能",
    version="0.3.0",
    author="Zaxpris",
    url="https://github.com/KroMiose/nekro-agent",
    support_adapter=["onebot_v11"],
)


@plugin.mount_prompt_inject_method(name="change_preset_prompt_inject")
async def change_preset_prompt_inject(_ctx: AgentCtx) -> str:
    """
    在每次对话开始时注入当前人设信息和可用人设列表。
    这是一个无状态的纯信息提供功能。
    """
    chat_key = _ctx.chat_key

    # 1. 获取当前会话的人设名称
    current_preset_name = "默认人设"
    channel = await DBChatChannel.get_or_none(chat_key=chat_key)
    if channel and channel.preset_id:
        current_preset = await DBPreset.get_or_none(id=channel.preset_id)
        if current_preset:
            current_preset_name = current_preset.name

    # 2. 获取所有人设列表用于提示
    presets = await DBPreset.all()
    if not presets:
        return f"你当前的人设是{current_preset_name}.系统中没有其他人设可供切换."

    preset_list_str = f"你当前的人设是{current_preset_name}.以下是可切换的人设列表:\n\n"
    for preset in presets:
        preset_list_str += f"- ID: {preset.id}\n  名称: {preset.name}\n"
        if preset.description:
            preset_list_str += f"  描述: {preset.description}\n"
    return preset_list_str


@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="人设切换",
    description="当需要切换到另一个人设来完成特定任务时使用。可以指定切换后要对它说的第一句话。",
)
async def change_preset(_ctx: AgentCtx, chat_key: str, preset_id: int, message_text: str) -> None:
    """
    人设切换

    Args:
        chat_key: 会话ID，必须是当前会话的ID
        preset_id: 目标人设的ID
        message_text: 对切换后的人设发送的消息或任务指令，这条消息会作为系统信息记录下来。

    Returns:
        None
    """
    channel = await DBChatChannel.get_or_none(chat_key=chat_key)
    if not channel:
        logger.warning(f"会话 {chat_key} 不存在，无法切换人设。")
        return

    # 获取原人设信息
    old_preset_name = "默认人设"
    if channel.preset_id:
        old_preset = await DBPreset.get_or_none(id=channel.preset_id)
        if old_preset:
            old_preset_name = old_preset.name

    # 检查目标人设是否存在
    new_preset = await DBPreset.get_or_none(id=preset_id)
    if not new_preset:
        logger.warning(f"尝试切换到不存在的人设ID {preset_id}。")
        await message_service.push_system_message(
            chat_key=chat_key,
            agent_messages=f"WARNING:人设{old_preset_name}尝试切换的人设id{preset_id}不存在,操作已取消.",
            trigger_agent=False,
        )
        return

    # 执行切换
    channel.preset_id = preset_id
    await channel.save()

    # 将任务消息作为系统消息推送到历史记录，并触发新的人设
    await message_service.push_system_message(
        chat_key=chat_key,
        agent_messages=f"人设{old_preset_name}尝试切换到人设{new_preset.name}，并向其发送了消息：{message_text}",
        trigger_agent=True,
    )
    logger.info(f"会话 {chat_key} 的人设已从 '{old_preset_name}' 切换为 '{new_preset.name}' (ID: {preset_id})")
    return


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="获取详细人设信息",
    description="获取详细人设信息",
)
async def get_preset_info(_ctx: AgentCtx, preset_id: int) -> str:
    """
    获取详细人设信息

    Args:
        preset_id: 人设ID

    Returns:
        str: 人设详细信息
    """
    preset = await DBPreset.get_or_none(id=preset_id)
    if not preset:
        return "人设不存在"
    return f"人设{preset.name}的详细信息：\n{preset.content}"


@plugin.mount_cleanup_method()
async def clean_up(_ctx: AgentCtx):
    """清理插件"""
