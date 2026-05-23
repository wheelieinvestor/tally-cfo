from dataclasses import dataclass

import structlog

from tally.agent.prompts import SYSTEM_PROMPT, build_user_query_prompt
from tally.config import get_anthropic_api_key

LOGGER = structlog.get_logger(__name__)
MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024


@dataclass(frozen=True)
class Trigger:
    pass


class BriefTrigger(Trigger):
    pass


class ReceiptTrigger(Trigger):
    pass


@dataclass(frozen=True)
class UserQueryTrigger(Trigger):
    query: str


@dataclass(frozen=True)
class AgentContext:
    data: dict
    user_question: str | None
    recent_conversations: list[dict]


@dataclass(frozen=True)
class AgentOutput:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    trigger_kind: str


def run_agent(trigger: Trigger, context: AgentContext) -> AgentOutput:
    if isinstance(trigger, BriefTrigger | ReceiptTrigger):
        raise NotImplementedError
    if not isinstance(trigger, UserQueryTrigger):
        raise NotImplementedError

    from anthropic import Anthropic

    prompt = build_user_query_prompt(trigger.query, context.data)
    client = Anthropic(api_key=get_anthropic_api_key())
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as error:
        LOGGER.error("anthropic_call_failed", trigger_kind="user_query", error=str(error))
        raise

    text = _extract_text(response.content).strip()
    output = AgentOutput(
        text=text,
        model=str(response.model),
        input_tokens=int(response.usage.input_tokens),
        output_tokens=int(response.usage.output_tokens),
        trigger_kind="user_query",
    )
    LOGGER.info(
        "anthropic_call_completed",
        trigger_kind=output.trigger_kind,
        model=output.model,
        input_tokens=output.input_tokens,
        output_tokens=output.output_tokens,
    )
    return output


def _extract_text(content: object) -> str:
    chunks = []
    for block in content:
        if getattr(block, "type", None) == "text":
            chunks.append(str(getattr(block, "text", "")))
    return "".join(chunks)
