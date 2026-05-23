from typing import Any, TypedDict


class AgentDataContext(TypedDict, total=False):
    accounts: list[dict[str, Any]]
    transactions: list[dict[str, Any]]
    subscriptions_note: str
    positions: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    recent_conversations: list[dict[str, Any]]
    context_notes: list[str]


SYSTEM_PROMPT = """You are Tally CFO, an AI CFO for a single user. You live in their terminal and their Telegram. You speak in their voice.

Voice rules:
- Direct. First person where appropriate. Casual but precise.
- Concise. Most answers are one to three sentences. Anything longer needs a real reason.
- No em dashes. No "it's not X, it's Y" constructions. No corporate hedging. No "I'd be happy to help!" No "Great question!" No closing offers like "Let me know if you want to dig in further."
- Do not use emoji.
- Lowercase casual punctuation is fine when it fits the moment. Don't try to be funny. Be useful and dry.

Factual discipline:
- Only state numbers, dates, vendors, and amounts that appear in the provided context. If the user asks something the context doesn't cover, say so plainly: "I don't have that data yet" or "the sync doesn't include that."
- Never invent vendors, amounts, or dates. Never extrapolate beyond what's in the context.
- When referencing brokerage trades, copy the symbol exactly. Never append put, call, option, share, or instrument type unless that word appears as its own field in the context.
- If you compute something, only use numbers from the context as inputs, and show your work briefly when the user asked for a calculation.

Scope rules:
- You are not a regulated financial advisor. Do not recommend specific trades, stock picks, or tax positions. You can describe what is in the user's accounts and observe patterns.
- If the user asks for advice that crosses into regulated territory, say "that's the kind of call you'd want to make yourself" and redirect to what you can observe.

Personality, Level 1 dry:
- Make factual observations. Point out a thing if it's notable. Do not yet make jabs or push back hard. That comes later.
- Example acceptable: "Mercury Checking is at $21.60. Last big charge was the $121 Mercury Credit on May 4."
- Example unacceptable, too spicy for slice 3: "Mercury Checking is at $21.60. That's not 'low,' that's 'almost zero.' What's the plan?"
- Example unacceptable, too helpful-assistant: "Your Mercury Checking account currently has a balance of $21.60. Would you like me to break down your recent activity?"

Few-shot examples:
Q: what's my balance?
A: Mercury Checking is at $21.60. Public Brokerage is at $0.00.

Q: how much did I spend this month?
A: I see $342.18 in outgoing transactions this month from the synced data. Biggest one is Mercury Credit at $121.00.

Q: what's my burn?
A: Using the transactions in context, outgoing spend is $342.18 across the period shown. That's the burn I can calculate from this sync, not a forecast.

Q: what did I spend on at stripe?
A: I don't see Stripe spend in the provided transactions. I see Stripe as incoming money, so calling it spend would be wrong.

Q: what's in my brokerage?
A: Public is synced, but I don't see any current positions in the provided snapshot. Looks like cash only from the data I have."""


def build_user_query_prompt(query: str, context: AgentDataContext) -> str:
    sections = [
        "User question:",
        query,
        "",
        "Context:",
        _format_context(context),
        "",
        "Answer the question using only the data above. If the data above does not contain what you need, say so.",
    ]
    return "\n".join(sections)


def _format_context(context: AgentDataContext) -> str:
    parts = [
        _format_accounts(context.get("accounts", [])),
        _format_transactions(context.get("transactions", [])),
        _format_subscriptions(context.get("subscriptions_note")),
        _format_positions(context.get("positions", [])),
        _format_trades(context.get("trades", [])),
        _format_conversations(context.get("recent_conversations", [])),
        _format_notes(context.get("context_notes", [])),
    ]
    return "\n\n".join(part for part in parts if part)


def _format_accounts(accounts: list[dict[str, Any]]) -> str:
    lines = ["Accounts:"]
    if not accounts:
        lines.append("- none")
        return "\n".join(lines)
    for account in accounts:
        lines.append(
            "- provider={provider}; name={account_name}; balance={balance}; last_synced_at={last_synced_at}".format(
                provider=account.get("provider"),
                account_name=account.get("account_name"),
                balance=account.get("balance"),
                last_synced_at=account.get("last_synced_at"),
            )
        )
    return "\n".join(lines)


def _format_transactions(transactions: list[dict[str, Any]]) -> str:
    lines = ["Transactions:"]
    if not transactions:
        lines.append("- not included or none matched")
        return "\n".join(lines)
    for transaction in transactions:
        lines.append(
            "- posted_at={posted_at}; amount={amount}; counterparty={counterparty}; description={description}; category={category}; account={account_name}; provider={provider}".format(
                posted_at=transaction.get("posted_at"),
                amount=transaction.get("amount"),
                counterparty=transaction.get("counterparty"),
                description=transaction.get("description"),
                category=transaction.get("category"),
                account_name=transaction.get("account_name"),
                provider=transaction.get("provider"),
            )
        )
    return "\n".join(lines)


def _format_subscriptions(note: str | None) -> str:
    return f"Subscriptions:\n- {note}" if note else ""


def _format_positions(positions: list[dict[str, Any]]) -> str:
    lines = ["Positions:"]
    if not positions:
        lines.append("- no current positions in context")
        return "\n".join(lines)
    for position in positions:
        lines.append(
            "- symbol={symbol}; quantity={quantity}; cost_basis={cost_basis}; current_value={current_value}; snapshot_at={snapshot_at}; account={account_name}; provider={provider}".format(
                symbol=position.get("symbol"),
                quantity=position.get("quantity"),
                cost_basis=position.get("cost_basis"),
                current_value=position.get("current_value"),
                snapshot_at=position.get("snapshot_at"),
                account_name=position.get("account_name"),
                provider=position.get("provider"),
            )
        )
    return "\n".join(lines)


def _format_trades(trades: list[dict[str, Any]]) -> str:
    lines = ["Trades:"]
    if not trades:
        lines.append("- no trades in context")
        return "\n".join(lines)
    for trade in trades:
        lines.append(
            "- executed_at={executed_at}; symbol={symbol}; side={side}; quantity={quantity}; price={price}; instrument_type=not provided; account={account_name}; provider={provider}".format(
                executed_at=trade.get("executed_at"),
                symbol=trade.get("symbol"),
                side=trade.get("side"),
                quantity=trade.get("quantity"),
                price=trade.get("price"),
                account_name=trade.get("account_name"),
                provider=trade.get("provider"),
            )
        )
    return "\n".join(lines)


def _format_conversations(conversations: list[dict[str, Any]]) -> str:
    lines = ["Recent conversation turns:"]
    if not conversations:
        lines.append("- none")
        return "\n".join(lines)
    for turn in conversations:
        lines.append(
            "- role={role}; created_at={created_at}; thread_id={thread_id}; content={content}".format(
                role=turn.get("role"),
                created_at=turn.get("created_at"),
                thread_id=turn.get("thread_id"),
                content=turn.get("content"),
            )
        )
    return "\n".join(lines)


def _format_notes(notes: list[str]) -> str:
    if not notes:
        return ""
    return "Context notes:\n" + "\n".join(f"- {note}" for note in notes)
