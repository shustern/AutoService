from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ClientCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None

class CarCreate(BaseModel):
    license_plate: str
    model: str
    vin: Optional[str] = None
    year: Optional[int] = None
    client_id: int

class WorkItemCreate(BaseModel):
    name: str
    standard_hours: float
    hourly_rate: float = 100.0

class SparePartCreate(BaseModel):
    name: str
    sku: str
    price: float
    quantity_in_stock: float

class AddWorkToOrder(BaseModel):
    work_id: int
    quantity: int = 1

class AddPartToOrder(BaseModel):
    part_id: int
    quantity: float

class OrderStatusUpdate(BaseModel):
    status: str  # будет проверка в сервисе
