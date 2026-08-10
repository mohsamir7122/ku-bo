# KU-BO Conversation Import and Retention Policy

## Purpose

Previous ChatGPT or Codex conversations may contain useful architectural decisions, source constraints, failed approaches, and acceptance criteria. They may also contain private, personal, medical, employment, relationship, email, credential-adjacent, or unrelated material.

The repository must retain the technical knowledge without publishing the private conversation.

## Storage rule

Raw conversation transcripts belong only in the private Google Drive folder:

```text
KU-BO Codex Control/PRIVATE_CONVERSATION_ARCHIVE
```

Raw transcripts must not be committed to GitHub.

## Permitted repository imports

Codex may import only a sanitized technical summary that is materially useful and not already represented. Acceptable destinations include:

```text
docs/codex/handoffs/
docs/decisions/
docs/architecture/
docs/source-policy/
tests/ as a minimal non-private regression case
```

A sanitized import may include:

- an architectural decision and rationale;
- a verified source-access limitation;
- a precise bug or failure mode;
- an acceptance gate;
- a data contract requirement;
- a user-approved workflow preference;
- a concise historical note explaining why a design exists.

## Forbidden repository imports

Never commit:

- raw or near-verbatim chat transcripts;
- names, phone numbers, emails, addresses, CV data, family details, relationship discussions, medical records, or employment correspondence unrelated to the public repository;
- access keys, tokens, passwords, sessions, browser cookies, signed links, or private Drive identifiers;
- private market files or licensed reports;
- copied third-party text that creates copyright or licensing risk;
- irrelevant personal context merely because it appeared in the same conversation.

## Sanitization procedure

For each candidate conversation:

1. identify the technical decision or requirement;
2. check whether it already exists in code, tests, schemas, docs, PRs, or handoffs;
3. classify the candidate:

```text
KEEP_PRIVATE_RAW
IMPORT_SANITIZED_SUMMARY
DUPLICATE_ARCHIVE
SUPERSEDED_ARCHIVE
DELETE_CANDIDATE_USER_APPROVAL
OUT_OF_SCOPE_PRIVATE
```

4. remove personal and unrelated context;
5. remove credentials and private identifiers;
6. replace chronology with the smallest useful decision context;
7. identify the current authoritative contract or task;
8. write a short summary, not a reconstructed dialogue;
9. record the source conversation filename or private archive reference only in Drive, not GitHub, when that reference itself is sensitive;
10. run secret and privacy review before committing.

## Authority rule

A conversation is historical context, not current authority.

The active user instruction, `AGENTS.md`, `CURRENT_TASK.md`, schemas, tests, and current source policy override older conversations.

A useful old decision that conflicts with the current design must be marked `SUPERSEDED`, not silently revived.

## Deletion rule

Codex may recommend deletion but may not permanently delete:

- a Drive conversation;
- a repository file;
- a branch;
- an evidence packet;
- an archived handoff.

Permanent deletion requires an explicit user decision recorded in `docs/codex/USER_DECISIONS.md` or an equivalent private Drive decision document.

Before recommending deletion, Codex must state:

- exact target;
- whether a sanitized summary was retained;
- whether any code, test, PR, issue, or document still references it;
- privacy benefit;
- recovery or archive alternative;
- recommendation.

## Preferred outcome

For most old conversations, the preferred outcome is:

```text
PRIVATE RAW ARCHIVE
+
ONE SANITIZED TECHNICAL SUMMARY IF UNIQUE
```

This preserves project memory without turning a public code repository into a diary.
