"""
Agent Action Plan Generation Prompts.

This module defines all prompt templates for Agent Action Plan (AAP) generation —
the process by which the system creates a structured summary of identified changes
and planned document updates (Feature F-003 — Agent Action Plan Generation).

These prompts are used primarily in UPDATE mode to generate a comprehensive action
plan before document sections are regenerated. They are consumed by the
``create_agent_action_plan()`` method in ``ReverseDocumentHelper``, which combines
them with actual state data (previous spec, repository changes, section
classifications) and sends the result to the primary LLM (Claude Opus 4.6).

Workflow position:
    Context Search → Change Identification → **Action Plan Generation** → Section Update

State integration:
    - ``ReverseDocumentState.agent_action_plan`` stores the generated plan.
    - ``ReverseDocumentState.identified_changes`` feeds into ``{repository_changes}``.

Format placeholders (compatible with ``str.format()``):
    - ``{previous_tech_spec}``      — Full text of the previous Technical Specification.
    - ``{repository_changes}``      — Summary of repository changes since the last spec.
    - ``{section_classifications}`` — CHANGED / UNCHANGED classifications per section.
    - ``{repository_url}``          — URL of the target repository being analyzed.
    - ``{repository_branch}``       — Branch of the repository being analyzed.

Note:
    This file contains **only** string constant definitions. There are no classes,
    functions, or application-level imports. The prompts are pure text templates
    that are framework-independent and passed directly to LLM API calls after
    formatting.
"""

# ---------------------------------------------------------------------------
# SUMMARY_CHANGES_INPUTS
# ---------------------------------------------------------------------------
# Defines the input structure that the LLM receives when generating the Agent
# Action Plan.  Each placeholder is populated at runtime by the
# ``create_agent_action_plan()`` method with concrete data from the workflow
# state.
# ---------------------------------------------------------------------------

SUMMARY_CHANGES_INPUTS: str = """\
You are generating an Agent Action Plan for an incremental update of a \
Technical Specification document.

Below you will find all the information you need to produce the action plan.

## Repository Information

- **Repository URL:** {repository_url}
- **Branch:** {repository_branch}

## Previous Technical Specification

The following is the full text of the previous Technical Specification that \
serves as the baseline for comparison.  Every section listed here must appear \
in your action plan output — no section may be silently dropped.

<previous_tech_spec>
{previous_tech_spec}
</previous_tech_spec>

## Repository Changes Summary

The following is a summary of all identified changes in the repository since \
the previous Technical Specification was generated.  Changes are organized by \
category.

<repository_changes>
{repository_changes}
</repository_changes>

## Section Classifications

The Architect Agent has pre-classified each section of the Technical \
Specification as either CHANGED or UNCHANGED based on the repository changes \
above.  Use these classifications as the authoritative starting point for \
your action plan.

<section_classifications>
{section_classifications}
</section_classifications>

## Your Task

Using all of the information above, generate a comprehensive Agent Action \
Plan that:
1. Lists every section with its CHANGED or UNCHANGED status.
2. Provides a clear justification for every CHANGED section.
3. Identifies cross-section impacts and processing dependencies.
4. Specifies the recommended processing order for changed sections.

Follow the rules provided in your system prompt exactly.\
"""

# ---------------------------------------------------------------------------
# SUMMARY_CHANGES_RULES
# ---------------------------------------------------------------------------
# Comprehensive rules governing how the LLM must generate the Agent Action
# Plan.  These rules are injected as part of the system prompt and enforce
# consistency, completeness, and correctness of the plan.
# ---------------------------------------------------------------------------

SUMMARY_CHANGES_RULES: str = """\
You must follow ALL of the rules below when generating the Agent Action Plan.

### Rule 1 — Scope Definition

The action plan MUST explicitly list every section of the previous Technical \
Specification and assign each one a status of either **CHANGED** (the section \
will be regenerated with updated content) or **UNCHANGED** (the section will \
be preserved verbatim from the previous specification).

- Do NOT omit any section.
- Do NOT introduce sections that did not exist in the previous specification.
- If new content warrants a new section, note it as a recommendation under \
the nearest existing section's entry.

**Rationale:** A complete scope definition ensures that no part of the \
document is accidentally skipped or duplicated during the update process.

### Rule 2 — Change Justification

For every section classified as CHANGED, provide a clear, specific \
justification that links the identified repository change to the section's \
content.

- State WHICH code change (file, module, dependency, configuration) affects \
the section.
- Explain WHY the change makes the current section content inaccurate or \
incomplete.
- Reference concrete evidence from the Repository Changes Summary.

**Rationale:** Justifications create an auditable trail and prevent \
unnecessary regeneration of sections that are not truly affected.

Example:
    Section "3.2 Frameworks & Libraries" → CHANGED
    Justification: The repository added Flask 3.1.3 as the web framework and \
removed the Cloud Run Job execution model.  The frameworks table and \
descriptions in this section no longer reflect the current stack.

### Rule 3 — Impact Assessment

For every CHANGED section, assess the **scope and severity** of the required \
update:

- **Minor Update:** Small factual corrections such as version bumps, renamed \
files, or updated configuration values.  The section's overall structure \
remains intact.
- **Moderate Update:** Meaningful additions or removals that affect a portion \
of the section, such as new API endpoints added to an existing API section.
- **Major Rewrite:** Structural changes that invalidate the majority of the \
section's content, such as a complete architecture migration.

**Rationale:** Impact severity guides the Author Agent's effort allocation \
and helps prioritize processing order.

### Rule 4 — Cross-Section Impact

Identify **cascading impacts** across sections:

- If Section A changes and Section B references Section A (e.g., "See Section \
A for details"), assess whether Section B also needs updating.
- Document cross-references explicitly in the action plan.
- If an unchanged section contains stale cross-references to a changed \
section, flag it as potentially requiring an update.

**Rationale:** Technical Specification sections are interconnected.  Updating \
one section may render cross-references in other sections inaccurate.

Example:
    Section "5.1 High-Level Architecture" → CHANGED (Major Rewrite)
    Cross-section impact: Sections 6.1, 6.2, and 6.3 reference the \
architecture diagram and component descriptions from 5.1 — review these \
sections for consistency.

### Rule 5 — Preservation Priority

Default to **UNCHANGED** when in doubt.

- Only mark a section as CHANGED if there is clear, concrete evidence from \
the Repository Changes Summary that the section's content is affected.
- Cosmetic or formatting-only changes in the codebase (whitespace, comment \
rewording) do NOT warrant marking a section as CHANGED.
- If a section's technical content remains accurate despite code changes, \
keep it UNCHANGED.

**Rationale:** Unnecessary regeneration wastes LLM processing time and risks \
introducing inconsistencies or regressions in previously accurate content.

### Rule 6 — Action Plan Format

The output action plan MUST use the following structure:

```
## Action Plan Summary

- **Total Sections:** <N>
- **Changed Sections:** <M>
- **Unchanged Sections:** <N - M>

## Section-by-Section Breakdown

### <Section Number> — <Section Title>
- **Status:** CHANGED | UNCHANGED
- **Impact:** Minor | Moderate | Major  (only for CHANGED sections)
- **Justification:** <reason>  (only for CHANGED sections)
- **Affected Code Areas:** <files, modules, configs>  (only for CHANGED)
- **Cross-Section Impact:** <list of impacted sections, if any>

(repeat for every section)

## Processing Order

1. <Section X> — <brief reason for ordering>
2. <Section Y> — <brief reason for ordering>
...
```

- The **Processing Order** section lists CHANGED sections only, in the \
recommended order of regeneration.
- Sections that other changed sections depend on should be processed first.

**Rationale:** A standardized, parseable format enables downstream automation \
and ensures all required metadata is present.

### Rule 7 — Completeness Check

Every section that exists in the previous Technical Specification MUST appear \
in the action plan.

- Perform a final pass to verify that no sections have been omitted.
- If the previous specification has N sections, the action plan must contain \
exactly N section entries.
- Sections that were removed from the codebase should still appear with a \
note explaining that the corresponding functionality no longer exists.

**Rationale:** Silent omission of sections leads to incomplete documents and \
data loss during incremental updates.

### Rule 8 — Consistency

The section classifications in the action plan MUST be consistent with the \
``DocumentSections`` structured output from the change identification step.

- If the Architect Agent classified a section as CHANGED, the action plan \
must also classify it as CHANGED (unless you have strong evidence to \
override — in which case, document the override reason).
- If the Architect Agent classified a section as UNCHANGED, the action plan \
should also classify it as UNCHANGED (overrides require justification).
- Any override of the Architect Agent's classification must include a \
**clear, documented rationale** explaining why the override is necessary.

**Rationale:** Consistency between the change identification step and the \
action plan prevents conflicting instructions to downstream agents and \
ensures a single source of truth for section status.\
"""
