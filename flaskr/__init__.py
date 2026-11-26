import os

from dotenv import load_dotenv
from flask import Flask

load_dotenv(override=True)


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        DATABASE=os.path.join(app.instance_path, 'flaskr.sqlite'),
    )

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import db
    db.init_app(app)

    from . import auth, chat
    app.register_blueprint(auth.bp)
    app.register_blueprint(chat.bp)
    # Permite url_for('index') además de url_for('chat.index')
    app.add_url_rule('/', endpoint='index')

    return app