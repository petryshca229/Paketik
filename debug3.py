import sys, os
sys.path.insert(0, r"C:\Users\Вова\Desktop\Python\Paketik 4.7")

# Test all icon loading paths
from pathlib import Path
from PyQt6.QtGui import QPixmap, QIcon

rel = Path(r"res/icons/green_key.png")
abs_path = str(rel.resolve())
print("REL exists:", rel.exists())
print("ABS path:", abs_path)
print("ABS exists:", os.path.exists(abs_path))

# Try rel path
pm1 = QPixmap(str(rel))
print("PM1 rel isNull:", pm1.isNull(), "w:", pm1.width(), "h:", pm1.height())

# Try abs path
pm2 = QPixmap(abs_path)
print("PM2 abs isNull:", pm2.isNull(), "w:", pm2.width(), "h:", pm2.height())

# Try icon -> pixmap
ico = QIcon(pm1)
print("ICO isNull:", ico.isNull())
pm3 = ico.pixmap(20)
print("PM3 from ico isNull:", pm3.isNull(), "w:", pm3.width(), "h:", pm3.height())

# QIcon from abs
ico2 = QIcon(abs_path)
print("ICO2 isNull:", ico2.isNull())
pm4 = ico2.pixmap(20)
print("PM4 from ico2 isNull:", pm4.isNull(), "w:", pm4.width(), "h:", pm4.height())

# license_manager summary
from license_mgr import license_manager
info = license_manager.get_summary()
print("\nLICENSE SUMMARY:")
for k,v in info.items():
    print(f"  {k}: {v!r}")
