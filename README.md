# 人设切换插件 (Change Preset Plugin)

一个为 Nekro Agent 提供人设切换功能的插件，支持通过 Web UI 管理人设配置。

## 功能特性

- 🎭 支持多人设管理与切换
- 🔧 可视化 Web 管理界面
- 🎯 支持触发词自动切换人设
- 📝 人设隔离与白名单/黑名单功能
- 🚀 支持 OneBot v11 适配器

## Web UI 访问

插件启动后，可通过以下地址访问 Web 管理界面：

```
http://<ip>:<port>/plugins/Zaxpris.change_preset/
```

其中：
- `<ip>` 是您的服务器 IP 地址
- `<port>` 是 Nekro Agent 配置的端口号

例如：
- 本地访问：`http://localhost:8080/plugins/Zaxpris.change_preset/`
- 局域网访问：`http://192.168.1.100:8080/plugins/Zaxpris.change_preset/`

## 插件信息

- **版本**: 0.3.2
- **作者**: Zaxpris
- **支持适配器**: OneBot v11
- **项目地址**: https://github.com/KroMiose/nekro-agent

## 使用说明

1. 确保 Nekro Agent 已正确安装并运行
2. 将插件放置在插件目录中
3. 重启 Nekro Agent 以加载插件
4. 通过上述 Web UI 地址访问管理界面
5. 在 Web 界面中配置人设和触发词

## 功能说明

### 人设管理
- 创建、编辑、删除人设配置
- 设置人设白名单/黑名单
- 配置人设隔离模式

### 触发词设置
- 支持包含匹配和完全匹配模式
- 可设置是否记录触发词到聊天记录
- 支持触发后自动调用 LLM

### 任务管理
- 查看和管理人设相关任务
- 实时监控插件运行状态

## 许可证

本项目基于相应开源许可证发布，详见 [LICENSE](LICENSE) 文件。