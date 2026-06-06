"""Debug script - write output to file"""
import sys, os, json, traceback
sys.path.insert(0, r"C:\Users\Вова\Desktop\Python\Paketik 4.7")
os.chdir(r"C:\Users\Вова\Desktop\Python\Paketik 4.7")

log = []
def log_write(msg):
    log.append(str(msg))

try:
    from pathlib import Path
    from PyQt6.QtGui import QPixmap, QIcon

    for name in ["green_key.png", "red_key.png", "logo.png"]:
        p = Path("res/icons") / name
        pm = QPixmap(str(p))
        ico = QIcon(pm)
        pm2 = ico.pixmap(20)
        log_write(f"{name}: exists={p.exists()}, isNull={pm.isNull()}, w={pm.width()}, h={pm.height()}, ico_isNull={ico.isNull()}, pm2_isNull={pm2.isNull()}, pm2_w={pm2.width()}, pm2_h={pm2.height()}")

    from license_mgr import license_manager
    info = license_manager.get_summary()
    log_write("LICENSE:")
    for k, v in info.items():
        log_write(f"  {k}: {v!r}")
except Exception:
    log_write("ERROR: " + traceback.format_exc())

with open("debug_out.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(log))