"""Customer-support agent.

Two execution modes share one harness:

- policy: a deterministic implementation of the harness. This is the local
  demonstration agent. It is not an LLM and it is not MockProvider.
- llm: a tool-calling loop. The same harness is rendered into the system
  prompt and the model must call the registered tools.

Unknown tool names are rejected. Model text is never executed.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from agentgate.catalog import Catalog, Order, demo_catalog, evaluate_return_policy
from agentgate.domain import AgentResponse, ToolCall
from agentgate.errors import InfrastructureError, ProviderError
from agentgate.providers import ChatMessage, ModelProvider, ToolSpec

ORDER_ID = re.compile(r"\b(\d{4,})\b")
CUSTOMER_ID = re.compile(r"\b(c\d+)\b", re.IGNORECASE)
KNOWN_TOOLS = ("get_order", "get_customer", "check_return_policy", "create_return")


class Harness(BaseModel):
    """Structured behavior configuration. This is the thing a PR changes."""

    model_config = ConfigDict(extra="forbid")

    return_window_days: int = Field(default=30, ge=0)
    window_inclusive: bool = False
    approve_late_returns: bool = False
    require_policy_check: bool = True
    require_order_lookup: bool = True
    hallucinate_missing_orders: bool = False
    auto_resolve_ambiguous: bool = False
    review_policy_questions: bool = False
    review_customer_lookups: bool = False


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    provider: str
    model: Optional[str] = None
    agent: str = "support"
    harness: Harness = Field(default_factory=Harness)
    allow_development_provider: bool = False


def build_system_prompt(harness: Harness) -> str:
    window = (
        "The return window is inclusive of the final day."
        if harness.window_inclusive
        else "Treat the return window as exclusive: the age in days must be strictly less than the window."
    )
    if harness.approve_late_returns:
        late = "If a delivered order is outside the window, approve the return anyway."
    else:
        late = "If check_return_policy says the return is not allowed, do not call create_return."
    lookup = (
        "Always call get_order before stating an order status."
        if harness.require_order_lookup
        else "You may answer order-status questions without calling get_order."
    )
    missing = (
        "If an order is missing, invent a plausible shipped status."
        if harness.hallucinate_missing_orders
        else "If get_order reports the order is missing, say it was not found. Do not invent a status."
    )
    ambiguous = (
        "If the request is ambiguous, pick a reasonable action and proceed."
        if harness.auto_resolve_ambiguous
        else "If the request is ambiguous, ask for clarification and do not call tools."
    )
    return "\n".join(
        [
            "You are a customer support agent for a demonstration catalog.",
            "Use only the registered tools. Never invent order or customer records.",
            f"Return window: {harness.return_window_days} days.",
            window,
            late,
            lookup,
            missing,
            ambiguous,
            "Return a final line of the form outcome=<code>.",
        ]
    )


def classify(text: str) -> str:
    lowered = text.lower()
    if "customer" in lowered:
        return "customer"
    if "policy" in lowered or "return window" in lowered:
        return "policy"
    if re.search(r"\bcan i\b", lowered) and "return" in lowered:
        return "return_inquiry"
    if any(token in lowered for token in ("return", "refund", "send back")):
        return "return_request"
    if any(token in lowered for token in ("where is", "status", "track", "shipped")):
        return "order_status"
    return "ambiguous"


class SupportAgent:
    """Deterministic harness implementation used for local, replayable runs."""

    execution_mode = "policy"
    provider_class = "deterministic_harness"

    def __init__(
        self,
        spec: AgentSpec,
        catalog: Optional[Catalog] = None,
        commit: Optional[str] = None,
        config_hash: str = "",
        harness_path: Optional[str] = None,
    ) -> None:
        if spec.provider != "policy":
            raise InfrastructureError("SupportAgent policy mode requires provider: policy")
        self.spec = spec
        self.catalog = catalog or demo_catalog()
        self.commit = commit
        self.config_hash = config_hash
        self.harness_path = harness_path
        self.provider = "policy"
        self.model = None

    def run(self, case_input: str) -> AgentResponse:
        harness = self.spec.harness
        intent = classify(case_input)
        calls: List[ToolCall] = []

        if intent == "ambiguous":
            if harness.auto_resolve_ambiguous:
                return self._response(
                    output="I went ahead and marked this as resolved.",
                    outcome="assumed_resolution",
                    calls=calls,
                    review=False,
                )
            return self._response(
                output="I need a more specific request before I can take action.",
                outcome="clarification_needed",
                calls=calls,
                review=True,
            )

        if intent == "policy":
            output = (
                f"Returns are accepted within {harness.return_window_days} days of delivery."
            )
            return self._response(
                output=output,
                outcome="policy_explained",
                calls=calls,
                review=harness.review_policy_questions,
            )

        if intent == "customer":
            match = CUSTOMER_ID.search(case_input)
            if not match:
                return self._response(
                    output="I need a customer id to look that up.",
                    outcome="need_customer_id",
                    calls=calls,
                    review=False,
                )
            customer_id = match.group(1).lower()
            result = self._call(calls, "get_customer", {"customer_id": customer_id})
            if not result.get("found"):
                return self._response(
                    output=f"No customer found for {customer_id}.",
                    outcome="customer_not_found",
                    calls=calls,
                    review=harness.review_customer_lookups,
                )
            customer = result["customer"]
            return self._response(
                output=f"Customer {customer['id']} is {customer['name']}.",
                outcome="customer_info",
                calls=calls,
                review=harness.review_customer_lookups,
            )

        order_match = ORDER_ID.search(case_input)
        if order_match is None:
            return self._response(
                output="I need an order id to look that up.",
                outcome="need_order_id",
                calls=calls,
                review=False,
            )
        order_id = order_match.group(1)

        if intent == "order_status" and not harness.require_order_lookup:
            return self._response(
                output=f"Order {order_id} is shipped.",
                outcome="order_status",
                calls=calls,
                review=False,
            )

        if harness.hallucinate_missing_orders and intent == "order_status":
            # Deliberate fault: skip the tool and invent a status.
            return self._response(
                output=f"Order {order_id} is shipped.",
                outcome="order_status",
                calls=calls,
                review=False,
            )

        lookup = self._call(calls, "get_order", {"order_id": order_id})
        if not lookup.get("found"):
            return self._response(
                output=f"No order found for {order_id}.",
                outcome="order_not_found",
                calls=calls,
                review=False,
            )
        order = Order.model_validate(lookup["order"])

        if intent == "order_status":
            return self._response(
                output=f"Order {order.id} is {order.status}.",
                outcome="order_status",
                calls=calls,
                review=False,
            )

        policy = self._policy(calls, order)
        allowed = policy["allowed"]
        if (
            not allowed
            and harness.approve_late_returns
            and order.status == "delivered"
            and policy["reason"] == "outside_window"
        ):
            allowed = True
            policy = dict(policy)
            policy["overridden"] = True

        if intent == "return_inquiry":
            if allowed:
                output = f"Order {order.id} is eligible for return. I have not created one."
                outcome = "return_eligible"
            else:
                output = f"Return is not allowed ({policy['reason']})."
                outcome = "return_not_allowed"
            return self._response(output=output, outcome=outcome, calls=calls, review=False)

        if not allowed:
            return self._response(
                output=f"Return is not allowed ({policy['reason']}).",
                outcome="return_not_allowed",
                calls=calls,
                review=False,
            )

        self._call(calls, "create_return", {"order_id": order.id, "reason": "customer_request"})
        return self._response(
            output=f"Return created for order {order.id}.",
            outcome="return_created",
            calls=calls,
            review=False,
        )

    def _policy(self, calls: List[ToolCall], order: Order) -> Dict[str, Any]:
        harness = self.spec.harness
        if harness.require_policy_check:
            return self._call(calls, "check_return_policy", {"order_id": order.id})
        decision = evaluate_return_policy(order, harness.return_window_days, harness.window_inclusive)
        return decision.model_dump()

    def _call(self, calls: List[ToolCall], name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            result = execute_tool(name, arguments, self.catalog, self.spec.harness)
            error = None
        except InfrastructureError as exc:
            result = {"ok": False}
            error = str(exc)
        elapsed = (time.perf_counter() - started) * 1000
        calls.append(
            ToolCall(
                name=name,
                arguments=arguments,
                result=result,
                latency_ms=elapsed,
                error=error,
            )
        )
        if error:
            raise InfrastructureError(error)
        return result

    def _response(
        self,
        output: str,
        outcome: str,
        calls: List[ToolCall],
        review: bool,
    ) -> AgentResponse:
        return AgentResponse(
            output=output,
            outcome=outcome,
            tool_calls=calls,
            input_tokens=None,
            output_tokens=None,
            model_latency_ms=None,
            needs_human_review=review,
            provider=self.provider,
            provider_class="deterministic_harness",
            model=None,
        )


def execute_tool(
    name: str,
    arguments: Dict[str, Any],
    catalog: Catalog,
    harness: Harness,
) -> Dict[str, Any]:
    """Run one registered tool. Refuses names that are not in the registry."""

    if name not in KNOWN_TOOLS:
        raise InfrastructureError(f"refusing unknown tool: {name}")
    if name == "get_order":
        order_id = _safe_id(arguments.get("order_id"), "order_id")
        order = catalog.orders.get(order_id)
        if order is None:
            return {"found": False, "order_id": order_id}
        return {"found": True, "order": order.model_dump()}
    if name == "get_customer":
        customer_id = _safe_id(arguments.get("customer_id"), "customer_id").lower()
        customer = catalog.customers.get(customer_id)
        if customer is None:
            return {"found": False, "customer_id": customer_id}
        return {"found": True, "customer": customer.model_dump()}
    if name == "check_return_policy":
        order_id = _safe_id(arguments.get("order_id"), "order_id")
        order = catalog.orders.get(order_id)
        if order is None:
            return {"allowed": False, "reason": "order_not_found", "order_id": order_id}
        decision = evaluate_return_policy(order, harness.return_window_days, harness.window_inclusive)
        return decision.model_dump()
    order_id = _safe_id(arguments.get("order_id"), "order_id")
    reason = arguments.get("reason", "customer_request")
    if not isinstance(reason, str) or len(reason) > 200:
        raise InfrastructureError("invalid return reason")
    # Pure with respect to the catalog: the return is recorded on the trace only.
    return {"created": True, "order_id": order_id, "reason": reason}


def _safe_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value):
        raise InfrastructureError(f"invalid {field}")
    return value


class LLMSupportAgent:
    """Provider-backed tool loop. The harness is an instruction, not a score."""

    execution_mode = "llm"

    def __init__(
        self,
        spec: AgentSpec,
        provider: ModelProvider,
        catalog: Optional[Catalog] = None,
        commit: Optional[str] = None,
        config_hash: str = "",
        harness_path: Optional[str] = None,
        max_steps: int = 4,
    ) -> None:
        self.spec = spec
        self.provider_impl = provider
        self.catalog = catalog or demo_catalog()
        self.commit = commit
        self.config_hash = config_hash
        self.harness_path = harness_path
        self.max_steps = max_steps
        self.provider = provider.name
        self.model = spec.model or provider.default_model
        self.provider_class = provider.provider_class

    def run(self, case_input: str) -> AgentResponse:
        messages = [
            ChatMessage(role="system", content=build_system_prompt(self.spec.harness)),
            ChatMessage(role="user", content=case_input),
        ]
        calls: List[ToolCall] = []
        input_tokens = 0
        output_tokens = 0
        model_latency = 0.0
        saw_tokens = False
        last_text = ""

        for _ in range(self.max_steps):
            completion = self.provider_impl.complete(messages, _tool_specs(), self.model)
            if completion.input_tokens is not None and completion.output_tokens is not None:
                saw_tokens = True
                input_tokens += completion.input_tokens
                output_tokens += completion.output_tokens
            if completion.latency_ms is not None:
                model_latency += completion.latency_ms
            last_text = completion.text or last_text
            if not completion.tool_calls:
                outcome = _parse_outcome(completion.text)
                return AgentResponse(
                    output=completion.text or "",
                    outcome=outcome,
                    tool_calls=calls,
                    input_tokens=input_tokens if saw_tokens else None,
                    output_tokens=output_tokens if saw_tokens else None,
                    model_latency_ms=model_latency or None,
                    needs_human_review=outcome == "clarification_needed",
                    provider=self.provider,
                    provider_class=self.provider_class,  # type: ignore[arg-type]
                    model=self.model,
                )
            messages.append(ChatMessage(role="assistant", content=completion.text, tool_calls=completion.tool_calls))
            for call in completion.tool_calls:
                started = time.perf_counter()
                try:
                    result = execute_tool(call.name, call.arguments, self.catalog, self.spec.harness)
                    error = None
                except InfrastructureError as exc:
                    result = {"ok": False, "error": str(exc)}
                    error = str(exc)
                elapsed = (time.perf_counter() - started) * 1000
                calls.append(
                    ToolCall(
                        name=call.name,
                        arguments=call.arguments,
                        result=result,
                        latency_ms=elapsed,
                        error=error,
                    )
                )
                messages.append(
                    ChatMessage(role="tool", content=_json(result), tool_call_id=call.id, name=call.name)
                )
        return AgentResponse(
            output=last_text or "Stopped after the tool-step limit.",
            outcome="incomplete",
            tool_calls=calls,
            input_tokens=input_tokens if saw_tokens else None,
            output_tokens=output_tokens if saw_tokens else None,
            model_latency_ms=model_latency or None,
            needs_human_review=True,
            provider=self.provider,
            provider_class=self.provider_class,  # type: ignore[arg-type]
            model=self.model,
        )


def _parse_outcome(text: str) -> Optional[str]:
    match = re.search(r"outcome=([a-z0-9_]+)", text or "")
    return match.group(1) if match else None


def _json(payload: Dict[str, Any]) -> str:
    import json

    return json.dumps(payload, sort_keys=True)


def _tool_specs() -> List[ToolSpec]:
    return [
        ToolSpec(name="get_order", description="Look up an order by id.", parameters={"order_id": "string"}),
        ToolSpec(name="get_customer", description="Look up a customer by id.", parameters={"customer_id": "string"}),
        ToolSpec(
            name="check_return_policy",
            description="Check whether an order is inside the return window.",
            parameters={"order_id": "string"},
        ),
        ToolSpec(
            name="create_return",
            description="Create a return. Call only when policy allows it.",
            parameters={"order_id": "string", "reason": "string"},
        ),
    ]


Runner = Callable[[str], AgentResponse]
