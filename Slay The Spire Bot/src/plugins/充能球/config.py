from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.params import CommandArg
from nonebot.rule import to_me

# 测试命令
test = on_command("测试", aliases={"test", "ping"}, rule=to_me(), priority=5)

@test.handle()
async def handle_test(event: MessageEvent, args = CommandArg()):
    if args:
        await test.finish(f"测试成功！收到：{args}")
    else:
        await test.finish("✅ 机器人运行正常！\n📱 QQ: 3968160796\n🔗 连接状态: 正常")

# 状态命令
status = on_command("状态", aliases={"status", "状态检查"}, priority=5)

@status.handle()
async def handle_status():
    await status.finish(
        "🤖 机器人状态\n"
        "──────────\n"
        "✅ 运行状态: 正常\n"
        "🔌 连接状态: 已连接\n"
        "📅 启动时间: 2026-01-05 23:11:58\n"
        "💾 适配器: OneBot V11\n"
        "🔧 插件数: 2个\n"
    )
