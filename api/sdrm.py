""" Public data API for the SDRM volunteer site (model/sdrm.py).

  GET    /api/sdrm/resources                    needs, locations and help resources
  GET    /api/sdrm/rates                        cost of a meal and a night of shelter
  GET    /api/sdrm/stats                        home page stat band
  GET    /api/sdrm/opportunities                days, interests and shifts with spots left
                                                (plus signedUp when logged in)
  POST   /api/sdrm/opportunities/<id>/signup    take a spot   (login required)
  DELETE /api/sdrm/opportunities/<id>/signup    give it back  (login required)
"""
from flask import Blueprint, g
from flask_restful import Api, Resource
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from __init__ import db
from api.authorize import auth_required, optional_user
from model.sdrm import (DAYS, SdrmInterest, SdrmLocation, SdrmNeed, SdrmOpportunity, SdrmRates, SdrmResource,
                        SdrmSignup, SdrmStat)

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


class SdrmAPI:
    class _Resources(Resource):
        def get(self):
            return {
                'needs': [n.read() for n in SdrmNeed.query.order_by(SdrmNeed.position)],
                'locations': [l.read() for l in SdrmLocation.query.order_by(SdrmLocation.position)],
                'resources': [r.read() for r in SdrmResource.query.order_by(SdrmResource.position)],
            }

    class _Rates(Resource):
        def get(self):
            rates = SdrmRates.query.order_by(SdrmRates.id).first()
            if rates is None:
                return {'message': 'No rates have been set'}, 404
            return rates.read()

    class _Stats(Resource):
        def get(self):
            return {'stats': [s.read() for s in SdrmStat.query.order_by(SdrmStat.position)]}

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

    api.add_resource(_Resources, '/resources')
    api.add_resource(_Rates, '/rates')
    api.add_resource(_Stats, '/stats')
    api.add_resource(_Opportunities, '/opportunities')
    api.add_resource(_Signup, '/opportunities/<string:opportunity_id>/signup')
