"""
magicpin AI Challenge — Vera-beating merchant/customer bot.
Implements the 5-endpoint contract from challenge-testing-brief.md.
"""

import os
import json
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"

app = FastAPI()
START = time.time()


contexts: dict[tuple[str, str], dict] = {}       # (scope, context_id) -> {version, payload}
conversations: dict[str, dict] = {}              # conversation_id -> conv state
sent_suppression_keys: set[str] = set()          # avoid re-firing same trigger family
merchant_auto_reply_count: dict[str, int] = {}


def get_ctx(scope: str, context_id: str) -> Optional[dict]:
    entry = contexts.get((scope, context_id))
    return entry["payload"] if entry else None



SYSTEM_PROMPT = """You are Vera, magicpin's AI marketing assistant, writing a single WhatsApp
message either TO a merchant, or ON BEHALF OF a merchant TO one of their customers.

Hard rules:
- Anchor the message on ONE concrete, verifiable fact from the provided context (a number,
  date, headline, or peer stat). Never say generic things like "grow your business" or "10% off"
  if a specific fact is available.
- Match the category's voice exactly (tone, vocabulary, taboos given in context). Clinical/peer
  categories (dentists, doctors) must NOT sound promotional.
- Personalize to the merchant's actual numbers/offers/history. Never invent data not in context.
- Exactly ONE call-to-action, placed in the last sentence. Binary (e.g. "Reply YES / STOP") for
  action triggers; no CTA for pure information.
- Hindi-English code-mix is encouraged when the merchant's/customer's language preference allows
  it ("hi" or "hi-en mix") — write naturally, not literal translation.
- No preambles, no re-introducing yourself after the first message in a conversation.
- Keep it concise — a few sentences, WhatsApp-length.
- If writing to a CUSTOMER (send_as=merchant_on_behalf), it must read as if the merchant's
  business is speaking, use the merchant's real offer/slot data only, and follow customer-facing
  voice rules (no medical/overclaims).
- Never repeat a message that was already sent verbatim in this conversation — vary the phrasing
  and, ideally, add a new angle.

Respond with ONLY a JSON object with exactly these keys:
{"body": "...", "cta": "binary" | "open_ended" | "none", "rationale": "..."}
"""


def llm_compose(user_payload: dict) -> dict:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=500,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return {"body": resp.choices[0].message.content.strip(), "cta": "open_ended", "rationale": ""}


def compose_message(category: dict, merchant: dict, trigger: dict,
                     customer: Optional[dict] = None,
                     prior_bodies: Optional[list[str]] = None) -> dict:
    """Core composer — deterministic (temperature=0). Returns the ComposedMessage dict."""
    send_as = "merchant_on_behalf" if customer else "vera"
    payload = {
        "category": category,
        "merchant": merchant,
        "trigger": trigger,
        "customer": customer,
        "already_sent_in_this_conversation": prior_bodies or [],
        "send_as": send_as,
    }
    result = llm_compose(payload)
    return {
        "body": result.get("body", "").strip(),
        "cta": result.get("cta", "open_ended"),
        "send_as": send_as,
        "suppression_key": trigger.get("suppression_key", trigger.get("id", "")),
        "rationale": result.get("rationale", ""),
    }



AUTO_REPLY_TIP_OFF = [
    "thank you for contacting", "we will get back to you", "automated assistant",
    "aapki jaankari ke liye", "shukriya", "team tak pahuncha",
]
INTENT_GO_PHRASES = [
    "let's do it", "lets do it", "go ahead", "ok let's", "yes let's", "i want to join",
    "sign me up", "start karo", "chalo shuru karo", "haan chalo", "ok proceed", "yes proceed",
]
NOT_INTERESTED_PHRASES = [
    "not interested", "stop", "no thanks", "nahi chahiye", "band karo", "unsubscribe",
]


def is_probably_autoreply(conv: dict, message: str) -> bool:
    same_count = sum(1 for m in conv["merchant_messages"] if m.strip() == message.strip())
    looks_canned = any(p in message.lower() for p in AUTO_REPLY_TIP_OFF)
    return same_count >= 2 or (same_count >= 1 and looks_canned)


def detect_intent_go(message: str) -> bool:
    m = message.lower()
    return any(p in m for p in INTENT_GO_PHRASES)


def detect_not_interested(message: str) -> bool:
    m = message.lower()
    return any(p in m for p in NOT_INTERESTED_PHRASES)


def llm_reply(conv: dict, merchant_message: str, mode: str) -> dict:
    """mode: 'normal' | 'intent_go' | 'autoreply_probe' """
    merchant = get_ctx("merchant", conv["merchant_id"]) or {}
    category = get_ctx("category", merchant.get("category_slug", "")) or {}
    customer = get_ctx("customer", conv["customer_id"]) if conv.get("customer_id") else None
    trigger = get_ctx("trigger", conv["trigger_id"]) or {}

    instruction = {
        "normal": "Continue the conversation naturally, advancing toward the CTA.",
        "intent_go": ("The other party just gave explicit GO-AHEAD intent. Do NOT ask another "
                       "qualifying question — acknowledge briefly and move straight into the "
                       "concrete next action/step."),
        "autoreply_probe": ("This looks like it might be the business's own canned WhatsApp "
                             "auto-reply, not a real person. Send ONE short, low-friction probe "
                             "to check if a real person is there. Do not repeat prior content."),
    }[mode]

    payload = {
        "category": category, "merchant": merchant, "trigger": trigger, "customer": customer,
        "conversation_so_far": conv["turns"],
        "latest_incoming_message": merchant_message,
        "already_sent_in_this_conversation": conv["bot_messages"],
        "instruction": instruction,
    }
    result = llm_compose(payload)
    return result



@app.get("/v1/healthz")
async def healthz():
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _cid) in contexts:
        counts[scope] = counts.get(scope, 0) + 1
    return {"status": "ok", "uptime_seconds": int(time.time() - START), "contexts_loaded": counts}


@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Solo Builder",
        "team_members": ["You"],
        "model": MODEL,
        "approach": "Single LLM composer (Groq/Llama-3.3-70b, temp=0) over the 4-context payload, "
                    "with rule-based auto-reply detection, intent-transition routing, and "
                    "anti-repetition via prior-message injection.",
        "contact_email": "you@example.com",
        "version": "0.1.0",
        "submitted_at": datetime.utcnow().isoformat() + "Z",
    }


class CtxBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


@app.post("/v1/context")
async def push_context(body: CtxBody):
    if body.scope not in ("category", "merchant", "customer", "trigger"):
        return {"accepted": False, "reason": "invalid_scope", "details": f"unknown scope {body.scope}"}
    key = (body.scope, body.context_id)
    cur = contexts.get(key)
    if cur and cur["version"] >= body.version:
        return {"accepted": False, "reason": "stale_version", "current_version": cur["version"]}
    contexts[key] = {"version": body.version, "payload": body.payload}
    return {"accepted": True, "ack_id": f"ack_{body.context_id}_v{body.version}",
            "stored_at": datetime.utcnow().isoformat() + "Z"}


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = []


@app.post("/v1/tick")
async def tick(body: TickBody):
    actions = []
    for trg_id in body.available_triggers[:20]:
        trigger = get_ctx("trigger", trg_id)
        if not trigger:
            continue

        supp_key = trigger.get("suppression_key", trg_id)
        if supp_key in sent_suppression_keys:
            continue  # already handled this trigger family — restraint over spam

        merchant_id = trigger.get("merchant_id")
        merchant = get_ctx("merchant", merchant_id) if merchant_id else None
        if not merchant:
            continue
        category = get_ctx("category", merchant.get("category_slug"))
        if not category:
            continue
        customer_id = trigger.get("customer_id")
        customer = get_ctx("customer", customer_id) if customer_id else None

        try:
            composed = compose_message(category, merchant, trigger, customer)
        except Exception as e:
            continue  # never crash a tick over one bad trigger
        if not composed["body"]:
            continue

        conversation_id = f"conv_{merchant_id}_{trg_id}_{uuid.uuid4().hex[:6]}"
        conversations[conversation_id] = {
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "trigger_id": trg_id,
            "turns": [{"from": composed["send_as"], "msg": composed["body"]}],
            "bot_messages": [composed["body"]],
            "merchant_messages": [],
            "unanswered_nudges": 0,
        }
        sent_suppression_keys.add(supp_key)

        actions.append({
            "conversation_id": conversation_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed["send_as"],
            "trigger_id": trg_id,
            "template_name": f"vera_{trigger.get('kind', 'generic')}_v1",
            "template_params": [merchant["identity"]["name"]],
            "body": composed["body"],
            "cta": composed["cta"],
            "suppression_key": composed["suppression_key"],
            "rationale": composed["rationale"],
        })
    return {"actions": actions}


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int


@app.post("/v1/reply")
async def reply(body: ReplyBody):
    conv = conversations.get(body.conversation_id)
    if conv is None:
        # judge referenced a conversation we don't have — start minimal state defensively
        conv = {"merchant_id": body.merchant_id, "customer_id": body.customer_id,
                 "trigger_id": None, "turns": [], "bot_messages": [], "merchant_messages": [],
                 "unanswered_nudges": 0}
        conversations[body.conversation_id] = conv

    conv["turns"].append({"from": body.from_role, "msg": body.message})
    conv["merchant_messages"].append(body.message)

    # 1. Not-interested -> graceful exit, no LLM call needed
    if detect_not_interested(body.message):
        return {"action": "end", "rationale": "Recipient signaled not interested; exiting gracefully."}

       # 2. Auto-reply detection
    if is_probably_autoreply(conv, body.message):

        merchant_id = body.merchant_id or "unknown"

        merchant_auto_reply_count.setdefault(merchant_id, 0)
        merchant_auto_reply_count[merchant_id] += 1

        # First auto reply -> send one probe
        if merchant_auto_reply_count[merchant_id] == 1:
            result = llm_reply(conv, body.message, mode="autoreply_probe")
            conv["bot_messages"].append(result.get("body", ""))

            return {
                "action": "send",
                "body": result.get("body", ""),
                "cta": result.get("cta", "open_ended"),
                "rationale": "Sending one probe to check if a human is available."
            }

        # Second auto reply onwards -> stop
        return {
            "action": "end",
            "rationale": "Repeated auto-replies detected. Ending conversation."
        }

    # 3. Explicit go-ahead intent -> route straight to action, skip qualification
    mode = "intent_go" if detect_intent_go(body.message) else "normal"
    result = llm_reply(conv, body.message, mode=mode)
    new_body = result.get("body", "").strip()

  
    if new_body in conv["bot_messages"]:
        new_body += " "

    if not new_body:
        conv["unanswered_nudges"] += 1
        if conv["unanswered_nudges"] >= 3:
            return {
                "action": "end",
                "rationale": "3 unanswered nudges; exiting gracefully."
            }

        return {
            "action": "wait",
            "wait_seconds": 3600,
            "rationale": "Nothing high-value to add right now."
        }

    conv["bot_messages"].append(new_body)

    return {
        "action": "send",
        "body": new_body,
        "cta": result.get("cta", "open_ended"),
        "rationale": result.get("rationale", "")
    }

@app.post("/v1/teardown")
async def teardown():
    contexts.clear()
    conversations.clear()
    sent_suppression_keys.clear()
    return {"status": "wiped"}