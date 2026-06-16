from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from enum import Enum

db = SQLAlchemy()

# Перечисление статусов для SQLAlchemy
class OrderStatusEnum(Enum):
    OPEN = "открыт"
    WAITING_PARTS = "ожидание запчастей"
    IN_WORK = "в работе"
    COMPLETED = "выполнен"
    CLOSED = "закрыт"
    CANCELLED = "отменен"

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cars = db.relationship('Car', backref='owner', lazy=True)
    orders = db.relationship('WorkOrder', backref='client', lazy=True)

class Car(db.Model):
    __tablename__ = 'cars'
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String(20), unique=True, nullable=False)
    model = db.Column(db.String(100), nullable=False)
    vin = db.Column(db.String(17))
    year = db.Column(db.Integer)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)

class SparePart(db.Model):
    __tablename__ = 'spare_parts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(50), unique=True)
    price = db.Column(db.Float, nullable=False)
    quantity_in_stock = db.Column(db.Float, default=0.0)

class WorkItem(db.Model):
    __tablename__ = 'work_items'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    standard_hours = db.Column(db.Float, nullable=False)
    hourly_rate = db.Column(db.Float, default=100.0)

class Mechanic(db.Model):
    __tablename__ = 'mechanics'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    specialization = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    active = db.Column(db.Boolean, default=True)

    orders = db.relationship('WorkOrder', backref='mechanic', lazy=True)

class OperationalTask(db.Model):
    __tablename__ = 'operational_tasks'
    id = db.Column(db.Integer, primary_key=True)
    task_key = db.Column(db.String(160), unique=True, nullable=False)
    task_type = db.Column(db.String(40), nullable=False, default='ops')
    status = db.Column(db.String(20), nullable=False, default='active')
    note = db.Column(db.String(300))
    snoozed_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WorkOrder(db.Model):
    __tablename__ = 'work_orders'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    car_id = db.Column(db.Integer, db.ForeignKey('cars.id'), nullable=False)
    mechanic_id = db.Column(db.Integer, db.ForeignKey('mechanics.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.Enum(OrderStatusEnum), default=OrderStatusEnum.OPEN)
    total_cost = db.Column(db.Float, default=0.0)

    car = db.relationship('Car', backref='orders', lazy=True)

    # Связи многие-ко-многим: работы, запчасти через промежуточные таблицы
    works = db.relationship('WorkOrderWork', backref='order', cascade='all, delete-orphan')
    parts = db.relationship('WorkOrderPart', backref='order', cascade='all, delete-orphan')

class WorkOrderWork(db.Model):
    __tablename__ = 'work_order_works'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'))
    work_id = db.Column(db.Integer, db.ForeignKey('work_items.id'))
    quantity = db.Column(db.Integer, default=1)  # сколько раз выполнить работу
    actual_hours = db.Column(db.Float, nullable=True)  # по факту

    work = db.relationship('WorkItem')

class WorkOrderPart(db.Model):
    __tablename__ = 'work_order_parts'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('work_orders.id'))
    part_id = db.Column(db.Integer, db.ForeignKey('spare_parts.id'))
    quantity_reserved = db.Column(db.Float, default=0.0)  # зарезервировано
    quantity_used = db.Column(db.Float, default=0.0)      # фактически использовано

    part = db.relationship('SparePart')
