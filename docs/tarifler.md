# Tarifler

Sık yapılan işler için kısa, çalışan örnekler. Her biri `termik çalıştır dosya.py --izle` ile denenebilir.

- [Ayarları hatırlayan form](#form)
- [Canlı grafik](#grafik)
- [Uzun iş, pencere donmadan](#uzun-is)
- [Dosya seçme ve bırakma](#dosya)
- [İkinci pencere](#pencere)
- [Sınıf yazmadan küçük araç](#sinifsiz)
- [Script'ten tablo, grafik ve form](#akis)
- [Test yazmak](#test)

<a id="form"></a>

## Ayarları hatırlayan form

`bind=` alanı uygulamanın özniteliğine bağlar; `SAVE_STATE = True` bağlı değerleri, pencerenin yerini
ve boyutunu kapanırken saklar, açılınca geri getirir. Parola alanları saklanmaz.

```python
import termik as ui

class Ayarlar(ui.App):
    TITLE = "Yedek ayarları"
    SIZE = (640, 360)
    SAVE_STATE = True

    kaynak = ui.reactive("C:/Projeler")
    duzey = ui.reactive(6)
    sakla = ui.reactive(5)

    def compose(self):
        with ui.Panel(title="Yedekleme"):
            with ui.Form():
                yield ui.Input(label="Kaynak", bind="kaynak")
                yield ui.Slider(max=9, label="Sıkıştırma", bind="duzey")
                yield ui.Spinbox(min=1, max=50, label="Sakla", bind="sakla")
                yield ui.Input(label="Parola", password=True, bind="parola")
        yield ui.Button("Özet", self.ozet, key="f5", variant="primary")
        yield ui.KeyBar()

    def ozet(self):
        self.notify(f"{self.kaynak} · düzey {self.duzey} · son {self.sakla} yedek", "ok")

if __name__ == "__main__":
    Ayarlar().run()
```

<a id="grafik"></a>

## Canlı grafik

`max_points` en son değerleri tutar; `append` grafiği kendiliğinden yeniden çizer.

```python
import random
import termik as ui

class Izleme(ui.App):
    TITLE = "İzleme"
    SIZE = (900, 500)

    def compose(self):
        yield ui.Chart({"cpu": [], "bellek": []}, title="Kullanım %", y_min=0, y_max=100,
                       max_points=60, id="grafik", height="1fr")
        yield ui.KeyBar()

    def on_mount(self):
        self.set_interval(0.5, self.olc)

    def olc(self):
        grafik = self.query_one("#grafik", ui.Chart)
        grafik.append("cpu", random.uniform(10, 90))
        grafik.append("bellek", random.uniform(40, 60))

if __name__ == "__main__":
    Izleme().run()
```

<a id="uzun-is"></a>

## Uzun iş, pencere donmadan

Bloklayan iş `run_worker` ile ayrı thread'de koşar; arayüzü güncellemek için `call_from_thread`.

```python
import time
import termik as ui

class Is(ui.App):
    TITLE = "Uzun iş"
    SIZE = (640, 240)

    def compose(self):
        yield ui.ProgressBar(id="cubuk")
        yield ui.Button("Başlat", self.baslat, key="f5", variant="primary")
        yield ui.KeyBar()

    async def baslat(self):
        sonuc = await self.run_worker(self.hesapla)
        self.notify(f"bitti: {sonuc}", "ok")

    def hesapla(self):  # ayrı thread'de
        cubuk = self.query_one("#cubuk", ui.ProgressBar)
        for i in range(1, 51):
            time.sleep(0.05)
            self.call_from_thread(setattr, cubuk, "progress", i / 50)
        return 42

if __name__ == "__main__":
    Is().run()
```

<a id="dosya"></a>

## Dosya seçme ve bırakma

`ask_open` işletim sisteminin diyaloğunu açar (`dialogs = "builtin"` ayarıyla termik'in gezgini).
Dosya yöneticisinden bırakılanlar `on_drop`'a gelir; yol alanına bırakılan yol oraya yazılır.

```python
import termik as ui

class Goruntule(ui.App):
    TITLE = "Resim"
    SIZE = (720, 520)

    def compose(self):
        yield ui.Image(placeholder="resim bırak ya da ctrl+o", id="resim", height="1fr", width="1fr")
        yield ui.KeyBar()

    @ui.action("Aç", key="ctrl+o")
    async def ac(self):
        yol = await self.ask_open("Resim seç", filetypes=[("Resimler", "*.png *.jpg *.gif")])
        if yol:
            self.query_one("#resim", ui.Image).source = yol

    def on_drop(self, event):
        if event.paths:
            self.query_one("#resim", ui.Image).source = event.paths[0]

if __name__ == "__main__":
    Goruntule().run()
```

<a id="pencere"></a>

## İkinci pencere

Ek pencere `Window`'dan türer; `open_window_wait` kapanınca `close(sonuç)`'a verileni döndürür.
`modal=True` o kapanana kadar ana pencereyi kilitler.

```python
import termik as ui

class Sor(ui.Window):
    TITLE = "Ad"
    SIZE = (420, 200)

    def compose(self):
        yield ui.Input(label="Adın", id="ad")
        yield ui.Button("Tamam", self.tamam, variant="primary")

    def tamam(self):
        self.close(self.query_one("#ad", ui.Input).value)

class Ana(ui.App):
    TITLE = "Ana"
    SIZE = (640, 360)

    def compose(self):
        yield ui.Button("Adını sor", self.sor, key="f5")
        yield ui.KeyBar()

    async def sor(self):
        ad = await self.open_window_wait(Sor(), modal=True)
        if ad:
            self.notify(f"Merhaba {ui.escape(ad)}!", "ok")

if __name__ == "__main__":
    Ana().run()
```

<a id="sinifsiz"></a>

## Sınıf yazmadan küçük araç

```python
import termik as ui

app = ui.App(title="Sayaç")
app.metin = ""

@app.compose
def arayuz():
    yield ui.TextArea(bind="metin", rows=6, placeholder="yaz…")
    yield ui.Button("Say", say, key="f5", variant="primary")
    yield ui.KeyBar()

def say():
    app.notify(f"{len(app.metin.split())} kelime, {len(app.metin)} karakter")

if __name__ == "__main__":
    app.run()
```

<a id="akis"></a>

## Script'ten tablo, grafik ve form

Akış API'si bileşen katmanının bileşenlerini de gösterebilir; tutamaklar script thread'inden güvenle
güncellenir. Terminal kipinde o anki hali yazıya dökülür.

```python
import time
import termik
import termik as ui

ayar = termik.form("Tarama", klasör="C:/Projeler", derinlik=ui.Slider(3, min=1, max=9))
tablo = termik.show(ui.Table("Dosya", ("Boyut", 10, "right"), height=8))
hiz = termik.chart({"hız": []}, title="MB/sn", max_points=40, height=8)
for i in range(40):
    tablo.add_row(f"dosya{i}.dat", f"{i * 3} KB")
    hiz.append("hız", 20 + i % 7)
    time.sleep(0.05)
termik.ok("bitti")
```

<a id="test"></a>

## Test yazmak

`run_test()` pencere açmadan (SDL'in sahte sürücüsüyle) başlatır; `Pilot` tuşlara basar, tıklar,
bırakır, ekran görüntüsü alır.

```python
import asyncio
import termik as ui
from ayarlar import Ayarlar

async def main():
    app = Ayarlar(save_state=False)
    async with app.run_test() as pilot:
        app.query_one(ui.Input).focus()
        await pilot.type("/yedek")
        await pilot.press("tab", "right", "f5")
        assert app.kaynak.endswith("/yedek") and app.duzey == 7
        pilot.snapshot("ayarlar.png")

asyncio.run(main())
```
