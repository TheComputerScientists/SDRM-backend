""" Data for the SDRM volunteer site that has to be shared between users: volunteer
shifts and the sign-ups for them (spots left are counted across everyone), and the help
resources (meals, shelter, programs) that coordinators keep up to date.

Resources are public program information only -- never anything about the people the
Mission serves. Page text and the other placeholder data (gift rates, home stats) are
static files in the frontend (assets/data/sdrm/*.json), not database tables.
init_sdrm() creates the tables if they're missing and fills empty ones with the
placeholder rows below (all marked "TODO: verify", none of them real figures).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import backref, relationship

from __init__ import app, db
from model.user import User

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Longest value each resource field may hold (checked by the API before saving)
RESOURCE_MAX = {'name': 200, 'description': 1000, 'address': 200, 'hours': 100, 'phone': 40}


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


SDRM_TABLES = [SdrmInterest.__table__, SdrmOpportunity.__table__, SdrmSignup.__table__,
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
