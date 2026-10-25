# astrbot_plugin_feiyu_qzone

让 bot 管理自己的 QQ 资料与空间：改昵称、改签名、改性别、发说说、删说说。

## 特性

- **不碰密码**：全部走 NapCat 的扩展 action，不需要 QQ 密码与 cookie
- **权限可控**：写操作限定管理员，普通群友只能看 `/账号信息`
- **可见范围**：发说说支持 `-p <权限>`（1 公开 / 4 好友 / 64 仅自己）
- **模型可调用**：改资料走 `llm_tool`，聊天里说「把签名改成 xxx」就能改

## 安装

1. 确保 NapCat 已登录且 AstrBot 的 QQ 适配器在线
2. 目录放到 `astrbot/data/plugins/`，无第三方依赖
3. 重启 AstrBot

## 指令

| 指令 | 说明 |
| --- | --- |
| `/账号信息` | 看当前登录账号 |
| `/改昵称 <新名字>` | 改昵称（管理员） |
| `/改签名 <内容>` | 改个性签名（管理员） |
| `/改性别 男/女` | 改性别（管理员） |
| `/发说说 [-p 64] <正文>` | 发说说（管理员） |
| `/删说说 <tid>` | 删说说（管理员） |

## LLM 工具

`change_qq_nickname`、`change_qq_signature`、`change_qq_gender`、`post_qzone_moment`。

## 常见问题

**报 action 不支持**
NapCat 版本太旧或不支持对应扩展。升级 NapCat 后重试。

**发说说权限参数不生效**
不同 NapCat 版本字段名略有差异，看日志里实际返回体。

## 许可

MIT，见 [LICENSE](LICENSE)。
