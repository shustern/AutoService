from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from app.config import Config
from app.models import db, Client, Car, WorkItem, SparePart, WorkOrder, OrderStatusEnum
from app.services import add_work_to_order, add_part_to_order, change_order_status, use_part
from app.reports import generate_order_document
import io

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)
    db.init_app(app)

    with app.app_context():
        db.create_all()

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
        order = WorkOrder(client_id=data['client_id'], car_id=data['car_id'])
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
            'status': o.status.value,
            'total': o.total_cost,
            'created_at': o.created_at.isoformat()
        } for o in orders])

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

    @app.route('/api/orders/<int:order_id>/add_work', methods=['POST'])
    def add_work(order_id):
        data = request.json
        try:
            add_work_to_order(order_id, data['work_id'], data.get('quantity', 1))
            return jsonify({'message': 'Работа добавлена'}), 200
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
