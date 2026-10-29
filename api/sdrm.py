""" Volunteer shifts and help resources API for the SDRM volunteer site (model/sdrm.py).

Page text, gift rates and home stats are static JSON in the frontend; only data shared
between users or kept up to date by coordinators lives here.

  GET    /api/sdrm/opportunities                days, interests and shifts with spots left
                                                (plus signedUp / groupSize when logged in)
  POST   /api/sdrm/opportunities                add a shift      (coordinator or admin)
  PUT    /api/sdrm/opportunities/<id>           replace a shift  (coordinator or admin)
  DELETE /api/sdrm/opportunities/<id>           remove a shift   (coordinator or admin)
  POST   /api/sdrm/opportunities/<id>/signup    take spots for {"groupSize": 1-10} (default 1);
                                                again to change the size  (login required)
  DELETE /api/sdrm/opportunities/<id>/signup    give them back  (login required)

  GET    /api/sdrm/hours/mine                   my hours logs, totals, and the shifts I can log
  POST   /api/sdrm/hours                        log hours on a shift I signed up for (login required)
  DELETE /api/sdrm/hours/<id>                   delete my own pending log            (login required)
  GET    /api/sdrm/hours?status=pending         logs to review     (coordinator or admin)
  PUT    /api/sdrm/hours/<id>                   {"status": "approved" | "rejected"}  (coordinator or admin)

  GET    /api/sdrm/resources                    needs, locations and help resources; optional
                                                ?need=meals&location=downtown&q=shelter
  POST   /api/sdrm/resources                    add a resource      (coordinator or admin)
  PUT    /api/sdrm/resources/<id>               replace a resource  (coordinator or admin)
  DELETE /api/sdrm/resources/<id>               remove a resource   (coordinator or admin)
"""
from datetime import datetime

from flask import Blueprint, g, request
from flask_restful import Api, Resource
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from __init__ import db
from api.authorize import auth_required, optional_user, role_required
from model.sdrm import (CAPACITY_MAX, DAYS, GROUP_SIZE_MAX, GROUP_SIZE_MIN, HOURS_MAX, HOURS_MIN, HOURS_NOTE_MAX,
                        HOURS_STATUSES, HOURS_STEP, OPPORTUNITY_MAX, RESOURCE_MAX, TODO, SdrmHoursLog, SdrmInterest,
                        SdrmLocation, SdrmNeed, SdrmOpportunity, SdrmResource, SdrmSignup)

sdrm_api = Blueprint('sdrm_api', __name__, url_prefix='/api/sdrm')
api = Api(sdrm_api)


def _taken_counts(opportunity_ids):
    """{opportunity id: spots taken (the group sizes added up)} in one query."""
    rows = (db.session.query(SdrmSignup.opportunity_id, func.sum(SdrmSignup.group_size))
            .filter(SdrmSignup.opportunity_id.in_(opportunity_ids))
            .group_by(SdrmSignup.opportunity_id))
    return {opportunity_id: int(taken or 0) for opportunity_id, taken in rows}


def _read_opportunity(opportunity, user_id):
    taken = _taken_counts([opportunity.id]).get(opportunity.id, 0)
    signup = SdrmSignup.query.filter_by(opportunity_id=opportunity.id, user_id=user_id).first()
    return opportunity.read(taken, signup)


def _whole_number(value):
    """True for an int that isn't a bool (JSON true would otherwise count as 1)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _group_size(body):
    """The groupSize in a sign-up body (1 when missing). Returns (size, None) or (None, error message)."""
    if body is None:
        return GROUP_SIZE_MIN, None
    if not isinstance(body, dict):
        return None, 'Send the sign-up as a JSON object'
    size = body.get('groupSize', GROUP_SIZE_MIN)
    if not _whole_number(size) or not GROUP_SIZE_MIN <= size <= GROUP_SIZE_MAX:
        return None, f'Group size must be a whole number from {GROUP_SIZE_MIN} to {GROUP_SIZE_MAX}'
    return size, None


def _opportunity_fields(body, opportunity=None):
    """Check a shift sent by a coordinator. Returns (fields, None) or (None, error message)."""
    if not isinstance(body, dict):
        return None, 'Send the shift as a JSON object'

    fields = {}
    for key in ('title', 'time', 'description'):
        value = body.get(key, '')
        if not isinstance(value, str):
            return None, f'{key.capitalize()} must be text'
        value = value.strip()
        if len(value) > OPPORTUNITY_MAX[key]:
            return None, f'{key.capitalize()} must be {OPPORTUNITY_MAX[key]} characters or fewer'
        fields[key] = value
    for key in ('title', 'description'):
        if not fields[key]:
            return None, f'{key.capitalize()} is required'
    # Not known yet: keep the same placeholder the seeded shifts use
    fields['time'] = fields['time'] or TODO

    day = body.get('day')
    if day not in DAYS:
        return None, f'Day must be one of {", ".join(DAYS)}'
    fields['day'] = day

    interest = body.get('interest')
    if not isinstance(interest, str) or not interest:
        return None, 'Interest is required'
    if SdrmInterest.query.get(interest) is None:
        return None, f'Unknown interest: {interest}'
    fields['interest_id'] = interest

    capacity = body.get('capacity')
    if not _whole_number(capacity) or not 0 <= capacity <= CAPACITY_MAX:
        return None, f'Capacity must be a whole number from 0 to {CAPACITY_MAX}'
    if opportunity is not None:
        taken = _taken_counts([opportunity.id]).get(opportunity.id, 0)
        if capacity < taken:
            return None, f'Capacity can\'t be less than the {taken} spots already taken'
    fields['capacity'] = capacity

    return fields, None


def _next_opportunity_id():
    """"o" plus one more than the highest number used so far (o1, o2, ... from the seed)."""
    numbers = [int(o.id[1:]) for o in SdrmOpportunity.query.with_entities(SdrmOpportunity.id) if o.id[1:].isdigit()]
    return f'o{max(numbers, default=0) + 1}'


def _hours_fields(body, user):
    """Check hours a volunteer is logging. Returns (fields, None) or (None, error message)."""
    if not isinstance(body, dict):
        return None, 'Send the hours as a JSON object'

    opportunity_id = body.get('opportunity')
    if not isinstance(opportunity_id, str) or not opportunity_id:
        return None, 'Choose the shift you volunteered on'
    if SdrmOpportunity.query.get(opportunity_id) is None:
        return None, f'Unknown shift: {opportunity_id}'
    if SdrmSignup.query.filter_by(opportunity_id=opportunity_id, user_id=user.id).first() is None:
        return None, 'You can only log hours for a shift you signed up for'

    hours = body.get('hours')
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not HOURS_MIN <= hours <= HOURS_MAX:
        return None, f'Hours must be a number from {HOURS_MIN} to {HOURS_MAX}'
    steps = hours / HOURS_STEP
    if abs(steps - round(steps)) > 1e-9:
        return None, 'Hours must be in quarter-hour steps (for example 1.25 or 2.5)'

    note = body.get('note', '')
    if note is None:
        note = ''
    if not isinstance(note, str):
        return None, 'Note must be text'
    note = note.strip()
    if len(note) > HOURS_NOTE_MAX:
        return None, f'Note must be {HOURS_NOTE_MAX} characters or fewer'

    return {'opportunity_id': opportunity_id, 'hours': float(hours), 'note': note}, None


def _resource_fields(body):
    """Check a resource sent by a coordinator. Returns (fields, None) or (None, error message)."""
    if not isinstance(body, dict):
        return None, 'Send the resource as a JSON object'

    fields = {}
    for key in ('name', 'description', 'address', 'hours', 'phone'):
        value = body.get(key, '')
        if not isinstance(value, str):
            return None, f'{key.capitalize()} must be text'
        value = value.strip()
        if len(value) > RESOURCE_MAX[key]:
            return None, f'{key.capitalize()} must be {RESOURCE_MAX[key]} characters or fewer'
        fields[key] = value
    for key in ('name', 'description'):
        if not fields[key]:
            return None, f'{key.capitalize()} is required'
    # Not known yet: keep the same placeholder the seeded resources use
    for key in ('address', 'hours', 'phone'):
        fields[key] = fields[key] or TODO

    need_ids = body.get('needs')
    if not isinstance(need_ids, list) or not need_ids or not all(isinstance(n, str) for n in need_ids):
        return None, 'Choose at least one need'
    needs = SdrmNeed.query.filter(SdrmNeed.id.in_(need_ids)).all()
    unknown = sorted(set(need_ids) - {n.id for n in needs})
    if unknown:
        return None, f'Unknown need: {", ".join(unknown)}'
    fields['needs'] = needs

    location = body.get('location')
    if not isinstance(location, str) or not location:
        return None, 'Location is required'
    if SdrmLocation.query.get(location) is None:
        return None, f'Unknown location: {location}'
    fields['location_id'] = location

    return fields, None


def _next_resource_id():
    """"r" plus one more than the highest number used so far (r1, r2, ... from the seed)."""
    numbers = [int(r.id[1:]) for r in SdrmResource.query.with_entities(SdrmResource.id) if r.id[1:].isdigit()]
    return f'r{max(numbers, default=0) + 1}'


class SdrmAPI:
    class _Opportunities(Resource):
        def get(self):
            user = optional_user()
            opportunities = SdrmOpportunity.query.order_by(SdrmOpportunity.position).all()
            taken = _taken_counts([o.id for o in opportunities])
            mine = {}
            if user is not None:
                mine = {s.opportunity_id: s for s in SdrmSignup.query.filter_by(user_id=user.id)}
            return {
                'days': list(DAYS),
                'interests': [i.read() for i in SdrmInterest.query.order_by(SdrmInterest.position)],
                'opportunities': [o.read(taken.get(o.id, 0), mine.get(o.id)) for o in opportunities],
                'loggedIn': user is not None,
            }

        @role_required("coordinator", "admin")
        def post(self):
            fields, error = _opportunity_fields(request.get_json(silent=True))
            if error:
                return {'message': error}, 400
            last = db.session.query(func.max(SdrmOpportunity.position)).scalar()
            opportunity = SdrmOpportunity(id=_next_opportunity_id(), position=(last or 0) + 1, **fields)
            db.session.add(opportunity)
            db.session.commit()
            return opportunity.read(0, None), 201

    class _OpportunityItem(Resource):
        @role_required("coordinator", "admin")
        def put(self, opportunity_id):
            opportunity = SdrmOpportunity.query.get(opportunity_id)
            if opportunity is None:
                return {'message': 'Shift not found'}, 404
            fields, error = _opportunity_fields(request.get_json(silent=True), opportunity)
            if error:
                return {'message': error}, 400
            for key, value in fields.items():
                setattr(opportunity, key, value)
            db.session.commit()
            return _read_opportunity(opportunity, g.current_user.id)

        @role_required("coordinator", "admin")
        def delete(self, opportunity_id):
            """Removes the shift with its sign-ups and unapproved hours; approved hours are kept, so it's refused."""
            opportunity = SdrmOpportunity.query.get(opportunity_id)
            if opportunity is None:
                return {'message': 'Shift not found'}, 404
            if SdrmHoursLog.query.filter_by(opportunity_id=opportunity.id, status='approved').first() is not None:
                return {'message': f'{opportunity.title} has approved service hours, so it can\'t be deleted. '
                                   'Set its capacity to 0 to close it instead.'}, 400
            SdrmHoursLog.query.filter_by(opportunity_id=opportunity.id).delete()
            SdrmSignup.query.filter_by(opportunity_id=opportunity.id).delete()
            db.session.delete(opportunity)
            db.session.commit()
            return {'message': f'Deleted {opportunity.title}', 'id': opportunity_id}

    class _Signup(Resource):
        @auth_required()
        def post(self, opportunity_id):
            """Take group_size spots, or change the size of an existing sign-up. Not enough spots left is 400."""
            user = g.current_user
            opportunity = SdrmOpportunity.query.get(opportunity_id)
            if opportunity is None:
                return {'message': 'Shift not found'}, 404
            size, error = _group_size(request.get_json(silent=True))
            if error:
                return {'message': error}, 400

            signup = SdrmSignup.query.filter_by(opportunity_id=opportunity.id, user_id=user.id).first()
            if signup is not None and signup.group_size == size:
                return _read_opportunity(opportunity, user.id)
            if signup is None:
                db.session.add(SdrmSignup(opportunity_id=opportunity.id, user_id=user.id, group_size=size))
            else:
                signup.group_size = size
            try:
                db.session.flush()
            except IntegrityError:
                # A second click raced the first; the spots are already theirs
                db.session.rollback()
                return _read_opportunity(opportunity, user.id)
            # Count after saving so two groups can't both take the last spots
            taken = _taken_counts([opportunity.id]).get(opportunity.id, 0)
            if taken > opportunity.capacity:
                db.session.rollback()
                left = max(0, opportunity.capacity - (taken - size))
                if left == 0:
                    return {'message': 'This shift is full', 'spots': 0}, 400
                return {'message': f'Only {left} {"spot" if left == 1 else "spots"} left on this shift; '
                                   f'your group needs {size}', 'spots': left}, 400
            db.session.commit()

            return _read_opportunity(opportunity, user.id)

        @auth_required()
        def delete(self, opportunity_id):
            """Give a spot back. Not signed up is fine (200)."""
            user = g.current_user
            opportunity = SdrmOpportunity.query.get(opportunity_id)
            if opportunity is None:
                return {'message': 'Shift not found'}, 404

            SdrmSignup.query.filter_by(opportunity_id=opportunity.id, user_id=user.id).delete()
            db.session.commit()
            return _read_opportunity(opportunity, user.id)

    class _Resources(Resource):
        def get(self):
            """Public list. need/location are ids; q matches name, description or a need's label."""
            need = request.args.get('need', '').strip()
            location = request.args.get('location', '').strip()
            q = request.args.get('q', '').strip().lower()

            needs = SdrmNeed.query.order_by(SdrmNeed.position).all()
            resources = SdrmResource.query.order_by(SdrmResource.position, SdrmResource.id).all()
            if need and need != 'all':
                resources = [r for r in resources if need in {n.id for n in r.needs}]
            if location and location != 'all':
                resources = [r for r in resources if r.location_id == location]
            if q:
                resources = [r for r in resources
                             if q in r.name.lower() or q in r.description.lower()
                             or any(q in n.label.lower() or q == n.id for n in r.needs)]
            return {
                'needs': [n.read() for n in needs],
                'locations': [l.read() for l in SdrmLocation.query.order_by(SdrmLocation.position)],
                'resources': [r.read() for r in resources],
            }

        @role_required("coordinator", "admin")
        def post(self):
            fields, error = _resource_fields(request.get_json(silent=True))
            if error:
                return {'message': error}, 400
            last = db.session.query(func.max(SdrmResource.position)).scalar()
            resource = SdrmResource(id=_next_resource_id(), position=(last or 0) + 1, **fields)
            db.session.add(resource)
            db.session.commit()
            return resource.read(), 201

    class _ResourceItem(Resource):
        @role_required("coordinator", "admin")
        def put(self, resource_id):
            resource = SdrmResource.query.get(resource_id)
            if resource is None:
                return {'message': 'Resource not found'}, 404
            fields, error = _resource_fields(request.get_json(silent=True))
            if error:
                return {'message': error}, 400
            for key, value in fields.items():
                setattr(resource, key, value)
            db.session.commit()
            return resource.read()

        @role_required("coordinator", "admin")
        def delete(self, resource_id):
            resource = SdrmResource.query.get(resource_id)
            if resource is None:
                return {'message': 'Resource not found'}, 404
            db.session.delete(resource)
            db.session.commit()
            return {'message': f'Deleted {resource.name}', 'id': resource_id}

    class _Hours(Resource):
        @role_required("coordinator", "admin")
        def get(self):
            """Logs for coordinators to review, newest first; ?status=pending|approved|rejected (all when left out)."""
            status = request.args.get('status', '').strip()
            query = SdrmHoursLog.query
            if status:
                if status not in HOURS_STATUSES:
                    return {'message': f'Status must be one of {", ".join(HOURS_STATUSES)}'}, 400
                query = query.filter_by(status=status)
            return {'logs': [log.read_for_review() for log in query.order_by(SdrmHoursLog.created.desc())]}

        @auth_required()
        def post(self):
            """Log hours on a shift I signed up for; a coordinator approves them later."""
            fields, error = _hours_fields(request.get_json(silent=True), g.current_user)
            if error:
                return {'message': error}, 400
            log = SdrmHoursLog(user_id=g.current_user.id, status='pending', **fields)
            db.session.add(log)
            db.session.commit()
            return log.read(), 201

    class _MyHours(Resource):
        @auth_required()
        def get(self):
            user = g.current_user
            logs = SdrmHoursLog.query.filter_by(user_id=user.id).order_by(SdrmHoursLog.created.desc()).all()
            signups = (SdrmOpportunity.query.join(SdrmSignup, SdrmSignup.opportunity_id == SdrmOpportunity.id)
                       .filter(SdrmSignup.user_id == user.id).order_by(SdrmOpportunity.position))
            return {
                'logs': [log.read() for log in logs],
                'totals': {status: sum(log.hours for log in logs if log.status == status)
                           for status in ('approved', 'pending')},
                'shifts': [{'id': o.id, 'title': o.title, 'day': o.day} for o in signups],
            }

    class _HoursItem(Resource):
        @role_required("coordinator", "admin")
        def put(self, log_id):
            log = SdrmHoursLog.query.get(log_id)
            if log is None:
                return {'message': 'Hours log not found'}, 404
            body = request.get_json(silent=True)
            status = body.get('status') if isinstance(body, dict) else None
            if status not in ('approved', 'rejected'):
                return {'message': 'Status must be approved or rejected'}, 400
            if log.user_id == g.current_user.id:
                return {'message': 'Another coordinator has to review your own hours'}, 403
            log.status = status
            log.reviewed_by = g.current_user.id
            log.reviewed_at = datetime.utcnow()
            db.session.commit()
            return log.read_for_review()

        @auth_required()
        def delete(self, log_id):
            """Delete one of my own logs while it's still pending."""
            log = SdrmHoursLog.query.get(log_id)
            if log is None:
                return {'message': 'Hours log not found'}, 404
            if log.user_id != g.current_user.id:
                return {'message': 'You can only delete your own hours'}, 403
            if log.status != 'pending':
                return {'message': f'These hours were already {log.status}, so they can\'t be deleted'}, 400
            db.session.delete(log)
            db.session.commit()
            return {'message': 'Deleted', 'id': log_id}

    api.add_resource(_Opportunities, '/opportunities')
    api.add_resource(_OpportunityItem, '/opportunities/<string:opportunity_id>')
    api.add_resource(_Signup, '/opportunities/<string:opportunity_id>/signup')
    api.add_resource(_Hours, '/hours')
    api.add_resource(_MyHours, '/hours/mine')
    api.add_resource(_HoursItem, '/hours/<int:log_id>')
    api.add_resource(_Resources, '/resources')
    api.add_resource(_ResourceItem, '/resources/<string:resource_id>')
