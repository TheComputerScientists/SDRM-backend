""" Volunteer shifts and help resources API for the SDRM volunteer site (model/sdrm.py).

Page text, gift rates and home stats are static JSON in the frontend; only data shared
between users or kept up to date by coordinators lives here.

  GET    /api/sdrm/opportunities                days, interests and shifts with spots left
                                                (plus signedUp when logged in)
  POST   /api/sdrm/opportunities/<id>/signup    take a spot   (login required)
  DELETE /api/sdrm/opportunities/<id>/signup    give it back  (login required)

  GET    /api/sdrm/resources                    needs, locations and help resources; optional
                                                ?need=meals&location=downtown&q=shelter
  POST   /api/sdrm/resources                    add a resource      (coordinator or admin)
  PUT    /api/sdrm/resources/<id>               replace a resource  (coordinator or admin)
  DELETE /api/sdrm/resources/<id>               remove a resource   (coordinator or admin)
"""
from flask import Blueprint, g, request
from flask_restful import Api, Resource
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from __init__ import db
from api.authorize import auth_required, optional_user, role_required
from model.sdrm import (DAYS, RESOURCE_MAX, TODO, SdrmInterest, SdrmLocation, SdrmNeed, SdrmOpportunity,
                        SdrmResource, SdrmSignup)

sdrm_api = Blueprint('sdrm_api', __name__, url_prefix='/api/sdrm')
api = Api(sdrm_api)


def _taken_counts(opportunity_ids):
    """{opportunity id: number of sign-ups} in one query."""
    rows = (db.session.query(SdrmSignup.opportunity_id, func.count(SdrmSignup.id))
            .filter(SdrmSignup.opportunity_id.in_(opportunity_ids))
            .group_by(SdrmSignup.opportunity_id))
    return dict(rows)


def _read_opportunity(opportunity, user_id):
    taken = _taken_counts([opportunity.id]).get(opportunity.id, 0)
    signed_up = SdrmSignup.query.filter_by(opportunity_id=opportunity.id, user_id=user_id).first() is not None
    return opportunity.read(taken, signed_up)


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
            mine = set()
            if user is not None:
                mine = {s.opportunity_id for s in SdrmSignup.query.filter_by(user_id=user.id)}
            return {
                'days': list(DAYS),
                'interests': [i.read() for i in SdrmInterest.query.order_by(SdrmInterest.position)],
                'opportunities': [o.read(taken.get(o.id, 0), o.id in mine) for o in opportunities],
                'loggedIn': user is not None,
            }

    class _Signup(Resource):
        @auth_required()
        def post(self, opportunity_id):
            """Take a spot. Already signed up is fine (200); a full shift is 409."""
            user = g.current_user
            opportunity = SdrmOpportunity.query.get(opportunity_id)
            if opportunity is None:
                return {'message': 'Shift not found'}, 404

            if SdrmSignup.query.filter_by(opportunity_id=opportunity.id, user_id=user.id).first() is None:
                db.session.add(SdrmSignup(opportunity_id=opportunity.id, user_id=user.id))
                try:
                    db.session.flush()
                except IntegrityError:
                    # A second click raced the first; the spot is already theirs
                    db.session.rollback()
                    return _read_opportunity(opportunity, user.id)
                # Count after inserting so two people can't both take the last spot
                if _taken_counts([opportunity.id]).get(opportunity.id, 0) > opportunity.capacity:
                    db.session.rollback()
                    return {'message': 'This shift is full'}, 409
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

    api.add_resource(_Opportunities, '/opportunities')
    api.add_resource(_Signup, '/opportunities/<string:opportunity_id>/signup')
    api.add_resource(_Resources, '/resources')
    api.add_resource(_ResourceItem, '/resources/<string:resource_id>')
