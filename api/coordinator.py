""" Coordinator-only API for the SDRM volunteer site.

Every route here is limited to coordinators and admins with @role_required, which returns
401 when the caller isn't logged in and 403 when a volunteer calls it. The needs board
(issue #4) can add its coordinator routes to this blueprint.
"""
from flask import Blueprint, g, jsonify
from flask_restful import Api, Resource

from api.authorize import role_required

coordinator_api = Blueprint('coordinator_api', __name__, url_prefix='/api/coordinator')
api = Api(coordinator_api)


class CoordinatorAPI:
    class _Ping(Resource):
        @role_required("coordinator", "admin")
        def get(self):
            """Lets the frontend (and tests) confirm the caller has coordinator access."""
            user = g.current_user
            return jsonify({'message': f'Hello {user.name}, you have coordinator access', 'role': user.role})

    api.add_resource(_Ping, '/ping')
