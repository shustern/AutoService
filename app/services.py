from app.models import db, WorkOrder, WorkOrderWork, WorkOrderPart, SparePart, WorkItem, OrderStatusEnum

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
