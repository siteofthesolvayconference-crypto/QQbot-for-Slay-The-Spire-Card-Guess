from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from nonebot import get_driver, logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent

from .core import (
    CardRepository,
    GuessGameState,
    WordGuessGameState,
    WordPlusGuessGameState,
    build_help_message,
    build_word_guess_help_message,
    build_word_plus_guess_help_message,
    create_game_state,
    create_word_guess_game,
    create_word_plus_guess_game,
    extract_command,
)


card_guess_message = on_message(priority=10, block=False)
repository = CardRepository()
session_lock = asyncio.Lock()
active_sessions: dict[str, "CardGuessSession"] = {}
INITIAL_HINT_DELAY_SECONDS = 10.0
FOLLOWUP_HINT_DELAY_SECONDS = 60.0

# 猜字游戏相关
word_guess_sessions: dict[str, WordGuessGameState] = {}
word_session_lock = asyncio.Lock()

# 猜字+游戏相关
word_plus_guess_sessions: dict[str, WordPlusGuessGameState] = {}
word_plus_session_lock = asyncio.Lock()


@dataclass
class CardGuessSession:
    group_id: str
    bot: Bot
    state: GuessGameState
    timer_task: asyncio.Task[None] | None = None


@card_guess_message.handle()
async def handle_card_guess_message(bot: Bot, event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return

    command, argument = extract_command(event.get_message().extract_plain_text())

    # 帮助命令
    if command in {"/猜卡", "/猜字", "/猜字+"} and (argument or "").strip().lower() in {"help", "帮助"}:
        if command == "/猜卡":
            await bot.send(event, build_help_message(), reply_message=True)
        elif command == "/猜字":
            await bot.send(event, build_word_guess_help_message(), reply_message=True)
        else:
            await bot.send(event, build_word_plus_guess_help_message(), reply_message=True)
        return

    # 猜字+命令
    if command in {"/猜字+", "/结束猜字+"}:
        await handle_word_plus_guess_game(bot, event)
        return

    # 猜字命令
    if command in {"/猜字", "/结束猜字"}:
        await handle_word_guess_game(bot, event)
        return

    # 猜卡命令
    if command in {"/猜卡", "/结束猜卡", "/提示", "/猜卡测试"}:
        if command == "/猜卡":
            await _handle_start_game(bot, event)
            return
        if command == "/结束猜卡":
            await _handle_end_game(bot, event)
            return
        if command == "/提示":
            await _handle_manual_hint(bot, event)
            return
        if command == "/猜卡测试":
            await _handle_test_game(bot, event, argument)
            return

    # 非命令消息（猜测）
    plain_text = event.get_message().extract_plain_text().strip()
    if plain_text and not plain_text.startswith("/"):
        # 优先检查猜字+
        if await _check_group_has_word_plus_game(str(event.group_id)):
            await _handle_word_plus_guess_attempt(bot, event, plain_text)
        elif await _check_group_has_word_game(str(event.group_id)):
            await _handle_word_guess_attempt(bot, event, plain_text)
        elif await _check_group_has_card_game(str(event.group_id)):
            await _handle_guess_attempt(bot, event, plain_text)


# ==================== 猜字+ 相关函数 ====================

async def handle_word_plus_guess_game(bot: Bot, event: GroupMessageEvent) -> None:
    command, argument = extract_command(event.get_message().extract_plain_text())

    if command == "/猜字+":
        await _handle_start_word_plus_game(bot, event)
        return

    if command == "/结束猜字+":
        await _handle_end_word_plus_game(bot, event)
        return


async def _handle_start_word_plus_game(bot: Bot, event: GroupMessageEvent) -> None:
    data_dir = _get_card_data_dir()
    repository.set_data_dir(data_dir)

    try:
        card = repository.pick_random_card_with_upgrade()
    except FileNotFoundError:
        await bot.send(event, f"猜卡牌数据目录不存在：`{data_dir}`，请配置。", reply_message=True)
        return
    except ValueError:
        await bot.send(event, "没有卡牌拥有升级描述，无法开始猜字+游戏。", reply_message=True)
        return
    except Exception:
        logger.exception("Failed to load card data for word+ game")
        await bot.send(event, "读取卡牌数据失败。", reply_message=True)
        return

    group_key = str(event.group_id)

    async with word_plus_session_lock:
        if group_key in word_plus_guess_sessions:
            await bot.send(event, "本群已经有一局猜字+游戏进行中，请先结束。", reply_message=True)
            return

        state = create_word_plus_guess_game(card)
        word_plus_guess_sessions[group_key] = state

    initial_message = (
        f"猜字+游戏开始！（使用升级版描述）\n"
        f"卡牌名称字数：{card.name_length} 字\n"
        f"现有描述：{state.render_hidden_description()}\n"
        f"你可以：\n"
        f"1. 猜字：牌（揭示所有“牌”字）\n"
        f"2. 猜多个字：抽牌\n"
        f"3. 猜卡牌名称：蛇咬"
    )
    await bot.send(event, initial_message, reply_message=True)


async def _handle_end_word_plus_game(bot: Bot, event: GroupMessageEvent) -> None:
    group_key = str(event.group_id)

    async with word_plus_session_lock:
        state = word_plus_guess_sessions.pop(group_key, None)

    if state is None:
        await bot.send(event, "本群当前没有正在进行的猜字+游戏。", reply_message=True)
        return

    answer_message = (
        f"猜字+游戏结束！\n"
        f"卡牌名称：{state.card.name}\n"
        f"升级描述：{state.card.upgraded_description}\n"
        f"类型：{state.card.type_label}\n"
        f"来源：{state.card.source_label}\n"
        f"费用：{state.card.cost}"
    )
    await bot.send(event, answer_message, reply_message=True)


async def _handle_word_plus_guess_attempt(bot: Bot, event: GroupMessageEvent, guess_text: str) -> None:
    group_key = str(event.group_id)

    async with word_plus_session_lock:
        state = word_plus_guess_sessions.get(group_key)
        if state is None:
            return

    # 检查是否猜对了卡牌名称
    if state.check_guess(guess_text):
        async with word_plus_session_lock:
            if group_key in word_plus_guess_sessions:
                del word_plus_guess_sessions[group_key]

        success_message = (
            f"恭喜猜对了！\n"
            f"卡牌名称：{state.card.name}\n"
            f"升级描述：{state.card.upgraded_description}\n"
            f"类型：{state.card.type_label}\n"
            f"来源：{state.card.source_label}"
        )
        await bot.send(event, success_message, reply_message=True)
        return

    # 猜字
    revealed_count = state.reveal_chars(guess_text)
    current_description = state.render_hidden_description()

    if revealed_count > 0:
        response = f"揭示了 {revealed_count} 个字：{current_description}"
        if state.is_finished():
            response += "\n\n所有字都已揭示！但卡牌名称还未猜出。"
    else:
        response = f"这些字不在描述中。当前描述：{current_description}"

    await bot.send(event, response, reply_message=True)


async def _check_group_has_word_plus_game(group_key: str) -> bool:
    async with word_plus_session_lock:
        return group_key in word_plus_guess_sessions


# ==================== 猜字 相关函数 ====================

async def handle_word_guess_game(bot: Bot, event: GroupMessageEvent) -> None:
    command, argument = extract_command(event.get_message().extract_plain_text())

    if command == "/猜字":
        await _handle_start_word_game(bot, event)
        return

    if command == "/结束猜字":
        await _handle_end_word_game(bot, event)
        return


async def _handle_start_word_game(bot: Bot, event: GroupMessageEvent) -> None:
    data_dir = _get_card_data_dir()
    repository.set_data_dir(data_dir)

    try:
        card = repository.pick_random_card()
    except FileNotFoundError:
        await bot.send(event, f"猜卡牌数据目录不存在：`{data_dir}`，请配置。", reply_message=True)
        return
    except ValueError:
        await bot.send(event, "猜卡牌卡池为空，暂时无法开始。", reply_message=True)
        return
    except Exception:
        logger.exception("Failed to load STS card data for word game")
        await bot.send(event, "读取猜卡牌数据失败。", reply_message=True)
        return

    group_key = str(event.group_id)

    async with word_session_lock:
        if group_key in word_guess_sessions:
            await bot.send(event, "本群已经有一局猜字游戏进行中，请先结束。", reply_message=True)
            return

        state = create_word_guess_game(card)
        word_guess_sessions[group_key] = state

    initial_message = (
        f"杀戮尖塔猜字游戏开始！\n"
        f"现有描述：{state.render_hidden_description()}\n"
        f"你可以：\n"
        f"1. 猜字：牌（揭示所有“牌”字）\n"
        f"2. 猜多个字：抽牌\n"
        f"3. 猜卡牌名称：蛇咬"
    )
    await bot.send(event, initial_message, reply_message=True)


async def _handle_end_word_game(bot: Bot, event: GroupMessageEvent) -> None:
    group_key = str(event.group_id)

    async with word_session_lock:
        state = word_guess_sessions.pop(group_key, None)

    if state is None:
        await bot.send(event, "本群当前没有正在进行的猜字游戏。", reply_message=True)
        return

    answer_message = (
        f"猜字游戏结束！\n"
        f"卡牌名称：{state.card.name}\n"
        f"完整描述：{state.card.description}\n"
        f"类型：{state.card.type_label}\n"
        f"来源：{state.card.source_label}\n"
        f"费用：{state.card.cost}"
    )
    await bot.send(event, answer_message, reply_message=True)


async def _handle_word_guess_attempt(bot: Bot, event: GroupMessageEvent, guess_text: str) -> None:
    group_key = str(event.group_id)

    async with word_session_lock:
        state = word_guess_sessions.get(group_key)
        if state is None:
            return

    if state.check_guess(guess_text):
        async with word_session_lock:
            if group_key in word_guess_sessions:
                del word_guess_sessions[group_key]

        success_message = (
            f"恭喜猜对了！\n"
            f"卡牌名称：{state.card.name}\n"
            f"完整描述：{state.card.description}\n"
            f"类型：{state.card.type_label}\n"
            f"来源：{state.card.source_label}\n"
            f"费用：{state.card.cost}"
        )
        await bot.send(event, success_message, reply_message=True)
        return

    revealed_count = state.reveal_chars(guess_text)
    current_description = state.render_hidden_description()

    if revealed_count > 0:
        response = f"揭示了 {revealed_count} 个字：{current_description}"
        if state.is_finished():
            response += "\n\n所有字都已揭示！但卡牌名称还未猜出。"
    else:
        response = f"这些字不在描述中。当前描述：{current_description}"

    await bot.send(event, response, reply_message=True)


async def _check_group_has_word_game(group_key: str) -> bool:
    async with word_session_lock:
        return group_key in word_guess_sessions


# ==================== 猜卡 原有函数 ====================

async def _handle_start_game(bot: Bot, event: GroupMessageEvent) -> None:
    data_dir = _get_card_data_dir()
    repository.set_data_dir(data_dir)
    try:
        card = repository.pick_random_card()
    except FileNotFoundError:
        await bot.send(event, f"猜卡牌数据目录不存在：`{data_dir}`，请配置。", reply_message=True)
        return
    except ValueError:
        await bot.send(event, "猜卡牌卡池为空，暂时无法开始。", reply_message=True)
        return
    except Exception:
        logger.exception("Failed to load STS card data")
        await bot.send(event, "读取猜卡牌数据失败。", reply_message=True)
        return

    await _start_session(bot, event, card=card)


async def _handle_test_game(bot: Bot, event: GroupMessageEvent, argument: Optional[str]) -> None:
    if not _is_admin_user(event):
        await bot.send(event, "您没有管理权限，无法开启测试局。", reply_message=True)
        return
    if not argument:
        await bot.send(event, "请使用 `/猜卡测试 卡牌名或ID` 来指定测试卡牌。", reply_message=True)
        return

    data_dir = _get_card_data_dir()
    repository.set_data_dir(data_dir)
    try:
        card = repository.find_card(argument)
    except FileNotFoundError:
        await bot.send(event, f"猜卡牌数据目录不存在：`{data_dir}`，请配置。", reply_message=True)
        return
    except Exception:
        logger.exception("Failed to search STS card data")
        await bot.send(event, "读取猜卡牌数据失败。", reply_message=True)
        return

    if card is None:
        await bot.send(event, f"没有找到卡牌：`{argument}`。请使用完整中文卡名或 card id。", reply_message=True)
        return

    await _start_session(bot, event, card=card, testing=True)


async def _start_session(bot: Bot, event: GroupMessageEvent, card, testing: bool = False) -> None:
    group_key = str(event.group_id)

    async with session_lock:
        existing = active_sessions.get(group_key)
        if existing is not None:
            await bot.send(event, "本群已经有一局猜卡进行中，请先猜完，或使用 `/结束猜卡` 结束当前游戏。", reply_message=True)
            return

        state = create_game_state(card, rng=random.Random())
        session = CardGuessSession(group_id=group_key, bot=bot, state=state)
        active_sessions[group_key] = session
        session.timer_task = asyncio.create_task(_hint_after_delay(group_key, INITIAL_HINT_DELAY_SECONDS))

    prefix = "猜卡测试开始：\n" if testing else ""
    await bot.send(event, prefix + state.build_start_message(), reply_message=True)


async def _handle_end_game(bot: Bot, event: GroupMessageEvent) -> None:
    session = await _remove_session(str(event.group_id))
    if session is None:
        await bot.send(event, "本群当前没有正在进行的猜卡游戏。", reply_message=True)
        return

    await bot.send(event, f"已结束本局猜卡。这张卡是 `{session.state.card.name}`。", reply_message=True)


async def _handle_manual_hint(bot: Bot, event: GroupMessageEvent) -> None:
    result = await _advance_group_session(str(event.group_id), next_delay=FOLLOWUP_HINT_DELAY_SECONDS)
    if result is None:
        await bot.send(event, "本群当前没有正在进行的猜卡游戏。", reply_message=True)
        return

    await bot.send(event, result.message, reply_message=True)


async def _handle_guess_attempt(bot: Bot, event: GroupMessageEvent, guess_text: str) -> None:
    group_key = str(event.group_id)
    async with session_lock:
        session = active_sessions.get(group_key)
        if session is None:
            return
        if session.state.check_guess(guess_text):
            active_sessions.pop(group_key, None)
            timer_task = session.timer_task
        else:
            timer_task = None
    if session is None:
        return
    if timer_task is not None:
        timer_task.cancel()
        await bot.send(event, f"猜对了，答案就是 `{session.state.card.name}`，本局游戏结束。", reply_message=True)
        return

    await bot.send(event, "猜错了，游戏继续。", reply_message=True)


async def _hint_after_delay(group_key: str, delay: float) -> None:
    try:
        await asyncio.sleep(delay)
        result = await _advance_group_session(group_key, next_delay=FOLLOWUP_HINT_DELAY_SECONDS)
        if result is None:
            return
        await _send_group_text(result.bot, result.group_id, result.message)
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Unexpected card guess timer failure")


async def _advance_group_session(group_key: str, next_delay: float) -> Optional["AdvanceEnvelope"]:
    async with session_lock:
        session = active_sessions.get(group_key)
        if session is None:
            return None

        result = session.state.advance()
        if result.finished:
            active_sessions.pop(group_key, None)
            current_task = asyncio.current_task()
            if session.timer_task is not None and session.timer_task is not current_task:
                session.timer_task.cancel()
            return AdvanceEnvelope(message=result.message, bot=session.bot, group_id=session.group_id)

        if session.timer_task is not None:
            session.timer_task.cancel()
        session.timer_task = asyncio.create_task(_hint_after_delay(group_key, next_delay))
        return AdvanceEnvelope(message=result.message, bot=session.bot, group_id=session.group_id)


@dataclass
class AdvanceEnvelope:
    message: str
    bot: Bot
    group_id: str


async def _remove_session(group_key: str) -> Optional[CardGuessSession]:
    async with session_lock:
        session = active_sessions.pop(group_key, None)
        if session is not None and session.timer_task is not None:
            session.timer_task.cancel()
        return session


async def _get_session(group_key: str) -> Optional[CardGuessSession]:
    async with session_lock:
        return active_sessions.get(group_key)


async def _send_group_text(bot: Bot, group_id: str, message: str) -> None:
    await bot.send_group_msg(group_id=int(group_id), message=message)


def _get_card_data_dir() -> Path:
    config = get_driver().config
    configured = getattr(config, "sts_card_data_dir", None)
    if configured is None:
        return repository.get_data_dir()
    value = str(configured).strip()
    if not value:
        return repository.get_data_dir()
    return Path(value)


def _is_admin_user(event: MessageEvent) -> bool:
    config = get_driver().config
    admin_qq = getattr(config, "admin_qq", None)
    if admin_qq is None:
        return False
    return str(event.user_id) == str(admin_qq).strip()


async def _check_group_has_card_game(group_key: str) -> bool:
    async with session_lock:
        return group_key in active_sessions
