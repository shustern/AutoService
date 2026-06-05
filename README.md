# Auto Service

Информационная система для автоматизации автосервиса на Python и Flask.

## Возможности

- учет клиентов;
- учет автомобилей клиентов;
- справочник работ с нормо-часами и ставками;
- склад запчастей;
- создание заказ-нарядов;
- добавление работ и резервирование запчастей в заказ;
- списание фактически использованных запчастей;
- управление статусами заказов;
- печатная форма заказ-наряда в HTML и простой PDF.

## Запуск

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

API будет доступен по адресу `http://localhost:5000`.

## Основные маршруты

- `GET /api/clients` - список клиентов
- `POST /api/clients` - создать клиента
- `GET /api/cars` - список автомобилей
- `POST /api/cars` - создать автомобиль
- `GET /api/works` - список работ
- `POST /api/works` - создать работу
- `GET /api/parts` - список запчастей
- `POST /api/parts` - создать запчасть
- `GET /api/orders` - список заказ-нарядов
- `POST /api/orders` - создать заказ-наряд
- `GET /api/orders/<id>` - детальная карточка заказа
- `POST /api/orders/<id>/add_work` - добавить работу
- `POST /api/orders/<id>/add_part` - зарезервировать запчасть
- `POST /api/orders/<id>/use_part` - списать запчасть
- `PUT /api/orders/<id>/status` - изменить статус
- `GET /api/orders/<id>/document?format=html` - HTML-документ
- `GET /api/orders/<id>/document?format=pdf` - PDF-документ

## Примеры JSON

Создание клиента:

```json
{
  "name": "Иван Петров",
  "phone": "+7 999 111-22-33",
  "email": "ivan@example.com"
}
```

Создание автомобиля:

```json
{
  "license_plate": "A123BC125",
  "model": "Toyota Corolla",
  "vin": "JTDBR32E720000001",
  "year": 2018,
  "client_id": 1
}
```

Изменение статуса:

```json
{
  "status": "в работе"
}
```
