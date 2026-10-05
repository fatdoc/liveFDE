from alembic import context

from live_review.core.config import get_settings
from live_review.core.database import Base, build_engine
from live_review.modules.identity import models  # noqa: F401
from live_review.modules.materials import models as material_models  # noqa: F401
from live_review.modules.sessions import models as session_models  # noqa: F401
from live_review.modules.streamers import models as streamer_models  # noqa: F401

metadata = Base.metadata
if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url.get_secret_value(),
        target_metadata=metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = build_engine(get_settings())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
