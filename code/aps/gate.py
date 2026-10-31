"""The action gate: one check that decides whether a signed call may run an action.

"No signature, no action." Every action tool (book, later pay) on a business's MCP server asks
the gate before it does anything. The gate checks, in this order, and stops at the first
signature that is missing:

    1. the call       a signed call (aps/call.py) for this tool
    2. caller         a known user agent in the registry, whose seals verify (gold or blue;
                      grey has no verified seal, broken has a forged one)
    3. fresh          stamped within CALL_MAX_AGE_S (an old call is a recording)
    4. signature      signed with the key in the caller's registry record
    5. nonce          not seen before from this agent (a recent call played again)
    6. delegation     the user's key lets this agent act for them, with the tool's scope (e.g.
                      "book"; `pay` has no scope: paying is never delegated), not expired
    7. agreement      if the call carries one: this business's own signed Agreement, valid, unused
    8. approval       if the action needs one: the user's signed "approved" decision for this
                      action and this business, not used before, for exactly the amount: the
                      agreement's price, or else the total the business computed itself (the
                      caller's own figures are never trusted)
       or mandate     for a payment (Needs.mandate) without an approval: the user's signed
                      mandate (aps/mandate.py) for this agent, payee and purpose, at most
                      CHF 10 per payment and within its total (the gate counts what was paid)

The answer is a Verdict: ok, or the refusal reason (safe to send back; it names what is
missing, never a private limit), plus the list of checks passed for the wallet ("approval ✓
delegation ✓ agreement ✓"). Nothing is used up until the action succeeded: then the service
calls `commit(verdict)`, which marks the approval and the agreement as used and counts a
mandate payment. The nonce is used as soon as the signature verified, so a refused call cannot be retried as it is either.

Hook for an action tool (owner of node/server.py), e.g. `book`:

    gate = ActionGate(node_id, own_public_key, user_public_key, authorities, lookup, agreements)
    ...
    total = <room + own signed extras>, or None when args carry an agreement
    verdict = await gate.check_action(call, Needs("book", scope="book", approval=True, amount_chf=total))
    if not verdict.ok:
        return refuse(verdict.reason)
    ... confirm the booking ...
    gate.commit(verdict)

For `pay` (the business computes what it charges):

    Needs("pay", scope=None, approval=True, mandate=True, amount_chf=charge, purpose="city tax")
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from aps.approval import verify_decision
from aps.call import CALL_MAX_AGE_S, NonceBook, call_body, verify_call
from aps.delegation import verify_delegation
from aps.envelope import is_fresh
from aps.mandate import mandate_refusal
from aps.seals import evaluate_record

Lookup = Callable[[str], Awaitable[dict | None]]  # node_id -> registry record, or None
TRUSTED_TIERS = {"gold", "blue"}


@dataclass(frozen=True)
class Needs:
    """What an action tool requires of a call.

    `scope` is the delegation scope the tool needs (None: any valid delegation, e.g. `pay`,
    which is never a scope). With `approval`, the user's signed approval must be for this
    tool and this business, for exactly `amount_chf` (the total the business computed; an
    agreement in the call replaces it with the agreed price). With `mandate` as well, a
    user-signed mandate for `purpose` may stand in for the approval of a small payment.
    """

    tool: str
    scope: str | None
    approval: bool = False
    amount_chf: float | None = None
    mandate: bool = False
    purpose: str | None = None


@dataclass
class Verdict:
    """The gate's answer. `checks` lists the checks passed, in order, also when refused."""

    ok: bool
    reason: str = ""
    checks: list[str] = field(default_factory=list)
    caller: dict | None = None      # the caller's registry record
    approval: dict | None = None    # the user's signed decision, if the action needed one
    agreement: object | None = None  # the parsed Agreement, if the call carried one
    mandate: dict | None = None     # the user's signed mandate, if it stood in for an approval
    amount_chf: float | None = None  # the approved amount the action runs with


class Refused(Exception):
    """One check failed; the message is the reason sent back."""


class ActionGate:
    """Checks signed calls for one business. Keeps the used nonces and approvals in memory.

    `agreements` is the business's AgreementRedeemer (negotiation/agreement.py) or None if
    it does not negotiate; it is passed in so APS stays below the negotiation code.
    """

    def __init__(self, node_id: str, own_public_key: str, user_public_key: str, authorities: dict,
                 lookup: Lookup, agreements=None):
        self.node_id = node_id
        self.own_public_key = own_public_key
        self.user_public_key = user_public_key
        self.authorities = authorities
        self.lookup = lookup
        self.agreements = agreements
        self.nonces = NonceBook(CALL_MAX_AGE_S)
        self.used_approvals: set[str] = set()
        self.paid_with_mandate: dict[str, float] = {}  # mandate id -> CHF paid with it

    async def check_action(self, call: dict, needs: Needs, now: datetime | None = None) -> Verdict:
        """Run every check for this call; never raises for bad input, refuses instead."""
        verdict = Verdict(ok=False)
        try:
            await self._check(call, needs, now or datetime.now(timezone.utc), verdict)
        except Refused as refusal:
            verdict.reason = str(refusal)
            return verdict
        verdict.ok = True
        return verdict

    async def _check(self, call: dict, needs: Needs, now: datetime, verdict: Verdict) -> None:
        body = call_body(call)
        if body is None:
            raise Refused("the call is not a signed call")
        if body["tool"] != needs.tool:
            raise Refused(f"the call is for {body['tool']}, not {needs.tool}")

        caller = await self.lookup(body["agent_id"])
        if caller is None or caller.get("kind") != "user-agent":
            raise Refused("the caller is not a known user agent")
        tier = evaluate_record(caller, self.authorities)["tier"]
        if tier == "broken":
            raise Refused("the caller's seals do not verify")
        if tier not in TRUSTED_TIERS:
            raise Refused("the caller has no verified seal")
        verdict.caller = caller
        verdict.checks.append("caller")

        if not is_fresh(body["timestamp"], CALL_MAX_AGE_S, now):
            raise Refused("the call is outdated (possible replay)")
        if not verify_call(call, caller["public_key"], needs.tool, CALL_MAX_AGE_S, now):
            raise Refused("the call is not signed by the caller's key")
        verdict.checks.append("signature")
        if not self.nonces.use(body["agent_id"], body["nonce"], now):
            raise Refused("the call was already used (replayed nonce)")

        delegation = call.get("delegation") or caller.get("delegation") or {}
        if not verify_delegation(delegation, self.user_public_key, body["agent_id"], caller["public_key"],
                                 scope=needs.scope, now=now):
            what = needs.scope or "anything"
            raise Refused(f"the user has not delegated {what} to this agent (missing, expired or not signed by the user)")
        verdict.checks.append("delegation")

        args = body["args"]
        if args.get("agreement") is not None:
            verdict.agreement = self._agreement(args["agreement"], now)
            verdict.checks.append("agreement")
        if needs.approval and needs.mandate and args.get("approval") is None and args.get("mandate") is not None:
            verdict.mandate, verdict.amount_chf = self._mandate(args["mandate"], body["agent_id"], needs, now)
            verdict.checks.append("mandate")
        elif needs.approval:
            verdict.approval, verdict.amount_chf = self._approval(args.get("approval"), needs, verdict.agreement)
            verdict.checks.append("approval")

    def _mandate(self, mandate, agent_id: str, needs: Needs, now: datetime) -> tuple[dict, float]:
        """The user's signed mandate covers this payment: agent, payee, purpose, limits, time."""
        if needs.amount_chf is None:
            raise Refused("there is no amount to pay")
        paid = self.paid_with_mandate.get(mandate.get("mandate_id"), 0) if isinstance(mandate, dict) else 0
        reason = mandate_refusal(mandate, self.user_public_key, agent_id, self.node_id, needs.purpose,
                                 needs.amount_chf, paid, now)
        if reason is not None:
            raise Refused(reason)
        return mandate, needs.amount_chf

    def _agreement(self, envelope, now: datetime):
        """This business's own signed agreement, not expired and not booked before."""
        if self.agreements is None:
            raise Refused("this business does not negotiate, so there is no agreement to redeem")
        try:
            return self.agreements.check(envelope, now)
        except Exception as error:  # AgreementInvalid; its message is safe to send back
            raise Refused(str(error)) from None

    def _approval(self, approval, needs: Needs, agreement) -> tuple[dict, float]:
        """The user's signed approval for this action, this business and exactly this amount."""
        if not isinstance(approval, dict) or not verify_decision(approval, self.user_public_key):
            raise Refused("the approval is not signed by the user")
        if (approval["action"], approval["payee_node_id"], approval["decision"]) != (needs.tool, self.node_id, "approved"):
            raise Refused(f"the approval does not approve {needs.tool} with this business")
        if approval["approval_id"] in self.used_approvals:
            raise Refused("the approval was already used")
        amount = agreement.price_chf if agreement is not None else needs.amount_chf
        if amount is None:
            raise Refused("there is no amount to approve")
        if round(amount, 2) != round(approval["amount_chf"], 2):
            raise Refused(f"approved CHF {approval['amount_chf']:g} does not match the total CHF {amount:g}")
        return approval, amount

    def commit(self, verdict: Verdict) -> None:
        """The action succeeded: its approval and agreement cannot be used again."""
        if not verdict.ok:
            raise ValueError("only a passed verdict can be committed")
        if verdict.approval is not None:
            self.used_approvals.add(verdict.approval["approval_id"])
        if verdict.agreement is not None and self.agreements is not None:
            self.agreements.mark_used(verdict.agreement)
        if verdict.mandate is not None:
            mandate_id = verdict.mandate["mandate_id"]
            self.paid_with_mandate[mandate_id] = self.paid_with_mandate.get(mandate_id, 0) + verdict.amount_chf
