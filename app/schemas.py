from pydantic import BaseModel, EmailStr


class ModifierOptionOut(BaseModel):
    id: int
    name: str
    price_cents: int


class ModifierGroupOut(BaseModel):
    id: int
    name: str
    required: bool
    min_select: int
    max_select: int
    options: list[ModifierOptionOut]


class MenuItemOut(BaseModel):
    id: int
    name: str
    description: str
    price_cents: int
    image_url: str | None
    available: bool
    modifier_groups: list[ModifierGroupOut]


class MenuCategoryOut(BaseModel):
    id: int
    name: str
    items: list[MenuItemOut]


class OrderItemModifierIn(BaseModel):
    modifier_name: str
    price_cents: int


class OrderItemIn(BaseModel):
    menu_item_id: int
    item_name: str
    quantity: int
    unit_price_cents: int
    special_notes: str = ""
    modifiers: list[OrderItemModifierIn] = []


class OrderCreateIn(BaseModel):
    customer_name: str
    customer_email: EmailStr
    customer_phone: str
    pickup_notes: str = ""
    items: list[OrderItemIn]


class OrderApproveIn(BaseModel):
    expected_pickup_time: str


class OrderOut(BaseModel):
    id: int
    status: str
    customer_name: str
    customer_email: str
    customer_phone: str
    pickup_notes: str
    subtotal_cents: int
    created_at: str
    expires_at: str
    expected_pickup_time: str | None

    class Config:
        from_attributes = True


# --- Restaurant app (Android) ---


class AcceptIn(BaseModel):
    preparation_minutes: int


class RejectIn(BaseModel):
    reason: str = ""


class PrintEventIn(BaseModel):
    status: str  # queued | sending | printed | failed | uncertain
    message: str = ""
    device: str = ""


class DeviceRegisterIn(BaseModel):
    token: str
    platform: str = "android"
