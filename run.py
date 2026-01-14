"""Run the Flask application."""

from src.safe_family.app import create_app
from src.safe_family.rules.scheduler import load_schedules, scheduler

flask_app = create_app()

if scheduler.running:
    with flask_app.app_context():
        load_schedules()


if __name__ == "__main__":
    debug = flask_app.config.get("FLASK_DEBUG", False)
    flask_app.run(debug=debug)
