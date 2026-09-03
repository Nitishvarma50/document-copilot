"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = "${up_revision}"
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str],None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}

def upgrade() -> None:
    """Upgrade database schema and/or data, creating a new revision."""
    ${upgrade if upgrade else "pass"}

def downgrade() -> None:
    """Downgrade database schema and/or data back to the previous revision."""
    ${downgrade if downgrade else "pass"}