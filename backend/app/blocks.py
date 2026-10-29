from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import Block


def blocked_pair_ids(db: Session, user_id: int) -> set[int]:
    q = select(Block.blocker_id, Block.blocked_id).where(or_(Block.blocker_id == user_id, Block.blocked_id == user_id))
    return {blocked if blocker == user_id else blocker for blocker, blocked in db.execute(q).all()}
