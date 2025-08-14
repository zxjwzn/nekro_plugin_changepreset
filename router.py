"""
人设切换插件路由功能

提供管理人设配置和查看任务的Web API界面
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
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
    is_chat_once: bool


class TriggerWordRequest(BaseModel):
    content: str
    is_record: bool = True
    trigger_mode: Literal["contains", "equals"] = "contains"
    is_trigger_llm: bool = False
    is_chat_once: bool = False


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
    is_chat_once=trigger_word.is_chat_once,
    )


def trigger_word_request_to_model(trigger_word_request: TriggerWordRequest) -> TriggerWord:
    """将 TriggerWordRequest 转换为 TriggerWord"""
    return TriggerWord(
        content=trigger_word_request.content,
        is_record=trigger_word_request.is_record,
        trigger_mode=trigger_word_request.trigger_mode,
    is_trigger_llm=trigger_word_request.is_trigger_llm,
    is_chat_once=trigger_word_request.is_chat_once,
    )


class TaskResponse(BaseModel):
    chat_key: str
    task_content: str


class PresetInfo(BaseModel):
    id: Optional[int]
    name: str
    description: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None


class PresetExportData(BaseModel):
    """人设导出数据模型"""
    id: Optional[int]
    remote_id: Optional[str]
    on_shared: bool
    name: str
    title: str
    avatar: str
    content: str
    description: str
    tags: str
    ext_data: Optional[Dict] = None
    author: str
    create_time: str
    update_time: str


class PresetImportData(BaseModel):
    """人设导入数据模型"""
    name: str
    title: str
    avatar: str
    content: str
    description: str = ""
    tags: str = ""
    author: str = ""
    ext_data: Optional[Dict] = None


class ImportResponse(BaseModel):
    """导入响应模型"""
    success_count: int
    failed_count: int
    total_count: int
    errors: List[str] = []


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
                            <li>GET /export-presets - 导出所有人设</li>
                            <li>GET /export-preset/{{preset_ids}} - 导出指定人设(支持多个ID，用逗号分隔)</li>
                            <li>POST /import-presets - 导入人设JSON文件</li>
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
            tags=None,
        ))
        
        # 添加数据库中的人设
        db_presets = await DBPreset.all()
        for preset in db_presets:
            presets.append(PresetInfo(
                id=preset.id,
                name=preset.name,
                description=preset.description,
                content=preset.content,
                tags=preset.tags,
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

    @router.get("/export-presets", summary="导出所有人设")
    async def export_all_presets():
        """导出所有人设为JSON格式 除了ID为None的默认人设"""
        try:
            # 获取所有人设
            presets = await DBPreset.all()
            
            export_data = []
            for preset in presets:
                preset_data = PresetExportData(
                    id=preset.id,
                    remote_id=preset.remote_id,
                    on_shared=preset.on_shared,
                    name=preset.name,
                    title=preset.title,
                    avatar=preset.avatar,
                    content=preset.content,
                    description=preset.description,
                    tags=preset.tags,
                    ext_data=preset.ext_data,
                    author=preset.author,
                    create_time=preset.create_time.strftime("%Y-%m-%d %H:%M:%S"),
                    update_time=preset.update_time.strftime("%Y-%m-%d %H:%M:%S"),
                )
                export_data.append(preset_data.model_dump())
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"presets_export_{timestamp}.json"
            
            # 创建临时文件
            temp_dir = Path.cwd() / "temp"
            temp_dir.mkdir(exist_ok=True)
            file_path = temp_dir / filename
            
            # 写入JSON文件
            with file_path.open("w", encoding="utf-8") as f:
                json.dump({
                    "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_count": len(export_data),
                    "presets": export_data,
                }, f, ensure_ascii=False, indent=2)
            
            return FileResponse(
                path=str(file_path),
                filename=filename,
                media_type="application/json",
            )
            
        except Exception as e:
            logger.error(f"导出人设失败: {e}")
            raise HTTPException(status_code=500, detail=f"导出失败: {e!s}") from e

    @router.get("/export-preset/{preset_ids}", summary="导出指定人设")
    async def export_preset(preset_ids: str):
        """导出指定人设为JSON格式 除了ID为None的默认人设
        
        支持单个或多个人设ID，用逗号分隔，例如：
        - /export-preset/1 - 导出单个人设
        - /export-preset/1,2,3 - 导出多个人设
        """
        # 解析人设ID列表
        id_list = []
        for id_str in preset_ids.split(","):
            id_str = id_str.strip()
            if not id_str:
                continue
            try:
                preset_id = int(id_str)
                id_list.append(preset_id)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"无效的人设ID: {id_str}") from e
        
        if not id_list:
            raise HTTPException(status_code=400, detail="请提供有效的人设ID")
        
        # 获取指定的人设
        presets = await DBPreset.filter(id__in=id_list).all()
        
        # 检查是否所有请求的人设都存在
        found_ids = {preset.id for preset in presets}
        missing_ids = set(id_list) - found_ids
        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail=f"以下人设不存在: {', '.join(map(str, missing_ids))}",
            )
        
        try:
            # 构建导出数据
            export_data = []
            preset_names = []
            for preset in presets:
                preset_data = PresetExportData(
                    id=preset.id,
                    remote_id=preset.remote_id,
                    on_shared=preset.on_shared,
                    name=preset.name,
                    title=preset.title,
                    avatar=preset.avatar,
                    content=preset.content,
                    description=preset.description,
                    tags=preset.tags,
                    ext_data=preset.ext_data,
                    author=preset.author,
                    create_time=preset.create_time.strftime("%Y-%m-%d %H:%M:%S"),
                    update_time=preset.update_time.strftime("%Y-%m-%d %H:%M:%S"),
                )
                export_data.append(preset_data.model_dump())
                # 收集人设名称用于文件名
                safe_name = "".join(c for c in preset.name if c.isalnum() or c in (" ", "-", "_")).rstrip()
                preset_names.append(safe_name)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"presets_export_{timestamp}.json"
            
            # 创建临时文件
            temp_dir = Path.cwd() / "temp"
            temp_dir.mkdir(exist_ok=True)
            file_path = temp_dir / filename
            
            # 写入JSON文件（使用与export_all_presets相同的格式）
            with file_path.open("w", encoding="utf-8") as f:
                json.dump({
                    "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_count": len(export_data),
                    "presets": export_data,
                }, f, ensure_ascii=False, indent=2)
            
            return FileResponse(
                path=str(file_path),
                filename=filename,
                media_type="application/json",
            )
            
        except Exception as e:
            logger.error(f"导出人设失败: {e}")
            raise HTTPException(status_code=500, detail=f"导出失败: {e!s}") from e

    @router.post("/import-presets", summary="导入人设", response_model=ImportResponse)
    async def import_presets(file: UploadFile = File(...)):
        """从JSON文件导入人设"""
        # 检查文件类型
        if not file.filename or not file.filename.endswith(".json"):
            raise HTTPException(status_code=400, detail="只支持JSON格式文件")
        
        try:
            # 读取文件内容
            content = await file.read()
            try:
                data = json.loads(content.decode("utf-8"))
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"JSON格式错误: {e!s}") from e
            
            success_count = 0
            failed_count = 0
            errors = []
            
            # 处理导入数据
            if "presets" in data:
                # 批量导入格式
                presets_data = data["presets"]
            else:
                # 直接是人设数组
                raise HTTPException(status_code=400, detail="JSON格式错误")  # noqa: TRY301
            
            total_count = len(presets_data)
            
            for preset_data in presets_data:
                try:
                    # 验证数据格式
                    import_data = PresetImportData(**preset_data)
                    
                    # 创建新人设
                    await DBPreset.create(
                        name=import_data.name,
                        title=import_data.title,
                        avatar=import_data.avatar,
                        content=import_data.content,
                        description=import_data.description,
                        tags=import_data.tags,
                        ext_data=import_data.ext_data,
                        author=import_data.author,
                        on_shared=False,
                    )
                    
                    success_count += 1
                    logger.info(f"成功导入人设: {import_data.name}")
                    
                except Exception as e:
                    error_msg = f"导入人设失败: {e!s}"
                    errors.append(error_msg)
                    failed_count += 1
                    logger.error(error_msg)
            
            return ImportResponse(
                success_count=success_count,
                failed_count=failed_count,
                total_count=total_count,
                errors=errors,
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"导入人设失败: {e}")
            raise HTTPException(status_code=500, detail=f"导入失败: {e!s}") from e

    return router
