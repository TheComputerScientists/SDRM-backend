""" Data for the SDRM volunteer site that has to be shared between users: volunteer
shifts, the sign-ups for them (spots left are counted across everyone) and the service
hours logged on them, and the help resources (meals, shelter, programs) that coordinators
keep up to date.

Resources are public program information only -- never anything about the people the
Mission serves. Page text and the other placeholder data (gift rates, home stats) are
static files in the frontend (assets/data/sdrm/*.json), not database tables.
init_sdrm() creates the tables if they're missing and fills empty ones with the
placeholder rows below (all marked "TODO: verify", none of them real figures).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint, inspect, text
from sqlalchemy.orm import backref, relationship

from __init__ import app, db
from model.user import User

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Longest value each resource field may hold (checked by the API before saving)
RESOURCE_MAX = {'name': 200, 'description': 1000, 'address': 200, 'hours': 100, 'phone': 40}

# Longest value each shift field may hold, and the largest capacity (checked by the API)
OPPORTUNITY_MAX = {'title': 200, 'time': 100, 'description': 1000}
CAPACITY_MAX = 500

# A sign-up can hold spots for a small group (e.g. a student club), not just one person
GROUP_SIZE_MIN, GROUP_SIZE_MAX = 1, 10

# Service hours per log: a quarter hour up to a 12-hour day, in quarter-hour steps
HOURS_MIN, HOURS_MAX, HOURS_STEP = 0.25, 12, 0.25
HOURS_NOTE_MAX = 300
HOURS_STATUSES = ('pending', 'approved', 'rejected')


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
    """A volunteer shift. `capacity` is how many people it takes; spots left = capacity - the group sizes signed up."""
    __tablename__ = 'sdrm_opportunities'

    id = Column(String(32), primary_key=True)
    title = Column(String(200), nullable=False)
    day = Column(String(10), nullable=False)
    interest_id = Column(String(32), ForeignKey('sdrm_interests.id'), nullable=False)
    time = Column(String(100), nullable=False, default='')
    capacity = Column(Integer, nullable=False, default=0)
    description = Column(Text, nullable=False, default='')
    position = Column(Integer, nullable=False, default=0)

    def read(self, taken, signup):
        """Public fields plus spots left, given how many spots are `taken` and the viewer's SdrmSignup (or None)."""
        return {
            'id': self.id,
            'title': self.title,
            'day': self.day,
            'interest': self.interest_id,
            'time': self.time,
            'description': self.description,
            'capacity': self.capacity,
            'spots': max(0, self.capacity - taken),
            'signedUp': signup is not None,
            'groupSize': signup.group_size if signup is not None else None,
        }


class SdrmSignup(db.Model):
    """One user holding `group_size` spots on one shift (themselves plus the rest of their group)."""
    __tablename__ = 'sdrm_signups'
    __table_args__ = (UniqueConstraint('opportunity_id', 'user_id', name='uq_sdrm_signup'),)

    id = Column(Integer, primary_key=True)
    opportunity_id = Column(String(32), ForeignKey('sdrm_opportunities.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    group_size = Column(Integer, nullable=False, default=1)
    created = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Deleting a user frees their spots
    user = relationship(User, backref=backref('sdrm_signups', cascade='all, delete-orphan'))


class SdrmHoursLog(db.Model):
    """Service hours a volunteer logged on a shift they signed up for. A coordinator approves or rejects it."""
    __tablename__ = 'sdrm_hours_logs'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    opportunity_id = Column(String(32), ForeignKey('sdrm_opportunities.id'), nullable=False)
    hours = Column(Float, nullable=False)
    note = Column(String(HOURS_NOTE_MAX), nullable=False, default='')
    status = Column(String(10), nullable=False, default='pending')
    created = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)

    # Deleting a user removes the hours they logged
    user = relationship(User, foreign_keys=[user_id], backref=backref('sdrm_hours_logs', cascade='all, delete-orphan'))
    reviewer = relationship(User, foreign_keys=[reviewed_by])
    opportunity = relationship(SdrmOpportunity)

    def read(self):
        return {
            'id': self.id,
            'opportunity': self.opportunity_id,
            'shift': self.opportunity.title if self.opportunity else self.opportunity_id,
            'day': self.opportunity.day if self.opportunity else '',
            'hours': self.hours,
            'note': self.note,
            'status': self.status,
            'created': self.created.isoformat(),
            'reviewedAt': self.reviewed_at.isoformat() if self.reviewed_at else None,
        }

    def read_for_review(self):
        """read() plus who logged it, for coordinators."""
        return {**self.read(), 'volunteer': self.user.name if self.user else None,
                'uid': self.user.uid if self.user else None}


""" Help resources """

class SdrmNeed(db.Model):
    """A kind of help, e.g. "meals" / "Meals"."""
    __tablename__ = 'sdrm_needs'

    id = Column(String(32), primary_key=True)
    label = Column(String(100), nullable=False)
    position = Column(Integer, nullable=False, default=0)

    def read(self):
        return {'id': self.id, 'label': self.label}


class SdrmLocation(db.Model):
    """An area of the county, e.g. "downtown" / "Downtown San Diego"."""
    __tablename__ = 'sdrm_locations'

    id = Column(String(32), primary_key=True)
    label = Column(String(100), nullable=False)
    position = Column(Integer, nullable=False, default=0)

    def read(self):
        return {'id': self.id, 'label': self.label}


sdrm_resource_needs = Table(
    'sdrm_resource_needs', db.metadata,
    Column('resource_id', String(32), ForeignKey('sdrm_resources.id'), primary_key=True),
    Column('need_id', String(32), ForeignKey('sdrm_needs.id'), primary_key=True),
)


class SdrmResource(db.Model):
    """A public program or service (shelter, meals, ...). Same shape as a resources.json entry."""
    __tablename__ = 'sdrm_resources'

    id = Column(String(32), primary_key=True)
    name = Column(String(RESOURCE_MAX['name']), nullable=False)
    location_id = Column(String(32), ForeignKey('sdrm_locations.id'), nullable=False)
    description = Column(Text, nullable=False, default='')
    address = Column(String(RESOURCE_MAX['address']), nullable=False, default='')
    hours = Column(String(RESOURCE_MAX['hours']), nullable=False, default='')
    phone = Column(String(RESOURCE_MAX['phone']), nullable=False, default='')
    position = Column(Integer, nullable=False, default=0)

    needs = relationship(SdrmNeed, secondary=sdrm_resource_needs, order_by=SdrmNeed.position)

    def read(self):
        return {
            'id': self.id,
            'name': self.name,
            'needs': [n.id for n in self.needs],
            'location': self.location_id,
            'description': self.description,
            'address': self.address,
            'hours': self.hours,
            'phone': self.phone,
        }


SDRM_TABLES = [SdrmInterest.__table__, SdrmOpportunity.__table__, SdrmSignup.__table__, SdrmHoursLog.__table__,
               SdrmNeed.__table__, SdrmLocation.__table__, SdrmResource.__table__, sdrm_resource_needs]


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

# The frontend lists these same resources from assets/data/sdrm/resources.json when this
# server can't be reached, so keep the two in step. Address, hours and phone stay TODO.
SEED_NEEDS = [("shelter", "Shelter"), ("meals", "Meals"), ("family", "Family services"), ("recovery", "Recovery")]

SEED_LOCATIONS = [("downtown", "Downtown San Diego"), ("north", "North County"), ("east", "East County"), ("south", "South Bay")]

SEED_RESOURCES = [
    ("r1", "Emergency Overnight Shelter", ["shelter", "meals"], "downtown", "A safe bed for the night, a shower, and a hot dinner for adults experiencing homelessness."),
    ("r2", "Community Meal Hall", ["meals"], "downtown", "Free walk-in meals served daily. No sign-up or ID needed."),
    ("r3", "Family Housing Program", ["shelter", "family"], "downtown", "Short-term housing for parents with children, plus help finding a longer-term home."),
    ("r4", "Residential Recovery Program", ["recovery", "shelter"], "downtown", "A structured, live-in program with counseling, life skills classes, and job readiness support."),
    ("r5", "Kids and Parents Resource Day", ["family", "meals"], "south", "Weekly drop-in with school supplies, a family lunch, and referrals to child care and health services."),
    ("r6", "Recovery Support Group", ["recovery"], "north", "Peer-led evening support meetings for people in or considering recovery."),
    ("r7", "Mobile Meal Outreach", ["meals"], "east", "A meal van that brings food and water to neighbors who cannot travel downtown."),
]


def init_sdrm():
    """Create any missing SDRM tables and seed the empty ones. Safe to run on every start; never overwrites rows."""
    with app.app_context():
        db.metadata.create_all(db.engine, tables=SDRM_TABLES)

        # create_all() doesn't add columns to an existing table. Sign-ups made before
        # group sign-up (issue #3) become groups of 1.
        if 'group_size' not in {c['name'] for c in inspect(db.engine).get_columns('sdrm_signups')}:
            with db.engine.begin() as connection:
                connection.execute(text('ALTER TABLE sdrm_signups ADD COLUMN group_size INTEGER NOT NULL DEFAULT 1'))

        if not SdrmInterest.query.first():
            db.session.add_all(SdrmInterest(id=i, label=label, position=n) for n, (i, label) in enumerate(SEED_INTERESTS))
        db.session.flush()

        if not SdrmOpportunity.query.first():
            db.session.add_all(SdrmOpportunity(id=i, title=title, day=day, interest_id=interest, time=TODO,
                                               capacity=capacity, description=description, position=n)
                               for n, (i, title, day, interest, capacity, description) in enumerate(SEED_OPPORTUNITIES))

        if not SdrmNeed.query.first():
            db.session.add_all(SdrmNeed(id=i, label=label, position=n) for n, (i, label) in enumerate(SEED_NEEDS))
        if not SdrmLocation.query.first():
            db.session.add_all(SdrmLocation(id=i, label=label, position=n) for n, (i, label) in enumerate(SEED_LOCATIONS))
        db.session.flush()

        if not SdrmResource.query.first():
            needs = {n.id: n for n in SdrmNeed.query}
            db.session.add_all(SdrmResource(id=i, name=name, needs=[needs[x] for x in need_ids], location_id=location,
                                            description=description, address=TODO, hours=TODO, phone=TODO, position=n)
                               for n, (i, name, need_ids, location, description) in enumerate(SEED_RESOURCES))

        db.session.commit()
