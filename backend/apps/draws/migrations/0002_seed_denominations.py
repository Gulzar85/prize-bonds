from django.db import migrations

BASE = "https://savings.gov.pk/"
DENOMINATIONS = [
    # slug, value, kind, name_en, name_ur, page path, sort
    ("rs-100", 100, "REGULAR", "Rs 100 Student Welfare Prize Bond", "100 روپے اسٹوڈنٹ ویلفیئر پرائز بانڈ", "rs-100-prize-bond-draw/", 10),
    ("rs-200", 200, "REGULAR", "Rs 200 Prize Bond", "200 روپے پرائز بانڈ", "rs-200-prize-bond-draw/", 20),
    ("rs-750", 750, "REGULAR", "Rs 750 Prize Bond", "750 روپے پرائز بانڈ", "rs-750-prize-bond-draw/", 30),
    ("rs-1500", 1500, "REGULAR", "Rs 1,500 Prize Bond", "1,500 روپے پرائز بانڈ", "rs-1500-prize-bond-draw/", 40),
    ("premium-25000", 25000, "PREMIUM", "Premium Prize Bond Rs 25,000", "25,000 روپے پریمیم پرائز بانڈ", "premium-prize-bond-rs-25000/", 50),
    ("premium-40000", 40000, "PREMIUM", "Premium Prize Bond Rs 40,000", "40,000 روپے پریمیم پرائز بانڈ", "premium-prize-bond-rs-40000/", 60),
]


def seed(apps, schema_editor):
    Denomination = apps.get_model("draws", "Denomination")
    for slug, value, kind, name_en, name_ur, path, sort in DENOMINATIONS:
        Denomination.objects.update_or_create(
            slug=slug,
            defaults={
                "value_pkr": value,
                "kind": kind,
                "name_en": name_en,
                "name_ur": name_ur,
                "source_page_url": BASE + path,
                "number_length": 6,
                "is_active": True,
                "sort_order": sort,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("draws", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
