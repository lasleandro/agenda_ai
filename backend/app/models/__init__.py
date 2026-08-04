# Import all models so Alembic autogenerate discovers their metadata.
from app.models.professional import Professional  # noqa: F401
from app.models.contact import Contact  # noqa: F401
from app.models.conversation import Conversation  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.appointment_candidate import AppointmentCandidate  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.appointment_evidence import AppointmentEvidence  # noqa: F401
from app.models.appointment_transition import AppointmentTransition  # noqa: F401
