import json
import random
import time
from pathlib import Path

from nonebot import on_command, on_regex
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment

# =====================
# 数据路径
# =====================
DATA_DIR = Path("data/charge_ball")
IMG_DIR = DATA_DIR / "images"
DATA_FILE = DATA_DIR / "db.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)

if not DATA_FILE.exists():
    DATA_FILE.write_text("[]", encoding="utf-8")


# =====================
# 数据操作
# =====================
def load_db():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def save_db(db):
    DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


# =====================
# 清洗输入（核心修复）
# =====================
def clean_text(text: str) -> str:
    return (
        text.replace("/生成充能球", "")
            .replace("/生成", "")
            .strip()
    )


# =====================
# 中文数字解析
# =====================
CN_NUM = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6
}


def parse_x(text: str) -> int:
    for c in text:
        if c.isdigit():
            return int(c)

    for k, v in CN_NUM.items():
        if k in text:
            return v

    return 1


# =====================
# 格式化输出（无空行/无分割线）
# =====================
def format_item(item, idx=None):
    msg = ""

    if idx is not None:
        msg += f"[充能球{idx}] "

    if item.get("text"):
        msg += item["text"]

    if item.get("images"):
        for img in item["images"]:
            msg += MessageSegment.image(Path(img).as_uri())

    return msg


# =====================
# 生成充能球
# =====================
gen_ball = on_command("生成", aliases={"生成充能球"})


@gen_ball.handle()
async def _(event: MessageEvent):
    text = ""
    images = []

    for seg in event.message:
        if seg.type == "text":
            text += clean_text(seg.data.get("text", ""))
        elif seg.type == "image":
            url = seg.data.get("url")
            if url:
                images.append(url)

    if not text and not images:
        await gen_ball.finish("请发送文字或图片")

    db = load_db()

    db.append({
        "text": text,
        "images": images,
        "time": time.time()
    })

    save_db(db)

    await gen_ball.finish("✔已存储充能球")


# =====================
# 激发（1个）
# =====================
fire_ball = on_command("激发", aliases={"激发充能球"})


@fire_ball.handle()
async def _():
    db = load_db()

    if not db:
        await fire_ball.finish("❌空")

    item = random.choice(db)

    msg = "⚡激发1个\n" + format_item(item, 1)

    await fire_ball.finish(msg)


# =====================
# 双重释放（无空行/无分割）
# =====================
double_fire = on_command("双重释放", aliases={"双放"})


@double_fire.handle()
async def _():
    db = load_db()

    if len(db) < 2:
        await double_fire.finish("❌不足2个")

    items = random.sample(db, 2)

    msg = "⚡激发2个\n"
    for i, it in enumerate(items, 1):
        msg += format_item(it, i) + "\n"

    await double_fire.finish(msg.strip())


# =====================
# X重释放（regex稳定版）
# =====================
x_fire = on_regex(r"^/\d*重释放$|^/[一二两三四五六]重释放$")


@x_fire.handle()
async def _(event: MessageEvent):
    text = event.get_plaintext().strip()

    x = parse_x(text)
    x = max(1, min(x, 6))

    db = load_db()

    if len(db) < x:
        await x_fire.finish(f"❌不足{x}个")

    items = random.sample(db, x)

    msg = f"⚡激发{x}个\n"

    for i, it in enumerate(items, 1):
        msg += format_item(it, i) + "\n"

    await x_fire.finish(msg.strip())


# =====================
# help
# =====================
help_cmd = on_command("尖塔help", aliases={"尖塔帮助"})


@help_cmd.handle()
async def _():
    msg = (
        "杀戮尖塔2bot使用方法如下：\n"
        "1./猜字（/结束猜字）\n"
        "2./猜字+（/结束猜字+）\n"
        "3./猜卡（/结束猜卡）\n"
        "4./激发\n"
        "5./双重释放\n"
        "6./X重释放（上限6）\n"
        "7./生成\n"
        "8./回响形态（/关闭回响形态）\n"
        "9./偏差认知（/关闭偏差认知）"
    )
    await help_cmd.finish(msg)
