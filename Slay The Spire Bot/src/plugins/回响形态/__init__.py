from nonebot import on_command, on_message
from nonebot.adapters import Message
from nonebot.params import CommandArg, EventPlainText
from nonebot.typing import T_State
from nonebot.plugin import PluginMetadata
from typing import Dict, Set

__plugin_meta__ = PluginMetadata(
    name="回声与偏差",
    description="实现回响形态和偏差认知的特殊效果",
    usage="""命令列表:
/回响形态 - 开启回响模式，之后的每句话都会被复读
/停止回响形态 - 关闭回响模式
/偏差认知 - 开启/关闭偏差认知模式
/停止偏差认知 - 关闭偏差认知模式
注意: 在效果持续期间，超过11个字的消息会触发防卡顿机制""",
    type="application"
)

# 存储用户状态的字典
user_states: Dict[str, Dict[str, bool]] = {}  # {user_id: {"echo": bool, "bias": bool}}

# 创建命令处理器
echo_on = on_command("回响形态", aliases={"/回响形态"}, priority=5, block=True)
echo_off = on_command("关闭回响形态", aliases={"/关闭回响形态"}, priority=5, block=True)
bias_toggle = on_command("偏差认知", aliases={"/偏差认知"}, priority=5, block=True)
bias_off = on_command("关闭偏差认知", aliases={"/关闭偏差认知"}, priority=5, block=True)
echo_handler = on_message(priority=10, block=True)

@echo_on.handle()
async def handle_echo_on(state: T_State, event):
    """开启回响形态"""
    user_id = str(event.get_user_id())
    
    if user_id not in user_states:
        user_states[user_id] = {"echo": False, "bias": False}
    
    user_states[user_id]["echo"] = True
    await echo_on.send("回响形态已开启")

@echo_off.handle()
async def handle_echo_off(state: T_State, event):
    """停止回响形态"""
    user_id = str(event.get_user_id())
    
    if user_id in user_states:
        user_states[user_id]["echo"] = False
        await echo_off.send("回响形态已关闭")
    else:
        await echo_off.send("尚未开启回响形态")

@bias_toggle.handle()
async def handle_bias_toggle(state: T_State, event):
    """切换偏差认知状态"""
    user_id = str(event.get_user_id())
    
    if user_id not in user_states:
        user_states[user_id] = {"echo": False, "bias": False}
    
    # 切换偏差认知状态
    new_state = not user_states[user_id]["bias"]
    user_states[user_id]["bias"] = new_state
    
    if new_state:
        await bias_toggle.send("偏差认知已开启")
    else:
        await bias_toggle.send("偏差认知已关闭")

@bias_off.handle()
async def handle_bias_off(state: T_State, event):
    """停止偏差认知"""
    user_id = str(event.get_user_id())
    
    if user_id in user_states and user_states[user_id]["bias"]:
        user_states[user_id]["bias"] = False
        await bias_off.send("偏差认知已关闭")
    else:
        await bias_off.send("偏差认知未开启")

@echo_handler.handle()
async def handle_echo(state: T_State, event, text: str = EventPlainText()):
    """处理消息并进行相应回复"""
    user_id = str(event.get_user_id())
    
    # 检查是否在有效状态中
    if user_id not in user_states:
        return
    
    echo_enabled = user_states[user_id]["echo"]
    bias_enabled = user_states[user_id]["bias"]
    
    # 如果两个效果都未开启，不处理
    if not echo_enabled and not bias_enabled:
        return
    
    # 检查消息是否超过11个字
    if len(text) > 11:
        await echo_handler.send("太长了，我还在启动…\n太长了，我还在启…")
        return
    
    # 生成回复
    reply_text = ""
    
    if echo_enabled and bias_enabled:
        # 同时开启两种效果
        lines = []
        lines.append(text)  # 第一行完整文本
        
        # 生成偏差认知的每一行（重复两次），从去掉1个字开始
        for i in range(1, 5):
            if len(text) > i:
                # 每行重复两次
                line = text[:-i]
                lines.append(line)
                lines.append(line)
        
        reply_text = "\n".join(lines)
        
    elif echo_enabled:
        # 只开启回响形态
        reply_text = text
        
    elif bias_enabled:
        # 只开启偏差认知
        lines = []
        # 修正：从去掉1个字开始，而不是从完整文本开始
        for i in range(1, 5):
            if len(text) > i:
                lines.append(text[:-i])
        
        # 如果没有生成任何行（文本太短），则返回空
        if not lines:
            return
        
        reply_text = "\n".join(lines)
    
    if reply_text:
        await echo_handler.send(reply_text)
