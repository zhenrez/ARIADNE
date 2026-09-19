# The Great Work — Global Project Rules

These rules apply across the overarching project and its connected research branches, including AYLI, ARIADNE, R.O.S.E.T.T.A.S., Harmonia-Occulta, Tempo-Gold, BURGAMOTS, SUN, SATURN, and later connected projects unless a branch explicitly requires a stricter rule.

## GPR-001 — Twenty-message ARIADNE checkpoint

**Status:** ACTIVE / GLOBAL / NON-OPTIONAL  
**Adopted:** 2026-09-13

For every **10 completed exchanges** — exactly **10 user inputs + 10 assistant outputs = 20 conversation-visible messages** — the assistant must push all project progress accumulated since the previous checkpoint into ARIADNE.

Tool calls, system/developer messages, hidden reasoning, and background execution do **not** count toward the 20-message cadence. The cadence counts the visible project conversation: one user input and one assistant output form one completed exchange.

### Purpose

The checkpoint exists so important work cannot remain trapped in conversational working memory or disappear when the research jumps eras, languages, projects, or abstraction levels.

It is a **continuity and navigation artifact**, not evidence for the underlying historical/scientific claims.

### Epistemic class

Every conversation checkpoint is permanently:

```yaml
epistemic_zone: G0
epistemic_class: DISCOVERY_GUIDANCE
evidence_eligible: false
claim_support_weight: 0
corroboration_eligible: false
derivative_inherits_zone: true
```

It is admissible for:

- research history;
- design rationale;
- decision provenance;
- hypothesis provenance;
- correction history;
- navigation / Where-To-Look-Next generation.

It is inadmissible for:

- historical claim support;
- textual claim support;
- scientific claim support;
- empirical validation;
- independent corroboration;
- convergence counts.

### Required contents

Each checkpoint records **only progress since the prior checkpoint**, including as applicable:

1. new discoveries or candidate pings;
2. new source/evidence acquisitions and exact provenance status;
3. hypotheses introduced, changed, weakened, strengthened, or rejected;
4. corrections and superseded interpretations;
5. decisions and newly adopted rules;
6. changed equations, schemas, transforms, mappings, or terminology;
7. newly opened, banked, burning, or reignited torches;
8. bright-red items and why they matter;
9. failed mappings, negative controls, residuals, missing variables, and outliers;
10. repo/artifact/code changes;
11. relationships to older project threads that were recontextualized;
12. unresolved questions and explicit return triggers;
13. immediate forward paths and recursive/orthogonal paths.

### Required separation

A checkpoint may say:

> "We hypothesized X and therefore decided to inspect source Y."

It may **not** convert that into:

> "X is supported because the checkpoint says X."

The checkpoint can create `GUIDES_TO`, `DISCOVERED_VIA`, `TESTS`, and `CONTRADICTS_GUIDANCE` relationships. It cannot create `SUPPORTS` or `CORROBORATES` relationships to research-object claims.

### Push location

Checkpoint files live under:

```text
checkpoints/YYYY-MM-DD/
```

with stable IDs such as:

```text
CP-20260913-0001.md
CP-20260913-0002.md
```

Each file records its predecessor so ARIADNE can reconstruct the continuous research path without treating repeated summaries as independent evidence.

### Accessibility rule

The checkpoint is the assistant/system's responsibility. The operator is **not** required to:

- request the checkpoint;
- remember the cadence;
- summarize the previous 20 messages;
- classify the material;
- open GitHub;
- manually push files.

The checkpoint should occur without interrupting discovery mode unless a consequential human decision is genuinely required.

### Failure fallback

If ARIADNE/GitHub write access is unavailable at the checkpoint boundary:

1. generate the checkpoint artifact locally/in-chat;
2. mark it `PENDING_PUSH`;
3. continue research without requiring operator reconstruction;
4. push the queued checkpoint at the next available write opportunity;
5. do not count the queued checkpoint as evidentiary support.

### Cadence ambiguity

If exact message counting becomes uncertain because of interrupted turns or platform behavior, checkpoint **early rather than late**. Never allow more than 10 completed user/assistant exchanges to accumulate without a continuity checkpoint.

---

## GPR-002 — Epistemic firewall

All research-history summaries, chat-derived continuity artifacts, design rationale, working hypotheses, machine predictions, structural alignments, TOL predictions, and checksum predictions are discovery guidance unless independently verified under the ARIADNE Epistemic Firewall.

See `docs/EPISTEMIC_FIREWALL.md` and `config/epistemic_policy.json`.

---

## GPR-003 — Prior-art and field-census gate

**Status:** ACTIVE / GLOBAL RESEARCH / NON-OPTIONAL  
**Adopted:** 2026-09-14

Before substantial original source interpretation or cross-domain synthesis begins for a new major research question, ARIADNE must first investigate the research landscape surrounding the question itself.

The default sequence is:

```text
QUESTION
  -> FIELD CENSUS
  -> PRIOR ART
  -> VOCABULARY
  -> KNOWN RESULTS
  -> KNOWN FAILURES
  -> SOURCE MAP
  -> ORIGINAL INVESTIGATION
  -> CONTRIBUTION DELTA
```

The forbidden default is:

```text
QUESTION -> HISTORICAL RABBIT HOLE
```

### First-order census questions

ARIADNE asks, before expensive original synthesis:

1. Who has proposed this or a structurally equivalent idea before?
2. What fields study the problem?
3. What terminology do those fields use?
4. What established theories, models, equations, or frameworks are closest?
5. What reviews, surveys, bibliographies, encyclopedias, dissertations, or meta-analyses already map the space?
6. What are the canonical papers, books, and authors?
7. What competing explanations exist?
8. What has already been falsified, criticized, or abandoned?
9. What unresolved questions remain?
10. What primary sources or datasets does the field itself consider important?
11. What historical lineages have scholars already connected?
12. What terminology changed over time and may conceal older versions of the same idea?
13. What adjacent disciplines may have rediscovered the same structure under another name?
14. Which reasonable prior-art searches produced no result?

A failed search is recorded as a bounded negative search result. It is **not** converted into a novelty claim merely because the first search returned nothing.

### Gate

Original deep-source analysis opens only when either:

- a reasonable field map has been established; or
- a documented, bounded search has reached saturation without identifying applicable prior art.

Until then, acquisition and custody may continue, but the research engine does not begin its ordinary reconnect / synthesis cycle for that question.

### Epistemic scope

Field-census index records are permanently treated as **G0 discovery metadata**. They may establish that a bibliographic record exists and may teach vocabulary, authors, titles, fields, citations, and likely source leads. They do not establish the underlying historical or scientific claim discussed by the indexed work.

A scholarly paper has scope-dependent roles. If the question is “did author P propose theory X?”, paper P can be primary evidence for P's own proposal after verification. It is not thereby primary evidence that an earlier historical author Q intended X.

This distinction is mandatory:

```text
CONTENT IDENTITY != CLAIM IDENTITY != EVIDENTIAL AUTHORITY
```

A hash answers whether the stored content is the same. A claim identity answers whether two records express the same proposition or occurrence. Evidential authority answers what that source may support, under which scope and dependencies. None may be substituted for another.

The operating rule is:

> Never rediscover manually what a field has already spent centuries organizing.

Use original effort where the field ends, disagrees, fragments, fails, or never connected the relevant pieces.

---

## GPR-004 — ABRUPT is the browser execution surface of ARIADNE

**Status:** ACTIVE / GLOBAL RESEARCH / NON-OPTIONAL  
**Adopted:** 2026-09-18

**ABRUPT — ARIADNE Browser Research Utility Protocol for Trustworthiness — is not a separate project, branch of research, parallel methodology, or independent state machine.**

It is the browser/chat execution profile for the canonical ARIADNE research instrument.

Therefore:

1. All work performed under ABRUPT is ARIADNE work.
2. All canonical ARIADNE rules remain active inside ABRUPT, including the Epistemic Firewall, P0 gate, source custody, disagreement preservation, E/U/D/A separation, residual retention, typed lineage, Global–Local navigation, Torch Ledger, checkpoint cadence, project/fork governance, and accessibility contract.
3. ABRUPT may add stricter browser-specific trustworthiness controls but may not weaken, bypass, fork, or silently replace an ARIADNE rule.
4. Browser/chat discoveries, hypotheses, summaries, calculations, and transfer packets are G0 discovery guidance unless independently promoted through the ARIADNE evidence pipeline.
5. Project-specific research state belongs in the appropriate downstream/federated ARIADNE project state. Generic mechanisms and constitutional rules belong upstream.
6. A locally generated ABRUPT artifact that has not been checkpointed/pushed is not considered durably integrated into ARIADNE.
7. A change in chat, browser session, model, or interface does not create a new research endeavor. Continuity resumes from the latest valid ARIADNE checkpoint, active focus, Torch Ledger, and provenance state.

Operating invariant:

```text
ABRUPT ⊂ ARIADNE
```

not:

```text
ABRUPT || ARIADNE
```

---

## GPR-005 — Runtime-status honesty and chat-to-ARIADNE bridge

**Status:** ACTIVE / GLOBAL / NON-OPTIONAL  
**Adopted:** 2026-09-18

ARIADNE's local Warden and the ChatGPT/browser research surface are separate processes unless an explicit message/feed bridge is running.

The assistant must never claim that ARIADNE is processing a chat “in the background” merely because the repository contains Warden code or because a checkpoint protocol exists.

A valid runtime-status claim requires one of:

- direct evidence that the local Warden process is running and receiving the relevant feed; or
- confirmed ingestion/checkpoint artifacts produced by that runtime.

Repository access alone proves repository state, not local process state.

### Browser responsibility when no live bridge is verified

If the browser/chat cannot verify a live message bridge:

1. continue research under the canonical ARIADNE/ABRUPT workflow;
2. checkpoint/push required G0 continuity artifacts through available repository tooling at the prescribed cadence;
3. mark any runtime-dependent work as `UNVERIFIED_RUNTIME` rather than implying it occurred;
4. preserve the exact feed/pointers needed for Warden to ingest later;
5. do not make the operator reconstruct lost progress.

### Local runtime requirement

The local Warden only performs continuous acquisition/discovery while its process is actually running. Chat messages enter that runtime only when an explicit sender/feed connection is configured. Running Warden without a chat feed does not make the current conversation automatically available to it.

### Drift safeguard

Every Protocol Alignment Audit must include:

- last confirmed ARIADNE checkpoint/push;
- whether a live runtime/feed is verified;
- whether any research has accumulated only in chat/local artifacts since the last durable checkpoint;
- whether a catch-up checkpoint is required.

If cadence was missed, repair transparently with a recovery checkpoint. Do not fabricate the missing cadence history or pretend the checkpoint occurred on time.


---

## GPR-006 — Re-entrant prior-art divergence and prediction-first search

**Status:** ACTIVE / GLOBAL RESEARCH / NON-OPTIONAL  
**Adopted:** 2026-09-18

The prior-art/field-census gate is **re-entrant**. A materially new finding, operator, relationship, recurrence, vocabulary, mechanism, prediction, or novelty claim must trigger a renewed bounded First-order / First-&-3/4-order prior-art check before substantial original effort continues downstream.

The purpose is not merely to avoid duplicate citations. It is to prevent the research program from independently spending its effort to arrive at an endpoint already reached by prior work without producing a meaningful contribution delta.

Operating rule:

```text
CHANGE SOMETHING.
BREAK NOTHING BETTER SUPPORTED.
DO NOT SPEND ORIGINAL-RESEARCH BUDGET
MERELY TO REDISCOVER A KNOWN ENDPOINT.
```

### Prediction-first navigation

Repeated patterns must be used prospectively. When a recurrence suggests a missing or next structural address, record the predicted location, relation/operator, invariant, allowed variation, and falsifier **before** searching that address.

```text
RECURRENCE
→ ABSTRACT INVARIANT
→ PREDICT ADDRESS
→ RECORD
→ SEARCH
→ HIT / MISS / PARTIAL / CONTRADICTION
→ NEIGHBOR + NON-BREAK TEST
→ UPDATE
```

Post-hoc fitting does not count as prediction. Misses and contradictions remain first-class records.

Prediction guides where ARIADNE searches; it does not become evidence for the predicted result. All findings remain subject to the Epistemic Firewall and independence analysis.

### Mandatory triggers

Re-run prior-art divergence checks:
- before every prescribed hop/forced-focus transition;
- after high-diagnostic findings;
- when previously separate torches connect;
- when a prediction hits unexpectedly;
- when new terminology or an adjacent field becomes visible;
- before mechanism promotion;
- before novelty/uniqueness/significance claims;
- before committing substantial work to a new branch.

ABRUPT implements the browser-specific enforcement details in `docs/ABRUPT.md`.
