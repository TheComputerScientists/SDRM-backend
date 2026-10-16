""" Data for the SDRM volunteer site: help resources, gift rates, home page stats,
volunteer shifts and the sign-ups for them.

The frontend has no data of its own; every page reads these tables through api/sdrm.py.
init_sdrm() creates the tables if they're missing and fills empty ones with the
placeholder rows below (all marked "TODO: verify", none of them real figures).
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import backref, relationship

from __init__ import app, db
from model.user import User

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


""" Get Help Now """

resource_needs = Table(
    'sdrm_resource_needs',
    db.metadata,
    Column('resource_id', String(32), ForeignKey('sdrm_resources.id'), primary_key=True),
    Column('need_id', String(32), ForeignKey('sdrm_needs.id'), primary_key=True),
)


class SdrmNeed(db.Model):
    """A kind of help, e.g. "shelter" / "Shelter"."""
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


class SdrmResource(db.Model):
    """A program someone can go to for help."""
    __tablename__ = 'sdrm_resources'

    id = Column(String(32), primary_key=True)
    name = Column(String(200), nullable=False)
    location_id = Column(String(32), ForeignKey('sdrm_locations.id'), nullable=False)
    description = Column(Text, nullable=False, default='')
    address = Column(String(255), nullable=False, default='')
    hours = Column(String(255), nullable=False, default='')
    phone = Column(String(50), nullable=False, default='')
    position = Column(Integer, nullable=False, default=0)

    needs = relationship(SdrmNeed, secondary=resource_needs, order_by=SdrmNeed.position)

    def read(self):
        return {
            'id': self.id,
            'name': self.name,
            'needs': [need.id for need in self.needs],
            'location': self.location_id,
            'description': self.description,
            'address': self.address,
            'hours': self.hours,
            'phone': self.phone,
        }


""" Ways to Give """

class SdrmRates(db.Model):
    """What one meal and one night of shelter cost. The site uses the first row."""
    __tablename__ = 'sdrm_rates'

    id = Column(Integer, primary_key=True)
    currency = Column(String(3), nullable=False, default='USD')
    cost_per_meal = Column(Float, nullable=False)
    cost_per_night = Column(Float, nullable=False)
    last_checked = Column(String(50), nullable=False, default='')

    def read(self):
        return {
            'currency': self.currency,
            'costPerMeal': self.cost_per_meal,
            'costPerNight': self.cost_per_night,
            'lastChecked': self.last_checked,
        }


""" Home page """

class SdrmStat(db.Model):
    """One number in the home page stat band."""
    __tablename__ = 'sdrm_stats'

    id = Column(String(32), primary_key=True)
    value = Column(Integer, nullable=False)
    suffix = Column(String(10), nullable=False, default='')
    label = Column(String(200), nullable=False)
    source = Column(String(255), nullable=False, default='')
    position = Column(Integer, nullable=False, default=0)

    def read(self):
        return {'id': self.id, 'value': self.value, 'suffix': self.suffix, 'label': self.label, 'source': self.source}


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


SDRM_TABLES = [
    SdrmNeed.__table__, SdrmLocation.__table__, SdrmResource.__table__, resource_needs,
    SdrmRates.__table__, SdrmStat.__table__,
    SdrmInterest.__table__, SdrmOpportunity.__table__, SdrmSignup.__table__,
]


""" Placeholder data (TODO: verify) -- NOT real San Diego Rescue Mission information """

TODO = "TODO: verify"

SEED_NEEDS = [("shelter", "Shelter"), ("meals", "Meals"), ("family", "Family services"), ("recovery", "Recovery")]

SEED_LOCATIONS = [("downtown", "Downtown San Diego"), ("north", "North County"), ("east", "East County"), ("south", "South Bay")]

SEED_RESOURCES = [
    ("r1", "Emergency Overnight Shelter", ["shelter", "meals"], "downtown",
     "A safe bed for the night, a shower, and a hot dinner for adults experiencing homelessness."),
    ("r2", "Community Meal Hall", ["meals"], "downtown",
     "Free walk-in meals served daily. No sign-up or ID needed."),
    ("r3", "Family Housing Program", ["shelter", "family"], "downtown",
     "Short-term housing for parents with children, plus help finding a longer-term home."),
    ("r4", "Residential Recovery Program", ["recovery", "shelter"], "downtown",
     "A structured, live-in program with counseling, life skills classes, and job readiness support."),
    ("r5", "Kids and Parents Resource Day", ["family", "meals"], "south",
     "Weekly drop-in with school supplies, a family lunch, and referrals to child care and health services."),
    ("r6", "Recovery Support Group", ["recovery"], "north",
     "Peer-led evening support meetings for people in or considering recovery."),
    ("r7", "Mobile Meal Outreach", ["meals"], "east",
     "A meal van that brings food and water to neighbors who cannot travel downtown."),
]

SEED_RATES = {"currency": "USD", "cost_per_meal": 2.5, "cost_per_night": 40, "last_checked": TODO}

SEED_STATS = [
    ("meals", 1000, "+", "Meals served each week (placeholder)"),
    ("beds", 250, "", "Shelter beds each night (placeholder)"),
    ("volunteers", 500, "+", "Volunteer shifts each month (placeholder)"),
]

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

        if not SdrmNeed.query.first():
            db.session.add_all(SdrmNeed(id=i, label=label, position=n) for n, (i, label) in enumerate(SEED_NEEDS))
        if not SdrmLocation.query.first():
            db.session.add_all(SdrmLocation(id=i, label=label, position=n) for n, (i, label) in enumerate(SEED_LOCATIONS))
        db.session.flush()

        if not SdrmResource.query.first():
            for n, (i, name, needs, location, description) in enumerate(SEED_RESOURCES):
                resource = SdrmResource(id=i, name=name, location_id=location, description=description,
                                        address=TODO, hours=TODO, phone=TODO, position=n)
                resource.needs = SdrmNeed.query.filter(SdrmNeed.id.in_(needs)).all()
                db.session.add(resource)

        if not SdrmRates.query.first():
            db.session.add(SdrmRates(**SEED_RATES))

        if not SdrmStat.query.first():
            db.session.add_all(SdrmStat(id=i, value=value, suffix=suffix, label=label, source=TODO, position=n)
                               for n, (i, value, suffix, label) in enumerate(SEED_STATS))

        if not SdrmInterest.query.first():
            db.session.add_all(SdrmInterest(id=i, label=label, position=n) for n, (i, label) in enumerate(SEED_INTERESTS))
        db.session.flush()

        if not SdrmOpportunity.query.first():
            db.session.add_all(SdrmOpportunity(id=i, title=title, day=day, interest_id=interest, time=TODO,
                                               capacity=capacity, description=description, position=n)
                               for n, (i, title, day, interest, capacity, description) in enumerate(SEED_OPPORTUNITIES))

        db.session.commit()
