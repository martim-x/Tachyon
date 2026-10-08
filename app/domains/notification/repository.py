from app.core.persistence.scoped_repository import ScopedRepository
from app.domains.notification.models import Notification


class NotificationRepository(ScopedRepository[Notification]):
    model = Notification