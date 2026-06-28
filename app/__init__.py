"""
Imou Camera Exotel Voice Call Agent Package
"""
from flask import Flask
from app.config import Config
from app.webhook import webhook_bp
from app.device_manager import device_manager
from app.imou_poller import imou_poller
from app.telegram_service import telegram_bot_poller
from app.lifecycle import app_lifecycle

def create_app(config_class=Config, start_poller: bool = True):
    """
    Application factory for creating and configuring the Flask app instance.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register blueprints
    app.register_blueprint(webhook_bp)

    @app.route("/health", methods=["GET"])
    def health_check():
        return {
            "status": "ok" if app_lifecycle.is_running else "stopping",
            "message": "Imou Exotel Monitor Service status",
            "is_paused": app_lifecycle.is_paused,
            "lifecycle_running": app_lifecycle.is_running,
            "poller_active": imou_poller._thread is not None and imou_poller._thread.is_alive(),
            "telegram_active": telegram_bot_poller._thread is not None and telegram_bot_poller._thread.is_alive()
        }, 200

    # Start active background polling threads if configured and enabled
    if start_poller and not app.config.get("TESTING", False):
        imou_poller.start()
        telegram_bot_poller.start()

    return app
