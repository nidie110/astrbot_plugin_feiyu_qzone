import json

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.event.filter import PermissionType
from astrbot.api.star import Context, Star
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
_KIT_PATH = _Path(__file__).resolve().parent / "_feiyu_kit.py"
kit = _sys.modules.get("_feiyu_kit")
if kit is None:
    # 全进程只有一份 kit：动作注册表必须共享，所以谁先加载谁就是那份，后来者直接复用。
    # 磁盘上的 kit 改动要重启整个 AstrBot 进程才生效（面板重载插件不会换掉已经加载的模块）。
    import importlib.util as _ilu  # noqa: PLC0415

    _spec = _ilu.spec_from_file_location("_feiyu_kit", _KIT_PATH)
    _fresh = _ilu.module_from_spec(_spec)
    _sys.modules["_feiyu_kit"] = _fresh
    _spec.loader.exec_module(_fresh)
    kit = _fresh

PLUGIN_NAME = "astrbot_plugin_feiyu_qzone"

UGC_RIGHT = {1: "所有人可见", 4: "好友可见", 16: "部分好友可见", 64: "仅自己可见", 128: "部分好友不可见"}
VISIBILITY = {"public": 1, "friends": 4, "private": 64, "self": 64, "部分": 16}

DEFAULT_CONFIG = {"owner_ids": ""}


def _client(event: AstrMessageEvent):
    bot = getattr(event, "bot", None)
    api = getattr(bot, "api", None)
    if bot is None or not hasattr(api, "call_action"):
        return None
    return bot


def _arg(event: AstrMessageEvent) -> str:
    text = (event.message_str or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _fmt(ret) -> str:
    return json.dumps(ret, ensure_ascii=False) if isinstance(ret, dict) else str(ret)


class FeiyuQzone(Star):
    """大肥鱼·QQ资料与空间：改 bot 自己的 QQ 资料、发/删空间说说（走 NapCat 扩展 action）。"""

    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        # 只有 owner_ids 一项：改资料、发说说这类不可逆动作要按号认人
        self.cfg = kit.merge_config(DEFAULT_CONFIG, config)
        kit.register_capability("feiyu_qzone", "能改自己QQ的昵称、签名、性别，能发说说", "admin")
        kit.register_action("改签名", self.tool_change_signature, "改QQ签名，参数 text")
        kit.register_action("改昵称", self.tool_change_nickname, "改QQ昵称，参数 nickname")
        kit.register_action("改性别", self.tool_change_gender, "改QQ资料性别，参数 gender")
        kit.register_action("发说说", self.tool_post_qzone, "发QQ空间说说，参数 content")

    async def _call(self, event: AstrMessageEvent, action: str, **payload):
        bot = _client(event)
        if bot is None:
            return None, "这个平台不支持（没有 aiocqhttp 反向 WS 连接）"
        try:
            ret = await bot.api.call_action(action, **payload)
            logger.info(f"[feiyu_qzone] {action} 成功: {_fmt(ret)[:200]}")
            return ret, None
        except Exception as e:
            logger.warning(f"[feiyu_qzone] {action} 失败: {e}")
            return None, f"{type(e).__name__}: {e}"

    async def _current_nickname(self, event: AstrMessageEvent) -> str:
        ret, _ = await self._call(event, "get_login_info")
        return str((ret or {}).get("nickname") or "") if isinstance(ret, dict) else ""

    # ================= LLM 工具（她自己会用的） =================

    async def tool_change_signature(self, event: AstrMessageEvent, text: str):
        """改自己的 QQ 个性签名。只在主人（管理员）明确要求时使用，比如“你把签名改成xxx”。

        不要主动改、不要自己想到就改；对方没明确说“改签名”就不要调用。

        Args:
            text(string): 新的个性签名，20 字以内最好
        """
        if not kit.is_owner(event, self.cfg):
            return "这个得主人开口我才能动。"
        text = (text or "").strip()
        if not text:
            return "签名不能是空的。"
        nickname = await self._current_nickname(event)
        if not nickname:
            return "取不到当前昵称，改不了。"
        ret, err = await self._call(event, "set_qq_profile", nickname=nickname, personal_note=text[:60])
        return f"签名改成「{text[:60]}」了。" if not err else f"没改成：{err}"

    async def tool_change_nickname(self, event: AstrMessageEvent, nickname: str):
        """改自己的 QQ 昵称。只在主人（管理员）明确要求时使用。

        不要主动改。

        Args:
            nickname(string): 新昵称，16 字以内
        """
        if not kit.is_owner(event, self.cfg):
            return "这个得主人开口我才能动。"
        nickname = (nickname or "").strip()
        if not nickname:
            return "昵称不能是空的。"
        ret, err = await self._call(event, "set_qq_profile", nickname=nickname[:32])
        return f"昵称改成「{nickname[:32]}」了。" if not err else f"没改成：{err}"

    async def tool_change_gender(self, event: AstrMessageEvent, gender: str):
        """改自己 QQ 资料里的性别。只在主人（管理员）明确要求时使用。

        注意：年龄和生日改不了（NapCat 没开放这个接口），只能手机上改。

        Args:
            gender(string): male / female / unknown（男/女/未知）
        """
        if not kit.is_owner(event, self.cfg):
            return "这个得主人开口我才能动。"
        mapping = {"male": 1, "男": 1, "female": 2, "女": 2, "unknown": 0, "未知": 0, "保密": 0, "": 0}
        key = str(gender or "").strip().lower()
        if key not in mapping:
            return "性别只能是 男 / 女 / 未知。"
        sex = mapping[key]
        nickname = await self._current_nickname(event)
        if not nickname:
            return "取不到当前昵称，改不了。"
        _, err = await self._call(event, "set_qq_profile", nickname=nickname, sex=sex)
        label = {1: "男", 2: "女", 0: "未知"}[sex]
        return f"性别改成「{label}」了。" if not err else f"没改成：{err}"

    async def tool_post_qzone(self, event: AstrMessageEvent, content: str, visibility: str = "private"):
        """发一条 QQ 空间说说。只在主人（管理员）明确要求“发个说说/发条空间/把这个发空间”时使用。

        不许自己主动发，不许把聊天内容随手发空间。默认只发“仅自己可见”，除非对方明确说“公开/所有人可见”。

        Args:
            content(string): 说说正文，不超过 300 字
            visibility(string): 可见范围，private（仅自己，默认）/ friends（好友）/ public（所有人）
        """
        if not kit.is_owner(event, self.cfg):
            return "发空间这个得主人点头。"
        content = (content or "").strip()
        if not content:
            return "正文不能是空的。"
        if len(content) > 300:
            content = content[:300]
        ugc = VISIBILITY.get(str(visibility or "private").strip().lower(), 64)
        ret, err = await self._call(event, "send_qzone_msg", content=content, ugc_right=ugc)
        if err:
            return f"没发出去：{err}"
        tid = (ret or {}).get("tid", "") if isinstance(ret, dict) else ""
        return f"发出去了（{UGC_RIGHT.get(ugc, ugc)}）。" + (f"tid={tid}，要删就用这个。" if tid else "")

    # ================= 管理员指令 =================

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("账号信息")
    async def cmd_login_info(self, event: AstrMessageEvent):
        """看 bot 自己当前的登录信息。"""
        ret, err = await self._call(event, "get_login_info")
        if err:
            yield event.plain_result(f"失败：{err}")
            return
        uid = (ret or {}).get("user_id", "") if isinstance(ret, dict) else ""
        nick = (ret or {}).get("nickname", "") if isinstance(ret, dict) else ""
        yield event.plain_result(f"{nick}（{uid}）")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("改昵称")
    async def cmd_nickname(self, event: AstrMessageEvent):
        """改昵称：/改昵称 新名字"""
        name = _arg(event)
        if not name:
            yield event.plain_result("用法：/改昵称 新名字")
            return
        _, err = await self._call(event, "set_qq_profile", nickname=name)
        yield event.plain_result("改好了" if not err else f"失败：{err}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("改签名")
    async def cmd_signature(self, event: AstrMessageEvent):
        """改签名：/改签名 内容"""
        note = _arg(event)
        if not note:
            yield event.plain_result("用法：/改签名 签名内容")
            return
        nickname = await self._current_nickname(event)
        if not nickname:
            yield event.plain_result("取不到当前昵称，改不了")
            return
        _, err = await self._call(event, "set_qq_profile", nickname=nickname, personal_note=note)
        yield event.plain_result("签名改好了" if not err else f"失败：{err}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("改性别")
    async def cmd_gender(self, event: AstrMessageEvent):
        """改性别：/改性别 男|女|未知（年龄生日改不了）"""
        raw = _arg(event).strip().lower()
        mapping = {"male": 1, "男": 1, "female": 2, "女": 2, "unknown": 0, "未知": 0, "保密": 0}
        if raw not in mapping:
            yield event.plain_result("用法：/改性别 男|女|未知")
            return
        nickname = await self._current_nickname(event)
        if not nickname:
            yield event.plain_result("取不到当前昵称，改不了")
            return
        _, err = await self._call(event, "set_qq_profile", nickname=nickname, sex=mapping[raw])
        yield event.plain_result("改好了" if not err else f"失败：{err}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("发说说")
    async def cmd_post(self, event: AstrMessageEvent):
        """发说说：/发说说 正文 或 /发说说 -p 64 正文"""
        raw = _arg(event)
        if not raw:
            yield event.plain_result("用法：/发说说 正文\n或 /发说说 -p 64 正文（仅自己可见）")
            return
        ugc, content = 1, raw
        if raw.startswith("-p"):
            parts = raw.split(maxsplit=2)
            if len(parts) >= 2 and parts[1].isdigit():
                ugc = int(parts[1])
                content = parts[2] if len(parts) > 2 else ""
        if not content:
            yield event.plain_result("正文不能为空")
            return
        if ugc not in UGC_RIGHT:
            yield event.plain_result(f"权限值只能是 {sorted(UGC_RIGHT)}")
            return
        ret, err = await self._call(event, "send_qzone_msg", content=content, ugc_right=ugc)
        if err:
            yield event.plain_result(f"失败：{err}")
            return
        tid = (ret or {}).get("tid", "") if isinstance(ret, dict) else ""
        yield event.plain_result(f"发出去了（{UGC_RIGHT[ugc]}）" + (f"，tid={tid}" if tid else ""))

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("删说说")
    async def cmd_delete(self, event: AstrMessageEvent):
        """删说说：/删说说 tid"""
        tid = _arg(event)
        if not tid:
            yield event.plain_result("用法：/删说说 tid")
            return
        _, err = await self._call(event, "delete_qzone_msg", tid=tid)
        yield event.plain_result("删了" if not err else f"失败：{err}")
