from flask import request, current_app, g
from flask_login import current_user
from functools import wraps
import jwt
from model.user import User, normalize_role

def _authenticate():
    '''
    Find the caller from the Flask-Login session, else from the JWT cookie or Bearer header.

    Returns (user, None) on success, or (None, (body, status)) describing why not.
    '''
    if current_user.is_authenticated:
        return current_user, None

    token = request.cookies.get(current_app.config.get("JWT_TOKEN_NAME"))
    if not token:
        auth_header = request.headers.get('Authorization', request.headers.get('authorization', '')) or ''
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1].strip()
        elif auth_header:
            token = auth_header.strip()

    if not token:
        return None, ({
            "message": "Authentication required. No session or token found.",
            "data": None,
            "error": "Unauthorized"
        }, 401)

    try:
        # Decode the token and retrieve the user data
        data = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
        user = User.query.filter_by(_uid=data["_uid"]).first()

        if user is None:
            return None, ({
                "message": "Invalid Authentication token!",
                "data": None,
                "error": "Unauthorized"
            }, 401)

        # Tokens issued before this field existed have no token_version claim
        # (treated as 0); reject if it doesn't match the account's current
        # value -- i.e. the password has changed since this token was issued.
        if data.get("token_version", 0) != (user.token_version or 0):
            return None, ({
                "message": "Token is no longer valid -- password has changed.",
                "data": None,
                "error": "Unauthorized"
            }, 401)

        return user, None

    except jwt.ExpiredSignatureError:
        return None, ({
            "message": "Token has expired!",
            "data": None,
            "error": "Unauthorized"
        }, 401)
    except jwt.InvalidTokenError:
        return None, ({
            "message": "Invalid token!",
            "data": None,
            "error": "Unauthorized"
        }, 401)
    except Exception as e:
        return None, ({
            "message": "Something went wrong decoding the token!",
            "data": None,
            "error": str(e)
        }, 500)


def optional_user():
    '''
    The logged-in user, or None for a visitor (or a bad/expired token). Never errors.

    For public endpoints that show a little more to signed-in users.
    '''
    user, _error = _authenticate()
    return user


def auth_required(roles=None):
    '''
    Hybrid authentication decorator supporting both session and JWT token authentication.
    
    This function guards API endpoints by:
      1. First checking for Flask-Login session authentication (current_user)
      2. If no session, checks for valid JWT token in request cookies
      3. Decodes the token and retrieves user data from database
      4. Validates user has required role(s) if specified
      5. Sets g.current_user in Flask's global context for use in decorated function
      6. Returns the decorated function if all checks pass
    
    Authentication priority:
      - Session authentication (Flask-Login) is checked first (faster)
      - JWT token authentication is fallback (stateless, works for APIs)
    
    Args:
        roles: String or list of allowed roles (e.g., "Admin" or ["Admin", "Teacher"])
               If None, any authenticated user is allowed
    
    Possible error responses:
      A. 401 / Unauthorized: no session and token is missing or invalid
      B. 403 / Forbidden: user has insufficient permissions
      C. 500 / Internal Server Error: something went wrong with token decoding
    '''
    def decorator(func_to_guard):
        @wraps(func_to_guard)
        def decorated(*args, **kwargs):
            # Session first (Flask-Login), then the JWT cookie / Bearer header
            user, error = _authenticate()
            if error:
                return error
            # Set g.current_user for consistency across both auth methods
            g.current_user = user

            # At this point, user is authenticated via either session or JWT
            # Now check role requirements if specified
            if roles:
                # Normalize roles to list for consistent checking
                required_roles = roles if isinstance(roles, list) else [roles]
                
                if user.role not in required_roles:
                    return {
                        "message": f"Insufficient permissions. Required roles: {', '.join(required_roles)}",
                        "data": None,
                        "error": "Forbidden"
                    }, 403
            
            # If this is a CORS preflight request, return 200 OK immediately
            if request.method == 'OPTIONS':
                return ('', 200)
            
            # Success - user is authenticated and authorized
            # func_to_guard is the function decorated with @auth_required
            # Returns with the original function arguments
            return func_to_guard(*args, **kwargs)
        
        return decorated
    
    return decorator


# Alias for backward compatibility with existing code using token_required
def token_required(roles=None):
    '''
    Backward compatibility alias for auth_required.
    Existing code using @token_required will continue to work.
    '''
    return auth_required(roles)



def role_required(*roles):
    '''
    Allow only users with one of these SDRM roles, e.g. @role_required("coordinator", "admin").

    Role names are matched without regard to letter case. Built on auth_required, so it returns
      401 / Unauthorized when not logged in, and
      403 / Forbidden when logged in with a role that isn't listed.
    '''
    allowed = [normalize_role(role) for role in roles]
    if not roles or None in allowed:
        raise ValueError(f"role_required: unknown role in {roles}")
    return auth_required(allowed)
