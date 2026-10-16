""" Data for the SDRM volunteer site: the text of every page, help resources, gift
rates, home page stats, volunteer shifts and the sign-ups for them.

The frontend has no data of its own; every page reads these tables through api/sdrm.py.
init_sdrm() creates the tables if they're missing and fills empty ones with the
placeholder rows below (all marked "TODO: verify", none of them real figures).
"""
import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import backref, relationship

from __init__ import app, db
from model.user import User

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Largest amount the Ways to Give calculator accepts, in dollars
GIFT_MAX = 1000000


""" Page text """

class SdrmContent(db.Model):
    """
    One piece of site text, e.g. "give.title" -> "Ways to Give".

    `value` is JSON: usually a string, or a list of objects for repeated things like
    nav links and cards. Strings may use **bold**, *italic*, `code` and [links](/path/).
    """
    __tablename__ = 'sdrm_content'

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)

    def read(self):
        return json.loads(self.value)


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
    SdrmContent.__table__,
    SdrmNeed.__table__, SdrmLocation.__table__, SdrmResource.__table__, resource_needs,
    SdrmRates.__table__, SdrmStat.__table__,
    SdrmInterest.__table__, SdrmOpportunity.__table__, SdrmSignup.__table__,
]


""" Placeholder data (TODO: verify) -- NOT real San Diego Rescue Mission information """

TODO = "TODO: verify"
OFFICIAL_SITE = "https://www.sdrescue.org/"

# Site-relative links ("/sdrm/give/") are resolved against the frontend's base URL.
SEED_CONTENT = {
    # Every page: header, footer, <title>
    "site.name": "Help & Hope",
    "site.tagline": "A student project",
    "site.topbar": [
        {"label": "Get help now", "href": "/sdrm/get-help/", "tone": "orange"},
        {"label": "Volunteer", "href": "/sdrm/volunteer/", "tone": "blue"},
        {"label": "Donate", "href": "/sdrm/give/", "tone": "red"},
    ],
    "site.nav": [
        {"label": "Home", "href": "/"},
        {"label": "Get Help Now", "href": "/sdrm/get-help/"},
        {"label": "Ways to Give", "href": "/sdrm/give/"},
        {"label": "Volunteer", "href": "/sdrm/volunteer/"},
        {"label": "About", "href": "/sdrm/about/"},
    ],
    "site.footer.text": "A student-built guide to finding help, giving, and volunteering in San Diego. "
                        "Every name, number, and shift on this site is placeholder data.",
    "site.footer.exploreHeading": "Explore",
    "site.footer.explore": [
        {"label": "Home", "href": "/"},
        {"label": "Get Help Now", "href": "/sdrm/get-help/"},
        {"label": "About", "href": "/sdrm/about/"},
    ],
    "site.footer.involvedHeading": "Get involved",
    "site.footer.involved": [
        {"label": "Ways to Give", "href": "/sdrm/give/"},
        {"label": "Volunteer", "href": "/sdrm/volunteer/"},
    ],
    "site.footer.emergencyHeading": "In an emergency",
    "site.footer.emergency": "Call 911. For other community services in San Diego County, dial 211.",
    "site.footer.note": f"Student project, not affiliated with San Diego Rescue Mission. Visit [sdrescue.org]({OFFICIAL_SITE}).",

    # Home
    "home.title": "Help and Hope in San Diego",
    "home.lead": "A student-built guide to finding help, giving, and volunteering, inspired by the work of the San Diego Rescue Mission.",
    "home.kicker": "Student project",
    "home.hero.cta": "Find help near you",
    "home.hero.ctaHref": "/sdrm/get-help/",
    "home.hero.image": "/images/sdrm/placeholder-welcome.svg",
    "home.hero.imageAlt": "Placeholder illustration of people gathered around a community table",
    "home.tools.kicker": "Our commitment",
    "home.tools.heading": "Three simple ways to connect",
    "home.tools.intro": "Everyone deserves a warm meal, a safe place to sleep, and a path forward. "
                        "Each tool below turns placeholder data into something you can explore.",
    "home.tools.cards": [
        {"tone": "orange", "icon": "pin", "title": "Get Help Now",
         "text": "Filter shelter, meals, family services, and recovery programs by what you need and where you are.",
         "link": "Find resources", "href": "/sdrm/get-help/"},
        {"tone": "red", "icon": "heart", "title": "Ways to Give",
         "text": "See how a one-time or monthly gift could turn into meals and nights of shelter.",
         "link": "See your impact", "href": "/sdrm/give/"},
        {"tone": "blue", "icon": "people", "title": "Volunteer",
         "text": "Pick the days and interests that suit you, then claim an open spot on a shift.",
         "link": "Find a shift", "href": "/sdrm/volunteer/"},
    ],
    "home.stats.kicker": "By the numbers",
    "home.stats.heading": "What a community can do",
    "home.stats.note": "Placeholder numbers marked “TODO: verify” in our database. They are not real figures.",
    "home.about.image": "/images/sdrm/placeholder-volunteer.svg",
    "home.about.imageAlt": "Placeholder illustration of a group of volunteers",
    "home.about.kicker": "Why this site exists",
    "home.about.heading": "Built by students, for learning",
    "home.about.text": "This class project practices accessible, data-driven web pages for a real-world cause. "
                       "It is not affiliated with the San Diego Rescue Mission, and every name, rate, and shift is a placeholder.",
    "home.about.items": [
        {"text": "Works with a keyboard, a screen reader, and a phone."},
        {"text": "No payments, and an account only keeps what you choose to share."},
        {"text": "All data comes from our Flask server and is marked “TODO: verify”."},
    ],
    "home.about.cta": "About this project",
    "home.about.ctaHref": "/sdrm/about/",
    "home.urgent.heading": "Need help right now?",
    "home.urgent.text": "**In an emergency, call 911.** For other community services in San Diego County, you can dial 211.",
    "home.urgent.buttons": [
        {"label": "Get Help Now", "href": "/sdrm/get-help/", "tone": "orange"},
        {"label": "Volunteer", "href": "/sdrm/volunteer/", "tone": "blue"},
        {"label": "Ways to Give", "href": "/sdrm/give/", "tone": "red"},
    ],

    # Get Help Now
    "getHelp.title": "Get Help Now",
    "getHelp.lead": "Choose what you need and where you are. The list updates as soon as you change a filter.",
    "getHelp.kicker": "Find support",
    "getHelp.filters.heading": "Filter resources",
    "getHelp.results.kicker": "Results",
    "getHelp.results.heading": "Matching resources",
    "getHelp.note": "**Placeholder data.** Program names and areas are examples written for a class project. "
                    "Details marked “TODO: verify” have not been confirmed. For real, current services, "
                    f"visit [sdrescue.org]({OFFICIAL_SITE}). In an emergency, call 911.",

    # Ways to Give
    "give.title": "Ways to Give",
    "give.lead": "Enter an amount to see what it could provide. This is a learning tool only; no payment is collected here.",
    "give.kicker": "Make an impact",
    "give.calc.heading": "Gift impact calculator",
    "give.calc.image": "/images/sdrm/placeholder-give.svg",
    "give.calc.imageAlt": "Placeholder illustration of a shared meal",
    "give.rates.kicker": "The math",
    "give.rates.heading": "How the numbers are calculated",
    "give.rates.caption": "Placeholder conversion rates",
    "give.rates.itemHeading": "Item",
    "give.rates.costHeading": "Placeholder cost",
    "give.rates.meal": "One meal",
    "give.rates.night": "One night of shelter",
    "give.rates.note": "These rates are placeholders marked “TODO: verify” in our database. They are not official figures. "
                       "Results are rounded down and show meals *or* nights, not both.",
    "give.other.kicker": "More than money",
    "give.other.heading": "Other ways to help",
    "give.other.cards": [
        {"title": "Donate items",
         "text": "Many shelters accept new socks, hygiene items, and gently used clothing. Check the official site for the current wish list."},
        {"title": "Host a drive", "text": "Organize a food or supply drive at school, work, or with friends."},
        {"title": "Spread the word",
         "text": "Share where people can find help. A single conversation can connect someone to a meal or a bed."},
    ],
    "give.other.cta": "Give on the official site",
    "give.other.ctaHref": OFFICIAL_SITE,

    # Volunteer
    "volunteer.title": "Volunteer",
    "volunteer.lead": "Pick the days you're free and what you enjoy. Leave a group empty to include every option.",
    "volunteer.kicker": "Give your time",
    "volunteer.filters.heading": "Find a shift",
    "volunteer.results.kicker": "Open shifts",
    "volunteer.results.heading": "Matching opportunities",
    "volunteer.note": "**Demo only.** Shifts and spot counts are placeholders marked “TODO: verify”. Signing up saves the shift "
                      "to your account on our server so you can cancel it any time, but it does not reserve a real shift. "
                      f"To volunteer for real, visit [sdrescue.org]({OFFICIAL_SITE}).",

    # About
    "about.title": "About This Project",
    "about.lead": "A student web development project that practices accessible, data-driven pages for a real-world cause.",
    "about.kicker": "Behind the project",
    "about.what.kicker": "The basics",
    "about.what.heading": "What this site is",
    "about.what.text": "This is a class project inspired by the San Diego Rescue Mission, a nonprofit that serves people "
                       "experiencing homelessness in San Diego. We are not affiliated with the organization, and nothing here "
                       "is official. All names, rates, shifts, addresses, and hours are placeholders stored in our database "
                       "and marked “TODO: verify”.",
    "about.what.image": "/images/sdrm/placeholder-volunteer.svg",
    "about.what.imageAlt": "Placeholder illustration of a group of volunteers",
    "about.built.heading": "Who built it",
    "about.built.text": "Built by students in a computer science course as part of the Open Coding Society curriculum. "
                        "Team member names are left out on purpose; add your team's first names or GitHub usernames here "
                        "if your class requires it.",
    "about.how.heading": "How it works",
    "about.how.items": [
        {"text": "Plain HTML, SASS, and vanilla JavaScript on a Jekyll site, with no frameworks, backed by a Python Flask server and database."},
        {"text": "Its own small SASS system in `_sass/sdrm/` with color, font, and spacing tokens and one partial per component."},
        {"text": "All of the site's text, links, and data come from our Flask server (`/api/sdrm/`), so updating information never requires editing the site."},
        {"text": "Pages are built to work with a keyboard, a screen reader, and a phone screen 375 pixels wide."},
    ],
    "about.privacy.heading": "Privacy",
    "about.privacy.text": "This site does not take payments. If you create an account, your name, email, and any guardian contact "
                          "you add are stored on our server, along with the volunteer shifts you sign up for. You can cancel a "
                          "shift or remove guardian info at any time.",
    "about.privacy.cta": "Visit the official site",
    "about.privacy.ctaHref": OFFICIAL_SITE,

    # Account pages
    "login.title": "Log In or Create an Account",
    "login.lead": "Log in to your account, or make a new one in about a minute.",
    "login.kicker": "Your account",
    "login.login.heading": "Log in",
    "login.login.text": "Welcome back. Enter your email and password.",
    "login.signup.heading": "Create an account",
    "login.signup.text": "New here? Fill in every field. If you're under 18, we'll also ask for a parent or guardian's contact.",
    "login.note": "This is a student project. Don't reuse a password you use anywhere else.",
    "profile.title": "Your Profile",
    "profile.lead": "Your account details, and a parent or guardian's contact if you're under 18.",
    "profile.kicker": "Your account",
    "profile.account.heading": "Your account",
    "profile.account.note": "Only an admin can change your role. Ask a volunteer coordinator if it looks wrong.",
    "profile.guardian.heading": "Parent or guardian",
    "profile.guardian.text": "Student volunteers under 18 add a parent or guardian we can contact. "
                             "Leave both fields empty if you're 18 or older.",
    "coordinator.title": "Coordinator Tools",
    "coordinator.lead": "Tools for volunteer coordinators. The volunteer needs board is coming next.",
    "coordinator.kicker": "Coordinators",
}

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
    """Create any missing SDRM tables, add missing text keys and seed the empty tables. Safe to run on every start; never overwrites rows."""
    with app.app_context():
        db.metadata.create_all(db.engine, tables=SDRM_TABLES)

        # Add any text keys that are missing (new pages / sections); edited ones are kept
        existing = {key for (key,) in db.session.query(SdrmContent.key)}
        db.session.add_all(SdrmContent(key=key, value=json.dumps(value, ensure_ascii=False))
                           for key, value in SEED_CONTENT.items() if key not in existing)

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
