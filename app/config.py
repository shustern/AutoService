import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'auto_service.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PUBLIC_APP_URL = os.environ.get('PUBLIC_APP_URL')
