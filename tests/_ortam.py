"""Testleri kullanıcının tercihlerinden yalıt: TERMIK_* ortam değişkenleri silinir, ayar dosyası
olmayan bir yolu gösterir. Her test dosyası termik'ten önce bunu içe aktarır."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _name in [n for n in os.environ if n.startswith("TERMIK_")]:
    del os.environ[_name]
NO_CONFIG = Path(tempfile.gettempdir()) / "termik-test" / "olmayan-ayarlar.toml"
os.environ["TERMIK_CONFIG"] = str(NO_CONFIG)
