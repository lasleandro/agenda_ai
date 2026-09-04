# Import all models so Alembic autogenerate discovers their metadata.
from app.models.professional import Professional  # noqa: F401
from app.models.place import Place  # noqa: F401
from app.models.contact import Contact  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.appointment_candidate import AppointmentCandidate  # noqa: F401
from app.models.passive_escalation import PassiveEscalation  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.appointment_participant import AppointmentParticipant  # noqa: F401
from app.models.appointment_evidence import AppointmentEvidence  # noqa: F401
from app.models.appointment_transition import AppointmentTransition  # noqa: F401
from app.models.pending_processing import PendingProcessing  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.account_access_request import AccountAccessRequest  # noqa: F401
from app.models.auth_action_token import AuthActionToken  # noqa: F401
from app.models.auth_security_event import AuthSecurityEvent  # noqa: F401
from app.models.email_delivery import EmailDelivery  # noqa: F401
from app.models.impersonation_log import ImpersonationLog  # noqa: F401
from app.models.tenant_feature import TenantFeature  # noqa: F401
from app.models.tenant_feature_audit_log import TenantFeatureAuditLog  # noqa: F401
from app.models.professional_financial_settings import ProfessionalFinancialSettings  # noqa: F401
from app.models.financial_change_audit_log import FinancialChangeAuditLog  # noqa: F401
from app.models.financial_scenario import FinancialScenario  # noqa: F401
from app.models.prime_time_window import PrimeTimeWindow  # noqa: F401
from app.models.place_financial_rate import PlaceFinancialRate  # noqa: F401
from app.models.work_journey_interval import WorkJourneyInterval  # noqa: F401
from app.models.revenue_occurrence import RevenueOccurrence  # noqa: F401
from app.models.revenue_occurrence_participant import RevenueOccurrenceParticipant  # noqa: F401
from app.models.revenue_occurrence_line import RevenueOccurrenceLine  # noqa: F401
from app.models.recurring_slot import RecurringSlot  # noqa: F401
from app.models.recurring_slot_participant import RecurringSlotParticipant  # noqa: F401
from app.models.recurring_slot_occurrence_participant import (  # noqa: F401
    RecurringSlotOccurrenceParticipant,
)
from app.models.entity_alias import EntityAlias  # noqa: F401
from app.models.schedule_occurrence_override import ScheduleOccurrenceOverride  # noqa: F401
from app.models.schedule_occurrence_class_override import (  # noqa: F401
    ScheduleOccurrenceClassOverride,
)
from app.models.operator_action_candidate import OperatorActionCandidate  # noqa: F401
from app.models.operational_event import OperationalEvent  # noqa: F401
from app.models.assistant_settings import AssistantSettings  # noqa: F401
from app.models.makeup_class_credit import MakeupClassCredit  # noqa: F401
from app.models.agent_channel_message import AgentChannelMessage  # noqa: F401
from app.models.waitlist_entry import WaitlistEntry  # noqa: F401
from app.models.instructor_event import InstructorEvent  # noqa: F401
from app.models.scheduled_task import ScheduledTask  # noqa: F401
from app.models.scheduled_task_run import ScheduledTaskRun  # noqa: F401
from app.models.webhook_receipt import WebhookReceipt  # noqa: F401
