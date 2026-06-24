# Import all the models, so that Base has them before being
# imported by Alembic or database initialization scripts
from app.core.database import Base # noqa
from app.models.service import Service # noqa
from app.models.investigation import Investigation # noqa
from app.models.investigation_timeline import InvestigationTimeline # noqa
from app.models.recommendation import Recommendation # noqa
from app.models.evidence import Evidence # noqa
from app.models.chat_session import ChatSession # noqa
from app.models.chat_message import ChatMessage # noqa
