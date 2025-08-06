"""
人设切换插件路由功能

提供管理人设配置和查看任务的Web API界面
"""

import os
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from nekro_agent.core.config import config
from nekro_agent.core.logger import logger
from nekro_agent.models.db_preset import DBPreset

from .plugin import ChangePresetConfig, PresetItem, TriggerWord, plugin


# 数据模型定义
class TriggerWordResponse(BaseModel):
    content: str
    is_record: bool
    trigger_mode: Literal["contains", "equals"]
    is_trigger_llm: bool


class TriggerWordRequest(BaseModel):
    content: str
    is_record: bool = True
    trigger_mode: Literal["contains", "equals"] = "contains"
    is_trigger_llm: bool = False


class PresetItemResponse(BaseModel):
    id: str
    whitelist: Optional[List[str]] = None
    blacklist: Optional[List[str]] = None
    trigger_words: Optional[List[TriggerWordResponse]] = None
    preset_session_block: bool = False


class UpdatePresetItemRequest(BaseModel):
    whitelist: Optional[List[str]] = None
    blacklist: Optional[List[str]] = None
    trigger_words: Optional[List[TriggerWordRequest]] = None
    preset_session_block: bool = False


# 工具函数
def trigger_word_to_response(trigger_word: TriggerWord) -> TriggerWordResponse:
    """将 TriggerWord 转换为 TriggerWordResponse"""
    return TriggerWordResponse(
        content=trigger_word.content,
        is_record=trigger_word.is_record,
        trigger_mode=trigger_word.trigger_mode,
        is_trigger_llm=trigger_word.is_trigger_llm,
    )


def trigger_word_request_to_model(trigger_word_request: TriggerWordRequest) -> TriggerWord:
    """将 TriggerWordRequest 转换为 TriggerWord"""
    return TriggerWord(
        content=trigger_word_request.content,
        is_record=trigger_word_request.is_record,
        trigger_mode=trigger_word_request.trigger_mode,
        is_trigger_llm=trigger_word_request.is_trigger_llm,
    )


class TaskResponse(BaseModel):
    chat_key: str
    task_content: str


class PresetInfo(BaseModel):
    id: Optional[int]
    name: str
    description: Optional[str] = None
    content: Optional[str] = None


@plugin.mount_router()
def create_router() -> APIRouter:
    """创建并配置插件路由"""
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse, summary="插件管理页面")
    async def plugin_home():
        """返回插件管理页面"""
        try:
            # 获取当前文件的绝对路径
            current_file_path = Path(__file__).resolve()
            # 获取插件目录（router.py 所在的目录）
            plugin_dir = current_file_path.parent
            # 构建 web/index.html 的完整路径
            web_file_path = plugin_dir / "web" / "index.html"
            
            if web_file_path.exists():
                return HTMLResponse(content=web_file_path.read_text(encoding="utf-8"))
            
        except Exception as e:
            logger.error(f"加载页面失败: {e}")
            return HTMLResponse(
                content=f"""
                <html>
                    <head><title>人设切换插件管理</title></head>
                    <body>
                        <h1>人设切换插件管理页面</h1>
                        <p>前端页面文件未找到: {e!s}</p>
                        <p>当前文件路径: {Path(__file__).resolve()}</p>
                        <p>插件目录: {Path(__file__).resolve().parent}</p>
                        <p>查找的文件路径: {Path(__file__).resolve().parent / "web" / "index.html"}</p>
                        <p>可用API端点:</p>
                        <ul>
                            <li>GET /presets - 获取所有人设信息</li>
                            <li>GET /preset-settings - 获取人设配置</li>
                            <li>PUT /preset-settings/{{preset_id}} - 更新人设配置</li>
                            <li>GET /tasks - 获取所有任务</li>
                            <li>DELETE /tasks/{{chat_key}} - 删除指定任务</li>
                        </ul>
                        <h3>调试信息</h3>
                        <p>请检查 web/index.html 文件是否在正确的位置。</p>
                    </body>
                </html>
                """,
            )

    @router.get("/static/{file_path:path}")
    async def serve_static(file_path: str):
        """提供静态文件服务"""
        # 获取当前文件的绝对路径
        current_file_path = Path(__file__).resolve()
        # 获取插件目录
        plugin_dir = current_file_path.parent
        # 构建静态文件的完整路径
        static_file_path = plugin_dir / "web" / file_path
        
        logger.info(f"请求静态文件: {file_path}")
        logger.info(f"静态文件完整路径: {static_file_path}")
        
        if not (static_file_path.exists() and static_file_path.is_file()):
            logger.warning(f"静态文件不存在: {static_file_path}")
            raise HTTPException(status_code=404, detail="文件未找到")
        return FileResponse(static_file_path)

    @router.get("/presets", response_model=List[PresetInfo], summary="获取所有人设信息")
    async def get_all_presets():
        """获取所有人设基本信息"""
        presets = []
        
        # 添加默认人设
        presets.append(PresetInfo(
            id=None,
            name=config.AI_CHAT_PRESET_NAME,
            description="系统默认人设",
            content=config.AI_CHAT_PRESET_SETTING,
        ))
        
        # 添加数据库中的人设
        db_presets = await DBPreset.all()
        for preset in db_presets:
            presets.append(PresetInfo(
                id=preset.id,
                name=preset.name,
                description=preset.description,
                content=preset.content,
            ))
        
        return presets

    @router.get("/preset-settings", response_model=Dict[str, PresetItemResponse], summary="获取人设配置")
    async def get_preset_settings():
        """获取所有人设的配置设置"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        result = {}
        for preset_id, preset_item in config_obj.PRESET_SETTINGS.items():
            # 转换 trigger_words
            trigger_words_response = None
            if preset_item.trigger_words:
                trigger_words_response = [
                    trigger_word_to_response(tw) for tw in preset_item.trigger_words
                ]
            
            result[preset_id] = PresetItemResponse(
                id=preset_item.id or preset_id,
                whitelist=preset_item.whitelist,
                blacklist=preset_item.blacklist,
                trigger_words=trigger_words_response,
                preset_session_block=preset_item.preset_session_block or False,
            )
        
        return result

    @router.get("/preset-settings/{preset_id}", response_model=PresetItemResponse, summary="获取指定人设配置")
    async def get_preset_setting(preset_id: str):
        """获取指定人设的配置"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        if preset_id not in config_obj.PRESET_SETTINGS:
            raise HTTPException(status_code=404, detail="人设配置不存在")
        
        preset_item = config_obj.PRESET_SETTINGS[preset_id]
        
        # 转换 trigger_words
        trigger_words_response = None
        if preset_item.trigger_words:
            trigger_words_response = [
                trigger_word_to_response(tw) for tw in preset_item.trigger_words
            ]
        
        return PresetItemResponse(
            id=preset_item.id or preset_id,
            whitelist=preset_item.whitelist,
            blacklist=preset_item.blacklist,
            trigger_words=trigger_words_response,
            preset_session_block=preset_item.preset_session_block or False,
        )

    @router.put("/preset-settings/{preset_id}", response_model=PresetItemResponse, summary="更新人设配置")
    async def update_preset_setting(preset_id: str, update_data: UpdatePresetItemRequest):
        """更新指定人设的配置"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        # 如果配置不存在，创建新的
        if preset_id not in config_obj.PRESET_SETTINGS:
            config_obj.PRESET_SETTINGS[preset_id] = PresetItem(id=preset_id)
        
        # 更新配置
        preset_item = config_obj.PRESET_SETTINGS[preset_id]
        preset_item.whitelist = update_data.whitelist
        preset_item.blacklist = update_data.blacklist
        
        # 转换 trigger_words
        if update_data.trigger_words is not None:
            preset_item.trigger_words = [
                trigger_word_request_to_model(tw) for tw in update_data.trigger_words
            ]
        else:
            preset_item.trigger_words = None
            
        preset_item.preset_session_block = update_data.preset_session_block
        
        # 保存配置
        plugin.save_config(config_obj)
        
        # 转换响应数据
        trigger_words_response = None
        if preset_item.trigger_words:
            trigger_words_response = [
                trigger_word_to_response(tw) for tw in preset_item.trigger_words
            ]
        
        return PresetItemResponse(
            id=preset_id,
            whitelist=preset_item.whitelist,
            blacklist=preset_item.blacklist,
            trigger_words=trigger_words_response,
            preset_session_block=preset_item.preset_session_block or False,
        )

    @router.delete("/preset-settings/{preset_id}", summary="删除人设配置")
    async def delete_preset_setting(preset_id: str):
        """删除指定人设的配置"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        if preset_id not in config_obj.PRESET_SETTINGS:
            raise HTTPException(status_code=404, detail="人设配置不存在")
        
        del config_obj.PRESET_SETTINGS[preset_id]
        plugin.save_config(config_obj)
        
        return {"message": f"人设配置 {preset_id} 已删除"}

    @router.get("/tasks", response_model=List[TaskResponse], summary="获取所有会话任务")
    async def get_all_tasks():
        """获取所有会话的任务"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        tasks = []
        for chat_key, task_content in config_obj.TASKS.items():
            if task_content:  # 只返回非空任务
                tasks.append(TaskResponse(
                    chat_key=chat_key,
                    task_content=task_content,
                ))
        
        return tasks

    @router.get("/tasks/{chat_key}", response_model=TaskResponse, summary="获取指定会话任务")
    async def get_task(chat_key: str):
        """获取指定会话的任务"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        if chat_key not in config_obj.TASKS or not config_obj.TASKS[chat_key]:
            raise HTTPException(status_code=404, detail="任务不存在或为空")
        
        return TaskResponse(
            chat_key=chat_key,
            task_content=config_obj.TASKS[chat_key],
        )

    @router.delete("/tasks/{chat_key}", summary="删除指定会话任务")
    async def delete_task(chat_key: str):
        """删除指定会话的任务"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        if chat_key not in config_obj.TASKS:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        del config_obj.TASKS[chat_key]
        plugin.save_config(config_obj)
        
        return {"message": f"会话 {chat_key} 的任务已删除"}

    @router.post("/tasks/{chat_key}/clear", summary="清空指定会话任务")
    async def clear_task(chat_key: str):
        """清空指定会话的任务内容"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        config_obj.TASKS[chat_key] = ""
        plugin.save_config(config_obj)
        
        return {"message": f"会话 {chat_key} 的任务已清空"}

    @router.get("/statistics", summary="获取统计信息")
    async def get_statistics():
        """获取插件统计信息"""
        config_obj: ChangePresetConfig = plugin.get_config(ChangePresetConfig)
        
        total_presets = len(config_obj.PRESET_SETTINGS)
        active_tasks = len([task for task in config_obj.TASKS.values() if task])
        total_tasks = len(config_obj.TASKS)
        
        # 统计触发词数量
        trigger_words_count = sum(
            len(preset.trigger_words or []) 
            for preset in config_obj.PRESET_SETTINGS.values()
        )
        
        return {
            "total_preset_settings": total_presets,
            "active_tasks": active_tasks,
            "total_task_sessions": total_tasks,
            "total_trigger_words": trigger_words_count,
        }

    return router
