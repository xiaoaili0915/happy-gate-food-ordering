from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MenuCategory, MenuItem, ModifierGroup, ModifierOption

router = APIRouter()


def _build_menu(db: Session):
    categories = (
        db.query(MenuCategory).order_by(MenuCategory.sort_order).all()
    )
    result = []
    for cat in categories:
        items = (
            db.query(MenuItem)
            .filter(MenuItem.category_id == cat.id, MenuItem.available == True)
            .order_by(MenuItem.sort_order)
            .all()
        )
        items_out = []
        for item in items:
            groups = db.query(ModifierGroup).filter(ModifierGroup.menu_item_id == item.id).all()
            groups_out = []
            for g in groups:
                options = db.query(ModifierOption).filter(ModifierOption.group_id == g.id).all()
                groups_out.append({
                    "id": g.id,
                    "name": g.name,
                    "name_en": g.name_en,
                    "name_zh": g.name_zh,
                    "required": g.required,
                    "min_select": g.min_select,
                    "max_select": g.max_select,
                    "options": [{"id": o.id, "name": o.name, "name_en": o.name_en, "name_zh": o.name_zh, "price_cents": o.price_cents} for o in options],
                })
            items_out.append({
                "id": item.id,
                "name": item.name,
                "name_en": item.name_en,
                "name_zh": item.name_zh,
                "description": item.description,
                "description_en": item.description_en,
                "description_zh": item.description_zh,
                "price_cents": item.price_cents,
                "image_url": item.image_url,
                "modifier_groups": groups_out,
            })
        if items_out:
            result.append({
                "id": cat.id,
                "name": cat.name,
                "name_en": cat.name_en,
                "name_zh": cat.name_zh,
                "image_url": cat.image_url,
                "menu_items": items_out,
            })
    return result


@router.get("/")
def menu_page(request: Request, db: Session = Depends(get_db)):
    from app.main import templates

    categories = _build_menu(db)
    return templates.TemplateResponse("menu.html", {"request": request, "categories": categories})


@router.get("/cart")
def cart_page(request: Request):
    from app.main import templates

    return templates.TemplateResponse("cart.html", {"request": request})


@router.get("/checkout")
def checkout_page(request: Request):
    from app.main import templates

    return templates.TemplateResponse("checkout.html", {"request": request})


@router.get("/api/menu")
def get_menu(db: Session = Depends(get_db)):
    return _build_menu(db)
