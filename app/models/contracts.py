from datetime import datetime
from enum import Enum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


class TriggerCommand(str, Enum):
    ANALYZE_INCIDENT = "analyze_incident"
    SUMMARIZE_THREAD = "summarize_thread"
    RERUN_ANALYSIS = "rerun_analysis"
    APPROVE_ACTION = "approve_action"


class SourceType(str, Enum):
    THREAD_MESSAGE = "thread_message"
    KNOWLEDGE_DOC = "knowledge_doc"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalysisResultStatus(str, Enum):
    SUCCESS = "success"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    TEMPORARY_FAILURE = "temporary_failure"


class CallbackHandlingStatus(str, Enum):
    VERIFIED = "verified"
    ACCEPTED = "accepted"
    IGNORED = "ignored"


class ExternalTaskTarget(str, Enum):
    GENERIC = "generic"
    JIRA = "jira"
    FEISHU = "feishu"


class TaskSyncStatus(str, Enum):
    REQUIRES_CONFIRMATION = "requires_confirmation"
    SYNCED = "synced"
    SYNC_FAILED = "sync_failed"


class PostmortemStatus(str, Enum):
    DRAFT = "draft"


class FollowUpSource(str, Enum):
    MEMORY = "memory"
    HEURISTIC = "heuristic"


class PendingActionType(str, Enum):
    TASK_SYNC = "task_sync"
    POSTMORTEM_DRAFT = "postmortem_draft"


class PendingActionStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"


class InteractionEventType(str, Enum):
    ANALYSIS_REPLY_SENT = "analysis_reply_sent"
    ACTIONS_PROPOSED = "actions_proposed"
    ACTION_EXECUTED = "action_executed"
    REPLY_SEND_FAILED = "reply_send_failed"


class SkillCandidateStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"
    RETIRED = "retired"


NonEmptyText: TypeAlias = str


class ThreadMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message_id: NonEmptyText = Field(min_length=1)
    sender_name: NonEmptyText = Field(min_length=1, default="Unknown")
    sent_at: datetime
    text: NonEmptyText = Field(min_length=1)


class FollowUpContext(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    previous_summary: NonEmptyText | None = None
    new_messages: list[ThreadMessage] = Field(default_factory=list)
    source: FollowUpSource | None = None


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    trigger_command: TriggerCommand
    chat_id: NonEmptyText = Field(min_length=1)
    thread_id: NonEmptyText = Field(min_length=1)
    trigger_message_id: NonEmptyText = Field(min_length=1)
    user_id: NonEmptyText = Field(min_length=1)
    user_display_name: str | None = None
    thread_messages: list[ThreadMessage] = Field(min_length=1)
    follow_up_context: FollowUpContext | None = None


class MemoryScope(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_id: NonEmptyText = Field(min_length=1)
    user_id: NonEmptyText = Field(min_length=1)
    thread_id: NonEmptyText = Field(min_length=1)


class ActionScope(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_id: NonEmptyText = Field(min_length=1)
    thread_id: NonEmptyText = Field(min_length=1)


class ThreadMemoryState(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    schema_version: int = Field(default=1, ge=1)
    last_summary_text: str | None = None
    last_summary_message_id: str | None = None
    last_processed_message_id: str | None = None
    last_processed_at: datetime | None = None
    last_trigger_command: TriggerCommand | None = None
    last_summary_status: AnalysisResultStatus | None = None
    updated_at: datetime
    known_facts: list[NonEmptyText] = Field(default_factory=list)
    open_questions: list[NonEmptyText] = Field(default_factory=list)


class MemorySnapshot(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_memory: dict[str, object] = Field(default_factory=dict)
    org_memory: dict[str, object] = Field(default_factory=dict)
    thread_memory: ThreadMemoryState | None = None


class KnowledgeCitation(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_type: SourceType
    label: NonEmptyText = Field(min_length=1)
    source_uri: NonEmptyText = Field(min_length=1)
    snippet: NonEmptyText = Field(min_length=1)


class KnowledgeDocumentMetadata(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    doc_id: NonEmptyText = Field(min_length=1)
    title: NonEmptyText = Field(min_length=1)
    path: NonEmptyText = Field(min_length=1)
    tags: list[NonEmptyText] = Field(default_factory=list)


class TodoDraftItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: NonEmptyText = Field(min_length=1)
    owner_hint: str | None = None
    rationale: str | None = None


class StructuredSummary(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: Literal[
        AnalysisResultStatus.SUCCESS,
        AnalysisResultStatus.INSUFFICIENT_CONTEXT,
    ]
    confidence: ConfidenceLevel
    current_assessment: NonEmptyText = Field(min_length=1)
    known_facts: list[NonEmptyText] = Field(default_factory=list)
    impact_scope: NonEmptyText = Field(min_length=1)
    next_actions: list[NonEmptyText] = Field(default_factory=list)
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    missing_information: list[NonEmptyText] = Field(default_factory=list)
    conclusion_summary: str | None = None
    todo_draft: list[TodoDraftItem] = Field(default_factory=list)


class TemporaryFailureReply(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: Literal[AnalysisResultStatus.TEMPORARY_FAILURE]
    headline: NonEmptyText = Field(min_length=1)
    known_facts: list[NonEmptyText] = Field(default_factory=list)
    missing_information: list[NonEmptyText] = Field(default_factory=list)
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    retry_hint: NonEmptyText = Field(min_length=1)


class ExternalTaskDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: NonEmptyText = Field(min_length=1)
    description: NonEmptyText = Field(min_length=1)
    owner_hint: str | None = None
    labels: list[NonEmptyText] = Field(default_factory=list)
    citations: list[KnowledgeCitation] = Field(default_factory=list)


class ExternalTaskSyncRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    target: ExternalTaskTarget
    source_thread_id: NonEmptyText = Field(min_length=1)
    requested_by: NonEmptyText = Field(min_length=1)
    task_drafts: list[ExternalTaskDraft] = Field(min_length=1)
    require_confirmation: bool = True
    confirmed: bool = False


class SyncedExternalTask(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: NonEmptyText = Field(min_length=1)
    external_id: NonEmptyText = Field(min_length=1)
    external_url: str | None = None


class ExternalTaskSyncResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: TaskSyncStatus
    target: ExternalTaskTarget
    source_thread_id: NonEmptyText = Field(min_length=1)
    prepared_drafts: list[ExternalTaskDraft] = Field(default_factory=list)
    synced_tasks: list[SyncedExternalTask] = Field(default_factory=list)
    message: NonEmptyText = Field(min_length=1)


class PostmortemTimelineEntry(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    timestamp_hint: NonEmptyText = Field(min_length=1)
    event: NonEmptyText = Field(min_length=1)


class PostmortemDraft(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    status: Literal[PostmortemStatus.DRAFT]
    title: NonEmptyText = Field(min_length=1)
    incident_summary: NonEmptyText = Field(min_length=1)
    impact_summary: NonEmptyText = Field(min_length=1)
    timeline: list[PostmortemTimelineEntry] = Field(default_factory=list)
    root_cause_hypothesis: NonEmptyText = Field(min_length=1)
    resolution_summary: NonEmptyText = Field(min_length=1)
    follow_up_actions: list[NonEmptyText] = Field(default_factory=list)
    open_questions: list[NonEmptyText] = Field(default_factory=list)
    citations: list[KnowledgeCitation] = Field(default_factory=list)


class PendingIncidentAction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    action_id: NonEmptyText = Field(min_length=1)
    action_type: PendingActionType
    status: PendingActionStatus
    title: NonEmptyText = Field(min_length=1)
    preview: NonEmptyText = Field(min_length=1)
    source_thread_id: NonEmptyText = Field(min_length=1)
    created_by: NonEmptyText = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    execution_message: str | None = None
    task_sync_request: ExternalTaskSyncRequest | None = None
    postmortem_draft: PostmortemDraft | None = None


class ActionQueueState(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    schema_version: int = Field(default=1, ge=1)
    updated_at: datetime
    actions: list[PendingIncidentAction] = Field(default_factory=list)


class InteractionRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: NonEmptyText = Field(min_length=1)
    correlation_key: NonEmptyText = Field(min_length=1)
    event_type: InteractionEventType
    tenant_id: NonEmptyText = Field(min_length=1)
    thread_id: NonEmptyText = Field(min_length=1)
    actor_id: NonEmptyText = Field(min_length=1)
    occurred_at: datetime
    trigger_command: TriggerCommand | None = None
    summary_status: AnalysisResultStatus | None = None
    action_id: str | None = None
    action_type: PendingActionType | None = None
    pattern_key: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id: NonEmptyText = Field(min_length=1)
    event_type: NonEmptyText = Field(min_length=1)
    tenant_id: NonEmptyText = Field(min_length=1)
    thread_id: NonEmptyText = Field(min_length=1)
    occurred_at: datetime
    summary: NonEmptyText = Field(min_length=1)
    related_action_id: str | None = None


class SkillCandidate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    schema_version: int = Field(default=1, ge=1)
    candidate_id: NonEmptyText = Field(min_length=1)
    tenant_id: NonEmptyText = Field(min_length=1)
    name: NonEmptyText = Field(min_length=1)
    workflow: NonEmptyText = Field(min_length=1)
    status: SkillCandidateStatus
    source_pattern_key: NonEmptyText = Field(min_length=1)
    trigger_conditions: list[NonEmptyText] = Field(default_factory=list)
    steps: list[NonEmptyText] = Field(default_factory=list)
    verification_steps: list[NonEmptyText] = Field(default_factory=list)
    failure_signals: list[NonEmptyText] = Field(default_factory=list)
    evidence_event_ids: list[NonEmptyText] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    activated_by: str | None = None
    activated_at: datetime | None = None


ReplyPayload: TypeAlias = StructuredSummary | TemporaryFailureReply


class AnalysisResultRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request_id: NonEmptyText = Field(min_length=1)
    trigger_command: TriggerCommand
    chat_id: NonEmptyText = Field(min_length=1)
    thread_id: NonEmptyText = Field(min_length=1)
    result_status: AnalysisResultStatus
    summary: ReplyPayload


class FeishuVerificationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    challenge: NonEmptyText = Field(min_length=1)
    token: str | None = None


class NormalizedFeishuMessageEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    chat_id: NonEmptyText = Field(min_length=1)
    message_id: NonEmptyText = Field(min_length=1)
    thread_id: NonEmptyText = Field(min_length=1)
    sender_id: NonEmptyText = Field(min_length=1)
    sender_name: str | None = None
    message_text: NonEmptyText = Field(min_length=1)
    mentions_bot: bool
    event_time: datetime


class FeishuThreadMessageRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message_id: NonEmptyText = Field(min_length=1)
    sender_name: str | None = None
    sent_at: datetime | None = None
    text: str | None = None


class FeishuThreadLoadResponse(BaseModel):
    thread_messages: list[FeishuThreadMessageRecord] = Field(default_factory=list)


class FeishuReplySendResult(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    success: bool
    reply_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class CallbackResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: CallbackHandlingStatus
    reason: str | None = None
    trigger_command: TriggerCommand | None = None
    message_event: NormalizedFeishuMessageEvent | None = None
