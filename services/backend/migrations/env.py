from alembic import context

from live_review.core.config import get_settings
from live_review.core.database import Base, build_engine

# No business tables/revision in LIVE-002. BE adds the first coordinated revision.
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
