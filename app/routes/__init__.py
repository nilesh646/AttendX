from flask import Blueprint

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
faculty_bp = Blueprint("faculty", __name__, url_prefix="/faculty")
student_bp = Blueprint("student", __name__, url_prefix="/student")


def register_blueprints(app):
    from app.routes import auth_routes    # noqa: F401
    from app.routes import admin_routes   # noqa: F401
    from app.routes import faculty_routes # noqa: F401
    from app.routes import student_routes # noqa: F401
    from app.routes.api_routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(faculty_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(api_bp)
