""" Data for the SDRM volunteer site that has to be shared between users: volunteer
shifts and the sign-ups for them (spots left are counted across everyone).

Page text and the other placeholder data (help resources, gift rates, home stats) are
static files in the frontend (assets/data/sdrm/*.json), not database tables.
init_sdrm() creates the tables if they're missing and fills empty ones with the
placeholder rows below (all marked "TODO: verify", none of them real figures).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import backref, relationship

from __init__ import app, db
from model.user import User

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


""" Volunteer """

class SdrmInterest(db.Model):
    """A kind of volunteer work, e.g. "meals" / "Meal service"."""
    __tablename__ = 'sdrm_interests'

    id = Column(String(32), primary_key=True)
    label = Column(String(100), nullable=False)
    position = Column(Integer, nullable=False, default=0)

    def read(self):
        return {'id': self.id, 'label': self.label}


class SdrmOpportunity(db.Model):
    """A volunteer shift. `capacity` is how many people it takes; spots left = capacity - sign-ups."""
    __tablename__ = 'sdrm_opportunities'

    id = Column(String(32), primary_key=True)
    title = Column(String(200), nullable=False)
    day = Column(String(10), nullable=False)
    interest_id = Column(String(32), ForeignKey('sdrm_interests.id'), nullable=False)
    time = Column(String(100), nullable=False, default='')
    capacity = Column(Integer, nullable=False, default=0)
    description = Column(Text, nullable=False, default='')
    position = Column(Integer, nullable=False, default=0)

    def read(self, taken, signed_up):
        """Public fields plus spots left, given how many spots are `taken` and whether the viewer holds one."""
        return {
            'id': self.id,
            'title': self.title,
            'day': self.day,
            'interest': self.interest_id,
            'time': self.time,
            'description': self.description,
            'spots': max(0, self.capacity - taken),
            'signedUp': signed_up,
        }


class SdrmSignup(db.Model):
    """One user holding one spot on one shift."""
    __tablename__ = 'sdrm_signups'
    __table_args__ = (UniqueConstraint('opportunity_id', 'user_id', name='uq_sdrm_signup'),)

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(String(32), ForeignKey('sdrm_opportunities.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Deleting a user frees their spots
    user = relationship(User, backref=backref('sdrm_signups', cascade='all, delete-orphan'))


SDRM_TABLES = [SdrmInterest.__table__, SdrmOpportunity.__table__, SdrmSignup.__table__]


""" Placeholder data (TODO: verify) -- NOT real San Diego Rescue Mission information """

TODO = "TODO: verify"

# The frontend lists these same shifts from assets/data/sdrm/opportunities.json when this
# server can't be reached, so keep the two in step (capacity here = "spots" there).
SEED_INTERESTS = [("meals", "Meal service"), ("donations", "Sorting donations"), ("tutoring", "Tutoring and kids"), ("events", "Events")]

SEED_OPPORTUNITIES = [
    ("o1", "Breakfast serving crew", "Monday", "meals", 4, "Plate and serve breakfast, then help reset the dining room."),
    ("o2", "Donation sorting team", "Tuesday", "donations", 6, "Sort clothing and household donations so they are ready to share."),
    ("o3", "Homework help", "Wednesday", "tutoring", 2, "Help school-age kids with reading and math homework."),
    ("o4", "Dinner serving crew", "Wednesday", "meals", 0, "Serve dinner and greet guests at the door."),
    ("o5", "Weekend lunch line", "Saturday", "meals", 1, "Serve a weekend lunch alongside a small team."),
    ("o6", "Community event helper", "Saturday", "events", 8, "Set up tables, welcome guests, and help run activities."),
    ("o7", "Hygiene kit assembly", "Friday", "donations", 0, "Pack toothbrushes, soap, and socks into kits for guests."),
    ("o8", "Story time for kids", "Sunday", "tutoring", 3, "Read aloud and lead a short craft with young children."),
]


def init_sdrm():
    """Create any missing SDRM tables and seed the empty ones. Safe to run on every start; never overwrites rows."""
    with app.app_context():
        db.metadata.create_all(db.engine, tables=SDRM_TABLES)

        if not SdrmInterest.query.first():
            db.session.add_all(SdrmInterest(id=i, label=label, position=n) for n, (i, label) in enumerate(SEED_INTERESTS))
        db.session.flush()

        if not SdrmOpportunity.query.first():
            db.session.add_all(SdrmOpportunity(id=i, title=title, day=day, interest_id=interest, time=TODO,
                                               capacity=capacity, description=description, position=n)
                               for n, (i, title, day, interest, capacity, description) in enumerate(SEED_OPPORTUNITIES))

        db.session.commit()
