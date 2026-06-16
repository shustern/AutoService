from flask import Flask, request, jsonify, send_file, render_template, session
from flask_cors import CORS
from app.config import Config
from app.models import db, Client, Car, Mechanic, OperationalTask, WorkItem, SparePart, WorkOrder, WorkOrderPart, WorkOrderWork, OrderStatusEnum
from app.services import (
    add_work_to_order,
    add_part_to_order,
    analyze_order_readiness,
    build_service_radar,
    change_order_status,
    forecast_spare_parts,
    get_car_health_card,
    get_maintenance_recommendations,
    get_master_priority,
    get_stuck_orders,
    remove_part_from_order,
    remove_work_from_order,
    suggest_works_by_complaint,
    use_part,
)
from app.reports import generate_order_document
import io
import os
from datetime import datetime, timedelta

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['ADMIN_USERNAME'] = os.environ.get('ADMIN_USERNAME', 'admin')
    app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'autoservice2026')
    CORS(app)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        _ensure_schema()

    @app.before_request
    def require_login():
        public_endpoints = {'index', 'static', 'login', 'auth_status', 'qr_page', 'qr_svg'}
        if request.endpoint in public_endpoints:
            return None
        if request.path.startswith('/api/') and not session.get('authenticated'):
            return jsonify({'error': 'Требуется вход в систему'}), 401
        return None

    @app.route('/')
    def index():
        return render_template('index.html')

    def get_public_url():
        configured_url = app.config.get('PUBLIC_APP_URL')
        if configured_url:
            return configured_url.rstrip('/')
        return request.host_url.rstrip('/')

    @app.route('/qr')
    def qr_page():
        public_url = get_public_url()
        return render_template('qr.html', public_url=public_url)

    @app.route('/qr.svg')
    def qr_svg():
        import qrcode
        import qrcode.image.svg

        public_url = get_public_url()
        qr = qrcode.QRCode(version=None, box_size=10, border=4)
        qr.add_data(public_url)
        qr.make(fit=True)
        output = io.BytesIO()
        qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(output)
        output.seek(0)
        return send_file(output, mimetype='image/svg+xml')

    @app.route('/api/auth/me', methods=['GET'])
    def auth_status():
        return jsonify({
            'authenticated': bool(session.get('authenticated')),
            'user': session.get('user')
        })

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.json or {}
        if (
            data.get('username') == app.config['ADMIN_USERNAME']
            and data.get('password') == app.config['ADMIN_PASSWORD']
        ):
            session['authenticated'] = True
            session['user'] = data.get('username')
            return jsonify({'message': 'Вход выполнен', 'user': session['user']}), 200
        return jsonify({'error': 'Неверный логин или пароль'}), 401

    @app.route('/api/auth/logout', methods=['POST'])
    def logout():
        session.clear()
        return jsonify({'message': 'Вы вышли из системы'}), 200

    @app.route('/api/dashboard', methods=['GET'])
    def get_dashboard():
        orders = WorkOrder.query.all()
        parts = SparePart.query.all()
        active_statuses = {
            OrderStatusEnum.OPEN,
            OrderStatusEnum.WAITING_PARTS,
            OrderStatusEnum.IN_WORK,
        }
        revenue = sum(order.total_cost for order in orders if order.status in (
            OrderStatusEnum.COMPLETED,
            OrderStatusEnum.CLOSED,
        ))
        stock_value = sum(part.price * part.quantity_in_stock for part in parts)
        active_orders = sum(1 for order in orders if order.status in active_statuses)
        low_stock = sum(1 for part in parts if part.quantity_in_stock <= 3)
        status_counts = {}
        for status in OrderStatusEnum:
            status_counts[status.value] = sum(1 for order in orders if order.status == status)
        return jsonify({
            'clients': Client.query.count(),
            'cars': Car.query.count(),
            'orders': len(orders),
            'active_orders': active_orders,
            'revenue': revenue,
            'stock_value': stock_value,
            'low_stock_parts': low_stock,
            'status_counts': status_counts,
            'kpi': {
                'before_order_minutes': 45,
                'after_order_minutes': 12,
                'before_people': 3,
                'after_people': 1,
                'stock_errors_reduction_percent': 70
            }
        })

    @app.route('/api/service-radar', methods=['GET'])
    def get_service_radar():
        return jsonify({
            'killer_feature': 'Сервисный радар повторных визитов',
            'description': 'Система сама находит клиентов, которым стоит позвонить, исходя из истории заказов, статуса работ и возраста автомобиля.',
            'items': build_service_radar()
        })

    @app.route('/api/parts/forecast', methods=['GET'])
    def get_parts_forecast():
        return jsonify({
            'killer_feature': 'Прогноз дефицита запчастей',
            'items': forecast_spare_parts()
        })

    @app.route('/api/complaints/suggest', methods=['POST'])
    def suggest_complaint_works():
        data = request.json or {}
        return jsonify(suggest_works_by_complaint(data.get('complaint', '')))

    @app.route('/api/cars/<int:car_id>/health', methods=['GET'])
    def get_car_health(car_id):
        try:
            return jsonify(get_car_health_card(car_id))
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/stuck', methods=['GET'])
    def get_orders_stuck():
        return jsonify({'items': get_stuck_orders()})

    @app.route('/api/orders/priority', methods=['GET'])
    def get_orders_priority():
        return jsonify({'items': get_master_priority()})

    @app.route('/api/maintenance/recommendations', methods=['GET'])
    def get_maintenance():
        return jsonify({'items': get_maintenance_recommendations()})

    @app.route('/api/ops/tasks', methods=['POST'])
    def save_operational_task():
        data = request.json or {}
        task_key = data.get('task_key')
        status = data.get('status')
        if not task_key:
            return jsonify({'error': 'Не указан идентификатор карточки'}), 400
        if status not in ('done', 'snoozed'):
            return jsonify({'error': 'Некорректное действие с карточкой'}), 400

        task = OperationalTask.query.filter_by(task_key=task_key).first()
        if not task:
            task = OperationalTask(task_key=task_key)
            db.session.add(task)

        task.task_type = data.get('task_type') or 'ops'
        task.status = status
        task.note = data.get('note')
        task.updated_at = datetime.utcnow()
        task.snoozed_until = datetime.utcnow() + timedelta(days=int(data.get('snooze_days', 7))) if status == 'snoozed' else None
        db.session.commit()

        return jsonify({
            'message': 'Карточка обработана' if status == 'done' else 'Карточка отложена',
            'task_key': task.task_key,
            'status': task.status,
            'snoozed_until': task.snoozed_until.isoformat() if task.snoozed_until else None,
        }), 200

    # ---------- Мастера ----------
    @app.route('/api/mechanics', methods=['GET'])
    def get_mechanics():
        mechanics = Mechanic.query.order_by(Mechanic.name).all()
        return jsonify([{
            'id': item.id,
            'name': item.name,
            'specialization': item.specialization,
            'phone': item.phone,
            'active': item.active
        } for item in mechanics])

    @app.route('/api/mechanics', methods=['POST'])
    def create_mechanic():
        data = request.json
        mechanic = Mechanic(
            name=data['name'],
            specialization=data['specialization'],
            phone=data.get('phone'),
            active=data.get('active', True),
        )
        db.session.add(mechanic)
        db.session.commit()
        return jsonify({'id': mechanic.id}), 201

    @app.route('/api/mechanics/<int:mechanic_id>', methods=['DELETE'])
    def delete_mechanic(mechanic_id):
        mechanic = Mechanic.query.get_or_404(mechanic_id)
        if mechanic.orders:
            return jsonify({'error': 'Нельзя удалить мастера, пока за ним закреплены заказы'}), 400
        db.session.delete(mechanic)
        db.session.commit()
        return jsonify({'message': 'Мастер удален'}), 200

    # ---------- Клиенты ----------
    @app.route('/api/clients', methods=['GET'])
    def get_clients():
        clients = Client.query.all()
        return jsonify([{'id': c.id, 'name': c.name, 'phone': c.phone, 'email': c.email} for c in clients])

    @app.route('/api/clients', methods=['POST'])
    def create_client():
        data = request.json
        client = Client(name=data['name'], phone=data['phone'], email=data.get('email'))
        db.session.add(client)
        db.session.commit()
        return jsonify({'id': client.id}), 201

    @app.route('/api/clients/<int:client_id>', methods=['DELETE'])
    def delete_client(client_id):
        client = Client.query.get_or_404(client_id)
        if client.cars or client.orders:
            return jsonify({'error': 'Нельзя удалить клиента, пока у него есть автомобили или заказы'}), 400
        db.session.delete(client)
        db.session.commit()
        return jsonify({'message': 'Клиент удален'}), 200

    # ---------- Автомобили ----------
    @app.route('/api/cars', methods=['POST'])
    def create_car():
        data = request.json
        if not Client.query.get(data['client_id']):
            return jsonify({'error': 'Клиент не найден'}), 400
        car = Car(license_plate=data['license_plate'], model=data['model'],
                  vin=data.get('vin'), year=data.get('year'), client_id=data['client_id'])
        db.session.add(car)
        db.session.commit()
        return jsonify({'id': car.id}), 201

    @app.route('/api/cars', methods=['GET'])
    def get_cars():
        cars = Car.query.all()
        return jsonify([{
            'id': c.id,
            'license_plate': c.license_plate,
            'model': c.model,
            'vin': c.vin,
            'year': c.year,
            'client_id': c.client_id,
            'client': c.owner.name
        } for c in cars])

    @app.route('/api/cars/<int:car_id>', methods=['DELETE'])
    def delete_car(car_id):
        car = Car.query.get_or_404(car_id)
        if car.orders:
            return jsonify({'error': 'Нельзя удалить автомобиль, пока по нему есть заказы'}), 400
        db.session.delete(car)
        db.session.commit()
        return jsonify({'message': 'Автомобиль удален'}), 200

    # ---------- Работы ----------
    @app.route('/api/works', methods=['GET'])
    def get_works():
        works = WorkItem.query.all()
        return jsonify([{'id': w.id, 'name': w.name, 'hours': w.standard_hours, 'rate': w.hourly_rate} for w in works])

    @app.route('/api/works', methods=['POST'])
    def create_work():
        data = request.json
        work = WorkItem(name=data['name'], standard_hours=data['standard_hours'], hourly_rate=data.get('hourly_rate', 100))
        db.session.add(work)
        db.session.commit()
        return jsonify({'id': work.id}), 201

    @app.route('/api/works/<int:work_id>', methods=['DELETE'])
    def delete_work(work_id):
        work = WorkItem.query.get_or_404(work_id)
        if WorkOrderWork.query.filter_by(work_id=work_id).first():
            return jsonify({'error': 'Нельзя удалить работу, которая уже добавлена в заказ'}), 400
        db.session.delete(work)
        db.session.commit()
        return jsonify({'message': 'Работа удалена'}), 200

    # ---------- Запчасти ----------
    @app.route('/api/parts', methods=['GET'])
    def get_parts():
        parts = SparePart.query.all()
        return jsonify([{'id': p.id, 'name': p.name, 'sku': p.sku, 'price': p.price, 'stock': p.quantity_in_stock} for p in parts])

    @app.route('/api/parts', methods=['POST'])
    def create_part():
        data = request.json
        part = SparePart(name=data['name'], sku=data['sku'], price=data['price'], quantity_in_stock=data.get('quantity_in_stock', 0))
        db.session.add(part)
        db.session.commit()
        return jsonify({'id': part.id}), 201

    @app.route('/api/parts/<int:part_id>', methods=['DELETE'])
    def delete_part(part_id):
        part = SparePart.query.get_or_404(part_id)
        if WorkOrderPart.query.filter_by(part_id=part_id).first():
            return jsonify({'error': 'Нельзя удалить запчасть, которая уже добавлена в заказ'}), 400
        db.session.delete(part)
        db.session.commit()
        return jsonify({'message': 'Запчасть удалена'}), 200

    # ---------- Заказ-наряды ----------
    @app.route('/api/orders', methods=['POST'])
    def create_order():
        data = request.json
        if not Client.query.get(data['client_id']):
            return jsonify({'error': 'Клиент не найден'}), 400
        car = Car.query.get(data['car_id'])
        if not car:
            return jsonify({'error': 'Автомобиль не найден'}), 400
        if car.client_id != data['client_id']:
            return jsonify({'error': 'Автомобиль не принадлежит клиенту'}), 400
        mechanic_id = data.get('mechanic_id')
        if mechanic_id and not Mechanic.query.get(mechanic_id):
            return jsonify({'error': 'Мастер не найден'}), 400
        order = WorkOrder(client_id=data['client_id'], car_id=data['car_id'], mechanic_id=mechanic_id)
        db.session.add(order)
        db.session.commit()
        return jsonify({'id': order.id}), 201

    @app.route('/api/orders', methods=['GET'])
    def get_orders():
        orders = WorkOrder.query.all()
        return jsonify([{
            'id': o.id,
            'client': o.client.name,
            'car': o.car.license_plate,
            'mechanic': o.mechanic.name if o.mechanic else 'не назначен',
            'status': o.status.value,
            'total': o.total_cost,
            'created_at': o.created_at.isoformat()
        } for o in orders])

    @app.route('/api/orders/<int:order_id>', methods=['DELETE'])
    def delete_order(order_id):
        order = WorkOrder.query.get_or_404(order_id)
        db.session.delete(order)
        db.session.commit()
        return jsonify({'message': 'Заказ удален'}), 200

    @app.route('/api/orders/<int:order_id>', methods=['GET'])
    def get_order(order_id):
        order = WorkOrder.query.get_or_404(order_id)
        return jsonify({
            'id': order.id,
            'client': {'id': order.client.id, 'name': order.client.name, 'phone': order.client.phone},
            'car': {
                'id': order.car.id,
                'license_plate': order.car.license_plate,
                'model': order.car.model,
                'vin': order.car.vin,
                'year': order.car.year
            },
            'mechanic': {
                'id': order.mechanic.id,
                'name': order.mechanic.name,
                'specialization': order.mechanic.specialization,
                'phone': order.mechanic.phone
            } if order.mechanic else None,
            'status': order.status.value,
            'total': order.total_cost,
            'created_at': order.created_at.isoformat(),
            'works': [{
                'id': item.id,
                'work_id': item.work_id,
                'name': item.work.name,
                'quantity': item.quantity,
                'standard_hours': item.work.standard_hours,
                'hourly_rate': item.work.hourly_rate
            } for item in order.works],
            'parts': [{
                'id': item.id,
                'part_id': item.part_id,
                'name': item.part.name,
                'sku': item.part.sku,
                'quantity_reserved': item.quantity_reserved,
                'quantity_used': item.quantity_used,
                'price': item.part.price
            } for item in order.parts]
        })

    @app.route('/api/orders/<int:order_id>/insight', methods=['GET'])
    def get_order_insight(order_id):
        try:
            return jsonify(analyze_order_readiness(order_id))
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/<int:order_id>/add_work', methods=['POST'])
    def add_work(order_id):
        data = request.json
        try:
            add_work_to_order(order_id, data['work_id'], data.get('quantity', 1))
            return jsonify({'message': 'Работа добавлена'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/<int:order_id>/works/<int:item_id>', methods=['DELETE'])
    def delete_order_work(order_id, item_id):
        try:
            remove_work_from_order(order_id, item_id)
            return jsonify({'message': 'Работа удалена из заказа'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/<int:order_id>/add_part', methods=['POST'])
    def add_part(order_id):
        data = request.json
        try:
            add_part_to_order(order_id, data['part_id'], data['quantity'])
            return jsonify({'message': 'Запчасть зарезервирована'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/<int:order_id>/parts/<int:item_id>', methods=['DELETE'])
    def delete_order_part(order_id, item_id):
        try:
            remove_part_from_order(order_id, item_id)
            return jsonify({'message': 'Запчасть удалена из заказа'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/<int:order_id>/use_part', methods=['POST'])
    def use_order_part(order_id):
        data = request.json
        try:
            item = use_part(order_id, data['part_id'], data['quantity'])
            return jsonify({
                'message': 'Запчасть списана',
                'quantity_reserved': item.quantity_reserved,
                'quantity_used': item.quantity_used
            }), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/<int:order_id>/status', methods=['PUT'])
    def update_status(order_id):
        data = request.json
        try:
            order = change_order_status(order_id, data['status'])
            return jsonify({'status': order.status.value}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/orders/<int:order_id>/mechanic', methods=['PUT'])
    def update_order_mechanic(order_id):
        data = request.json or {}
        order = WorkOrder.query.get_or_404(order_id)
        mechanic_id = data.get('mechanic_id')
        if mechanic_id in ('', None):
            order.mechanic_id = None
        else:
            mechanic = Mechanic.query.get(mechanic_id)
            if not mechanic:
                return jsonify({'error': 'Мастер не найден'}), 400
            order.mechanic_id = mechanic.id
        db.session.commit()
        return jsonify({'mechanic': order.mechanic.name if order.mechanic else None}), 200

    @app.route('/api/orders/<int:order_id>/document', methods=['GET'])
    def get_document(order_id):
        fmt = request.args.get('format', 'html')
        doc = generate_order_document(order_id, fmt)
        if not doc:
            return 'Order not found', 404
        if fmt == 'html':
            return doc, 200, {'Content-Type': 'text/html; charset=utf-8'}
        elif fmt == 'pdf':
            return send_file(io.BytesIO(doc), mimetype='application/pdf', download_name=f'order_{order_id}.pdf')
        return 'Unsupported format', 400

    return app


def _ensure_schema():
    inspector = db.inspect(db.engine)
    columns = [column['name'] for column in inspector.get_columns('work_orders')]
    if 'mechanic_id' not in columns:
        db.session.execute(db.text('ALTER TABLE work_orders ADD COLUMN mechanic_id INTEGER REFERENCES mechanics(id)'))
        db.session.commit()
