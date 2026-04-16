"""
Chainlit demo app for Lab 11 guardrails + red-team testing.

Run:
    chainlit run src/chainlit_app.py
"""
import os
from typing import Any

import chainlit as cl

from agents.agent import create_protected_agent, create_unsafe_agent
from attacks.attacks import adversarial_prompts
from core.utils import chat_with_agent
from guardrails.input_guardrails import InputGuardrailPlugin
from guardrails.output_guardrails import OutputGuardrailPlugin, _init_judge


def _build_agent(mode: str):
    """Create unsafe/protected agent pair based on selected mode."""
    if mode == "protected":
        _init_judge()
        plugins = [InputGuardrailPlugin(), OutputGuardrailPlugin(use_llm_judge=True)]
        return create_protected_agent(plugins)
    return create_unsafe_agent()


def _format_attack_catalog() -> str:
    rows = ["### Available red-team attacks"]
    for attack in adversarial_prompts:
        rows.append(f"- `{attack['id']}`: {attack['category']}")
    return "\n".join(rows)


async def _run_single_prompt(prompt: str) -> str:
    agent = cl.user_session.get("agent")
    runner = cl.user_session.get("runner")
    response, _ = await chat_with_agent(agent, runner, prompt)
    return response


async def _set_mode(mode: str) -> str:
    agent, runner = _build_agent(mode)
    cl.user_session.set("mode", mode)
    cl.user_session.set("agent", agent)
    cl.user_session.set("runner", runner)
    return f"Switched to `{mode}` mode."


async def _execute_attack(attack: dict[str, Any]) -> str:
    response = await _run_single_prompt(attack["input"])
    return (
        f"### Attack #{attack['id']} - {attack['category']}\n"
        f"**Prompt**: {attack['input']}\n\n"
        f"**Response**: {response}"
    )


@cl.on_chat_start
async def on_chat_start():
    if not os.getenv("OPENAI_API_KEY"):
        await cl.Message(
            content=(
                "Missing `OPENAI_API_KEY`. Please set it in your environment "
                "before using this demo."
            )
        ).send()
        return

    note = await _set_mode("protected")
    help_text = (
        f"{note}\n\n"
        "Use commands:\n"
        "- `/mode protected` or `/mode unsafe`\n"
        "- `/redteam` to run all predefined attacks\n"
        "- `/attack <id>` to run one attack\n"
        "- `/catalog` to list red-team prompts\n"
        "- `/help` to show instructions\n\n"
        "Or send a normal banking question directly."
    )
    await cl.Message(content=help_text).send()


@cl.on_message
async def on_message(message: cl.Message):
    content = (message.content or "").strip()
    if not content:
        return

    lowered = content.lower()
    if lowered == "/help":
        await cl.Message(
            content=(
                "Commands:\n"
                "- `/mode protected|unsafe`\n"
                "- `/catalog`\n"
                "- `/attack <id>`\n"
                "- `/redteam`\n"
                "- Or ask a normal question."
            )
        ).send()
        return

    if lowered == "/catalog":
        await cl.Message(content=_format_attack_catalog()).send()
        return

    if lowered.startswith("/mode "):
        mode = lowered.split(" ", 1)[1].strip()
        if mode not in {"unsafe", "protected"}:
            await cl.Message(content="Invalid mode. Use `/mode unsafe` or `/mode protected`.").send()
            return
        await cl.Message(content=await _set_mode(mode)).send()
        return

    if lowered.startswith("/attack "):
        payload = lowered.split(" ", 1)[1].strip()
        if not payload.isdigit():
            await cl.Message(content="Usage: `/attack <id>` (example: `/attack 3`)").send()
            return
        attack_id = int(payload)
        attack = next((a for a in adversarial_prompts if a["id"] == attack_id), None)
        if attack is None:
            await cl.Message(content=f"Attack id `{attack_id}` not found. Use `/catalog`.").send()
            return
        await cl.Message(content=await _execute_attack(attack)).send()
        return

    if lowered == "/redteam":
        await cl.Message(content="Running all predefined red-team prompts...").send()
        for attack in adversarial_prompts:
            await cl.Message(content=await _execute_attack(attack)).send()
        return

    reply = await _run_single_prompt(content)
    mode = cl.user_session.get("mode", "protected")
    await cl.Message(content=f"[{mode}] {reply}").send()
