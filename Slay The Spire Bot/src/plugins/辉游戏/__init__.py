# 文件名: huigame.py
# 放置位置: plugins/huigame.py

import json
import json
import os
import random
import time
import asyncio
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any
from enum import Enum

from nonebot import on_command, require, get_driver, on_notice
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, Message, MessageSegment, GroupRequestEvent, FriendRequestEvent
from nonebot.params import CommandArg, ArgPlainText, EventMessage
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot.matcher import Matcher
from nonebot import get_bots

# ============ 导入模块 ============
import json
from pathlib import Path
from typing import Tuple
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import to_me
import random
import time
from datetime import datetime

# ============ 工具函数定义（必须先定义） ============
def load_data(file_path: Path, default: dict = None) -> dict:
    """加载数据文件"""
    if default is None:
        default = {}
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"ERROR: 加载数据失败 {file_path}: {e}")
            return default
    return default


def save_data(data: dict, file_path: Path):
    """保存数据到文件，支持序列化集合类型"""
    
    # 辅助函数：转换不可JSON序列化的类型
    def convert_for_json(obj):
        """递归转换不可JSON序列化的对象"""
        if isinstance(obj, set):
            return list(obj)
        elif isinstance(obj, dict):
            return {k: convert_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_for_json(item) for item in obj]
        elif isinstance(obj, tuple):
            return list(obj)
        else:
            # 尝试处理其他类型
            try:
                json.dumps(obj)  # 检查是否可序列化
                return obj
            except TypeError:
                # 如果是自定义对象，转换为字符串
                return str(obj)
    
    # 转换数据
    try:
        converted_data = convert_for_json(data)
        
        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(converted_data, f, ensure_ascii=False, indent=2)
        
        print(f"SUCCESS: 数据已保存到: {file_path}")
        
    except Exception as e:
        print(f"ERROR: 保存数据到 {file_path} 时出错: {e}")
        # 尝试保存备份
        backup_path = file_path.with_suffix('.json.bak')
        try:
            import shutil
            if file_path.exists():
                shutil.copy2(file_path, backup_path)
                print(f"SUCCESS: 已创建备份: {backup_path}")
        except Exception as backup_e:
            print(f"ERROR: 创建备份失败: {backup_e}")


# ============ 数据存储路径 ============
DATA_DIR = Path() / "data" / "huigame"
USER_DATA_FILE = DATA_DIR / "users.json"
WORKS_DATA_FILE = DATA_DIR / "works.json"
RELATION_DATA_FILE = DATA_DIR / "relations.json"
STATE_DATA_FILE = DATA_DIR / "states.json"
REVIEW_DATA_FILE = DATA_DIR / "reviews.json"
AUDIT_LOG_FILE = DATA_DIR / "audit_log.json"
IMAGES_DIR = DATA_DIR / "images"
PENDING_IMAGES_DIR = IMAGES_DIR / "pending"
APPROVED_IMAGES_DIR = IMAGES_DIR / "approved"
PENDING_RELATIONS_FILE = DATA_DIR / "pending_relations.json"

HUIYAN_DIR = DATA_DIR / "huiyan"  # 修复：统一放在DATA_DIR下
HUIYAN_IMAGES_DIR = HUIYAN_DIR / "images"
HUIYAN_DATA_FILE = HUIYAN_DIR / "huiyan.json"


# ============ 数据初始化 ============
# 用户数据
users_data = load_data(USER_DATA_FILE, {})

# 作品数据
works_data = load_data(WORKS_DATA_FILE, {})

# 关系数据
relations_data = load_data(RELATION_DATA_FILE, {})

# 状态数据
states_data = load_data(STATE_DATA_FILE, {
    "sign_times": {},
    "upload_times": {},
    "hjk_times": {},
    "hjq_times": {},
    "kh_times": {},
    "yh_times": {},
    "yhx_times": {},
    "yh_guessing": {},
    "kh_active": {},
    "mj_mode": {}
})

# 审核数据
reviews_data = load_data(REVIEW_DATA_FILE, {"pending": {}, "approved": {}, "rejected": {}})

# 审核日志
audit_log_data = load_data(AUDIT_LOG_FILE, {"logs": []})

# ============ 关键修复：待处理关系请求数据 ============
pending_relations = load_data(PENDING_RELATIONS_FILE, {})

# 创建目录
DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
PENDING_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
APPROVED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


# ============ 辅助函数 ============
def get_user_id(event: MessageEvent) -> str:
    """获取用户ID字符串"""
    return f"{event.user_id}"


def get_group_id(event: GroupMessageEvent) -> str:
    """获取群ID字符串"""
    return f"{event.group_id}"


def can_active_consume(jihui: int, amount: int) -> bool:
    """主动消耗机辉检查"""
    return jihui - amount >= 0


def passive_consume(jihui: int, amount: int) -> int:
    """被动消耗机辉"""
    return jihui - amount


def check_cooldown(state_key: str, user_id: str, cooldown_seconds: int) -> Tuple[bool, int]:
    """检查冷却时间"""
    now = time.time()
    last_time = states_data.get(state_key, {}).get(user_id, 0)
    
    if now - last_time < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - last_time))
        return False, remaining
    return True, 0


def update_cooldown(state_key: str, user_id: str):
    """更新冷却时间"""
    if state_key not in states_data:
        states_data[state_key] = {}
    states_data[state_key][user_id] = time.time()
    save_data(states_data, STATE_DATA_FILE)


def generate_review_id() -> str:
    """生成审核ID"""
    import uuid
    return f"review_{uuid.uuid4().hex[:8]}"


def log_audit_action(auditor_id: str, action: str, review_id: str, details: dict):
    """记录审核日志"""
    log_entry = {
        "timestamp": time.time(),
        "auditor_id": auditor_id,
        "action": action,
        "review_id": review_id,
        "details": details
    }
    audit_log_data["logs"].append(log_entry)
    # 只保留最近1000条日志
    if len(audit_log_data["logs"]) > 1000:
        audit_log_data["logs"] = audit_log_data["logs"][-1000:]
    save_data(audit_log_data, AUDIT_LOG_FILE)


class ReviewStatus:
    """审核状态枚举"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXCELLENT = "excellent"


# ============ 指令1: 创建账号 ============
create_hui = on_command("创建辉辉", priority=5, block=True)

@create_hui.handle()
async def handle_create_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    hui_name = args.extract_plain_text().strip()
    
    if not hui_name:
        await create_hui.finish("请输入辉辉的名字，格式：/创建辉辉 [辉辉的名字]")
    
    if user_id in users_data:
        await create_hui.finish("你已经创建过辉辉账号了！")
    
    users_data[user_id] = {
        "hui_name": hui_name,
        "jihui": 3,
        "treasure": "",
        "works": []
    }
    
    save_data(users_data, USER_DATA_FILE)
    await create_hui.finish(f"恭喜！辉辉【{hui_name}】创建成功！初始获得3次机辉！")

# ============ 指令2: 查看机辉 ============
my_hui_1 = on_command("我的辉辉", priority=5, block=True)
my_hui_2 = on_command("我的机辉", priority=5, block=True)

@my_hui_1.handle()
@my_hui_2.handle()
async def handle_my_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    # 打印调试信息
    print(f"DEBUG: 我的机辉命令被调用，用户ID: {user_id}")
    print(f"DEBUG: 消息内容: {event.get_plaintext()}")
    
    if user_id not in users_data:
        await my_hui_1.finish("你还没有创建辉辉账号，请先使用 /创建辉辉 [名字] 创建账号")
    
    user_data = users_data[user_id]
    response = f"辉辉【{user_data['hui_name']}】\n当前机辉：{user_data['jihui']}次"
    
    print(f"DEBUG: 返回响应: {response}")
    await my_hui_1.finish(response)
# ============ 指令2: 辉签到 ============
sign_hui = on_command("辉签到", priority=5, block=True)

@sign_hui.handle()
async def handle_sign_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await sign_hui.finish("你还没有创建辉辉账号")
    
    # 检查是否已签到
    today = datetime.now().strftime("%Y%m%d")
    sign_times = states_data["sign_times"]
    
    if sign_times.get(user_id) == today:
        await sign_hui.finish("今天已经签到过了，明天再来吧！")
    
    # 签到成功
    users_data[user_id]["jihui"] += 1
    sign_times[user_id] = today
    
    save_data(users_data, USER_DATA_FILE)
    save_data(states_data, STATE_DATA_FILE)
    
    await sign_hui.finish(f"签到成功！获得1次机辉！当前机辉：{users_data[user_id]['jihui']}次")

# ============ 指令3: 上传辉品 ============

upload_hui = on_command("上传辉品", priority=5, block=True)

@upload_hui.handle()
async def handle_upload_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 收到上传辉品请求，用户: {user_id}")
    
    if user_id not in users_data:
        await upload_hui.finish("你还没有创建辉辉账号")
    
    # 检查冷却时间
    can_upload, remaining = check_cooldown("upload_times", user_id, 600)  # 1小时冷却
    if not can_upload:
        await upload_hui.finish(f"上传作品冷却中，请等待 {remaining} 秒后再试")
    
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await upload_hui.finish("请输入作品名称，格式：/上传辉品 [作品名称] + 图片")
    
    # 解析作品名称（取第一个空格前的内容）
    work_name = args_text.split()[0] if args_text else ""
    
    if not work_name:
        await upload_hui.finish("作品名称不能为空")
    
    # 检查是否已有同名作品
    user_works = users_data[user_id].get("works", [])
    if work_name in user_works:
        # 被动扣除一次机辉
        users_data[user_id]["jihui"] = passive_consume(users_data[user_id]["jihui"], 1)
        save_data(users_data, USER_DATA_FILE)
        await upload_hui.finish(f"已存在同名作品【{work_name}】，被动扣除1次机辉！当前机辉：{users_data[user_id]['jihui']}次")
    
    # 将作品名称存入 state，供后续使用
    state["work_name"] = work_name
    state["user_id"] = user_id
    
    # 更新冷却时间
    update_cooldown("upload_times", user_id)
    
    # 提示用户发送图片
    await upload_hui.send(f"请发送作品【{work_name}】的图片（可多张）\n发送完成后请输入'完成'或'结束'")
    
    # 设置等待图片的状态
    # 使用正则表达式匹配用户发送的图片和"完成"命令
    from nonebot.rule import Rule
    import re
    
    def wait_for_images():
        async def _checker(bot: Bot, event: MessageEvent, state: T_State) -> bool:
            msg = event.get_plaintext().strip()
            # 检查是否是"完成"或"结束"命令
            if msg in ["完成", "结束", "done", "finish"]:
                return True
            # 检查是否包含图片
            for segment in event.message:
                if segment.type == "image":
                    return False  # 有图片，继续等待
            return False
        return Rule(_checker)
    
    # 使用 got 来接收消息
    @upload_hui.got("image_or_finish", prompt="等待图片或完成命令...")
    async def got_image_or_finish(bot: Bot, event: MessageEvent, state: T_State):
        user_id = state["user_id"]
        work_name = state["work_name"]
        
        msg = event.get_plaintext().strip()
        
        # 如果用户输入"完成"或"结束"
        if msg in ["完成", "结束", "done", "finish"]:
            # 检查是否收到图片
            if "image_paths" not in state or not state["image_paths"]:
                await upload_hui.finish("未收到任何图片，上传已取消")
            
            # 处理已收到的图片
            image_paths = state["image_paths"]
            
            # 创建审核记录
            review_id = generate_review_id()
            
            review_record = {
                "review_id": review_id,
                "user_id": user_id,
                "user_name": users_data[user_id]["hui_name"],
                "work_name": work_name,
                "image_paths": image_paths,
                "upload_time": time.time(),
                "status": ReviewStatus.PENDING.value,
                "group_id": str(event.group_id) if isinstance(event, GroupMessageEvent) else "private"
            }
            
            # 保存到待审核列表
            reviews_data["pending"][review_id] = review_record
            save_data(reviews_data, REVIEW_DATA_FILE)
            
            await upload_hui.finish(
                f"✅ 作品【{work_name}】上传成功！\n"
                f"📝 审核ID：{review_id}\n"
                f"🖼️ 图片数量：{len(image_paths)}张\n"
                f"⏳ 请等待SUPERUSER审核通过后即可展示作品"
            )
            return
        
        # 如果用户发送的是图片
        if event.message and any(seg.type == "image" for seg in event.message):
            # 初始化图片路径列表
            if "image_paths" not in state:
                state["image_paths"] = []
            
            # 保存图片路径
            timestamp = int(time.time())
            image_count = len(state["image_paths"])
            
            for segment in event.message:
                if segment.type == "image":
                    url = segment.data.get("url", "")
                    if url:
                        filename = f"{user_id}_{work_name}_{timestamp}_{image_count}.jpg"
                        filepath = PENDING_IMAGES_DIR / filename
                        
                        # 保存图片信息（实际下载逻辑需要另外实现）
                        image_info = {
                            "url": url,
                            "pending_path": str(filepath),
                            "approved_path": str(APPROVED_IMAGES_DIR / filename)
                        }
                        state["image_paths"].append(image_info)
                        image_count += 1
            
            # 告知用户图片已收到，可以继续发送或输入完成
            await upload_hui.send(
                f"✅ 收到 {len([seg for seg in event.message if seg.type == 'image'])} 张图片\n"
                f"当前共 {len(state['image_paths'])} 张图片\n"
                f"可继续发送图片，或输入'完成'结束上传"
            )
            
            # 重新等待
            await got_image_or_finish.reject()
        
        # 如果用户发送的不是图片也不是完成命令
        await upload_hui.send("请发送图片或输入'完成'结束上传")
        await got_image_or_finish.reject()


    
    # 将作品添加到待审核队列（这里简化处理）
    # 在实际应用中，应该有一个审核系统
    
# 创建目录
for dir_path in [DATA_DIR, IMAGES_DIR, PENDING_IMAGES_DIR, APPROVED_IMAGES_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# 审核状态枚举
class ReviewStatus(Enum):
    PENDING = "pending"      # 待审核
    APPROVED = "approved"    # 通过
    REJECTED = "rejected"    # 不通过
    EXCELLENT = "excellent"  # 非常辉

# 加载数据
def load_data(file_path: Path, default: dict = None) -> dict:
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default or {}
    return default or {}

def save_data(data: dict, file_path: Path):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 加载所有数据
users_data = load_data(USER_DATA_FILE, {})
works_data = load_data(WORKS_DATA_FILE, {})
relations_data = load_data(RELATION_DATA_FILE, {})
reviews_data = load_data(REVIEW_DATA_FILE, {"pending": {}, "approved": {}, "rejected": {}})
states_data = load_data(STATE_DATA_FILE, {
    "sign_times": {},
    "upload_times": {},
    "hjk_times": {},
    "hjq_times": {},
    "kh_times": {},
    "yh_times": {},
    "yhx_times": {},
    "yh_guessing": {},
    "kh_active": {},
    "mj_mode": {}
})
audit_log_data = load_data(AUDIT_LOG_FILE, {"logs": []})

# 审核数据结构
# reviews_data = {
#     "pending": {
#         "review_id": {
#             "user_id": "123",
#             "user_name": "用户名",
#             "work_name": "作品名",
#             "image_paths": ["path1", "path2"],
#             "upload_time": 1234567890,
#             "status": "pending"
#         }
#     },
#     "approved": {...},
#     "rejected": {...}
# }

def get_user_id(event: MessageEvent) -> str:
    """获取用户ID字符串"""
    return f"{event.user_id}"

def get_group_id(event: GroupMessageEvent) -> str:
    """获取群ID字符串"""
    return f"{event.group_id}"

def generate_review_id() -> str:
    """生成审核ID"""
    return f"review_{int(time.time())}_{random.randint(1000, 9999)}"

def can_active_consume(jihui: int, amount: int) -> bool:
    """主动消耗机辉检查"""
    return jihui - amount >= 0

def passive_consume(jihui: int, amount: int) -> int:
    """被动消耗机辉"""
    return jihui - amount

def check_cooldown(state_key: str, user_id: str, cooldown_seconds: int) -> Tuple[bool, int]:
    """检查冷却时间"""
    now = time.time()
    last_time = states_data[state_key].get(user_id, 0)
    
    if now - last_time < cooldown_seconds:
        remaining = int(cooldown_seconds - (now - last_time))
        return False, remaining
    return True, 0

def update_cooldown(state_key: str, user_id: str):
    """更新冷却时间"""
    states_data[state_key][user_id] = time.time()
    save_data(states_data, STATE_DATA_FILE)

def save_image_from_url(image_url: str, save_path: Path) -> bool:
    """从URL下载图片并保存"""
    # 这里需要根据实际情况实现图片下载
    # 由于NoneBot适配器不同，这里简化处理
    return True

def log_audit_action(auditor_id: str, action: str, review_id: str, details: Dict = None):
    """记录审核日志"""
    log_entry = {
        "timestamp": time.time(),
        "auditor_id": auditor_id,
        "action": action,
        "review_id": review_id,
        "details": details or {}
    }
    audit_log_data["logs"].append(log_entry)
    
    # 只保留最近1000条日志
    if len(audit_log_data["logs"]) > 1000:
        audit_log_data["logs"] = audit_log_data["logs"][-1000:]
    
    save_data(audit_log_data, AUDIT_LOG_FILE)

# ============ 修改指令3: 上传辉品 ============
upload_hui = on_command("上传辉品", priority=5, block=True)

@upload_hui.handle()
async def handle_upload_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 收到上传辉品请求，用户: {user_id}")
    
    if user_id not in users_data:
        await upload_hui.finish("你还没有创建辉辉账号")
    
    # 检查冷却时间
    can_upload, remaining = check_cooldown("upload_times", user_id, 600)  # 1小时冷却
    if not can_upload:
        await upload_hui.finish(f"上传作品冷却中，请等待 {remaining} 秒后再试")
    
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await upload_hui.finish("请输入作品名称，格式：/上传辉品 [作品名称]+一张图片")
    
    # 解析作品名称（取第一个空格前的内容）
    work_name = args_text.split()[0] if args_text else ""
    
    if not work_name:
        await upload_hui.finish("作品名称不能为空")
    
    # 检查是否已有同名作品
    user_works = users_data[user_id].get("works", [])
    if work_name in user_works:
        # 被动扣除一次机辉
        users_data[user_id]["jihui"] = passive_consume(users_data[user_id]["jihui"], 1)
        save_data(users_data, USER_DATA_FILE)
        await upload_hui.finish(f"已存在同名作品【{work_name}】，被动扣除1次机辉！当前机辉：{users_data[user_id]['jihui']}次")
    
    # 检查消息中是否有图片
    message = event.message
    image_segments = [seg for seg in message if seg.type == "image"]
    
    # 严格检查：只允许一张图片
    if not image_segments:
        await upload_hui.finish("请在上传作品时包含一张图片，格式：/上传辉品 [作品名称]+一张图片")
    
    if len(image_segments) > 1:
        await upload_hui.finish("每次只能上传一张图片，请重新发送")
    
    # 获取唯一的图片段
    image_segment = image_segments[0]
    url = image_segment.data.get("url", "")
    
    if not url:
        await upload_hui.finish("图片URL获取失败，请重试")
    
    # ============ 下载图片并保存到本地 ============
    saved_image_path = await download_and_save_image(user_id, work_name, url)
    
    if not saved_image_path:
        await upload_hui.finish("图片保存失败，请重试")
    
    print(f"DEBUG: 图片已保存到: {saved_image_path}")
    
    # 创建审核记录
    review_id = generate_review_id()
    
    review_record = {
        "review_id": review_id,
        "user_id": user_id,
        "user_name": users_data[user_id]["hui_name"],
        "work_name": work_name,
        "image_paths": [
            {
                "url": url,
                "pending_path": saved_image_path,
                "approved_path": str(APPROVED_IMAGES_DIR / Path(saved_image_path).name)
            }
        ],
        "upload_time": time.time(),
        "status": ReviewStatus.PENDING.value,
        "group_id": str(event.group_id) if isinstance(event, GroupMessageEvent) else "private"
    }
    
    # 保存到待审核列表
    reviews_data["pending"][review_id] = review_record
    save_data(reviews_data, REVIEW_DATA_FILE)
    
    # 更新冷却时间
    update_cooldown("upload_times", user_id)
    
    # 保存用户数据
    save_data(users_data, USER_DATA_FILE)
    
    await upload_hui.finish(
        f"✅ 作品【{work_name}】已提交审核！\n"
        f"📝 审核ID：{review_id}\n"
        f"🖼️ 图片已保存\n"
        f"请等待SUPERUSER审核。"
    )


async def download_and_save_image(user_id: str, work_name: str, image_url: str) -> str:
    """
    下载图片并保存到本地待审核目录
    
    Args:
        user_id: 用户ID
        work_name: 作品名称
        image_url: 图片URL
    
    Returns:
        保存后的本地路径，失败返回None
    """
    import aiohttp
    import aiofiles
    
    try:
        # 确保待审核目录存在
        pending_dir = PENDING_IMAGES_DIR / str(user_id) / work_name
        pending_dir.mkdir(parents=True, exist_ok=True)
        print(f"DEBUG: 待审核目录: {pending_dir}")
        
        # 生成唯一文件名
        timestamp = int(time.time() * 1000)
        filename = f"{timestamp}.jpg"
        save_path = pending_dir / filename
        
        print(f"DEBUG: 准备下载图片，URL: {image_url}")
        print(f"DEBUG: 保存路径: {save_path}")
        
        # 下载图片
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as response:
                if response.status != 200:
                    print(f"ERROR: 图片下载失败，HTTP状态码: {response.status}")
                    return None
                
                # 读取图片数据
                image_data = await response.read()
                
                # 检查图片大小（限制10MB）
                max_size = 10 * 1024 * 1024  # 10MB
                if len(image_data) > max_size:
                    print(f"ERROR: 图片过大: {len(image_data)} bytes")
                    return None
                
                # 异步写入文件
                async with aiofiles.open(save_path, 'wb') as f:
                    await f.write(image_data)
        
        # 验证文件是否保存成功
        if save_path.exists() and save_path.stat().st_size > 0:
            print(f"SUCCESS: 图片下载并保存成功: {save_path}")
            return str(save_path)
        else:
            print(f"ERROR: 文件保存失败或为空: {save_path}")
            return None
            
    except aiohttp.ClientError as e:
        print(f"ERROR: 网络请求失败: {e}")
        return None
    except asyncio.TimeoutError:
        print(f"ERROR: 图片下载超时")
        return None
    except Exception as e:
        print(f"ERROR: 下载图片时发生错误: {e}")
        return None


# ============ 审核通过时移动图片到已审核目录 ============
def move_approved_image(user_id: str, work_name: str, review_id: str):
    """
    审核通过时将图片从待审核目录移动到已审核目录
    
    Args:
        user_id: 用户ID
        work_name: 作品名称
        review_id: 审核ID
    """
    import shutil
    
    if review_id not in reviews_data["pending"]:
        print(f"ERROR: 审核ID不存在: {review_id}")
        return False
    
    review = reviews_data["pending"][review_id]
    image_paths = review.get("image_paths", [])
    
    if not image_paths:
        print(f"ERROR: 审核记录中没有图片路径")
        return False
    
    # 获取第一张图片的待审核路径
    first_image = image_paths[0]
    pending_path = first_image.get("pending_path", "")
    
    if not pending_path or not os.path.exists(pending_path):
        print(f"ERROR: 待审核图片不存在: {pending_path}")
        return False
    
    try:
        # 确保已审核目录存在
        approved_dir = APPROVED_IMAGES_DIR / str(user_id) / work_name
        approved_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成已审核文件名
        filename = os.path.basename(pending_path)
        approved_path = approved_dir / f"approved_{filename}"
        
        # 移动文件
        shutil.move(pending_path, approved_path)
        print(f"SUCCESS: 图片已移动到已审核目录: {approved_path}")
        
        # 更新审核记录中的路径
        first_image["approved_path"] = str(approved_path)
        first_image["pending_path"] = ""  # 清空待审核路径
        
        return True
        
    except Exception as e:
        print(f"ERROR: 移动图片失败: {e}")
        return False


# ============ 审核通过（修改版） ============
review_approve = on_command("审核通过", permission=SUPERUSER, priority=5, block=True)

@review_approve.handle()
async def handle_review_approve(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    review_id = args.extract_plain_text().strip()
    
    if not review_id:
        await review_approve.finish("请输入审核ID，格式：/审核通过 [审核ID]")
    
    if review_id not in reviews_data["pending"]:
        await review_approve.finish(f"未找到待审核的ID {review_id}")
    
    review = reviews_data["pending"][review_id]
    user_id = review["user_id"]
    work_name = review["work_name"]
    
    # 移动图片到已审核目录
    if not move_approved_image(user_id, work_name, review_id):
        await review_approve.finish(f"图片移动失败，审核处理终止")
        return
    
    # 从待审核列表移除
    del reviews_data["pending"][review_id]
    
    # 更新审核状态
    review["status"] = ReviewStatus.APPROVED.value
    review["audit_time"] = time.time()
    review["auditor_id"] = str(event.user_id)
    
    # 给予奖励（4-7次随机机辉）
    reward = random.randint(4, 7)
    
    if user_id in users_data:
        users_data[user_id]["jihui"] += reward
        
        # 保存作品到正式目录
        approved_image_paths = []
        for img_info in review["image_paths"]:
            approved_path = img_info.get("approved_path", "")
            if approved_path:
                approved_image_paths.append(approved_path)
        
        # 保存作品信息
        if user_id not in works_data:
            works_data[user_id] = {}
        
        works_data[user_id][work_name] = approved_image_paths
        
        # 添加到用户作品列表
        if "works" not in users_data[user_id]:
            users_data[user_id]["works"] = []
        
        if work_name not in users_data[user_id]["works"]:
            users_data[user_id]["works"].append(work_name)
    
    # 保存到已通过列表
    reviews_data["approved"][review_id] = review
    
    # 保存所有数据
    save_data(reviews_data, REVIEW_DATA_FILE)
    save_data(users_data, USER_DATA_FILE)
    save_data(works_data, WORKS_DATA_FILE)
    
    # 记录审核日志
    log_audit_action(
        auditor_id=str(event.user_id),
        action="approve",
        review_id=review_id,
        details={
            "user_id": user_id,
            "work_name": work_name,
            "reward": reward
        }
    )
    
    # 通知用户
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_msg(
                group_id=int(review.get("group_id", 0)),
                message=f"【审核通知】\n用户 {review['user_name']} 的作品《{work_name}》已通过审核！\n获得 {reward} 次机辉奖励！"
            )
        else:
            await bot.send_private_msg(
                user_id=int(user_id),
                message=f"【审核通知】\n你的作品《{work_name}》已通过审核！\n获得 {reward} 次机辉奖励！"
            )
    except:
        pass
    
    await review_approve.finish(f"✅ 审核通过！\n用户 {review['user_name']} 的作品《{work_name}》\n奖励 {reward} 次机辉！")


# ============ 审核非常辉（修改版） ============
review_excellent = on_command("审核非常辉", permission=SUPERUSER, priority=5, block=True)

@review_excellent.handle()
async def handle_review_excellent(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    review_id = args.extract_plain_text().strip()
    
    if not review_id:
        await review_excellent.finish("请输入审核ID，格式：/审核非常辉 [审核ID]")
    
    if review_id not in reviews_data["pending"]:
        await review_excellent.finish(f"未找到待审核的ID {review_id}")
    
    review = reviews_data["pending"][review_id]
    user_id = review["user_id"]
    work_name = review["work_name"]
    
    # 移动图片到已审核目录
    if not move_approved_image(user_id, work_name, review_id):
        await review_excellent.finish(f"图片移动失败，审核处理终止")
        return
    
    # 从待审核列表移除
    del reviews_data["pending"][review_id]
    
    # 更新审核状态
    review["status"] = ReviewStatus.EXCELLENT.value
    review["audit_time"] = time.time()
    review["auditor_id"] = str(event.user_id)
    
    # 给予奖励（9-12次随机机辉）
    reward = random.randint(9, 12)
    
    if user_id in users_data:
        users_data[user_id]["jihui"] += reward
        
        # 保存作品到正式目录
        approved_image_paths = []
        for img_info in review["image_paths"]:
            approved_path = img_info.get("approved_path", "")
            if approved_path:
                approved_image_paths.append(approved_path)
        
        # 保存作品信息
        if user_id not in works_data:
            works_data[user_id] = {}
        
        works_data[user_id][work_name] = approved_image_paths
        
        # 添加到用户作品列表
        if "works" not in users_data[user_id]:
            users_data[user_id]["works"] = []
        
        if work_name not in users_data[user_id]["works"]:
            users_data[user_id]["works"].append(work_name)
    
    # 保存到已通过列表（非常辉也属于通过）
    reviews_data["approved"][review_id] = review
    
    # 保存所有数据
    save_data(reviews_data, REVIEW_DATA_FILE)
    save_data(users_data, USER_DATA_FILE)
    save_data(works_data, WORKS_DATA_FILE)
    
    # 记录审核日志
    log_audit_action(
        auditor_id=str(event.user_id),
        action="excellent",
        review_id=review_id,
        details={
            "user_id": user_id,
            "work_name": work_name,
            "reward": reward
        }
    )
    
    # 通知用户
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_msg(
                group_id=int(review.get("group_id", 0)),
                message=f"【审核通知】\n用户 {review['user_name']} 的作品《{work_name}》被评为【非常辉】！\n获得 {reward} 次机辉奖励！"
            )
        else:
            await bot.send_private_msg(
                user_id=int(user_id),
                message=f"【审核通知】\n你的作品《{work_name}》被评为【非常辉】！\n获得 {reward} 次机辉奖励！"
            )
    except:
        pass
    
    await review_excellent.finish(f"🎉 非常辉！\n用户 {review['user_name']} 的作品《{work_name}》\n奖励 {reward} 次机辉！")


# ============ 审核不通过（修改版） ============
review_reject = on_command("审核不通过", permission=SUPERUSER, priority=5, block=True)

@review_reject.handle()
async def handle_review_reject(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    review_id = args.extract_plain_text().strip()
    
    if not review_id:
        await review_reject.finish("请输入审核ID，格式：/审核不通过 [审核ID]")
    
    if review_id not in reviews_data["pending"]:
        await review_reject.finish(f"未找到待审核的ID {review_id}")
    
    review = reviews_data["pending"][review_id]
    user_id = review["user_id"]
    work_name = review["work_name"]
    
    # 清理待审核图片
    image_paths = review.get("image_paths", [])
    for img_info in image_paths:
        pending_path = img_info.get("pending_path", "")
        if pending_path and os.path.exists(pending_path):
            try:
                os.remove(pending_path)
                print(f"SUCCESS: 已删除待审核图片: {pending_path}")
            except Exception as e:
                print(f"ERROR: 删除图片失败: {e}")
    
    # 从待审核列表移除
    del reviews_data["pending"][review_id]
    
    # 更新审核状态
    review["status"] = ReviewStatus.REJECTED.value
    review["audit_time"] = time.time()
    review["auditor_id"] = str(event.user_id)
    
    # 扣除机辉
    if user_id in users_data:
        users_data[user_id]["jihui"] = passive_consume(users_data[user_id]["jihui"], 1)
    
    # 保存到已拒绝列表
    reviews_data["rejected"][review_id] = review
    
    # 保存所有数据
    save_data(reviews_data, REVIEW_DATA_FILE)
    save_data(users_data, USER_DATA_FILE)
    
    # 记录审核日志
    log_audit_action(
        auditor_id=str(event.user_id),
        action="reject",
        review_id=review_id,
        details={
            "user_id": user_id,
            "work_name": work_name,
            "penalty": 1
        }
    )
    
    # 通知用户
    try:
        if isinstance(event, GroupMessageEvent):
            await bot.send_group_msg(
                group_id=int(review.get("group_id", 0)),
                message=f"【审核通知】\n用户 {review['user_name']} 的作品《{work_name}》审核不通过。\n扣除1次机辉。"
            )
        else:
            await bot.send_private_msg(
                user_id=int(user_id),
                message=f"【审核通知】\n你的作品《{work_name}》审核不通过。\n扣除1次机辉。"
            )
    except:
        pass
    
    await review_reject.finish(f"❌ 审核不通过！\n用户 {review['user_name']} 的作品《{work_name}》\n扣除1次机辉。")

# ============ 指令4: 设置辉宝 ============
treasure_hui = on_command("辉宝", priority=5, block=True)

@treasure_hui.handle()
async def handle_treasure_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await treasure_hui.finish("你还没有创建辉辉账号")
    
    work_name = args.extract_plain_text().strip()
    if not work_name:
        await treasure_hui.finish("请输入作品名称，格式：/辉宝 [作品名称]")
    
    user_data = users_data[user_id]
    
    # 检查作品数量
    if len(user_data.get("works", [])) < 3:
        await treasure_hui.finish("至少需要有3个作品才能设置辉宝")
    
    # 检查作品是否存在
    if work_name not in user_data.get("works", []):
        await treasure_hui.finish(f"你还没有作品【{work_name}】")
    
    # 设置辉宝
    users_data[user_id]["treasure"] = work_name
    save_data(users_data, USER_DATA_FILE)
    
    await treasure_hui.finish(f"已成功将【{work_name}】设置为辉宝！")

# ============ 指令5: 辉眼识人 ============
eye_hui = on_command("辉眼识人", aliases={"辉眼"}, priority=5, block=True)  # 修正别名

@eye_hui.handle()
async def handle_eye_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 辉眼识人命令，用户: {user_id}")
    print(f"DEBUG: 事件类型: {type(event)}")
    print(f"DEBUG: 消息类型: {type(event.message)}")
    print(f"DEBUG: 消息段: {[(seg.type, seg.data) for seg in event.message]}")
    print(f"DEBUG: 参数字符串: {args.extract_plain_text()}")
    
    if user_id not in users_data:
        await eye_hui.finish("你还没有创建辉辉账号")
    
    # 解析@的用户 - 从 event.message 中解析
    target_id = None
    for segment in event.message:
        print(f"DEBUG: 检查消息段: type={segment.type}, data={segment.data}")
        if segment.type == "at":
            target_id = str(segment.data.get("qq", ""))
            print(f"DEBUG: 从消息段解析到@用户: {target_id}")
            break
    
    # 如果上面没解析到，尝试从 args 中解析
    if not target_id:
        print(f"DEBUG: 从消息段未解析到@用户，尝试从args解析")
        for segment in args:
            if segment.type == "at":
                target_id = str(segment.data.get("qq", ""))
                print(f"DEBUG: 从args解析到@用户: {target_id}")
                break
    
    # 如果还是没解析到，尝试正则解析消息字符串
    if not target_id:
        print(f"DEBUG: 尝试正则解析消息字符串")
        import re
        message_str = str(event.message)
        at_pattern = r'\[CQ:at,qq=(\d+)\]'
        matches = re.findall(at_pattern, message_str)
        if matches:
            target_id = matches[0]
            print(f"DEBUG: 从正则解析到@用户: {target_id}")
    
    # 检查是否成功解析到目标用户
    if not target_id:
        await eye_hui.finish("请@一个用户，格式：/辉眼识人 @用户")
    
    print(f"DEBUG: 最终目标用户ID: {target_id}")
    
    # 检查目标用户是否存在
    if target_id not in users_data:
        await eye_hui.finish("请@一个已创建辉辉账号的用户")
    
    if target_id == user_id:
        await eye_hui.finish("不能查看自己的作品哦！")
    
    # 检查机辉
    if not can_active_consume(users_data[user_id]["jihui"], 1):
        await eye_hui.finish("机辉不足！需要1次机辉！")
    
    # 检查目标用户是否有作品
    target_works = users_data[target_id].get("works", [])
    if not target_works:
        await eye_hui.finish("该用户还没有作品")
    
    # 消耗机辉
    users_data[user_id]["jihui"] -= 1
    
    # 随机选择一个作品
    random_work = random.choice(target_works)
    print(f"DEBUG: 随机选择的作品: {random_work}")
    
    # 获取目标用户的作品数据
    target_works_data = works_data.get(target_id, {})
    print(f"DEBUG: 目标用户的作品数据: {target_works_data}")
    
    # 检查该作品是否有图片
    if random_work not in target_works_data or not target_works_data[random_work]:
        # 如果没有图片，只发送文字
        msg = f"👀 看到了作品【{random_work}】\n⚠️ 该作品暂无图片"
    else:
        # 有图片，尝试发送图片
        image_paths = target_works_data[random_work]
        print(f"DEBUG: 作品图片路径: {image_paths}")
        
        # 随机选择一张图片
        selected_image_info = random.choice(image_paths) if image_paths else None
        
        if selected_image_info:
            # 提取图片路径
            if isinstance(selected_image_info, dict):
                image_path = selected_image_info.get("approved_path") or selected_image_info.get("url")
            else:
                image_path = selected_image_info
            
            print(f"DEBUG: 选择的图片路径: {image_path}")
            
            if image_path and os.path.exists(image_path):
                # 发送文字和图片
                from nonebot.adapters.onebot.v11 import MessageSegment
                
                # 构建消息
                try:
                    # 先发送文字
                    treasure = users_data[target_id].get("treasure", "")
                    is_treasure = random_work == treasure
                    
                    if is_treasure:
                        users_data[user_id]["jihui"] += 3
                        msg_text = f"✨ 看到了辉宝【{random_work}】！获得3次机辉！"
                    else:
                        msg_text = f"👀 看到了作品【{random_work}】"
                    
                    # 更新机辉
                    save_data(users_data, USER_DATA_FILE)
                    
                    # 发送文字消息
                    await eye_hui.send(msg_text)
                    
                    # 发送图片
                    await bot.send(event, MessageSegment.image(f"file:///{os.path.abspath(image_path)}"))
                    
                    # 发送机辉信息
                    await eye_hui.send(f"💫 当前机辉：{users_data[user_id]['jihui']}次")
                    return
                    
                except Exception as e:
                    print(f"ERROR: 发送图片失败: {e}")
                    msg = f"👀 看到了作品【{random_work}】\n⚠️ 图片加载失败: {e}"
            else:
                msg = f"👀 看到了作品【{random_work}】\n⚠️ 图片文件不存在"
        else:
            msg = f"👀 看到了作品【{random_work}】\n⚠️ 该作品暂无图片"
    
    # 如果没有发送图片，只发送文字
    # 检查是否是辉宝
    treasure = users_data[target_id].get("treasure", "")
    if random_work == treasure:
        users_data[user_id]["jihui"] += 3
        msg = f"✨ 看到了辉宝【{random_work}】！获得3次机辉！\n{msg}"
    else:
        msg = f"👀 看到了作品【{random_work}】\n{msg}"
    
    save_data(users_data, USER_DATA_FILE)
    
    await eye_hui.finish(f"{msg}\n💫 当前机辉：{users_data[user_id]['jihui']}次")

# ============ 指令5: 偷辉 ============
steal_hui = on_command("偷辉", priority=5, block=True)

@steal_hui.handle()
async def handle_steal_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 偷辉命令，用户: {user_id}")
    
    if user_id not in users_data:
        await steal_hui.finish("你还没有创建辉辉账号")
    
    # 解析@的用户
    target_id = None
    for segment in event.message:
        if segment.type == "at":
            target_id = str(segment.data.get("qq", ""))
            print(f"DEBUG: 解析到@用户: {target_id}")
            break
    
    if not target_id:
        await steal_hui.finish("请@一个用户，格式：/偷辉 @用户 [作品名称]")
    
    # 解析作品名称
    import re
    args_text = args.extract_plain_text().strip()
    print(f"DEBUG: 原始参数: {args_text}")
    
    # 移除 @用户 部分
    work_name = re.sub(r'\[CQ:at,qq=\d+\]', '', args_text).strip()
    print(f"DEBUG: 作品名称: {work_name}")
    
    if not work_name:
        await steal_hui.finish("格式：/偷辉 @用户 [作品名称]")
    
    # 检查目标用户是否存在
    if target_id not in users_data:
        await steal_hui.finish("请@一个已创建辉辉账号的用户")
    
    if target_id == user_id:
        await steal_hui.finish("不能偷看自己的作品哦！")
    
    # 检查机辉
    if not can_active_consume(users_data[user_id]["jihui"], 2):
        await steal_hui.finish("机辉不足！需要2次机辉！")
    
    # 检查目标用户是否有该作品
    if work_name not in users_data[target_id].get("works", []):
        await steal_hui.finish(f"该用户没有作品【{work_name}】")
    
    # 加载目标用户的已审核图片
    images = load_approved_images(target_id, work_name)
    print(f"DEBUG: 找到图片: {len(images)} 张")
    
    if not images:
        # 如果没有已审核图片，检查待审核
        pending_images = load_pending_images(target_id, work_name)
        if pending_images:
            await steal_hui.finish(f"作品【{work_name}】正在审核中，暂时无法偷看")
        else:
            await steal_hui.finish(f"作品【{work_name}】没有可用的图片")
    
    # 消耗机辉
    users_data[user_id]["jihui"] -= 2
    save_data(users_data, USER_DATA_FILE)
    
    # 随机选择一张图片
    import random
    img_path = random.choice(images)
    print(f"DEBUG: 选择的图片路径: {img_path}")
    
    # 获取目标用户信息
    target_name = users_data[target_id]["hui_name"]
    
    # 构建消息
    response = f"🥷 成功偷看到【{target_name}】的作品【{work_name}】！\n"
    response += f"💫 消耗2次机辉，当前机辉：{users_data[user_id]['jihui']}次\n"
    
    # 发送文字信息
    await steal_hui.send(response)
    
    # 发送图片
    try:
        # 验证文件存在
        if not os.path.exists(img_path):
            print(f"ERROR: 图片文件不存在: {img_path}")
            await bot.send(event, f"⚠️ 图片文件丢失")
            return
        
        # 验证文件大小
        file_size = os.path.getsize(img_path)
        if file_size == 0:
            print(f"ERROR: 图片文件为空: {img_path}")
            await bot.send(event, f"⚠️ 图片文件损坏")
            return
        
        # 发送本地图片
        abs_path = os.path.abspath(img_path)
        await bot.send(event, MessageSegment.image(f"file:///{abs_path}"))
        print(f"SUCCESS: 成功发送图片: {abs_path}")
        
    except Exception as e:
        print(f"ERROR: 发送图片失败 ({img_path}): {e}")
        await bot.send(event, f"⚠️ 图片加载失败: {str(e)}")
# ============ 指令6: 光辉岁月 ============
glory_hui = on_command("光辉岁月", priority=5, block=True)

@glory_hui.handle()
async def handle_glory_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await glory_hui.finish("你还没有创建辉辉账号")
    
    works = users_data[user_id].get("works", [])
    treasure = users_data[user_id].get("treasure", "")
    
    if not works:
        await glory_hui.finish("你还没有任何作品")
    
    works_list = []
    for work in works:
        if work == treasure:
            works_list.append(f"⭐ {work} (辉宝)")
        else:
            works_list.append(f"  {work}")
    
    works_text = "\n".join(works_list)
    await glory_hui.finish(f"【{users_data[user_id]['hui_name']}】的作品列表：\n{works_text}\n共计 {len(works)} 个作品")


# ============ 指令8: 辉忆 ============
memory_hui = on_command("辉忆", priority=5, block=True)

@memory_hui.handle()
async def handle_memory_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 辉忆命令，用户: {user_id}")
    
    # 检查用户是否创建了账号
    if user_id not in users_data:
        await memory_hui.finish("你还没有创建辉辉账号，请先使用 /创建辉辉 [名字] 创建账号")
    
    # 获取作品名称参数
    work_name = args.extract_plain_text().strip()
    
    # 如果没有输入作品名称，显示作品列表
    if not work_name:
        user_works = users_data[user_id].get("works", [])
        if not user_works:
            await memory_hui.finish("你还没有任何作品，快去上传吧！")
        
        work_list = "\n".join([f"  • {name}" for name in user_works])
        await memory_hui.finish(
            f"📋 你的作品列表：\n{work_list}\n\n"
            f"📌 查看具体作品请使用：/辉忆 [作品名称]"
        )
    
    # 检查作品是否存在
    if work_name not in users_data[user_id].get("works", []):
        await memory_hui.finish(f"❌ 你还没有作品【{work_name}】")
    
    # ============ 从本地存储加载图片 ============
    images = load_approved_images(user_id, work_name)
    
    # ============ 发送作品信息 ============
    user_name = users_data[user_id]["hui_name"]
    response = f"📸 辉忆【{work_name}】\n✨ 作者：{user_name}\n"
    
    if images:
        response += f"🖼️ 共 {len(images)} 张图片\n\n"
        
        # 先发送文字信息
        await memory_hui.send(response)
        
        # 逐个发送图片
        for i, img_path in enumerate(images, 1):
            try:
                # 验证文件存在
                if not os.path.exists(img_path):
                    print(f"ERROR: 图片文件不存在: {img_path}")
                    await bot.send(event, f"⚠️ 第{i}张图片文件丢失")
                    continue
                
                # 验证文件大小
                file_size = os.path.getsize(img_path)
                if file_size == 0:
                    print(f"ERROR: 图片文件为空: {img_path}")
                    await bot.send(event, f"⚠️ 第{i}张图片文件损坏")
                    continue
                
                # 发送本地图片
                # 使用绝对路径
                abs_path = os.path.abspath(img_path)
                await bot.send(event, MessageSegment.image(f"file:///{abs_path}"))
                print(f"SUCCESS: 成功发送图片 {i}/{len(images)}: {abs_path}")
                await asyncio.sleep(0.5)  # 避免发送过快
                
            except Exception as e:
                print(f"ERROR: 发送图片失败 ({img_path}): {e}")
                await bot.send(event, f"⚠️ 第{i}张图片加载失败: {str(e)}")
        
        return
    else:
        # 没有找到已审核通过的图片，检查待审核
        pending_images = load_pending_images(user_id, work_name)
        
        if pending_images:
            response += f"⏳ 该作品正在审核中，有 {len(pending_images)} 张待审核图片"
        else:
            response += "⚠️ 图片暂未加载，可能正在审核中或图片文件丢失"
        
        await memory_hui.finish(response)


def load_approved_images(user_id: str, work_name: str) -> list:
    """
    加载已审核通过的本地图片
    
    Args:
        user_id: 用户ID
        work_name: 作品名称
    
    Returns:
        已审核通过的本地图片路径列表
    """
    images = []
    
    # 方法1: 从 works_data 中获取已审核通过的图片路径
    if user_id in works_data and work_name in works_data[user_id]:
        image_records = works_data[user_id][work_name]
        print(f"DEBUG: 从works_data获取图片记录: {image_records}")
        
        for record in image_records:
            if isinstance(record, dict):
                # 优先使用 approved_path
                img_path = record.get("approved_path")
                if img_path:
                    full_path = resolve_local_path(img_path)
                    if full_path and os.path.exists(full_path):
                        images.append(full_path)
                        print(f"DEBUG: 添加已审核图片: {full_path}")
                        
                # 兼容旧格式：使用 local_path 或 path
                elif not img_path:
                    img_path = record.get("local_path") or record.get("path")
                    if img_path:
                        full_path = resolve_local_path(img_path)
                        if full_path and os.path.exists(full_path):
                            images.append(full_path)
                            print(f"DEBUG: 添加本地图片(兼容格式): {full_path}")
                            
            elif isinstance(record, str):
                # 字符串格式，直接解析路径
                full_path = resolve_local_path(record)
                if full_path and os.path.exists(full_path):
                    images.append(full_path)
                    print(f"DEBUG: 添加图片路径: {full_path}")
    
    # 方法2: 直接从已审核目录扫描
    if not images:
        approved_dir = APPROVED_IMAGES_DIR / str(user_id) / work_name
        print(f"DEBUG: 扫描已审核目录: {approved_dir}")
        images = scan_image_directory(str(approved_dir))
    
    # 方法3: 兼容旧版本 - 从全局索引查找
    if not images:
        images = find_images_by_user_and_work(user_id, work_name)
    
    print(f"DEBUG: 最终找到 {len(images)} 张已审核图片")
    return images


def load_pending_images(user_id: str, work_name: str) -> list:
    """
    加载待审核的本地图片
    
    Args:
        user_id: 用户ID
        work_name: 作品名称
    
    Returns:
        待审核的本地图片路径列表
    """
    images = []
    
    # 从待审核目录扫描
    pending_dir = PENDING_IMAGES_DIR / str(user_id) / work_name
    print(f"DEBUG: 扫描待审核目录: {pending_dir}")
    images = scan_image_directory(str(pending_dir))
    
    # 从审核记录中查找
    for review_id, review in reviews_data.get("pending", {}).items():
        if review["user_id"] == user_id and review["work_name"] == work_name:
            for img_info in review.get("image_paths", []):
                if isinstance(img_info, dict):
                    # 获取本地路径
                    local_path = img_info.get("pending_path") or img_info.get("local_path")
                    if local_path:
                        full_path = resolve_local_path(local_path)
                        if full_path and os.path.exists(full_path):
                            images.append(full_path)
                elif isinstance(img_info, str):
                    full_path = resolve_local_path(img_info)
                    if full_path and os.path.exists(full_path):
                        images.append(full_path)
    
    print(f"DEBUG: 找到 {len(images)} 张待审核图片")
    return images


def resolve_local_path(path: str) -> str:
    """
    将相对路径解析为绝对路径
    
    Args:
        path: 可能是相对路径或绝对路径
    
    Returns:
        绝对路径或None
    """
    if not path:
        return None
    
    # 如果是完整的URL，跳过
    if path.startswith("http://") or path.startswith("https://"):
        return None
    
    # 如果是绝对路径，直接返回
    if os.path.isabs(path):
        return path if os.path.exists(path) else None
    
    # 如果是相对路径，相对于 DATA_DIR 解析
    # 支持多种相对路径格式
    possible_base_dirs = [
        DATA_DIR,                          # 主数据目录
        IMAGES_DIR,                        # 图片主目录
        APPROVED_IMAGES_DIR,               # 已审核图片目录
        PENDING_IMAGES_DIR,                # 待审核图片目录
    ]
    
    for base_dir in possible_base_dirs:
        if base_dir:
            full_path = base_dir / path
            if os.path.exists(full_path):
                return str(full_path.resolve())
    
    # 最后尝试直接拼接
    full_path = DATA_DIR / path
    if os.path.exists(full_path):
        return str(full_path.resolve())
    
    return None


def scan_image_directory(directory: str) -> list:
    """
    扫描指定目录下的所有图片文件
    
    Args:
        directory: 目录路径
    
    Returns:
        图片文件路径列表
    """
    images = []
    
    if not directory:
        return images
    
    dir_path = Path(directory)
    
    if not dir_path.exists():
        print(f"DEBUG: 目录不存在: {directory}")
        return images
    
    if not dir_path.is_dir():
        print(f"DEBUG: 不是目录: {directory}")
        return images
    
    # 支持的图片格式
    supported_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
    
    try:
        for file_path in dir_path.iterdir():
            if not file_path.is_file():
                continue
            
            # 检查文件扩展名
            ext = file_path.suffix.lower()
            if ext in supported_extensions:
                images.append(str(file_path.resolve()))
                print(f"DEBUG: 发现图片: {file_path}")
            
            # 检查无扩展名的图片文件
            elif ext == "" and file_path.stat().st_size > 0:
                # 简单检查文件头判断是否是图片
                try:
                    with open(file_path, 'rb') as f:
                        header = f.read(10)
                        # JPEG: FF D8 FF
                        # PNG: 89 50 4E 47
                        # GIF: 47 49 46 38
                        if header.startswith(b'\xff\xd8\xff') or \
                           header.startswith(b'\x89PNG') or \
                           header.startswith(b'GIF8'):
                            images.append(str(file_path.resolve()))
                            print(f"DEBUG: 发现无扩展名图片: {file_path}")
                except Exception as e:
                    print(f"DEBUG: 检查文件头失败: {e}")
                    
    except PermissionError as e:
        print(f"ERROR: 没有权限访问目录 {directory}: {e}")
    except Exception as e:
        print(f"ERROR: 扫描目录失败 {directory}: {e}")
    
    return images


def find_images_by_user_and_work(user_id: str, work_name: str) -> list:
    """
    在全局图片索引中按用户和作品查找图片（兼容旧版本）
    
    Args:
        user_id: 用户ID
        work_name: 作品名称
    
    Returns:
        图片文件路径列表
    """
    images = []
    
    # 检查全局图片索引文件
    image_index_file = DATA_DIR / "image_index.json"
    
    if not image_index_file.exists():
        return images
    
    try:
        import json
        with open(image_index_file, 'r', encoding='utf-8') as f:
            image_index = json.load(f)
        
        user_key = str(user_id)
        
        # 查找用户的图片索引
        if user_key in image_index:
            user_images = image_index[user_key]
            
            # 精确匹配作品名称
            if work_name in user_images:
                image_paths = user_images[work_name]
                for img_path in image_paths:
                    full_path = resolve_local_path(img_path)
                    if full_path:
                        images.append(full_path)
            
            # 模糊匹配（忽略大小写）
            for stored_work_name, paths in user_images.items():
                if stored_work_name.lower() == work_name.lower():
                    for img_path in paths:
                        full_path = resolve_local_path(img_path)
                        if full_path and full_path not in images:
                            images.append(full_path)
                            
    except Exception as e:
        print(f"ERROR: 读取全局索引失败: {e}")
    
    return images


# ============ 调试命令：查看图片存储状态 ============
debug_images = on_command("调试图片", priority=10, block=True)

@debug_images.handle()
async def handle_debug_images(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await debug_images.finish("你还没有创建辉辉账号")
    
    work_name = args.extract_plain_text().strip()
    
    result = f"🔍 图片存储调试信息\n"
    result += f"用户ID: {user_id}\n"
    result += f"作品名: {work_name or '全部'}\n\n"
    
    # 检查各个图片存储目录
    directories_to_check = [
        ("已审核图片目录", APPROVED_IMAGES_DIR / str(user_id)),
        ("已审核作品目录", APPROVED_IMAGES_DIR / str(user_id) / work_name if work_name else None),
        ("待审核图片目录", PENDING_IMAGES_DIR / str(user_id)),
        ("待审核作品目录", PENDING_IMAGES_DIR / str(user_id) / work_name if work_name else None),
    ]
    
    for dir_name, dir_path in directories_to_check:
        if dir_path is None:
            continue
        
        if dir_path.exists():
            files = list(dir_path.iterdir())
            image_files = [f for f in files if f.is_file() and f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.webp'}]
            result += f"📁 {dir_name}: {dir_path}\n"
            result += f"   📄 总文件数: {len(files)}\n"
            result += f"   🖼️ 图片数: {len(image_files)}\n"
            if image_files:
                result += f"   📝 图片列表: {', '.join([f.name for f in image_files[:5]])}{'...' if len(image_files) > 5 else ''}\n"
        else:
            result += f"❌ {dir_name}: {dir_path} (不存在)\n"
    
    # 检查 works_data 中的数据
    result += f"\n📊 works_data 中的作品信息:\n"
    if user_id in works_data:
        user_works = works_data[user_id]
        for w_name, images in user_works.items():
            if work_name and w_name != work_name:
                continue
            result += f"   • {w_name}: {len(images) if isinstance(images, list) else 'N/A'} 张图片\n"
    else:
        result += f"   用户无作品数据\n"
    
    await debug_images.finish(result)


# ============ 辅助函数：确保图片目录存在 ============
def ensure_user_image_directory(user_id: str, work_name: str = None, approved: bool = True) -> Path:
    """
    确保用户图片目录存在
    
    Args:
        user_id: 用户ID
        work_name: 作品名称（可选）
        approved: True=已审核目录, False=待审核目录
    
    Returns:
        目录路径
    """
    if approved:
        base_dir = APPROVED_IMAGES_DIR
    else:
        base_dir = PENDING_IMAGES_DIR
    
    if work_name:
        dir_path = base_dir / str(user_id) / work_name
    else:
        dir_path = base_dir / str(user_id)
    
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


# ============ 兼容旧版本：迁移图片到新目录结构 ============
def migrate_old_images(user_id: str, work_name: str):
    """
    将旧格式的图片路径迁移到新的目录结构
    
    Args:
        user_id: 用户ID
        work_name: 作品名称
    """
    if user_id not in works_data:
        return
    
    if work_name not in works_data[user_id]:
        return
    
    image_records = works_data[user_id][work_name]
    migrated = False
    
    for record in image_records:
        if isinstance(record, dict):
            old_path = record.get("approved_path") or record.get("local_path") or record.get("path")
            if old_path and os.path.exists(old_path):
                # 复制文件到新的目录结构
                new_dir = ensure_user_image_directory(user_id, work_name, approved=True)
                filename = os.path.basename(old_path)
                new_path = new_dir / filename
                
                try:
                    import shutil
                    shutil.copy2(old_path, new_path)
                    record["approved_path"] = str(new_path)
                    migrated = True
                    print(f"SUCCESS: 迁移图片: {old_path} -> {new_path}")
                except Exception as e:
                    print(f"ERROR: 迁移图片失败: {e}")
    
    if migrated:
        save_data(works_data, WORKS_DATA_FILE)
        print(f"SUCCESS: 作品 {work_name} 图片迁移完成")

        
# ============ 指令7: 辉心一笑 ============
heart_hui = on_command("辉心一笑", aliases={"辉笑"}, priority=5, block=True)

@heart_hui.handle()
async def handle_heart_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 辉心一笑命令，用户: {user_id}")
    print(f"DEBUG: 消息段: {[(seg.type, seg.data) for seg in event.message]}")
    
    if user_id not in users_data:
        await heart_hui.finish("你还没有创建辉辉账号")
    
    # 检查冷却时间
    can_use, remaining = check_cooldown("yhx_times", user_id, 86400)  # 24小时冷却
    if not can_use:
        await heart_hui.finish(f"辉心一笑冷却中，请等待 {remaining} 秒后再试")
    
    # 检查是否已有亲密关系
    if user_id in relations_data:
        partner_id = relations_data[user_id]
        partner_name = users_data[partner_id]["hui_name"]
        await heart_hui.finish(f"你已经和【{partner_name}】绑定亲密关系了")
    
    # 解析@的用户 - 从 event.message 中解析
    target_id = None
    for segment in event.message:
        if segment.type == "at":
            target_id = str(segment.data.get("qq", ""))
            print(f"DEBUG: 解析到@用户: {target_id}")
            break
    
    if not target_id:
        await heart_hui.finish("请@一个用户，格式：/辉心一笑 @用户")
    
    if target_id not in users_data:
        await heart_hui.finish("请@一个已创建辉辉账号的用户")
    
    if target_id == user_id:
        await heart_hui.finish("不能和自己绑定亲密关系哦！")
    
    # 检查目标用户是否已有亲密关系
    if target_id in relations_data:
        partner_id = relations_data[target_id]
        partner_name = users_data[partner_id]["hui_name"]
        await heart_hui.finish(f"该用户已经和【{partner_name}】绑定亲密关系了")
    
    # 检查是否已经有待处理的请求
    pending_request_key = f"{user_id}_{target_id}"
    reverse_request_key = f"{target_id}_{user_id}"
    
    # 关键修复：确保 pending_relations 已定义
    if 'pending_relations' not in globals():
        global pending_relations
        if PENDING_RELATIONS_FILE.exists():
            with open(PENDING_RELATIONS_FILE, 'r', encoding='utf-8') as f:
                pending_relations = json.load(f)
        else:
            pending_relations = {}
    
    if pending_request_key in pending_relations or reverse_request_key in pending_relations:
        await heart_hui.finish("你们之间已经有待处理的亲密关系请求了")
    
    # 保存待处理的请求
    pending_relations[pending_request_key] = {
        "from_user": user_id,
        "to_user": target_id,
        "from_name": users_data[user_id]["hui_name"],
        "to_name": users_data[target_id]["hui_name"],
        "create_time": time.time()
    }
    save_data(pending_relations, PENDING_RELATIONS_FILE)
    
    user_name = users_data[user_id]["hui_name"]
    target_name = users_data[target_id]["hui_name"]
    
    # 发送绑定请求给目标用户（私聊）
    try:
        await bot.send_private_msg(
            user_id=int(target_id),
            message=f"💕 【{user_name}】向你发送了亲密关系绑定请求！\n"
                    f"发送 /同意 或 /不同意 来回应"
        )
        await heart_hui.finish(f"已向【{target_name}】发送亲密关系绑定请求！\n请等待对方回应")
    except Exception as e:
        print(f"ERROR: 发送私聊消息失败: {e}")
        if isinstance(event, GroupMessageEvent):
            await heart_hui.finish(
                f"已向【{target_name}】发送亲密关系绑定请求！\n"
                f"请【{target_name}】私聊机器人发送 /同意 或 /不同意"
            )
        else:
            await heart_hui.finish(f"发送请求失败，请让对方主动联系机器人")


# ============ 同意/不同意响应 ============
# 需要记录是谁发起的请求，所以使用不同的命令处理
agree_relation = on_command("同意", priority=5, block=True)
disagree_relation = on_command("不同意", priority=5, block=True)

# 存储待处理请求的字典（需要在文件顶部定义）
# pending_relations = {}

@agree_relation.handle()
async def handle_agree_relation(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await agree_relation.finish("你还没有创建辉辉账号")
    
    # 查找待处理的请求
    found_request = None
    found_key = None
    
    for key, request in pending_relations.items():
        if request["to_user"] == user_id:
            found_request = request
            found_key = key
            break
    
    if not found_request:
        await agree_relation.finish("你没有待处理的亲密关系请求")
    
    from_user = found_request["from_user"]
    to_user = found_request["to_user"]
    from_name = found_request["from_name"]
    to_name = found_request["to_name"]
    
    # 检查发起方是否还在线/存在
    if from_user not in users_data:
        del pending_relations[found_key]
        save_data(pending_relations, RELATION_DATA_FILE)
        await agree_relation.finish("对方账号已不存在")
    
    # 建立双向亲密关系
    relations_data[from_user] = to_user
    relations_data[to_user] = from_user
    
    # 删除待处理请求
    del pending_relations[found_key]
    save_data(pending_relations, RELATION_DATA_FILE)
    save_data(relations_data, RELATION_DATA_FILE)
    
    # 通知双方
    try:
        await bot.send_private_msg(
            user_id=int(from_user),
            message=f"💕 好消息！【{to_name}】同意了你的亲密关系绑定请求！\n你们现在是亲密伙伴了！"
        )
    except Exception as e:
        print(f"ERROR: 通知发起方失败: {e}")
    
    await agree_relation.finish(
        f"💕 恭喜！你已和【{from_name}】绑定亲密关系！\n你们现在是亲密伙伴了！"
    )


@disagree_relation.handle()
async def handle_disagree_relation(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await disagree_relation.finish("你还没有创建辉辉账号")
    
    # 查找待处理的请求
    found_request = None
    found_key = None
    
    for key, request in pending_relations.items():
        if request["to_user"] == user_id:
            found_request = request
            found_key = key
            break
    
    if not found_request:
        await disagree_relation.finish("你没有待处理的亲密关系请求")
    
    from_user = found_request["from_user"]
    from_name = found_request["from_name"]
    to_name = found_request["to_name"]
    
    # 删除待处理请求
    del pending_relations[found_key]
    save_data(pending_relations, RELATION_DATA_FILE)
    
    # 通知发起方
    try:
        await bot.send_private_msg(
            user_id=int(from_user),
            message=f"💔 【{to_name}】拒绝了你的亲密关系绑定请求..."
        )
    except Exception as e:
        print(f"ERROR: 通知发起方失败: {e}")
    
    await disagree_relation.finish(f"已拒绝【{from_name}】的亲密关系绑定请求")


# ============ 查看亲密关系状态 ============
relation_status = on_command("亲密关系", priority=5, block=True)

@relation_status.handle()
async def handle_relation_status(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await relation_status.finish("你还没有创建辉辉账号")
    
    if user_id in relations_data:
        partner_id = relations_data[user_id]
        partner_name = users_data[partner_id]["hui_name"]
        await relation_status.finish(f"💕 你和【{partner_name}】是亲密伙伴！")
    else:
        await relation_status.finish("你目前没有亲密关系\n使用 /辉心一笑 @用户 来发起绑定请求")


# ============ 解除亲密关系 ============
break_relation = on_command("心辉意冷", aliases={"辉心"}, priority=5, block=True)

@break_relation.handle()
async def handle_break_relation(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await break_relation.finish("你还没有创建辉辉账号")
    
    if user_id not in relations_data:
        await break_relation.finish("你目前没有亲密关系")
    
    partner_id = relations_data[user_id]
    partner_name = users_data[partner_id]["hui_name"]
    user_name = users_data[user_id]["hui_name"]
    
    # 双向解除
    del relations_data[user_id]
    if partner_id in relations_data:
        del relations_data[partner_id]
    
    save_data(relations_data, RELATION_DATA_FILE)
    
    # 通知对方
    try:
        await bot.send_private_msg(
            user_id=int(partner_id),
            message=f"💔 【{user_name}】解除了你们的亲密关系"
        )
    except Exception as e:
        print(f"ERROR: 通知对方失败: {e}")
    
    await break_relation.finish(f"已解除与【{partner_name}】的亲密关系")

# ============ 指令9: 约辉 ============
date_hui = on_command("约辉", priority=5, block=True)

@date_hui.handle()
async def handle_date_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await date_hui.finish("你还没有创建辉辉账号")
    
    # 检查是否有亲密关系
    if user_id not in relations_data:
        await date_hui.finish("你还没有绑定亲密关系")
    
    partner_id = relations_data[user_id]
    
    # 生成关系键（排序后的ID对）
    relation_key = "_".join(sorted([user_id, partner_id]))
    
    # 检查冷却时间（每对关系12小时）
    can_date, remaining = check_cooldown("yh_times", relation_key, 43200)  # 12小时
    if not can_date:
        await date_hui.finish(f"约辉冷却中，请等待 {remaining} 秒后再试")
    
    # 双方获得机辉
    users_data[user_id]["jihui"] += 5
    users_data[partner_id]["jihui"] += 5
    
    # 更新冷却时间
    update_cooldown("yh_times", relation_key)
    
    save_data(users_data, USER_DATA_FILE)
    
    user_name = users_data[user_id]["hui_name"]
    partner_name = users_data[partner_id]["hui_name"]
    
    await date_hui.finish(f"【{user_name}】和【{partner_name}】约会成功！\n双方各获得5次机辉！")

# ============ 指令10: 幽辉 ============
ghost_hui = on_command("幽辉", priority=5, block=True)

@ghost_hui.handle()
async def handle_ghost_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await ghost_hui.finish("你还没有创建辉辉账号")
    
    # 检查是否有亲密关系
    if user_id not in relations_data:
        await ghost_hui.finish("你还没有绑定亲密关系")
    
    partner_id = relations_data[user_id]
    
    # 生成关系键
    relation_key = "_".join(sorted([user_id, partner_id]))
    
    # 检查冷却时间（24小时）
    can_ghost, remaining = check_cooldown("yh_guessing", relation_key, 86400)
    if not can_ghost:
        await ghost_hui.finish(f"幽辉冷却中，请等待 {remaining} 秒后再试")
    
    # 检查目标用户是否有作品
    partner_works = users_data[partner_id].get("works", [])
    if not partner_works:
        await ghost_hui.finish("你的亲密伙伴还没有作品")
    
    # 随机选择一个作品
    random_work = random.choice(partner_works)
    
    # 记录猜谜状态
    states_data["yh_guessing"][relation_key] = {
        "work_name": random_work,
        "guesser": user_id,
        "partner": partner_id,
        "start_time": time.time()
    }
    
    # 更新冷却时间
    update_cooldown("yh_guessing", relation_key)
    
    save_data(states_data, STATE_DATA_FILE)
    
    await ghost_hui.finish(f"幽辉开始！猜猜看这是【{users_data[partner_id]['hui_name']}】的哪个作品？\n（请发送作品名称）")

# 猜作品响应
@on_command("", rule=lambda: True, priority=10, block=False).handle()
async def handle_guess_work(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    guess_text = event.get_plaintext().strip()
    
    # 检查是否在猜谜状态中
    for relation_key, guess_data in states_data["yh_guessing"].items():
        if user_id in [guess_data["guesser"], guess_data["partner"]]:
            correct_work = guess_data["work_name"]
            guesser_id = guess_data["guesser"]
            partner_id = guess_data["partner"]
            
            if guess_text == correct_work:
                # 猜对了
                users_data[guesser_id]["jihui"] += 8
                users_data[partner_id]["jihui"] += 8
                
                save_data(users_data, USER_DATA_FILE)
                
                # 清除猜谜状态
                del states_data["yh_guessing"][relation_key]
                save_data(states_data, STATE_DATA_FILE)
                
                await bot.send(event, f"猜对了！【{correct_work}】\n双方各获得8次机辉！")
            else:
                # 猜错了
                users_data[guesser_id]["jihui"] = passive_consume(users_data[guesser_id]["jihui"], 3)
                users_data[partner_id]["jihui"] = passive_consume(users_data[partner_id]["jihui"], 3)
                
                save_data(users_data, USER_DATA_FILE)
                
                # 清除猜谜状态
                del states_data["yh_guessing"][relation_key]
                save_data(states_data, STATE_DATA_FILE)
                
                await bot.send(event, f"猜错了！正确答案是【{correct_work}】\n双方各扣除3次机辉！")

# ============ 指令11: 打辉机 ============
machine_hui = on_command(("打辉机"), priority=5, block=True)

@machine_hui.handle()
async def handle_machine_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await machine_hui.finish("你还没有创建辉辉账号")
    
    # 检查冷却时间（10分钟）
    can_use, remaining = check_cooldown("hjk_times", user_id, 600)
    if not can_use:
        await machine_hui.finish(f"打辉机冷却中，请等待 {remaining} 秒后再试")
    
    # 检查机辉
    if not can_active_consume(users_data[user_id]["jihui"], 1):
        await machine_hui.finish("机辉不足！需要1次机辉！")
    
    # 消耗机辉
    users_data[user_id]["jihui"] -= 1
    
    # 随机结果
    rand = random.random()
    if rand < 0.4:  # 40% 获得2次
        reward = 2
        users_data[user_id]["jihui"] += reward
        result_msg = f"获得{reward}次机辉！"
    elif rand < 0.6:  # 20% 获得1次
        reward = 1
        users_data[user_id]["jihui"] += reward
        result_msg = f"获得{reward}次机辉！"
    else:  # 40% 获得0次
        reward = 0
        result_msg = "获得0次机辉！"
    
    # 更新冷却时间
    update_cooldown("hjk_times", user_id)
    
    save_data(users_data, USER_DATA_FILE)
    
    await machine_hui.finish(f"打辉机结果：{result_msg}\n当前机辉：{users_data[user_id]['jihui']}次")

# ============ 指令12: 辉舞拳头 ============
punch_hui = on_command("辉舞拳头", aliases={"辉拳"}, priority=5, block=True)

@punch_hui.handle()
async def handle_punch_hui(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 辉拳命令，用户: {user_id}")
    print(f"DEBUG: 事件类型: {type(event)}")
    print(f"DEBUG: 消息类型: {type(event.message)}")
    
    # 打印消息中的所有段
    for i, segment in enumerate(event.message):
        print(f"DEBUG: 消息段[{i}]: type={segment.type}, data={segment.data}")
    
    if user_id not in users_data:
        await punch_hui.finish("你还没有创建辉辉账号")
    
    # 检查冷却时间（10分钟）
    can_use, remaining = check_cooldown("hjq_times", user_id, 600)
    if not can_use:
        await punch_hui.finish(f"辉拳冷却中，请等待 {remaining} 秒后再试")
    
    # 解析@的用户
    target_id = None
    
    # 方法1: 从 event.message 的消息段中直接获取 at 类型（最可靠）
    for segment in event.message:
        print(f"DEBUG: 检查消息段: {segment.type}")
        if segment.type == "at":
            target_id = str(segment.data.get("qq", ""))
            print(f"DEBUG: 从消息段解析到@用户: {target_id}")
            break
    
    # 方法2: 如果方法1没获取到，手动解析消息字符串
    if not target_id:
        # 将整个消息转换为字符串来解析
        message_str = str(event.message)
        print(f"DEBUG: 消息字符串: {message_str}")
        
        # 解析 [CQ:at,qq=123456] 格式
        import re
        at_pattern = r'\[CQ:at,qq=(\d+)\]'
        matches = re.findall(at_pattern, message_str)
        if matches:
            target_id = matches[0]
            print(f"DEBUG: 从字符串解析到@用户: {target_id}")
    
    # 检查是否成功解析到目标用户
    if not target_id:
        await punch_hui.finish("请@一个用户，格式：/辉拳 @用户")
    
    print(f"DEBUG: 目标用户ID: {target_id}")
    
    # 检查目标用户是否存在
    if target_id not in users_data:
        await punch_hui.finish("请@一个已创建辉辉账号的用户")
    
    if target_id == user_id:
        await punch_hui.finish("不能对自己使用辉拳哦！")
    
    # 检查机辉
    if not can_active_consume(users_data[user_id]["jihui"], 3):
        await punch_hui.finish("机辉不足！需要3次机辉！")
    
    # 消耗机辉
    users_data[user_id]["jihui"] -= 3
    users_data[target_id]["jihui"] = passive_consume(users_data[target_id]["jihui"], 2)
    
    # 随机结果
    rand = random.random()
    if rand < 0.7:  # 70% 用户获得
        users_data[user_id]["jihui"] += 5
        winner = users_data[user_id]["hui_name"]
    else:  # 30% 目标获得
        users_data[target_id]["jihui"] += 5
        winner = users_data[target_id]["hui_name"]
    
    # 更新冷却时间
    update_cooldown("hjq_times", user_id)
    
    save_data(users_data, USER_DATA_FILE)
    
    user_name = users_data[user_id]["hui_name"]
    target_name = users_data[target_id]["hui_name"]
    
    await punch_hui.finish(
        f"👊 【{user_name}】对【{target_name}】使用了辉拳！\n"
        f"🎉 胜利者：{winner} 获得5次机辉！"
    )
# ============ 指令13: 开辉 ============
open_hui = on_command("开辉", priority=5, block=True)

@open_hui.handle()
async def handle_open_hui(bot: Bot, event: GroupMessageEvent):
    user_id = get_user_id(event)
    group_id = get_group_id(event)
    
    print(f"DEBUG: 开辉命令，用户: {user_id}, 群: {group_id}")
    
    if user_id not in users_data:
        await open_hui.finish("你还没有创建辉辉账号")
    
    # 检查机辉
    if not can_active_consume(users_data[user_id]["jihui"], 12):
        await open_hui.finish("机辉不足！需要12次机辉！")
    
    # 检查群冷却时间（24小时）
    can_open, remaining = check_cooldown("kh_times", group_id, 86400)
    if not can_open:
        await open_hui.finish(f"本群开辉冷却中，请等待 {remaining} 秒后再试")
    
    # 消耗机辉
    users_data[user_id]["jihui"] -= 12
    
    # 记录开辉状态 - 使用列表而不是集合
    states_data["kh_active"][group_id] = {
        "starter": user_id,
        "start_time": time.time(),
        "responded": [],  # 改为列表
        "all_members": []  # 改为列表
    }
    
    # 更新冷却时间
    update_cooldown("kh_times", group_id)
    
    # 保存数据
    save_data(users_data, USER_DATA_FILE)
    save_data(states_data, STATE_DATA_FILE)
    
    print(f"DEBUG: 开辉成功，用户 {user_id} 机辉: {users_data[user_id]['jihui']}")
    
    # 发送@全体消息
    message = Message()
    message.append(MessageSegment.at("all"))
    message.append("\n开辉了！请在10分钟内发送'怎么辉事？'，否则扣除1次机辉！")
    
    await open_hui.finish(message)

# 响应"怎么辉事？"
response_hui = on_command("怎么辉事？", priority=5, block=True)

@response_hui.handle()
async def handle_response_hui(bot: Bot, event: GroupMessageEvent):
    user_id = get_user_id(event)
    group_id = get_group_id(event)
    
    print(f"DEBUG: 收到响应，用户: {user_id}, 群: {group_id}")
    
    if group_id not in states_data["kh_active"]:
        print(f"DEBUG: 群 {group_id} 没有开辉活动")
        return
    
    # 记录已响应
    kh_data = states_data["kh_active"][group_id]
    if user_id not in kh_data["responded"]:
        kh_data["responded"].append(user_id)  # 使用append
        save_data(states_data, STATE_DATA_FILE)
        print(f"DEBUG: 用户 {user_id} 已响应开辉")
    else:
        print(f"DEBUG: 用户 {user_id} 已经响应过了")

# 4. 修改超时检查函数中的集合使用
async def check_kh_timeout():
    while True:
        await asyncio.sleep(60)  # 每分钟检查一次
        
        current_time = time.time()
        to_remove = []
        
        for group_id, kh_data in states_data["kh_active"].items():
            start_time = kh_data["start_time"]
            
            if current_time - start_time > 600:  # 10分钟
                # 开辉结束，处理未响应成员
                starter_id = kh_data["starter"]
                responded = kh_data["responded"]  # 现在是列表
                
                # 这里应该获取实际群成员列表
                # 简化处理：扣除所有未响应的已创建账号用户
                for uid, user_data in users_data.items():
                    if uid != starter_id and uid not in responded:
                        if uid in users_data:  # 确保用户已创建账号
                            users_data[uid]["jihui"] = passive_consume(users_data[uid]["jihui"], 1)
                
                save_data(users_data, USER_DATA_FILE)
                to_remove.append(group_id)
        
        # 清理已结束的开辉
        for group_id in to_remove:
            del states_data["kh_active"][group_id]
        
        if to_remove:
            save_data(states_data, STATE_DATA_FILE)

# ============ 指令14: 辉家 ============
home_hui = on_command("辉家", priority=5, block=True)

@home_hui.handle()
async def handle_home_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await home_hui.finish("你还没有创建辉辉账号")
    
    # 检查机辉
    if not can_active_consume(users_data[user_id]["jihui"], 8):
        await home_hui.finish("机辉不足！需要8次机辉！")
    
    # 消耗机辉
    users_data[user_id]["jihui"] -= 8
    
    # 进入免打扰模式
    states_data["mj_mode"][user_id] = True
    
    save_data(users_data, USER_DATA_FILE)
    save_data(states_data, STATE_DATA_FILE)
    
    await home_hui.finish(f"已进入免打扰模式！获得清净！\n当前机辉：{users_data[user_id]['jihui']}次")

# ============ 指令14: 起辉 ============
wake_hui = on_command("起辉", priority=5, block=True)

@wake_hui.handle()
async def handle_wake_hui(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await wake_hui.finish("你还没有创建辉辉账号")
    
    # 检查是否在免打扰模式
    if not states_data["mj_mode"].get(user_id, False):
        await wake_hui.finish("你不在免打扰模式中")
    
    # 退出免打扰模式
    del states_data["mj_mode"][user_id]
    
    # 获得机辉
    users_data[user_id]["jihui"] += 1
    
    save_data(users_data, USER_DATA_FILE)
    save_data(states_data, STATE_DATA_FILE)
    
    await wake_hui.finish(f"已退出免打扰模式！获得1次机辉！\n当前机辉：{users_data[user_id]['jihui']}次")

# ============ 指令15: 机辉排行榜 ============
rank_hui = on_command("机辉排行榜", priority=5, block=True)

@rank_hui.handle()
async def handle_rank_hui(bot: Bot, event: MessageEvent):
    if not users_data:
        await rank_hui.finish("还没有用户创建辉辉账号")
    
    # 按机辉排序
    sorted_users = sorted(
        users_data.items(),
        key=lambda x: x[1]["jihui"],
        reverse=True
    )
    
    rank_text = "🏆 机辉排行榜 🏆\n"
    for i, (uid, user_data) in enumerate(sorted_users[:20], 1):  # 显示前20名
        rank_text += f"{i}. {user_data['hui_name']} - {user_data['jihui']}次机辉\n"
    
    await rank_hui.finish(rank_text)

# ============ 免打扰模式检查 ============
async def check_mj_mode(user_id: str) -> bool:
    """检查用户是否在免打扰模式"""
    return states_data["mj_mode"].get(user_id, False)

# 在所有指令前添加免打扰检查（需要修改每个命令的处理函数）
# 这里简化处理，在实际使用中应该在每个命令开始时检查

# ============ 定时任务启动 ============
driver = get_driver()

@driver.on_startup
async def startup():
    # 启动开辉超时检查
    asyncio.create_task(check_kh_timeout())

# ============ 指令9: 辉除作品 ============
remove_work = on_command("辉除作品", priority=5, block=True)

@remove_work.handle()
async def handle_remove_work(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 辉除作品命令，用户: {user_id}")
    
    # 检查用户是否创建了账号
    if user_id not in users_data:
        await remove_work.finish("你还没有创建辉辉账号，请先使用 /创建辉辉 [名字] 创建账号")
    
    # 获取作品名称参数
    work_name = args.extract_plain_text().strip()
    
    if not work_name:
        await remove_work.finish("请输入要删除的作品名称，格式：/辉除作品 [作品名称]")
    
    # 检查作品是否存在
    user_works = users_data[user_id].get("works", [])
    if work_name not in user_works:
        await remove_work.finish(f"你还没有作品【{work_name}】")
    
    # 检查作品是否正在审核中
    is_pending = False
    pending_review_id = None
    for review_id, review in reviews_data.get("pending", {}).items():
        if review["user_id"] == user_id and review["work_name"] == work_name:
            is_pending = True
            pending_review_id = review_id
            break
    
    # 检查作品是否已通过审核
    is_approved = False
    if user_id in works_data and work_name in works_data[user_id]:
        is_approved = True
    
    # 计算需要扣除的机辉次数
    # 如果作品已通过审核，扣除7次；如果还在审核中，扣除7次
    penalty = 7
    
    # 检查机辉是否足够
    current_jihui = users_data[user_id].get("jihui", 0)
    if current_jihui < penalty:
        await remove_work.finish(
            f"机辉不足！\n"
            f"删除作品需要扣除 {penalty} 次机辉\n"
            f"你当前只有 {current_jihui} 次机辉"
        )
    
    # 执行删除操作
    removed_images = []
    
    # 1. 如果作品在待审核中，删除审核记录并清理图片
    if is_pending and pending_review_id:
        review = reviews_data["pending"][pending_review_id]
        
        # 清理待审核图片
        for img_info in review.get("image_paths", []):
            pending_path = img_info.get("pending_path", "")
            if pending_path and os.path.exists(pending_path):
                try:
                    os.remove(pending_path)
                    removed_images.append(pending_path)
                    print(f"SUCCESS: 已删除待审核图片: {pending_path}")
                except Exception as e:
                    print(f"ERROR: 删除待审核图片失败: {e}")
        
        # 从待审核列表移除
        del reviews_data["pending"][pending_review_id]
        print(f"SUCCESS: 已删除待审核记录: {pending_review_id}")
    
    # 2. 如果作品已通过审核，删除已审核图片
    if is_approved:
        approved_image_paths = works_data[user_id].get(work_name, [])
        
        for img_path in approved_image_paths:
            if isinstance(img_path, str) and os.path.exists(img_path):
                try:
                    os.remove(img_path)
                    removed_images.append(img_path)
                    print(f"SUCCESS: 已删除已审核图片: {img_path}")
                except Exception as e:
                    print(f"ERROR: 删除已审核图片失败: {e}")
            elif isinstance(img_path, dict):
                approved_path = img_path.get("approved_path", "")
                if approved_path and os.path.exists(approved_path):
                    try:
                        os.remove(approved_path)
                        removed_images.append(approved_path)
                        print(f"SUCCESS: 已删除已审核图片: {approved_path}")
                    except Exception as e:
                        print(f"ERROR: 删除已审核图片失败: {e}")
        
        # 从 works_data 中删除作品
        del works_data[user_id][work_name]
        print(f"SUCCESS: 已从 works_data 删除作品: {work_name}")
    
    # 3. 从用户作品列表中移除
    if work_name in users_data[user_id].get("works", []):
        users_data[user_id]["works"].remove(work_name)
        print(f"SUCCESS: 已从用户作品列表删除: {work_name}")
    
    # 4. 扣除机辉
    users_data[user_id]["jihui"] -= penalty
    print(f"SUCCESS: 已扣除 {penalty} 次机辉，剩余: {users_data[user_id]['jihui']}")
    
    # 5. 保存所有数据
    save_data(users_data, USER_DATA_FILE)
    save_data(works_data, WORKS_DATA_FILE)
    save_data(reviews_data, REVIEW_DATA_FILE)
    
    # 6. 记录操作日志
    log_audit_action(
        auditor_id=user_id,
        action="remove_work",
        review_id=pending_review_id if pending_review_id else "direct_remove",
        details={
            "user_id": user_id,
            "work_name": work_name,
            "penalty": penalty,
            "removed_images_count": len(removed_images),
            "was_pending": is_pending,
            "was_approved": is_approved
        }
    )
    
    # 7. 发送删除成功消息
    result_message = (
        f"🗑️ 作品【{work_name}】已删除\n"
        f"💫 被动扣除 {penalty} 次机辉\n"
        f"📊 当前机辉：{users_data[user_id]['jihui']} 次\n"
    )
    
    if removed_images:
        result_message += f"🖼️ 已清理 {len(removed_images)} 张图片\n"
    
    if is_pending:
        result_message += "⏳ 该作品原本处于待审核状态\n"
    if is_approved:
        result_message += "✅ 该作品原本已通过审核\n"
    
    await remove_work.finish(result_message)


# ============ 调试命令：查看我的作品状态 ============
my_works_status = on_command("我的作品状态", priority=5, block=True)

@my_works_status.handle()
async def handle_my_works_status(bot: Bot, event: MessageEvent):
    user_id = get_user_id(event)
    
    if user_id not in users_data:
        await my_works_status.finish("你还没有创建辉辉账号")
    
    user_works = users_data[user_id].get("works", [])
    current_jihui = users_data[user_id].get("jihui", 0)
    
    if not user_works:
        await my_works_status.finish(
            f"你还没有任何作品\n"
            f"当前机辉：{current_jihui} 次\n"
            f"使用 /辉除作品 [作品名称] 可删除作品（扣除7机辉）"
        )
    
    message = f"📋 {users_data[user_id]['hui_name']} 的作品状态\n"
    message += f"💫 当前机辉：{current_jihui} 次\n"
    message += f"📊 作品总数：{len(user_works)} 个\n\n"
    
    for work_name in user_works:
        status_icons = []
        
        # 检查是否在待审核
        is_pending = False
        for review in reviews_data.get("pending", {}).values():
            if review["user_id"] == user_id and review["work_name"] == work_name:
                is_pending = True
                status_icons.append("⏳待审核")
                break
        
        # 检查是否已通过审核
        is_approved = False
        if user_id in works_data and work_name in works_data[user_id]:
            is_approved = True
            status_icons.append("✅已通过")
        
        status_text = " ".join(status_icons) if status_icons else "❓未知"
        
        message += f"  • 【{work_name}】{status_text}\n"
    
    message += f"\n💡 删除作品命令：/辉除作品 [作品名称]（扣除7机辉）"
    
    await my_works_status.finish(message)

# ============ 指令7: 改名 ============
rename_hui = on_command("辉名", priority=5, block=True)

@rename_hui.handle()
async def handle_rename_hui(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 改名命令，用户: {user_id}")
    
    # 检查用户是否创建了账号
    if user_id not in users_data:
        await rename_hui.finish("你还没有创建辉辉账号，请先使用 /创建辉辉 [名字] 创建账号")
    
    # 获取新的名字参数
    new_name = args.extract_plain_text().strip()
    
    if not new_name:
        await rename_hui.finish("请输入要改的名字，格式：/辉名 [新名字]")
    
    # 名字格式检查
    if len(new_name) < 1 or len(new_name) > 20:
        await rename_hui.finish("名字长度应在1-20个字符之间")
    
    # 检查是否有禁用字符
    import re
    # 允许中文、字母、数字、下划线、连字符、空格
    if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_\-]+$', new_name):
        await rename_hui.finish("名字只能包含中文、字母、数字、下划线(_)和连字符(-)")
    
    # 检查重复名字
    for uid, user_info in users_data.items():
        if uid != user_id and user_info.get("hui_name") == new_name:
            await rename_hui.finish(f"名字【{new_name}】已经被其他用户使用了")
    
    # 检查机辉消耗 - 改名需要消耗5次机辉
    rename_cost = 5
    
    # 使用 can_active_consume 检查机辉是否足够
    if not can_active_consume(users_data[user_id]["jihui"], rename_cost):
        await rename_hui.finish(f"机辉不足！改名需要消耗{rename_cost}次机辉")
    
    # 获取旧名字
    old_name = users_data[user_id]["hui_name"]
    
    # 执行改名操作
    # 1. 消耗5次机辉
    users_data[user_id]["jihui"] -= rename_cost
    # 2. 更新名字
    users_data[user_id]["hui_name"] = new_name
    
    # 保存数据
    save_data(users_data, USER_DATA_FILE)
    
    # 发送成功消息
    response = f"✅ 改名成功！\n"
    response += f"📝 旧名字：{old_name}\n"
    response += f"✨ 新名字：{new_name}\n"
    response += f"💫 消耗{rename_cost}次机辉，当前机辉：{users_data[user_id]['jihui']}次\n"
       
    await rename_hui.finish(response)

# ============ 辉言功能 ============
# 辉言数据存储
# 注意：HUIYAN_DIR 已经在路径定义中修复

# 确保目录存在
HUIYAN_DIR.mkdir(parents=True, exist_ok=True)
HUIYAN_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# 辉言数据结构
huiyan_data = {}

# 加载辉言数据
if HUIYAN_DATA_FILE.exists():
    try:
        with open(HUIYAN_DATA_FILE, 'r', encoding='utf-8') as f:
            huiyan_data = json.load(f)
    except Exception as e:
        print(f"加载辉言数据失败: {e}")
        huiyan_data = {}

# 保存辉言数据
def save_huiyan_data():
    """保存辉言数据到文件"""
    try:
        with open(HUIYAN_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(huiyan_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存辉言数据失败: {e}")


# 指令8: 上传辉言
upload_huiyan = on_command("上传辉言", priority=5, block=True)

@upload_huiyan.handle()
async def handle_upload_huiyan(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    # 调试信息
    print(f"DEBUG: 上传辉言命令，用户: {user_id}")
    
    # 检查上传者是否有辉辉账号
    if user_id not in users_data:
        await upload_huiyan.finish("你还没有创建辉辉账号，请先使用 /创建辉辉 [名字] 创建账号")
    
    # 检查机辉
    if not can_active_consume(users_data[user_id]["jihui"], 1):
        await upload_huiyan.finish("机辉不足！需要1次机辉！")
    
    # 解析@的用户
    target_id = None
    for segment in event.message:
        if segment.type == "at":
            target_id = str(segment.data.get("qq", ""))
            print(f"DEBUG: 解析到@用户: {target_id}")
            break
    
    if not target_id:
        await upload_huiyan.finish("请@一个用户，格式：/上传辉言@用户+一张图片")
    
    # 检查被@用户是否有辉辉账号
    if target_id not in users_data:
        await upload_huiyan.finish("请@一个已创建辉辉账号的用户")
    
    if target_id == user_id:
        await upload_huiyan.finish("不能给自己上传辉言哦！")
    
    # 检查消息中是否有图片
    image_segments = [seg for seg in event.message if seg.type == "image"]
    
    if not image_segments:
        await upload_huiyan.finish("请在上传辉言时包含一张图片，格式：/上传辉言@用户+一张图片")
    
    if len(image_segments) > 1:
        await upload_huiyan.finish("每次只能上传一张图片")
    
    # 获取唯一的图片段
    image_segment = image_segments[0]
    url = image_segment.data.get("url", "")
    
    if not url:
        await upload_huiyan.finish("图片URL获取失败，请重试")
    
    # 下载并保存图片
    try:
        # 确保目标用户的辉言图片目录存在
        target_huiyan_dir = HUIYAN_IMAGES_DIR / target_id
        target_huiyan_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成唯一文件名
        timestamp = int(time.time())
        filename = f"{timestamp}_{user_id}.jpg"
        filepath = target_huiyan_dir / filename
        
        # 下载图片
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    await upload_huiyan.finish("图片下载失败，请重试")
                
                image_data = await response.read()
                
                # 检查图片大小（限制10MB）
                max_size = 10 * 1024 * 1024
                if len(image_data) > max_size:
                    await upload_huiyan.finish("图片过大，请使用小于10MB的图片")
                
                # 异步保存图片
                import aiofiles
                async with aiofiles.open(filepath, 'wb') as f:
                    await f.write(image_data)
        
        # 创建辉言记录
        huiyan_record = {
            "uploader_id": user_id,
            "uploader_name": users_data[user_id]["hui_name"],
            "image_filename": filename,
            "upload_time": timestamp,
            "upload_time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        }
        
        # 初始化目标用户的辉言列表
        if target_id not in huiyan_data:
            huiyan_data[target_id] = []
        
        # 添加到辉言列表
        huiyan_data[target_id].append(huiyan_record)
        
        # 消耗机辉
        users_data[user_id]["jihui"] -= 1
        
        # 保存数据
        save_data(users_data, USER_DATA_FILE)
        save_huiyan_data()
        
        # 获取用户名
        uploader_name = users_data[user_id]["hui_name"]
        target_name = users_data[target_id]["hui_name"]
        
        response = f"✅ 辉言上传成功！\n"
        response += f"🎯 目标用户：{target_name}\n"
        response += f"👤 上传者：{uploader_name}\n"
        response += f"📅 上传时间：{huiyan_record['upload_time_str']}\n"
        response += f"💫 消耗1次机辉，当前机辉：{users_data[user_id]['jihui']}次"
        
        await upload_huiyan.finish(response)
        
    except aiohttp.ClientError as e:
        print(f"ERROR: 网络请求失败: {e}")
        await upload_huiyan.finish("图片下载失败，请检查网络连接")
    except asyncio.TimeoutError:
        await upload_huiyan.finish("图片下载超时，请重试")
    except Exception as e:
        print(f"ERROR: 上传辉言失败: {e}")


# 指令9: 看辉言（只发图片版本）
view_huiyan = on_command("看辉言", priority=5, block=True)

@view_huiyan.handle()
async def handle_view_huiyan(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    user_id = get_user_id(event)
    
    print(f"DEBUG: 看辉言命令，用户: {user_id}")
    
    # 检查用户是否有辉辉账号
    if user_id not in users_data:
        await view_huiyan.finish("你还没有创建辉辉账号，请先使用 /创建辉辉 [名字] 创建账号")
    
    # 解析@的用户
    target_id = None
    for segment in event.message:
        if segment.type == "at":
            target_id = str(segment.data.get("qq", ""))
            break
    
    if not target_id:
        await view_huiyan.finish("请@一个用户，格式：/看辉言@用户")
    
    if target_id not in users_data:
        await view_huiyan.finish("请@一个已创建辉辉账号的用户")
    
    # 检查辉言数据文件
    if not HUIYAN_DATA_FILE.exists():
        # 不发送文字，直接结束
        await view_huiyan.finish("")
        return
    
    # 加载辉言数据
    try:
        with open(HUIYAN_DATA_FILE, 'r', encoding='utf-8') as f:
            current_huiyan_data = json.load(f)
    except Exception as e:
        print(f"ERROR: 加载辉言数据失败: {e}")
        # 不发送文字，直接结束
        await view_huiyan.finish("")
        return
    
    # 检查目标用户是否有辉言记录
    if target_id not in current_huiyan_data or not current_huiyan_data[target_id]:
        # 不发送文字，直接结束
        await view_huiyan.finish("")
        return
    
    target_huiyan_list = current_huiyan_data[target_id]
    
    # 从所有辉言中随机选择
    import random
    random_record = random.choice(target_huiyan_list)
    print(f"DEBUG: 选择的辉言记录: {random_record}")
    
    # 构建图片路径
    image_path = HUIYAN_IMAGES_DIR / target_id / random_record["image_filename"]
    print(f"DEBUG: 图片路径: {image_path}")
    
    if not image_path.exists():
        # 不发送文字，直接结束
        await view_huiyan.finish("")
        return
    
    # 只发送图片，不发送文字
    try:
        # 使用绝对路径
        abs_path = str(image_path.absolute())
        
        # 使用base64方式发送图片
        import base64
        with open(image_path, "rb") as f:
            img_data = f.read()
            base64_str = base64.b64encode(img_data).decode()
            # 只发送图片，不发送文字
            await bot.send(event, MessageSegment.image(f"base64://{base64_str}"))
        
        print(f"DEBUG: 辉言图片发送成功")
        # 注意：这里不调用 await view_huiyan.finish()，因为我们不发送文字消息
        # 让函数自然结束，不发送任何回复
        
    except Exception as e:
        print(f"ERROR: 发送辉言图片失败: {e}")
        # 图片发送失败时也不发送文字
        # 函数自然结束
        
    # 函数结束，不发送任何消息

# ============ 插件信息 ============
__plugin_name__ = "辉游戏"
__plugin_usage__ = """
辉游戏 - 一个有趣的折纸作品分享游戏

基本指令：
1. /创建辉辉 [名字] - 创建账号，初始3次机辉
2. /我的辉辉 或 /我的机辉 - 查看机辉
3. /辉签到 - 每日签到获得1次机辉

作品相关：
4. /上传辉品 [名称] +图片 - 上传作品等待审核（每小时一次）
6. /辉宝 [名称] - 设置辉宝（需3个作品）
7. /光辉岁月 - 查看作品列表
8. /辉忆 [名称] - 查看作品

SUPERUSER审核指令：
9. /审核列表 - 查看待审核作品
10. /审核详情 [审核ID] - 查看审核详情
11. /审核通过 [审核ID] - 通过审核（奖励4-7机辉）
12. /审核不通过 [审核ID] - 不通过审核（扣除1机辉）
13. /审核非常辉 [审核ID] - 非常辉评价（奖励9-12机辉）
14. /批量审核 [操作] [ID列表] - 批量审核
15. /审核统计 - 查看审核统计
16. /清理待审核 [天数] - 清理过期待审核
17. /审核日志 [数量] - 查看审核日志

互动功能：
18. /辉眼识人 @用户 或 /辉眼 @用户 - 查看随机作品（消耗1机辉）
19. /偷辉 @用户 [名称] - 查看指定作品（消耗2机辉）
20. /打辉机 或 /辉机 - 概率获得机辉（10分钟冷却）
21. /辉舞拳头 @用户 或 /辉拳 @用户 - 辉拳对决（10分钟冷却）

亲密关系：
22. /辉心一笑 @用户 或 /辉笑 @用户 - 绑定关系（24小时冷却）
23. /心辉意冷 或 /辉心 - 解除关系（被动消耗6机辉）
24. /约辉 - 双方获得5机辉（12小时冷却）
25. /幽辉 - 猜作品游戏（24小时冷却）

群功能：
26. /开辉 - @全体成员活动（24小时冷却，消耗12机辉）
27. /辉家 - 进入免打扰（消耗8机辉）
28. /起辉 - 退出免打扰（获得1机辉）
29. /机辉排行榜 - 查看排行榜
"""
