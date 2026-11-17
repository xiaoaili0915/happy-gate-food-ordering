"""Load the menu from data/menu_seed.json. Used by seed.py and the admin endpoint."""
import json
from pathlib import Path

from app.models import MenuCategory, MenuItem, ModifierGroup, ModifierOption

SEED_FILE = Path(__file__).resolve().parents[2] / "data" / "menu_seed.json"


def seed_menu(db) -> dict:
    """Replace the whole menu with the contents of the seed file. Orders are untouched."""
    db.query(ModifierOption).delete()
    db.query(ModifierGroup).delete()
    db.query(MenuItem).delete()
    db.query(MenuCategory).delete()
    db.flush()

    data = json.loads(SEED_FILE.read_text())
    counts = {"categories": 0, "items": 0, "options": 0}
    for cat_data in data["categories"]:
        category = MenuCategory(
            name=cat_data["name"],
            name_en=cat_data.get("name_en", ""),
            name_zh=cat_data.get("name_zh", ""),
            sort_order=cat_data["sort_order"],
            image_url=cat_data.get("image_url"),
        )
        db.add(category)
        db.flush()
        counts["categories"] += 1

        for item_data in cat_data["items"]:
            item = MenuItem(
                category_id=category.id,
                name=item_data["name"],
                name_en=item_data.get("name_en", ""),
                name_zh=item_data.get("name_zh", ""),
                description=item_data.get("description", ""),
                description_en=item_data.get("description_en", ""),
                description_zh=item_data.get("description_zh", ""),
                price_cents=item_data["price_cents"],
                sort_order=item_data.get("sort_order", 0),
            )
            db.add(item)
            db.flush()
            counts["items"] += 1

            for group_data in item_data.get("modifier_groups", []):
                group = ModifierGroup(
                    menu_item_id=item.id,
                    name=group_data["name"],
                    name_en=group_data.get("name_en", ""),
                    name_zh=group_data.get("name_zh", ""),
                    required=group_data.get("required", False),
                    min_select=group_data.get("min_select", 0),
                    max_select=group_data.get("max_select", 1),
                )
                db.add(group)
                db.flush()

                for opt_data in group_data.get("options", []):
                    db.add(
                        ModifierOption(
                            group_id=group.id,
                            name=opt_data["name"],
                            name_en=opt_data.get("name_en", ""),
                            name_zh=opt_data.get("name_zh", ""),
                            price_cents=opt_data.get("price_cents", 0),
                        )
                    )
                    counts["options"] += 1

    db.commit()
    return counts
