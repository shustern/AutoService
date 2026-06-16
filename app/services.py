from app.models import db, OperationalTask, WorkOrder, WorkOrderWork, WorkOrderPart, SparePart, WorkItem, OrderStatusEnum
from datetime import datetime


def _hidden_operational_task_keys():
    now = datetime.utcnow()
    hidden = set()
    for task in OperationalTask.query.filter(OperationalTask.status.in_(('done', 'snoozed'))).all():
        if task.status == 'done':
            hidden.add(task.task_key)
        elif task.snoozed_until and task.snoozed_until > now:
            hidden.add(task.task_key)
    return hidden


def analyze_order_readiness(order_id: int):
    """Подсказать оператору следующее действие по заказу."""
    order = WorkOrder.query.get(order_id)
    if not order:
        raise ValueError("Заказ не найден")

    checklist = []
    score_by_status = {
        OrderStatusEnum.OPEN: 15,
        OrderStatusEnum.WAITING_PARTS: 40,
        OrderStatusEnum.IN_WORK: 65,
        OrderStatusEnum.COMPLETED: 90,
        OrderStatusEnum.CLOSED: 100,
        OrderStatusEnum.CANCELLED: 0,
    }
    score = score_by_status[order.status]
    risk_level = "средний"
    next_action = "Проверьте состав заказа"

    if order.works:
        score += 10 if order.status in (OrderStatusEnum.OPEN, OrderStatusEnum.WAITING_PARTS) else 0
        checklist.append({"label": "Работы добавлены", "ok": True})
    else:
        checklist.append({"label": "Добавьте хотя бы одну работу", "ok": False})
        next_action = "Добавить работу в заказ"

    parts_ready = True
    parts_reserved = False
    for item in order.parts:
        parts_reserved = parts_reserved or item.quantity_reserved > 0 or item.quantity_used > 0
        if item.quantity_reserved > item.part.quantity_in_stock:
            parts_ready = False

    if not order.parts:
        checklist.append({"label": "Заказ можно выполнить без запчастей", "ok": True})
    elif parts_ready:
        score += 5 if order.status == OrderStatusEnum.WAITING_PARTS else 0
        checklist.append({"label": "Запчасти зарезервированы без дефицита", "ok": True})
    else:
        score -= 15
        checklist.append({"label": "Есть риск дефицита запчастей", "ok": False})
        next_action = "Проверить склад и поставщика"

    if order.status == OrderStatusEnum.OPEN and order.works:
        next_action = "Перевести заказ в работу"
    elif order.status == OrderStatusEnum.WAITING_PARTS and parts_ready:
        next_action = "Передать заказ мастеру"
    elif order.status == OrderStatusEnum.IN_WORK:
        next_action = "Завершить заказ после выполнения работ"
    elif order.status == OrderStatusEnum.COMPLETED:
        next_action = "Закрыть заказ и выдать документ клиенту"
    elif order.status == OrderStatusEnum.CLOSED:
        next_action = "Заказ закрыт"
    elif order.status == OrderStatusEnum.CANCELLED:
        next_action = "Заказ отменен"

    if order.total_cost > 0:
        checklist.append({"label": "Стоимость рассчитана", "ok": True})
    else:
        checklist.append({"label": "Стоимость появится после работ/списания деталей", "ok": False})

    if order.status in (OrderStatusEnum.COMPLETED, OrderStatusEnum.CLOSED):
        risk_level = "низкий"
    elif order.status == OrderStatusEnum.CANCELLED:
        risk_level = "не актуален"
        score = 0
    elif not order.works or not parts_ready:
        score = min(score, 45)
        risk_level = "высокий"
    elif parts_reserved or order.status == OrderStatusEnum.IN_WORK:
        risk_level = "низкий"

    score = max(0, min(score, 100))
    score_explanation = {
        OrderStatusEnum.OPEN: "Заказ создан, но работы еще не начаты.",
        OrderStatusEnum.WAITING_PARTS: "Заказ ожидает запчасти или передачу мастеру.",
        OrderStatusEnum.IN_WORK: "Работы выполняются, заказ еще не завершен.",
        OrderStatusEnum.COMPLETED: "Работы выполнены, заказ осталось закрыть.",
        OrderStatusEnum.CLOSED: "Заказ полностью закрыт.",
        OrderStatusEnum.CANCELLED: "Заказ отменен и не считается выполненным.",
    }[order.status]

    return {
        "order_id": order.id,
        "readiness_score": score,
        "score_explanation": score_explanation,
        "risk_level": risk_level,
        "next_action": next_action,
        "checklist": checklist,
        "killer_feature": "Умный мастер-план заказа",
        "business_effect": "Оператор сразу видит готовность заказа, риск по складу и следующий шаг."
    }


def build_service_radar(limit: int = 6):
    """Найти клиентов и автомобили, по которым стоит сделать следующий контакт."""
    from app.models import Car

    current_year = datetime.utcnow().year
    hidden_keys = _hidden_operational_task_keys()
    radar = []

    for car in Car.query.all():
        task_key = f"contact:car:{car.id}"
        if task_key in hidden_keys:
            continue
        orders = sorted(car.orders, key=lambda order: order.created_at, reverse=True)
        last_order = orders[0] if orders else None
        car_age = current_year - car.year if car.year else 0
        priority = 35
        reason = "Нет истории визитов"
        action = "Позвонить клиенту и предложить первичную диагностику"

        if last_order:
            days_since = (datetime.utcnow() - last_order.created_at).days
            priority = min(95, 40 + days_since)
            reason = f"Последний заказ: {last_order.status.value}, {days_since} дн. назад"
            action = "Проверить удовлетворенность и предложить следующий визит"
            if last_order.status == OrderStatusEnum.WAITING_PARTS:
                priority = 90
                action = "Уточнить поставку запчастей и предупредить клиента"
            elif last_order.status == OrderStatusEnum.IN_WORK:
                priority = 82
                action = "Проконтролировать срок завершения работ"
            elif last_order.status in (OrderStatusEnum.COMPLETED, OrderStatusEnum.CLOSED) and days_since >= 90:
                priority = 88
                action = "Пригласить на повторную диагностику после выполненного заказа"

        if car_age >= 10:
            priority = min(100, priority + 12)
            reason += f"; возраст авто {car_age} лет"
        elif car_age >= 6:
            priority = min(100, priority + 6)
            reason += f"; возраст авто {car_age} лет"

        radar.append({
            "task_key": task_key,
            "client": car.owner.name,
            "phone": car.owner.phone,
            "car": f"{car.license_plate} {car.model}",
            "priority": priority,
            "reason": reason,
            "action": action,
        })

    return sorted(radar, key=lambda item: item["priority"], reverse=True)[:limit]


def forecast_spare_parts(limit: int = 8):
    """Прогнозировать риск дефицита запчастей по текущему спросу в заказах."""
    parts = []
    for part in SparePart.query.all():
        reserved = db.session.query(db.func.sum(WorkOrderPart.quantity_reserved)).filter_by(part_id=part.id).scalar() or 0
        used = db.session.query(db.func.sum(WorkOrderPart.quantity_used)).filter_by(part_id=part.id).scalar() or 0
        demand = reserved + used
        typical_need = max(1, round(demand / 2, 1)) if demand else 1
        orders_left = int(part.quantity_in_stock // typical_need) if typical_need else 0
        if part.quantity_in_stock <= 0:
            risk = "критический"
            action = "Срочно заказать у поставщика"
        elif orders_left <= 2:
            risk = "высокий"
            action = "Пополнить запас в ближайшую закупку"
        elif orders_left <= 5:
            risk = "средний"
            action = "Поставить на контроль закупки"
        else:
            risk = "низкий"
            action = "Запас достаточный"
        parts.append({
            "id": part.id,
            "name": part.name,
            "sku": part.sku,
            "stock": part.quantity_in_stock,
            "reserved": reserved,
            "used": used,
            "orders_left": orders_left,
            "risk": risk,
            "action": action,
        })
    risk_rank = {"критический": 0, "высокий": 1, "средний": 2, "низкий": 3}
    return sorted(parts, key=lambda item: (risk_rank[item["risk"]], item["orders_left"]))[:limit]


def suggest_works_by_complaint(text: str):
    """Подобрать работы по жалобе клиента простыми экспертными правилами."""
    source = (text or "").lower()
    rules = [
        (("стук", "подвес", "шум", "скрип"), ["Компьютерная диагностика", "Ремонт подвески", "Развал-схождение"]),
        (("масло", "течь", "двигател"), ["Компьютерная диагностика", "Замена масла двигателя"]),
        (("тормоз", "колод", "скрежет"), ["Компьютерная диагностика", "Замена тормозных колодок"]),
        (("фильтр", "запах", "воздух"), ["Замена воздушного фильтра", "Компьютерная диагностика"]),
        (("увод", "руль", "резин", "колес"), ["Развал-схождение", "Компьютерная диагностика"]),
        (("не завод", "свеч", "зажиган"), ["Компьютерная диагностика"]),
    ]
    matched_names = []
    reasons = []
    for keywords, names in rules:
        if any(keyword in source for keyword in keywords):
            matched_names.extend(names)
            reasons.append("найдены признаки: " + ", ".join(keywords[:3]))

    if not matched_names:
        matched_names = ["Компьютерная диагностика"]
        reasons.append("универсальная стартовая проверка")

    result = []
    seen = set()
    for name in matched_names:
        if name in seen:
            continue
        seen.add(name)
        work = WorkItem.query.filter_by(name=name).first()
        result.append({
            "work_id": work.id if work else None,
            "name": name,
            "hours": work.standard_hours if work else None,
            "rate": work.hourly_rate if work else None,
        })
    return {"complaint": text, "reason": "; ".join(reasons), "suggestions": result}


def get_car_health_card(car_id: int):
    """Сформировать историю автомобиля и рекомендацию следующего ТО."""
    from app.models import Car

    car = Car.query.get(car_id)
    if not car:
        raise ValueError("Автомобиль не найден")
    orders = sorted(car.orders, key=lambda order: order.created_at, reverse=True)
    timeline = []
    for order in orders:
        timeline.append({
            "order_id": order.id,
            "date": order.created_at.isoformat(),
            "status": order.status.value,
            "total": order.total_cost,
            "works": [item.work.name for item in order.works],
            "parts": [item.part.name for item in order.parts],
        })

    current_year = datetime.utcnow().year
    age = current_year - car.year if car.year else None
    if not orders:
        recommendation = "Создать первичный заказ и провести базовую диагностику"
    elif orders[0].status in (OrderStatusEnum.COMPLETED, OrderStatusEnum.CLOSED):
        recommendation = "Запланировать контрольный звонок и следующее ТО через 90 дней"
    elif orders[0].status == OrderStatusEnum.WAITING_PARTS:
        recommendation = "Проверить срок поставки запчастей"
    else:
        recommendation = "Проконтролировать текущий открытый заказ"
    if age and age >= 8:
        recommendation += "; добавить расширенную диагностику возрастного автомобиля"

    return {
        "car_id": car.id,
        "car": f"{car.license_plate} {car.model}",
        "client": car.owner.name,
        "phone": car.owner.phone,
        "age": age,
        "recommendation": recommendation,
        "timeline": timeline,
    }


def get_stuck_orders(limit: int = 8):
    """Найти заказы, которые зависли в активном статусе."""
    hidden_keys = _hidden_operational_task_keys()
    result = []
    for order in WorkOrder.query.all():
        task_key = f"order-followup:{order.id}"
        if task_key in hidden_keys:
            continue
        if order.status not in (OrderStatusEnum.OPEN, OrderStatusEnum.WAITING_PARTS, OrderStatusEnum.IN_WORK):
            continue
        age_days = (datetime.utcnow() - order.created_at).days
        if age_days < 1 and order.status != OrderStatusEnum.WAITING_PARTS:
            continue
        priority = age_days * 10
        if order.status == OrderStatusEnum.WAITING_PARTS:
            priority += 45
            action = "Проверить поставку запчастей"
        elif order.status == OrderStatusEnum.IN_WORK:
            priority += 30
            action = "Уточнить срок завершения у мастера"
        else:
            action = "Назначить работы или передать мастеру"
        result.append({
            "task_key": task_key,
            "order_id": order.id,
            "client": order.client.name,
            "car": order.car.license_plate,
            "status": order.status.value,
            "age_days": age_days,
            "priority": min(priority, 100),
            "action": action,
        })
    return sorted(result, key=lambda item: item["priority"], reverse=True)[:limit]


def get_master_priority(limit: int = 8):
    """Сформировать очередь работ мастера на день."""
    hidden_keys = _hidden_operational_task_keys()
    items = []
    for order in WorkOrder.query.all():
        task_key = f"order-followup:{order.id}"
        if task_key in hidden_keys:
            continue
        if order.status in (OrderStatusEnum.COMPLETED, OrderStatusEnum.CLOSED, OrderStatusEnum.CANCELLED):
            continue
        insight = analyze_order_readiness(order.id)
        priority = insight["readiness_score"]
        if order.status == OrderStatusEnum.IN_WORK:
            priority += 15
        if order.status == OrderStatusEnum.WAITING_PARTS:
            priority -= 10
        items.append({
            "task_key": task_key,
            "order_id": order.id,
            "client": order.client.name,
            "car": f"{order.car.license_plate} {order.car.model}",
            "mechanic": order.mechanic.name if order.mechanic else "не назначен",
            "status": order.status.value,
            "priority": max(0, min(priority, 100)),
            "next_action": insight["next_action"],
        })
    return sorted(items, key=lambda item: item["priority"], reverse=True)[:limit]


def get_maintenance_recommendations(limit: int = 8):
    """Рекомендации по следующему ТО для клиентской базы."""
    recommendations = []
    for item in build_service_radar(limit=100):
        if item["priority"] < 50:
            continue
        recommendations.append({
            "task_key": item["task_key"],
            "client": item["client"],
            "phone": item["phone"],
            "car": item["car"],
            "reason": item["reason"],
            "recommendation": item["action"],
        })
    return recommendations[:limit]

def recalc_order_total(order_id: int):
    """Пересчитать стоимость заказа: работы + использованные запчасти"""
    order = WorkOrder.query.get(order_id)
    if not order:
        return

    total = 0.0
    # работы
    for wow in order.works:
        work = wow.work
        total += work.standard_hours * work.hourly_rate * wow.quantity
    # запчасти (только использованные)
    for wop in order.parts:
        if wop.quantity_used > 0:
            total += wop.part.price * wop.quantity_used
    order.total_cost = total
    db.session.commit()

def add_work_to_order(order_id: int, work_id: int, quantity: int = 1):
    """Добавить работу в заказ-наряд"""
    if quantity <= 0:
        raise ValueError("Количество должно быть больше нуля")
    order = WorkOrder.query.get(order_id)
    work = WorkItem.query.get(work_id)
    if not order or not work:
        raise ValueError("Заказ или работа не найдены")
    # проверим, нет ли уже такой работы (опционально)
    existing = WorkOrderWork.query.filter_by(order_id=order_id, work_id=work_id).first()
    if existing:
        existing.quantity += quantity
    else:
        wow = WorkOrderWork(order_id=order_id, work_id=work_id, quantity=quantity)
        db.session.add(wow)
    db.session.commit()
    recalc_order_total(order_id)


def remove_work_from_order(order_id: int, item_id: int):
    """Удалить работу из конкретного заказ-наряда."""
    item = WorkOrderWork.query.filter_by(order_id=order_id, id=item_id).first()
    if not item:
        raise ValueError("Работа в заказе не найдена")
    db.session.delete(item)
    db.session.commit()
    recalc_order_total(order_id)

def add_part_to_order(order_id: int, part_id: int, quantity: float):
    """Резервирование запчасти. Проверяем остаток на складе."""
    if quantity <= 0:
        raise ValueError("Количество должно быть больше нуля")
    order = WorkOrder.query.get(order_id)
    part = SparePart.query.get(part_id)
    if not order or not part:
        raise ValueError("Заказ или запчасть не найдены")
    # свободный остаток с учётом уже зарезервированного
    reserved_total = db.session.query(db.func.sum(WorkOrderPart.quantity_reserved)).filter(
        WorkOrderPart.part_id == part_id,
        WorkOrderPart.order_id != order_id
    ).scalar() or 0
    available = part.quantity_in_stock - reserved_total
    wop = WorkOrderPart.query.filter_by(order_id=order_id, part_id=part_id).first()
    current_reserved = wop.quantity_reserved if wop else 0
    if available < current_reserved + quantity:
        raise ValueError(f"Недостаточно запчастей {part.name}. Доступно: {available}")
    # добавить или обновить резерв
    if wop:
        wop.quantity_reserved += quantity
    else:
        wop = WorkOrderPart(order_id=order_id, part_id=part_id, quantity_reserved=quantity)
        db.session.add(wop)
    db.session.commit()
    # если резерв появился, перевести заказ в статус ожидания (если он открыт)
    if order.status == OrderStatusEnum.OPEN:
        order.status = OrderStatusEnum.WAITING_PARTS
        db.session.commit()


def remove_part_from_order(order_id: int, item_id: int):
    """Удалить запчасть из заказа и вернуть списанное количество на склад."""
    item = WorkOrderPart.query.filter_by(order_id=order_id, id=item_id).first()
    if not item:
        raise ValueError("Запчасть в заказе не найдена")
    if item.quantity_used > 0:
        item.part.quantity_in_stock += item.quantity_used
    db.session.delete(item)
    db.session.commit()
    recalc_order_total(order_id)

def use_part(order_id: int, part_id: int, quantity: float):
    """Списать запчасть (фактическое использование) - обычно при завершении работ"""
    if quantity <= 0:
        raise ValueError("Количество должно быть больше нуля")
    wop = WorkOrderPart.query.filter_by(order_id=order_id, part_id=part_id).first()
    if not wop:
        raise ValueError("Запчасть не была зарезервирована")
    if wop.quantity_reserved < quantity:
        raise ValueError("Нельзя использовать больше, чем зарезервировано")
    wop.quantity_used += quantity
    wop.quantity_reserved -= quantity
    # реально списываем со склада
    part = SparePart.query.get(part_id)
    part.quantity_in_stock -= quantity
    db.session.commit()
    recalc_order_total(order_id)
    return wop

def change_order_status(order_id: int, new_status_str: str):
    """Изменить статус с проверками допустимости переходов"""
    order = WorkOrder.query.get(order_id)
    if not order:
        raise ValueError("Заказ не найден")
    try:
        new_status = OrderStatusEnum(new_status_str)
    except ValueError:
        raise ValueError("Некорректный статус")

    # Правила переходов (упрощённо, но достаточно)
    if new_status == OrderStatusEnum.IN_WORK:
        if order.status not in (OrderStatusEnum.OPEN, OrderStatusEnum.WAITING_PARTS):
            raise ValueError("Переход в работу возможен только из 'открыт' или 'ожидание запчастей'")
        # также можно проверить, что есть хотя бы одна работа
        if not order.works:
            raise ValueError("Невозможно начать работу без добавленных работ")
    elif new_status == OrderStatusEnum.COMPLETED:
        if order.status != OrderStatusEnum.IN_WORK:
            raise ValueError("Завершить можно только заказ в работе")
        # автоматически списать все зарезервированные запчасти (можно спросить, но сделаем автоматически)
        for wop in order.parts:
            if wop.quantity_reserved > 0:
                use_part(order_id, wop.part_id, wop.quantity_reserved)
    elif new_status == OrderStatusEnum.CLOSED:
        if order.status != OrderStatusEnum.COMPLETED:
            raise ValueError("Закрыть можно только выполненный заказ")
    elif new_status == OrderStatusEnum.CANCELLED:
        # отмена снимает резерв; склад не увеличиваем, потому что резервирование
        # не уменьшает quantity_in_stock
        for wop in order.parts:
            if wop.quantity_reserved > 0:
                wop.quantity_reserved = 0
        db.session.commit()
    order.status = new_status
    db.session.commit()
    return order
