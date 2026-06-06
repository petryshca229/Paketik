import sys, os, json
sys.path.insert(0, r"C:\Users\Вова\Desktop\Python\Paketik 4.7")

from pathlib import Path
from PyQt6.QtGui import QPixmap, QIcon

# --- Test icon loading ---
test_icons = ["green_key.png", "red_key.png", "logo.png"]
for name in test_icons:
    p = Path("res/icons") / name
    pm = QPixmap(str(p))
    ico = QIcon(pm)
    pm2 = ico.pixmap(20)
    print(f"{name}: exists={p.exists()}, isNull={pm.isNull()}, "
          f"pm_size={pm.width()}x{pm.height()}, "
          f"ico_isNull={ico.isNull()}, "
          f"ico_pixmap_isNull={pm2.isNull()}, ico_pixmap_size={pm2.width()}x{pm2.height()}")

# --- Test license ---
lic_file = Path.home() / ".paketik" / "license.json"
print(f"\nlicense.json exists: {lic_file.exists()}")
if lic_file.exists():
    with open(lic_file) as f:
        d = json.load(f)
    for k, v in d.items():
        print(f"  {k}: {v!r}")

# --- Test license_manager ---
os.chdir(r"C:\Users\Вова\Desktop\Python\Paketik 4.7")
from license_mgr import license_manager
info = license_manager.get_summary()
print("\nget_summary():")
for k, v in info.items():
    print(f"  {k}: {v!r}")