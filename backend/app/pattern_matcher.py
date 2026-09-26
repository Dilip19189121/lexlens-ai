"""
pattern_matcher.py — Local regex engine for known risky clauses (Phase 2).

The "fast lane" of the hybrid risk engine: scans contract text against
patterns distilled from the reference datasets in /datasets (all kept local,
never committed — see prd.md section 7):

  CUAD v1 (datasets/CUAD/CUAD_v1.json)
      510 contracts x 41 annotated clause categories. Its taxonomy names
      (Non-Compete, Cap On Liability, Liquidated Damages, Renewal Term,
      Notice Period To Terminate Renewal, Ip Ownership Assignment, ...) drive
      the clause names below, and its annotated quotes shaped the regexes.
  UnfairToS (datasets/UnfairToS/*.parquet, 5,532 ToS snippets)
      Its unfair-clause vocabulary ("sole discretion", "at any time",
      "without notice", "no refund", unilateral-change phrasing) feeds the
      aggravator keywords and rule patterns.
  MAUD (datasets/MAUD/MAUD_train.csv, M&A agreement clauses)
      Public-company acquisition language (exclusivity/no-shop, change of
      control, governing law, assignment) — the consumer-hostile variants of
      those clauses reuse the same core constructions.

Design goals:
  - Zero network calls, zero API cost, results in milliseconds.
  - Every finding quotes text EXACTLY as it appears in the document (the
    anti-hallucination rule from prd.md section 8 is trivially satisfied).
  - analyzer.py merges these findings with LLM output — the matcher catches
    known patterns; the LLM catches everything else.

Pattern syntax (one unified mini-language, compiled by _compile_pattern):
  - Patterns are matched with re.IGNORECASE against the raw document text.
  - A literal space in a pattern matches ANY run of whitespace and/or commas
    (PDF extraction wraps lines and inserts punctuation unpredictably).
  - '-' matches a hyphen, en/em dash, or a whitespace run (all optional).
  - "'" matches an apostrophe, right single quote, or nothing.
  - Standard regex constructs ((?:...), [classes], {n,m}, .{0,40} gaps) pass
    through unchanged — write an optional gap GLUED to its neighbours, e.g.
    "liability(?:.{0,90})?exceed the fees paid".
"""

import re
from typing import List, Pattern, Tuple

from .schemas import ClauseFinding

# Pre-compiled at import so a bad regex surfaces at startup, not per-request.
_RISK_PATTERNS: List[dict] = []


def _compile_pattern(pattern: str) -> Pattern:
    """Compile a rulebook pattern into a punctuation-tolerant regex."""
    out: List[str] = []
    i, n = 0, len(pattern)
    in_class = False
    in_brace = False  # inside a {n,m} quantifier — pass raw, don't touch commas
    while i < n:
        ch = pattern[i]
        if ch == "\\" and i + 1 < n:  # escaped pair passes through raw
            out.append(pattern[i : i + 2])
            i += 2
            continue
        if in_class:
            out.append(ch)
            if ch == "]":
                in_class = False
            i += 1
            continue
        if in_brace:
            out.append(ch)
            if ch == "}":
                in_brace = False
            i += 1
            continue
        if ch == "[":
            in_class = True
            out.append(ch)
            i += 1
            continue
        if ch == "{":
            in_brace = True
            out.append(ch)
            i += 1
            continue
        if ch == " ":  # whitespace run in pattern -> flexible separator
            while i < n and pattern[i] == " ":
                i += 1
            out.append(r"[\s,]+")
            continue
        if ch == ",":
            out.append(r"[\s,]*")
            i += 1
            continue
        if ch == "'":
            out.append("['\u2019\u02bc]?")
            i += 1
            continue
        if ch == "-":  # hyphen / en dash / em dash / none
            out.append(r"(?:\s*[\u2010-\u2015]\s*|\s+)?")
            i += 1
            continue
        if ch == '"':
            out.append("[\u201c\u201d\"]?")
            i += 1
            continue
        out.append(ch)  # letters and regex metachars pass through raw
        i += 1
    return re.compile("".join(out), re.IGNORECASE)


def rule(name, risk, patterns, summary, action, category, source):
    """Register one rule; stored as a plain dict to keep this module declarative."""
    _RISK_PATTERNS.append(
        {
            "clause_name": name,
            "risk_level": risk,
            "patterns": [_compile_pattern(p) for p in patterns],
            "plain_summary": summary,
            "action_step": action,
            "category": category,
            "source": source,
        }
    )


# ── The rulebook ─────────────────────────────────────────────────────────────

# 1. Termination for convenience with no/short notice — CUAD "Termination For
#    Convenience" + "Notice Period To Terminate Renewal"; UnfairToS label 1.
rule(
    "Termination Without Notice",
    "HIGH",
    [
        r"terminate this agreement at any time for any reason",
        r"terminate(?:.{0,40})?at any time without notice",
        r"at any time for any reason with zero",
        r"at any time with or without cause",
        r"terminate this agreement at any time",
    ],
    "The other party can end this contract immediately, for any reason, "
    "without warning or compensation.",
    "Negotiate a minimum written notice period (14-30 days) and payment for "
    "all work completed before termination.",
    "Termination",
    "CUAD + UnfairToS",
)

# 2. Payment withheld at sole discretion / satisfaction clauses — UnfairToS
#    vocabulary ("sole discretion"); the core freelancer cash-flow risk.
rule(
    "Discretionary Payment Withholding",
    "HIGH",
    [
        r"withhold payment at (?:its|their|his|her) sole discretion",
        r"withhold(?:.{0,20})?payment(?:.{0,60})?sole discretion",
        r"until(?:.{0,30})?fully satisfied",
        r"not (?:required|obligated) to (?:provide|issue) (?:a[\s,]+|any[\s,]+)?refund",
        r"no refunds? (?:will be provided|for any reason)",
    ],
    "Payment can be refused or delayed indefinitely at the other party's "
    "sole discretion — you may never get paid for completed work.",
    "Ask for objective acceptance criteria, a fixed payment deadline "
    "(net-30 or better), and a narrow definition of when withholding is allowed.",
    "Payment",
    "UnfairToS",
)

# 3. Net payment terms of 60+ days — unusually long for freelancers/SMBs.
rule(
    "Extended Payment Terms",
    "MEDIUM",
    [
        r"net[ \-]?(?:[6-9][0-9]|1[0-9][0-9])",
    ],
    "Payment is due two or more months after invoicing, which can starve "
    "your cash flow.",
    "Counter with net-30 (or net-45) terms and late-payment interest.",
    "Payment",
    "UnfairToS",
)

# 4. Retroactive / overbroad IP assignment — CUAD "Ip Ownership Assignment";
#    pre-existing work being assigned away is the red flag.
rule(
    "Broad IP Assignment",
    "HIGH",
    [
        r"assigns? to [a-z .]{1,40} all right title and interest",
        r"assigns? all right title and interest",
        r"in all work product created prior to",
        r"all intellectual property(?:.{0,60})?created (?:prior to|before)",
        r"work made for hire",
    ],
    "You may be signing away ownership of work — even work you created "
    "before this agreement started.",
    "Limit the assignment to work created under this agreement, and "
    "explicitly carve out pre-existing IP and portfolio rights.",
    "Intellectual Property",
    "CUAD",
)

# 5. Perpetual / irrevocable licenses — CUAD "Irrevocable Or Perpetual License".
rule(
    "Perpetual / Irrevocable License",
    "MEDIUM",
    [
        r"perpetual irrevocable",
        r"irrevocable perpetual",
        r"worldwide royalty[ \-]?free perpetual",
        r"sublicensable and transferable license",
    ],
    "The license granted never expires and cannot be taken back, even after "
    "the contract ends.",
    "Add an end date (matching the contract term) and scope the license to "
    "specific uses.",
    "Licensing",
    "CUAD",
)

# 6. Auto-renewal (evergreen) clauses — CUAD "Renewal Term" + "Notice Period
#    To Terminate Renewal".
rule(
    "Auto-Renewal Trap",
    "HIGH",
    [
        r"renews automatically for successive",
        r"automatically renews for successive",
        r"shall (?:be )?automatically renew",
        r"renews? automatically",
        r"auto-renewal",
    ],
    "This contract renews itself automatically for another term unless you "
    "actively cancel — miss the window and you are locked in again.",
    "Diary the cancellation deadline now, and negotiate written-notice "
    "cancellation (e.g., 30 days) with no special delivery method.",
    "Renewal",
    "CUAD",
)

# 7. Cancellation via burdensome methods — the consumer-hostile tell.
rule(
    "Burdensome Cancellation Method",
    "MEDIUM",
    [
        r"cancels? in person",
        r"cancellation(?:.{0,40})?certified mail",
        r"notice(?:.{0,60})?certified mail",
        r"written notice by registered mail",
    ],
    "Cancelling requires an awkward method (in person, certified mail) "
    "designed to make you give up.",
    "Require cancellation by ordinary email or through an online account.",
    "Renewal",
    "UnfairToS",
)

# 8. Liability caps — CUAD "Cap On Liability"; month-based caps are tiny.
rule(
    "Low Liability Cap",
    "MEDIUM",
    [
        r"liability(?:.{0,90})?exceed the fees paid",
        r"liability(?:.{0,90})?exceed the amounts paid",
        r"liability(?:.{0,120})?shall not exceed the (?:total )?fees",
        r"aggregate liability(?:.{0,60})?shall not exceed",
    ],
    "If something goes badly wrong, any payout is capped at recent fees — "
    "often far less than the actual damage.",
    "Negotiate a cap of at least 12 months of fees, with carve-outs for "
    "willful misconduct, gross negligence, and IP infringement.",
    "Liability",
    "CUAD",
)

# 9. Uncapped liability — CUAD "Uncapped Liability".
rule(
    "Uncapped Liability (One-Sided)",
    "HIGH",
    [
        r"no limitation of liability",
        r"uncapped liability",
        r"liability(?:.{0,50})?unlimited",
        r"unlimited liability",
    ],
    "One party faces unlimited financial exposure if something goes wrong.",
    "Insist on a mutual liability cap and a list of excluded damages.",
    "Liability",
    "CUAD",
)

# 10. Indemnification loaded onto the individual.
rule(
    "One-Way Indemnification",
    "HIGH",
    [
        r"you(?:.{0,30})?indemnify and hold",
        r"indemnify and hold harmless",
        r"indemnify defend and hold harmless",
        r"defend and hold harmless against any and all claims",
    ],
    "You must cover the other party's legal costs and damages for almost "
    "any claim, while they owe you nothing in return.",
    "Make indemnification mutual and limit it to claims caused by your own "
    "breach or negligence.",
    "Liability",
    "CUAD + UnfairToS",
)

# 11. Non-compete — CUAD "Non-Compete".
rule(
    "Non-Compete Restriction",
    "HIGH",
    [
        r"shall not directly or indirectly (?:engage|compete|participate|be employed)",
        r"directly or indirectly compete",
        r"non-compet(?:e|ition)",
        r"covenant not to compete",
        r"agree(?:s|ment)? not to compete",
    ],
    "You are restricted from working in your own field after this contract "
    "ends, which can block your next job or clients.",
    "Push back on scope/duration/geography, or convert it into a narrow "
    "non-solicit limited to actual clients you served.",
    "Restrictive Covenants",
    "CUAD",
)

# 12. Non-solicit — CUAD "No-Solicit Of Customers" / "No-Solicit Of Employees".
rule(
    "Non-Solicitation Restriction",
    "MEDIUM",
    [
        r"shall not (?:directly or indirectly )?solicit",
        r"not (?:hire|recruit|solicit) any (?:employee|customer|client)",
        r"agree(?:s)? not to solicit",
        r"non-solicitation",
    ],
    "You cannot approach the company's staff or clients after leaving, "
    "which may limit how you work next.",
    "Limit it to people you actually interacted with, and add a duration "
    "cap (12 months or less).",
    "Restrictive Covenants",
    "CUAD",
)

# 13. Exclusivity — CUAD "Exclusivity"; MAUD no-shop provisions reuse the
#     "shall not solicit/negotiate with third parties" construction.
rule(
    "Exclusivity / No-Shop",
    "HIGH",
    [
        r"shall not (?:solicit|initiate|encourage|facilitate) any (?:third party|person|other party|entity)",
        r"shall not negotiate with any third party",
        r"no-shop",
        r"exclusive dealing",
        r"shall not enter into any agreement with any third party",
    ],
    "You are barred from working with, negotiating with, or selling to "
    "anyone else during the deal/contract period.",
    "Narrow it to genuinely confidential negotiations, and add an expiry "
    "date and carve-outs for existing customers.",
    "Exclusivity",
    "CUAD + MAUD",
)

# 14. Unilateral modification — UnfairToS label 2 ("we may make changes to
#     this agreement ... at any time").
rule(
    "Unilateral Contract Changes",
    "HIGH",
    [
        r"may (?:modify|change|amend|revise|update) (?:this agreement|these terms|this contract|the terms) at any time",
        r"reserves the right to (?:modify|change|amend|update) (?:this agreement|these terms|the terms) at any time",
        r"we may make changes to this agreement",
        r"(?:may be|is) (?:amended|modified|changed|revised) at any time",
        r"may (?:modify|change|amend|revise|update) or discontinue",
    ],
    "The other party can rewrite the contract whenever it wants, without "
    "your agreement.",
    "Require written mutual consent (countersignature) for any amendment, "
    "and advance notice of changes.",
    "Amendment",
    "UnfairToS",
)

# 15. Unilateral service/feature changes — UnfairToS label 3.
rule(
    "One-Sided Service Changes",
    "MEDIUM",
    [
        r"may (?:add|remove|suspend|discontinue)(?:.{0,50})?(?:features?|services?|functionality)",
        r"reserves the right to (?:remove|discontinue|suspend) (?:features?|services?|content)",
        r"delete any content in whole or in part",
        r"remove or (?:delete|disable) (?:any )?content",
    ],
    "Features or content you rely on can be removed at any moment, with no "
    "compensation or remedy.",
    "Ask for notice before material feature removal and a pro-rated refund "
    "for prepaid services.",
    "Service Levels",
    "UnfairToS",
)

# 16. Arbitration + class-action waiver — UnfairToS label 7.
rule(
    "Binding Arbitration & Class-Action Waiver",
    "HIGH",
    [
        r"binding arbitration",
        r"arbitration clause and class action waiver",
        r"class action waiver",
        r"waive(?:.{0,40})?class action",
        r"shall be (?:resolved|settled) by (?:binding )?arbitration",
    ],
    "You give up your right to sue in court or join a class action; "
    "disputes go to a private arbitrator chosen under the contract's terms.",
    "Negotiate a carve-out for small-claims court, and confirm the "
    "arbitration venue/cost rules before agreeing.",
    "Dispute Resolution",
    "UnfairToS",
)

# 17. Forced jurisdiction / venue — CUAD "Governing Law"; UnfairToS labels 5/6.
rule(
    "Inconvenient Governing Law / Venue",
    "MEDIUM",
    [
        r"exclusive jurisdiction (?:of|to|in|lies with) the courts",
        r"irrevocably agree that the courts",
        r"submit to the (?:exclusive )?jurisdiction of the courts",
        r"shall have exclusive jurisdiction",
    ],
    "Any dispute must be fought under distant law or in a faraway court, "
    "making it expensive for you to enforce your rights.",
    "Request your home jurisdiction, or at minimum a neutral venue with "
    "each side bearing its own costs.",
    "Dispute Resolution",
    "CUAD + UnfairToS",
)

# 18. No-charge fee changes — UnfairToS "sole discretion" pricing.
rule(
    "Unilateral Price Changes",
    "MEDIUM",
    [
        r"reserves the right to charge fees(?:.{0,60})?sole discretion",
        r"may (?:change|increase|adjust) (?:the )?(?:fees|prices|charges|rates) at any time",
        r"change (?:its|their) fees at any time",
    ],
    "Prices or fees can be raised at any time without renegotiation.",
    "Cap annual increases (e.g., CPI or a fixed percentage) and require "
    "30 days' written notice before any change.",
    "Payment",
    "UnfairToS",
)

# 19. Content / data deletion rights — UnfairToS label 3.
rule(
    "Content Removal Without Recourse",
    "MEDIUM",
    [
        r"reserves the right to (?:review and )?remove (?:any )?content",
        r"may remove or (?:delete|disable) (?:any )?content",
        r"without liability to you(?:.{0,80})?remove(?:.{0,40})?content",
    ],
    "Your content can be deleted without warning and without any appeal "
    "or refund.",
    "Require notice and a cure period before removal of non-infringing "
    "content.",
    "Data & Content",
    "UnfairToS",
)

# 20. Assignment of the contract to third parties — CUAD "Change Of Control"
#     / MAUD assignment language.
rule(
    "Assignment To Third Parties",
    "MEDIUM",
    [
        r"may assign this agreement(?:.{0,60})?without (?:your|prior written) consent",
        r"freely assign this agreement",
        r"transfer(?:.{0,40})?rights and obligations(?:.{0,60})?without consent",
    ],
    "Your contract can be handed to an unknown third company without "
    "asking you.",
    "Require consent for assignment, or at least notice plus the right to "
    "terminate if the new party changes the deal.",
    "Assignment",
    "CUAD + MAUD",
)

# 21. Covenant not to sue — CUAD category, direct name.
rule(
    "Covenant Not To Sue",
    "MEDIUM",
    [
        r"covenant not to sue",
        r"agree(?:s)? not to sue",
        r"waives? any right to sue",
    ],
    "You promise never to bring certain lawsuits, even if you later "
    "discover you were harmed.",
    "Delete this clause, or limit it to settled disputes only.",
    "Dispute Resolution",
    "CUAD",
)

# 22. Liquidated damages / penalties — CUAD "Liquidated Damages".
rule(
    "Liquidated Damages / Penalties",
    "MEDIUM",
    [
        r"liquidated damages",
        r"penalty of [a-z$0-9]+",
        r"shall pay (?:as a )?penalty",
        r"late fee of",
        r"late charge of",
    ],
    "Specific cash penalties are pre-agreed for certain breaches, which "
    "can exceed your actual loss.",
    "Ensure any amount reflects a reasonable estimate of real damages, and "
    "make it mutual.",
    "Damages",
    "CUAD",
)

# 23. Most-favored-nation — CUAD "Most Favored Nation".
rule(
    "Most Favored Nation Clause",
    "LOW",
    [
        r"most favored nation",
        r"most-favored-nation",
        r"no less favorable than(?:.{0,60})?provided to any",
    ],
    "If the vendor gives anyone a better deal, you must match it — this "
    "can pressure you into unplanned discounts.",
    "Scope it to identical volumes/terms and add a notice period before it "
    "triggers.",
    "Pricing",
    "CUAD",
)

# 24. Audit rights — CUAD "Audit Rights".
rule(
    "Open-Ended Audit Rights",
    "LOW",
    [
        r"right to (?:inspect|audit) (?:your )?(?:records|books|accounts|facilities)",
        r"audits? of (?:your )?(?:books|records|accounts)",
        r"may audit(?:.{0,60})?records",
    ],
    "The other party can inspect your records, potentially without clear "
    "limits on frequency or scope.",
    "Limit audits to once per year, on reasonable notice, during business "
    "hours, and at the auditor's expense.",
    "Compliance",
    "CUAD",
)

# 25. Anti-assignment protecting the drafter only — CUAD "Anti-Assignment".
rule(
    "One-Sided Anti-Assignment",
    "MEDIUM",
    [
        r"shall not assign (?:or transfer )?this agreement",
        r"may not assign or transfer this agreement",
        r"shall not assign or transfer",
    ],
    "You cannot transfer this contract to anyone (e.g., a buyer of your "
    "business), while the other side often can.",
    "Make the restriction mutual, and allow assignment to affiliates or a "
    "successor in interest.",
    "Assignment",
    "CUAD",
)

# 26. Non-disparagement — CUAD "Non-Disparagement".
rule(
    "Non-Disparagement Gag",
    "MEDIUM",
    [
        r"non-disparagement",
        r"shall not disparage",
        r"shall not (?:make any negative|criticize)",
        r"shall not in any way malign",
    ],
    "You are silenced from publicly criticizing the other party — even "
    "truthfully — which can hide real problems from others.",
    "Limit it to false statements only, make it mutual, and preserve "
    "legally protected speech rights.",
    "Restrictive Covenants",
    "CUAD",
)

# 27. Unconditional waiver of liability ("no liability to you") — UnfairToS
#     label 0 vocabulary.
rule(
    "Total Liability Disclaimer",
    "HIGH",
    [
        r"shall have no liability to you",
        r"shall have no liability whatsoever",
        r"assumes? no liability whatsoever",
        r"in no event shall(?:.{0,80})?be liable (?:to you|for any)",
        r"disclaims? all warranties(?:.{0,80})?express or implied",
    ],
    "The other party disclaims essentially all responsibility for harm "
    "caused by its service or product.",
    "Strike the blanket disclaimer, or limit it to non-core services; "
    "keep liability for negligence and data breaches.",
    "Liability",
    "UnfairToS",
)


# ── Matching & span helpers ──────────────────────────────────────────────────

def _sentence_bounds(text: str, start: int, end: int) -> Tuple[int, int]:
    """Widen a match span to sentence-ish boundaries (period or newline)."""
    head = max(text.rfind(".", 0, start), text.rfind("\n", 0, start))
    s = head + 1 if head != -1 else 0
    tail = text.find(".", end)
    e = min(tail + 1, len(text)) if tail != -1 and tail < end + 200 else min(end + 120, len(text))
    return s, e


def _sentence_quote(text: str, start: int, end: int) -> str:
    """Verbatim quote for a match, widened to sentence boundaries."""
    s, e = _sentence_bounds(text, start, end)
    quote = re.sub(r"\s+", " ", text[s:e]).strip()
    return quote[:450]


def match_with_spans(text: str) -> Tuple[List[ClauseFinding], List[Tuple[int, int]]]:
    """Run every rule against the text.

    Returns (findings, match_spans). One finding per rule — the same clause
    family shouldn't spam the dashboard with duplicates. Spans are the raw
    regex match positions, used by analyzer.py to decide what still needs
    the LLM.
    """
    findings: List[ClauseFinding] = []
    spans: List[Tuple[int, int]] = []
    for r in _RISK_PATTERNS:
        for rx in r["patterns"]:
            m = rx.search(text)
            if m:
                findings.append(
                    ClauseFinding(
                        clause_name=r["clause_name"],
                        risk_level=r["risk_level"],
                        quote=_sentence_quote(text, m.start(), m.end()),
                        plain_summary=r["plain_summary"],
                        action_step=r["action_step"],
                    )
                )
                spans.append((m.start(), m.end()))
                break
    return findings, spans


def match_text(text: str) -> List[ClauseFinding]:
    """Findings only — convenience wrapper over match_with_spans."""
    return match_with_spans(text)[0]


def uncovered_text(text: str, spans: List[Tuple[int, int]]) -> str:
    """Return the text NOT claimed by any match span.

    Match spans are first widened to sentence boundaries so the LLM lane
    receives whole sentences (never mid-sentence fragments). This is the
    text that actually needs LLM analysis; everything else was resolved
    locally at zero API cost. No length threshold: dropping even short
    fragments could silently skip a real clause.
    """
    widened = sorted(_sentence_bounds(text, s, e) for s, e in spans)

    parts: List[str] = []
    pos = 0
    for s, e in widened:
        if s > pos:
            seg = text[pos:s].strip()
            if seg:
                parts.append(seg)
        pos = max(pos, e)
    tail = text[pos:].strip()
    if tail:
        parts.append(tail)
    return "\n\n".join(parts)


def rules_count() -> int:
    """Number of registered rules (for /health diagnostics)."""
    return len(_RISK_PATTERNS)
