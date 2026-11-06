# termik rehberi

Bu belge termik'i **öğretmek** için yazıldı: hiç bilmeyen bir insanın ya da kod üreten bir dil
modelinin (LLM) baştan sona okuyup doğru, deyimsel termik kodu yazabilmesi için. README bir başvuru
özetidir, [tarifler](tarifler.md) hazır örneklerdir, [galeri](bilesenler.md) her bileşenin görüntüsüdür;
bu belge ise *neden böyle* ve *nasıl düşünülür* sorularını cevaplar.

Sürüm: 0.10 ve sonrası. Kod örneklerinin hepsi kopyalanıp çalıştırılabilir.

---

## İçindekiler

1. [termik nedir, ne değildir](#1)
2. [Kurulum ve ilk çalıştırma](#2)
3. [İki katman: hangisini seçmeli](#3)
4. [Akış API'si: adım adım](#4)
5. [Bileşen katmanının zihinsel modeli](#5)
6. [Ders 1 · İlk uygulama](#6)
7. [Ders 2 · Yerleşim: Row, Column, boyutlar](#7)
8. [Ders 3 · Durum: reactive ve bind](#8)
9. [Ders 4 · Olaylar ve mesajlar](#9)
10. [Ders 5 · Eylemler, kısayollar, komut paleti, menüler](#10)
11. [Ders 6 · async, zamanlayıcılar ve uzun işler](#11)
12. [Ders 7 · Diyaloglar ve ekranlar](#12)
13. [Ders 8 · Pencereler, tam ekran, dosya diyalogları, sürükle-bırak](#13)
14. [Ders 9 · Kendi bileşenini yazmak](#14)
15. [Ders 10 · Test yazmak](#15)
16. [Görünüm: tema, görünüm kümesi, yoğunluk, belirteçler](#16)
17. [Ayarlar ve durum kaydı](#17)
18. [Markup](#18)
19. [Bileşen başvurusu](#19)
20. [Sık yapılan hatalar](#20)
21. [LLM'ler için kurallar](#21)
22. [Sözlük](#22)

---

<a id="1"></a>

## 1. termik nedir, ne değildir

termik, **terminal uygulamalarının görünüşünü** (eş genişlikli yazı, `[ köşeli ]` butonlar, `┌─┐`
çerçeveler, kısayol satırı, komut paleti) **gerçek bir pencerede** sunan bir Python arayüz
kütüphanesidir. Çizimi pygame-ce yapar; terminal kullanılmaz (akış API'sinin terminal kipi hariç).

Bu yüzden terminalin kısıtları yoktur: fare her yerde çalışır, resim gösterilir, yazı tipi pürüzsüzdür,
pencere yeniden boyutlanır, birden çok pencere açılır, işletim sisteminin dosya diyaloğu kullanılır.
Ama tasarım dili CLI'dır: ölçüler **karakter ve satır** birimindedir, her şey klavyeyle de yapılır.

termik **değildir**:

- Bir terminal (TUI) kütüphanesi değil. Textual'a benzeyen bir API'si var ama SSH üzerinden ya da
  terminalde çalışmaz (akış API'si bunun istisnası; aşağıda).
- Bir web çatısı değil; HTML/CSS yok. Biçim, tema belirteçleriyle seçilir.
- Bir tkinter sarmalayıcısı değil; bütün bileşenler termik'in kendi çizimidir.

Kime göre: script'ine hızlıca pencere eklemek isteyenler (akış API'si), klavye ağırlıklı araçlar ve
paneller yazanlar (bileşen katmanı).

---

<a id="2"></a>

## 2. Kurulum ve ilk çalıştırma

```bash
pip install termik
```

Python 3.11+ gerekir; pygame-ce bağımlılık olarak gelir. Kurulunca `termik` komutu da gelir:

| Komut | İş |
|---|---|
| `termik demo [klasör]` | Çok panelli örnek uygulama (bileşen katmanının vitrini) |
| `termik akis` | Akış API'siyle yazılmış örnek betik |
| `termik yeni AD [--tur uygulama\|arac\|betik]` | Yeni proje iskeleti (testiyle birlikte) |
| `termik çalıştır DOSYA.py [--izle]` | Çalıştır; `--izle` kaydettikçe yeniden açar |
| `termik ayarlar` | Görünüm ve kip tercihlerini seç, ayar dosyasına kaydet |
| `termik ayarlar --yol` | Ayar dosyasının yerini yaz |
| `termik --version` | Sürüm |

Yeni bir şey öğrenirken en hızlı döngü: `termik yeni deneme`, sonra
`termik çalıştır deneme/deneme.py --izle`; dosyayı her kaydettiğinde pencere yeniden açılır.

---

<a id="3"></a>

## 3. İki katman: hangisini seçmeli

termik'in iki katmanı vardır ve **ikisi aynı kütüphanedir**; aynı tema, aynı ayarlar.

| | Akış API'si | Bileşen katmanı |
|---|---|---|
| Ne için | Baştan sona akan script'ler | Kullanıcının istediği sırayla gezdiği uygulamalar |
| Yazım | `termik.ask(...)`, `termik.print(...)`: sıradan fonksiyon çağrıları | `class Uygulama(ui.App)`: `compose()`, olaylar, eylemler |
| Akış | Senin kodun sırayı belirler; soru cevaplanınca devam eder | Olay döngüsü belirler; sen olaylara cevap verirsin |
| Pencere yoksa | Terminalde çalışmayı sürdürür | pygame-ce ve ekran gerekir |
| Örnek | Kurulum sihirbazı, yedek alma betiği, veri dönüştürücü | Dosya yöneticisi, izleme paneli, ayar aracı |

**Karar kuralı:** Program "şunu sor, sonra şunu yap, sonra şunu göster" diye düz bir çizgide
ilerliyorsa akış API'si. Kullanıcı aynı anda birden çok şeyle uğraşabiliyorsa (panel, liste, form,
butonlar) bileşen katmanı. Emin değilsen akışla başla; `termik.show(widget)` ile akışın içine bileşen
de koyabilirsin.

İçe aktarma alışkanlığı:

```python
import termik            # akış API'si: termik.ask, termik.print …
import termik as ui      # bileşen katmanı: ui.App, ui.Button … (ikisi aynı modül)
```

---

<a id="4"></a>

## 4. Akış API'si: adım adım

### 4.1 En küçük örnek

```python
import termik

ad = termik.ask("Adın?")
termik.ok(f"Merhaba [bold]{termik.escape(ad)}[/]!")
```

İlk `termik.*` çağrısı bir **döküm penceresi** açar. Yazılanlar alt alta akar; sorulan soru
pencerede cevap bekler. Script bitince pencerenin altında "bitti" yazar; ⏎ ya da Esc kapatır.

Nasıl çalışır: pencere ayrı bir thread'de döner, senin kodun kendi thread'inde. `ask()` cevap gelene
kadar senin thread'ini bekletir ama pencere donmaz. Pencereyi kapatmak script'te
`KeyboardInterrupt` doğurur; yani Ctrl+C gibi davranır.

### 4.2 Yazdırmak

```python
termik.print("düz yazı ve [green]markup[/]")   # print() gibi: sep=, end=, markup=False
termik.ok("bitti")        # ✓ yeşil
termik.info("bilgi")      # • mavi
termik.warn("dikkat")     # ⚠ sarı
termik.error("olmadı")    # ✗ kırmızı
termik.rule("Bölüm")      # ── Bölüm ──────
termik.table([{"ad": "a.txt", "boyut": "1 KB"}, {"ad": "b.txt", "boyut": "2 KB"}])
termik.table([["a.txt", "1 KB"]], headers=["ad", "boyut"])
```

Yakalama varsayılan olarak açıktır: script'teki sıradan `print()`, `sys.stderr`, `logging` ve hatta
`input()` da pencereye gider. Yani var olan bir script'in başına `import termik` ve bir
`termik.setup(title="Aracım")` eklemek çoğu zaman yeter.

### 4.3 Sormak

```python
yas   = termik.ask("Yaşın?", type=int, validate=lambda n: n > 0 or "pozitif olmalı")
parola = termik.ask("Parola", password=True)
yol   = termik.ask_path("Kaynak klasör", kind="dir")          # Tab tamamlar, Ctrl+O dosya diyaloğu
mod   = termik.choose("Mod", ["Tam", "Artımlı"])
mod   = termik.choose("Mod", {"Tam yedek": "full", "Artımlı": "inc"})   # etiket → değer
türler = termik.choose_many("Türler", ["jpg", "png", "pdf"], default=["jpg"])
if termik.confirm("Başlansın mı?", default=True): ...
```

Kurallar:

- `type=` cevabı çevirir; çeviri hatası kullanıcıya gösterilir ve soru tekrar sorulur.
- `validate=` `True`/`None` dönerse geçerli; `False` ya da **bir yazı** dönerse geçersiz ve o yazı
  hata olarak gösterilir (`lambda n: n > 0 or "pozitif olmalı"` deyimi bu yüzden çalışır).
- `default=` alanı dolu getirir; boş bırakılırsa default döner.
- Cevaplanan soru dökümde tek satırlık bir özete (`✓ Yaşın? 34`) dönüşür.

### 4.4 Form: birden çok alanı tek seferde

```python
ayar = termik.form("Bağlantı",
                   sunucu="localhost",          # yazı alanı (türü değerden: str)
                   port=8080,                   # sayı alanı (int)
                   güvenli=True,                # onay kutusu (bool)
                   parola=termik.Password,      # gizli alan
                   mod=termik.Field("Tam", choices=["Tam", "Artımlı"]))
print(ayar["port"] + 1)
```

Alanın türü **varsayılan değerinden** çıkar. `termik.Field(default, label=, type=, choices=,
password=, validate=)` ayrıntı verir. Değer olarak bir bileşen de verilebilir:
`derinlik=ui.Slider(3, min=1, max=9)`.

### 4.5 İlerleme

```python
for dosya in termik.track(dosyalar, "Kopyalanıyor", unit="dosya"):
    kopyala(dosya)

with termik.progress("İndiriliyor", total=boyut, unit="B") as bar:
    for parca in parcalar:
        bar.advance(len(parca))

with termik.spinner("Bağlanılıyor"):
    baglan()
```

### 4.6 Akışın içinde bileşen ve grafik

```python
import termik, termik as ui

tablo = termik.show(ui.Table("Dosya", ("Boyut", 10, "right"), height=8))
hiz = termik.chart({"hız": []}, title="MB/sn", max_points=40, height=8)
for i in range(40):
    tablo.add_row(f"dosya{i}.dat", f"{i * 3} KB")   # script thread'inden güvenle çağrılır
    hiz.append("hız", 20 + i % 7)
```

`termik.show()` bir tutamak döndürür; tutamağın metotları pencerenin thread'ine güvenle iletilir.

### 4.7 Pencere yoksa: terminal kipi

Ekran yoksa (SSH, sunucu) ya da `TERMIK_MODE=terminal` ise aynı script terminalde çalışır: renkler
ANSI, sorular satır satır, ilerleme yerinde güncellenen satır. Kod değişmez. Kipi seçmek:
`termik.setup(mode="terminal")`, ayar dosyasında `mode = "terminal"` ya da ortam değişkeni.

### 4.8 Akış API'sinde dikkat

- Akış fonksiyonları **senkron**dur; `await` edilmez.
- Kullanıcıdan gelen yazıyı markup'a gömerken `termik.escape()` kullan: `[` ile başlayan bir dosya adı
  yoksa biçim etiketi sanılır.
- `termik.setup(...)` ilk `termik.*` çağrısından **önce** yapılmalı (başlık, tema, kip).

---

<a id="5"></a>

## 5. Bileşen katmanının zihinsel modeli

Bileşen katmanını beş fikir taşır. Bunları kavrayınca geri kalanı ayrıntıdır.

**1. Ağaç.** Arayüz bir bileşen ağacıdır. Kök `App`'tir (aynı zamanda ana penceredir). `compose()`
çocukları üretir; `with ui.Row():` bloğu içinde üretilenler o Row'un çocuğu olur.

```
App (ana pencere)
└── ana ekran (Screen)
    ├── Panel "Yedekleme"
    │   ├── Input #kaynak
    │   └── Button "Başlat"
    └── KeyBar
```

**2. Yerleşim karakter birimindedir.** `width=30` otuz karakter, `height=5` beş satır. Kalan alanı
`"1fr"` payları paylaşır. Piksel hesaplamazsın; yazı boyutu ya da ekran ölçeği değişince her şey
orantılı kalır.

**3. Olaylar yukarı kabarcıklanır.** Bir buton basılınca `Button.Pressed` mesajı butondan başlar,
ebeveynlerine doğru çıkar. Herhangi bir ata `on_button_pressed` metodu tanımlayarak yakalar. Tuşlar
da önce odaktaki bileşene gider, sonra yukarı çıkar.

**4. Komutlar `@action` ile tek yerde tanımlanır.** Bir metot bir kez tanımlanır; tuşa bağlanır,
kısayol satırında (KeyBar) görünür, komut paletinde (Ctrl+P) aranır, butona ve menüye adıyla verilir.

**5. Ekran yalnızca değişince çizilir, döngü asyncio'dur.** Bir değeri değiştirdiğinde (`reactive`)
bileşen kendini yeniden çizdirir; elle "ekranı yenile" demezsin. İşleyiciler `async def`
olabilir; bloklayan işler `run_worker` ile thread'e gider.

Bir de ekranlar: üst üste yığılan katmanlar. Diyalog, komut paleti, açılır liste birer ekrandır;
en üstteki girdiyi alır, kapanınca (`dismiss`) odak önceki yerine döner.

---

<a id="6"></a>

## 6. Ders 1 · İlk uygulama

```python
import termik as ui

class Merhaba(ui.App):
    TITLE = "Merhaba"          # pencere başlığı
    SIZE = (640, 320)          # pencere boyutu (ölçek 1.0'da piksel; ekran ölçeğine göre büyür)

    def compose(self):
        with ui.Panel(title="Selam"):
            yield ui.Input(label="Adın", id="ad")
            yield ui.Button("Selamla", self.selamla, key="f5", variant="primary")
        yield ui.KeyBar()      # alt satır: f5 selamla · tab sonraki · ctrl+p komutlar · ctrl+q çık

    def selamla(self):
        ad = self.query_one("#ad", ui.Input).value
        self.notify(f"Merhaba {ui.escape(ad)}!", "ok")

if __name__ == "__main__":
    Merhaba().run()
```

Satır satır:

- `class Merhaba(ui.App)`: uygulama bir sınıftır. Sınıf öznitelikleri pencereyi tarif eder (`TITLE`,
  `SIZE`, `PADDING`, `GAP`, `ICON`, `FULLSCREEN`, `SAVE_STATE`).
- `compose()` bir **üreteçtir** (`yield`). Bileşenler burada kurulur, ama henüz çizilmez.
- `with ui.Panel(...)`: Panel bir kapsayıcıdır; bloğun içindeki `yield`ler onun çocuğu olur.
- `ui.Button("Selamla", self.selamla, key="f5")`: ikinci argüman ne yapılacağıdır (fonksiyon ya da
  eylem adı). `key=` ekranın neresinde olunursa olsun F5'in butona basmasını sağlar ve kısayolu
  KeyBar'a ekler.
- `self.query_one("#ad", ui.Input)`: ağaçta `id="ad"` olanı bulur; ikinci argüman türü denetler.
- `self.notify(yazı, tür)`: sağ üstte kısa bildirim. Türler: `"info"`, `"ok"`, `"warn"`, `"err"`.
- `ui.escape(ad)`: kullanıcının yazdığını markup'tan korur.
- `run()` pencereyi açar ve kapanana kadar bekler; `exit(sonuç)`'a verileni döndürür.

Hazır gelen kısayollar: **Tab / Shift+Tab** odak, **Ctrl+P** komut paleti, **Ctrl+Q** çıkış, **F11**
tam ekran, **F10** ya da **Alt+harf** menü (MenuBar varsa), **Shift+F10** bağlam menüsü.

### Sınıf yazmadan

Küçük araçlar için:

```python
import termik as ui

app = ui.App(title="Sayaç")
app.metin = ""

@app.compose
def arayuz():
    yield ui.TextArea(bind="metin", rows=6)
    yield ui.Button("Say", lambda: app.notify(f"{len(app.metin.split())} kelime"), key="f5")
    yield ui.KeyBar()

app.run()
```

---

<a id="7"></a>

## 7. Ders 2 · Yerleşim: Row, Column, boyutlar

### 7.1 Dizim

- Varsayılan dizim **alt alta**dır (her kapsayıcı bir sütundur).
- `ui.Row()` çocuklarını **yan yana** dizer, `ui.Column()` açıkça alt alta.
- `gap=` çocuklar arasındaki boşluk (Row'da karakter, Column'da satır).
- `padding=` iç boşluk: `1` her yan; `(dikey, yatay)`; `(üst, sağ, alt, sol)`. Dikey satır, yatay karakter.
- `ui.Spacer()` kalan yeri doldurur: butonu sağa yaslamanın yolu.

```python
with ui.Row(gap=2):
    yield ui.Spacer()                      # sola itilen boşluk
    yield ui.Button("Vazgeç", "cancel")
    yield ui.Button("Kaydet", "save", variant="primary")
```

### 7.2 Boyut birimleri

| Yazım | Anlamı |
|---|---|
| `30` | 30 karakter (genişlik) ya da 30 satır (yükseklik) |
| `2.5` | kesirli de olur |
| `"12px"` | piksel (nadiren gerekir) |
| `"40%"` | kabın yüzde 40'ı |
| `"1fr"`, `"2fr"` | kalan alandan pay |
| `"auto"` | içeriği kadar |

`width=`, `height=`, `min_width=`, `max_width=`, `min_height=`, `max_height=` her bileşende vardır.

### 7.3 Neyin ne kadar yer kapladığı (önemli)

- Bileşenlerin çoğunun **genişliği** varsayılan olarak `"1fr"`dir: kabın genişliğini doldurur.
  İstisnalar içerik kadardır (`"auto"`): `Button`, `Select`, `Spinbox`, `Image`.
- **Yükseklik** varsayılan olarak içeriği kadardır; büyüyebilen bir çocuğu olan kap (ör. `Log`,
  `height="1fr"` verilmiş bir bileşen) kalan yüksekliği alır.
- Bir şeyin pencerenin geri kalanını doldurmasını istiyorsan ona `height="1fr"` ver.

```python
def compose(self):
    yield ui.Header("araç", "alt başlık")
    with ui.Row(gap=1):                        # orta bölge
        yield ui.Panel(ui.DirectoryTree("."), title="Dosyalar", width=32)
        yield ui.Panel(ui.Log(id="log"), title="Günlük")   # Log büyür → panel ve satır büyür
    yield ui.KeyBar()
```

### 7.4 Kullanıcının boyutlandırdığı paneller: Split

```python
with ui.Split(sizes=[32, "1fr"]):              # aradaki ayraç fareyle sürüklenir
    yield ui.Panel(ui.DirectoryTree("."), title="Dosyalar")
    with ui.Split(direction="column", sizes=["2fr", "1fr"]):
        yield ui.Panel(ui.Log(), title="Günlük")
        yield ui.Panel(ui.TextArea(), title="Notlar")
```

Ayraca çift tık başa döndürür; Alt+Shift+ok klavyeyle kaydırır; `SAVE_STATE` açıksa oranlar saklanır.

### 7.5 Form: etiketli alanlar

Etiketleri hizalamak için `Form` kullanılır; içindeki her bileşen `label=` alır:

```python
with ui.Form():
    yield ui.Input(label="Kaynak", bind="kaynak")
    yield ui.Slider(6, max=9, label="Düzey")
    yield ui.Select(["Elle", "Her gün"], label="Zamanlama")
    with ui.Row(label="Seçenekler", gap=2):      # kendi yazısı olan bileşenler için Row'a label
        yield ui.Checkbox("Sıkıştır", True)
        yield ui.Checkbox("Şifrele")
```

Etiketler solda hizalı ya da alanın üstünde durur (`form_label` belirteci: `left` / `top`).

---

<a id="8"></a>

## 8. Ders 3 · Durum: reactive ve bind

### 8.1 reactive

Bir değer değişince ekranın kendiliğinden güncellenmesi için `ui.reactive` kullanılır:

```python
class Sayac(ui.Widget):
    deger = ui.reactive(0)

    def render(self, p):
        p.write(self.content.x, self.content.y, f"[bold]{self.deger}[/]")

    def watch_deger(self, eski, yeni):     # isteğe bağlı: değişince çağrılır (async olabilir)
        if yeni > 10:
            self.app.notify("10'u geçti", "warn")
```

- `self.deger += 1` yazmak yeter; yeniden çizim kendiliğinden olur.
- İzleyici `watch_<ad>` `(eski, yeni)`, `(yeni)` ya da hiç argüman almayabilir.
- Boyutu etkileyen değerlerde `ui.reactive(..., layout=True)`: yerleşim de yeniden hesaplanır.
- Varsayılan değiştirilebilir bir nesneyse fabrika ver: `ui.reactive(list)` (her nesneye ayrı liste).

### 8.2 bind: alanı bir özniteliğe bağlamak

Formdaki alanların değerini elle okumak yerine bir özniteliğe bağla:

```python
class Ayarlar(ui.App):
    kaynak = ui.reactive("C:/Projeler")
    duzey = ui.reactive(6)

    def compose(self):
        with ui.Form():
            yield ui.Input(label="Kaynak", bind="kaynak")
            yield ui.Slider(max=9, label="Düzey", bind="duzey")
        yield ui.Button("Göster", lambda: self.notify(f"{self.kaynak} · {self.duzey}"))
```

- Bağ **iki yönlüdür**: kullanıcı yazınca `self.kaynak` değişir; koddan `self.kaynak = "D:/"`
  atayınca alan güncellenir.
- Ad, bileşenden yukarı doğru, o adı taşıyan ilk atada aranır (bulunmazsa pencerede).
- Düz öznitelik de olur (`app.metin = ""`), ama `reactive` olursa `watch_` izleyicisi de çalışır.
- `bind=` alanlar: Input, TextArea, Checkbox, RadioSet, Select, Slider, Spinbox, OptionList...
  Değeri olmayan bir bileşene (`Static` gibi) `bind=` vermek `TypeError`dır.

---

<a id="9"></a>

## 9. Ders 4 · Olaylar ve mesajlar

### 9.1 Adlandırma kuralı

Mesaj sınıfının adı yakalayan metodun adını belirler: `<Bileşen>.<Mesaj>` → `on_<bileşen>_<mesaj>`
(küçük harf, alt çizgili).

| Mesaj | Yakalayan metot | Taşıdıkları |
|---|---|---|
| `Button.Pressed` | `on_button_pressed` | `event.button` |
| `Input.Changed` / `Input.Submitted` | `on_input_changed` / `on_input_submitted` | `event.input`, `event.value` |
| `TextArea.Changed` | `on_text_area_changed` | `event.text` |
| `Checkbox.Changed` | `on_checkbox_changed` | `event.checkbox`, `event.value` |
| `RadioSet.Changed` | `on_radio_set_changed` | `event.value` |
| `Select.Changed` | `on_select_changed` | `event.select`, `event.index`, `event.value` |
| `Slider.Changed` / `Spinbox.Changed` | `on_slider_changed` / `on_spinbox_changed` | `event.value` |
| `Tabs.Changed` | `on_tabs_changed` | |
| `Tree.NodeSelected` / `NodeHighlighted` | `on_tree_node_selected` / `..._highlighted` | `event.node`, `event.node.data` |
| `Table.RowSelected` | `on_table_row_selected` | `event.table`, `event.key` |
| `OptionList.Selected` | `on_option_list_selected` | `event.index` |
| `Split.Resized` | `on_split_resized` | `event.fractions` |
| `Canvas.Clicked` / `Dragged` | `on_canvas_clicked` / `on_canvas_dragged` | `event.x`, `event.y` (birim) |
| `Key` | `on_key` | `event.key` ("ctrl+s"), `event.char` |
| `Click`, `MouseDown`, `MouseUp`, `MouseMove`, `MouseScroll` | `on_click` … | `event.x`, `event.y`, `event.button`, `event.count` (Click) |
| `Drop` | `on_drop` | `event.paths` (Path listesi), `event.text` |
| `Focus` / `Blur` | `on_focus` / `on_blur` | |

### 9.2 Kabarcıklanma ve durdurma

Mesaj gönderenden başlar, ebeveynlere çıkar. Bir ata yakalayıp `event.stop()` derse daha yukarı gitmez.
Böylece "bütün formdaki değişiklikler" tek yerde (formun ya da uygulamanın metodunda) dinlenir:

```python
class Uygulama(ui.App):
    def on_input_changed(self, event):       # içerideki bütün Input'lar buraya gelir
        if event.input.id == "ara":
            self.filtrele(event.value)
```

Bazı olaylar kabarcıklanmaz (`Focus`, `Blur`, `MouseMove`, `MouseEnter/Leave`, `TextInput`).

### 9.3 Kısa yollar: geri çağırma parametreleri

Birçok bileşen mesaja ek olarak doğrudan fonksiyon alır: `Button("Tamam", fn)`,
`Input(on_submit=fn, on_change=fn)`, `Select(..., on_change=fn)`, `Slider(on_change=fn)`. Küçük
işler için mesaj metodu yazmaktan pratiktir.

### 9.4 Kendi mesajın

```python
class Sepet(ui.Widget):
    class Eklendi(ui.Message):
        def __init__(self, urun):
            super().__init__()
            self.urun = urun

    def ekle(self, urun):
        self.post_message(Sepet.Eklendi(urun))   # ataları on_sepet_eklendi ile yakalar
```

---

<a id="10"></a>

## 10. Ders 5 · Eylemler, kısayollar, komut paleti, menüler

### 10.1 @action

```python
class Editor(ui.App):
    @ui.action("Kaydet", key="ctrl+s", hint="kaydet")
    async def save(self):
        ...

    @ui.action("Yenile", key="f5,ctrl+r", show=False)
    def reload(self):
        ...
```

Parametreler: `label` (palette ve menüde görünen ad), `key=` (virgülle birden çok tuş), `hint=`
(KeyBar'daki kısa ad), `show=False` (KeyBar'da gösterme), `palette=False` (palette gösterme),
`priority=True` (odak bir yazı alanında bile önce çalışsın; Ctrl+Q gibi).

Bir eylem nerede tanımlıysa o bileşen ve torunları odaktayken geçerlidir. Odaktaki bileşenden yukarı
aranır; aynı tuşu içteki kazanır. Uygulamada tanımlanan eylem her yerde geçerlidir.

**Tuş adları:** küçük harf, değiştiriciler `+` ile: `"ctrl+s"`, `"shift+tab"`, `"alt+d"`,
`"ctrl+shift+z"`, `"f5"`, `"enter"`, `"escape"`, `"space"`, `"up"`, `"pageup"`, `"home"`,
`"delete"`, `"backspace"`. Türkçe klavyede AltGr (`@` için) `"altgr+q"` olarak gelir, kısayolları
tetiklemez.

**Yazı alanındayken** harf tuşları kısayol değil yazıdır: odak bir Input'tayken `"a"` kısayolu
çalışmaz, `"ctrl+a"` çalışır.

### 10.2 Eylemi adıyla çağırmak

`Button("Kaydet", "save")`, `MenuItem("Kaydet", "save")`, `self.run_action("save")`. Ad bileşenden
yukarı aranır; `"app.save"` doğrudan uygulamada, `"window.close"` bileşenin penceresinde aranır.

### 10.3 Komut paleti

Ctrl+P bağlamdaki bütün `@action`'ları listeler; bulanık arar (`baslat` yazınca "Başlat" bulunur).
Ek komutlar için:

```python
def get_commands(self):
    yield from super().get_commands()           # tema ve yoğunluk seçimi
    yield ui.Command("Önbelleği temizle", self.temizle)
```

### 10.4 Menü çubuğu ve sağ tık menüsü

```python
yield ui.MenuBar(
    ui.Menu("&Dosya", [ui.MenuItem("&Aç…", "open"), ui.MenuItem("&Kaydet", "save"), None,
                       ui.MenuItem("Çı&k", "app.quit")]),
    ui.Menu("&Görünüm", [ui.MenuItem("&Tam ekran", "window.toggle_fullscreen")]),
)
```

`&` kısayol harfini belirler (Alt+D Dosya'yı açar). `None` ayraçtır. Eylemin tuşu menüde
kendiliğinden yazar; bulunamayan eylem soluk görünür.

Sağ tık menüsü için bileşene `context_menu` yaz:

```python
class DosyaListesi(ui.Tree):
    def context_menu(self, event):
        return [ui.MenuItem("&Sil", self.sil), ui.MenuItem("&Yeniden adlandır", "rename")]
```

---

<a id="11"></a>

## 11. Ders 6 · async, zamanlayıcılar ve uzun işler

Olay döngüsü asyncio'dur ve **tek thread**'dir. Kural: **arayüz işleyicisinde asla bloklama.**

| İş | Yol |
|---|---|
| Ağ, `asyncio` kütüphaneleri | İşleyiciyi `async def` yap, `await` et |
| Bloklayan iş (dosya tarama, `requests`, hesap) | `await self.run_worker(fonksiyon, argümanlar)`: ayrı thread |
| Başka thread'den arayüzü güncellemek | `self.call_from_thread(fn, *args)` |
| Tekrarlayan iş | `self.set_interval(saniye, fn)` → `Timer`; `.stop()` |
| Bir kez, gecikmeli | `self.set_timer(saniye, fn)` |
| Sonraki turda | `self.call_later(fn)` |

```python
class Tarayici(ui.App):
    def compose(self):
        yield ui.ProgressBar(id="cubuk")
        yield ui.Button("Tara", self.tara, key="f5")

    async def tara(self):
        sayi = await self.run_worker(self.say, "C:/Projeler")   # pencere donmaz
        self.notify(f"{sayi} dosya", "ok")

    def say(self, klasor):                     # ayrı thread: arayüze doğrudan dokunma
        import os
        cubuk = self.query_one("#cubuk", ui.ProgressBar)
        n = 0
        for i, (_, _, dosyalar) in enumerate(os.walk(klasor)):
            n += len(dosyalar)
            self.call_from_thread(setattr, cubuk, "progress", min(1, i / 500))
        return n
```

Zamanlayıcılar bileşen ağaçtan çıkınca kendiliğinden durur. İşleyicideki bir hata uygulamayı düşürmez:
konsola iz, ekrana kırmızı bildirim düşer.

---

<a id="12"></a>

## 12. Ders 7 · Diyaloglar ve ekranlar

```python
if await self.confirm("Silinsin mi?", yes="Sil", no="Vazgeç"):
    ...
await self.alert("Bitti.")
ad = await self.prompt("Yeni ad", value="rapor.md")       # Esc → None
```

Bunlar `async`tır: çağıran işleyici `async def` olmalı. Diyalog açıkken arka plandaki işler sürer.

Kendi diyaloğun:

```python
secim = await self.push_screen_wait(
    ui.Dialog("Biçim", "Hangi biçimde kaydedilsin?",
              buttons=[("Vazgeç", None), ("CSV", "csv"), ("JSON", "json")], default=2))
```

Ekran yığını: `push_screen(ekran, callback=)` ekranı üste koyar; ekran `self.dismiss(sonuç)` ile
kapanır; `push_screen_wait` sonucu bekler. Kendi tam ekran görünümün için `ui.Screen`'den türet;
`modal = True` arkayı kilitler (ve karartır; `veil = False` karartmaz). Yüzen kutu için `ui.Popup`.

---

<a id="13"></a>

## 13. Ders 8 · Pencereler, tam ekran, dosya diyalogları, sürükle-bırak

### 13.1 İkinci pencere

```python
class Ayarlar(ui.Window):
    TITLE = "Ayarlar"
    SIZE = (520, 300)

    def compose(self):
        yield ui.Select(list(ui.THEMES), label="Tema", id="tema")
        yield ui.Button("Kapat", "window.close")

    def on_select_changed(self, event):
        self.app.set_theme(event.value)          # tema bütün pencerelere yansır

class Ana(ui.App):
    @ui.action("Ayarlar…", key="f9")
    def ayarlar(self):
        self.open_window(Ayarlar())              # açanın ortasına açılır

    async def sor(self):
        sonuc = await self.open_window_wait(Ayarlar(), modal=True)   # close(sonuç)'u bekler
```

- Her pencerenin kendi ekran yığını, odağı, bildirimleri vardır. Bileşen kendi penceresine
  `self.window` ile ulaşır: `self.window.confirm(...)`, `self.window.notify(...)`.
- `self.app` her yerde uygulamadır (= ana pencere). **Ek pencerede `self.app.confirm` ana pencerede
  açılır**; çoğu zaman istenen `self.window.confirm`'dur.
- `modal=True`: o kapanana kadar öncekiler girdi almaz.
- Kapatma: ✕, Alt+F4, Ctrl+W (ek pencerede) `can_close()`'u sorar. `close(sonuç)` sormadan kapatır.
  Ana pencere kapanınca uygulama kapanır.

```python
async def can_close(self):
    return not self.degisti or await self.window.confirm("Kaydedilmedi. Kapatılsın mı?")
```

### 13.2 Tam ekran

- **F11** her pencerede tam ekranı açar/kapatır (komut paletinde "Tam ekran").
- Koddan: `self.window.fullscreen = True` (ya da `False`).
- Açılışta tam ekran: sınıfta `FULLSCREEN = True`, `App(fullscreen=True)` ya da kullanıcı ayarı
  `fullscreen = true` (`TERMIK_FULLSCREEN=evet`). Öncelik: kod > ortam > ayar dosyası.
- Tam ekran "masaüstü" kipidir: ekran çözünürlüğü değişmez, Alt+Tab hızlı kalır. Yerleşim karakter
  birimiyle olduğu için arayüz yeni boyuta kendiliğinden yayılır.
- Görünür düğme: `yield ui.FullscreenButton()` (kendiliğinden eklenmez; istediğin yere koy). Yazısı
  duruma göre `⛶ Tam ekran` / `⛶ Pencere` olur, F11 ile de güncellenir.

### 13.3 Dosya diyalogları

```python
yol = await self.ask_open("Resim seç", filetypes=[("Resimler", "*.png *.jpg"), ("Tümü", "*.*")])
yollar = await self.ask_open(multiple=True)                 # liste; vazgeçilirse boş
hedef = await self.ask_save(name="rapor.md", filetypes=[("Markdown", "*.md")])
klasor = await self.ask_folder(folder="~/Belgeler")
```

Sonuç `pathlib.Path` (vazgeçilirse `None`). Varsayılan olarak **işletim sisteminin** diyaloğu açılır
(Windows'ta Common Item Dialog, macOS'ta Finder, Linux'ta zenity/kdialog); `dialogs = "builtin"`
ayarıyla termik'in klavyeyle gezilen gezgini. Kaydederken uzantı yoksa süzgeçtekisi eklenir, dosya
varsa üzerine yazma sorulur.

### 13.4 Sürükle-bırak

Dosya yöneticisinden bırakılanlar farenin altındaki bileşene `Drop` mesajıyla gider:

```python
def on_drop(self, event):
    for yol in event.paths:        # pathlib.Path
        self.ekle(yol)
```

`Input` ve `TextArea` bırakılan yolu kendileri yazar (`input.drop_replaces = True` yazının yerine
koyar). Akış API'sinde bırakılan dosya cevap bekleyen yol sorusuna gider.

### 13.5 Pencere simgesi

Verilmezse temanın vurgu renginde `❯` ve imleç çizilir. Kendi simgen: `ICON = "simge.png"`,
`App(icon=...)` ya da `self.window.set_icon(...)`.

---

<a id="14"></a>

## 14. Ders 9 · Kendi bileşenini yazmak

Bir bileşen `ui.Widget`'tan türer ve üç şeyden birini yapar: **birleştirir** (`compose`), **çizer**
(`render`), **ölçer** (`measure`).

### 14.1 Birleştirerek (en kolayı)

```python
class AramaKutusu(ui.Widget):
    default_height = "auto"

    def compose(self):
        with ui.Row(gap=1):
            yield ui.Input(placeholder="ara…", id="sorgu")
            yield ui.Button("Ara", self.ara)

    def ara(self):
        self.post_message(AramaKutusu.Arandi(self.query_one("#sorgu", ui.Input).value))

    class Arandi(ui.Message):
        def __init__(self, sorgu):
            super().__init__()
            self.sorgu = sorgu
```

### 14.2 Çizerek

```python
class Rozet(ui.Widget):
    default_width = "auto"
    default_height = "auto"
    metin = ui.reactive("YENİ", layout=True)

    def measure(self, p, width):             # içeriğin doğal boyutu (piksel)
        return p.text.width(self.metin) + p.ch * 2, p.row

    def render(self, p):                     # p: Painter; çizim self.region'a kırpılır
        th = p.theme
        p.round_rect(self.region, th.accent)
        p.write(self.content.x + p.ch, self.content.y, self.metin, color=th.bg)
```

Bilinmesi gerekenler:

- `self.region`: bileşenin dikdörtgeni; `self.content`: iç boşluk düşülmüş hali (piksel).
- `p.ch` bir karakterin genişliği, `p.row` bir satırın yüksekliği (piksel). Ölçüleri bunlarla yaz.
- `p.theme` renkler (`bg`, `surface`, `raised`, `border`, `text`, `dim`, `faint`, `accent`, `accent2`,
  `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`) ve biçim belirteçleri.
- `p.write(x, y, markup, color=)` yazı; `p.surface` pygame yüzeyi (doğrudan `pygame.draw` da olur).
- Etkileşimli bileşen için `can_focus = True`, fare imleci için `cursor = "hand"`.
- Değişince `self.refresh()` (boyut değiştiyse `refresh(layout=True)`); `reactive` bunu kendisi yapar.
- Yaşam döngüsü: `on_mount()` ağaca bağlandıktan sonra, `on_unmount()` çıkarken.

### 14.3 Çalışırken ağacı değiştirmek

`kap.mount(yeni_bilesen)`, `bilesen.remove()`, `kap.remove_children()`, `bilesen.display = False`
(gizle, yer kaplamaz), `bilesen.disabled = True`.

---

<a id="15"></a>

## 15. Ders 10 · Test yazmak

`run_test()` pencere açmadan (SDL'in sahte sürücüsüyle) başlatır; `Pilot` kullanıcı gibi davranır.

```python
import asyncio
import termik as ui
from uygulamam import Merhaba

async def main():
    app = Merhaba()
    async with app.run_test(size=(800, 500)) as pilot:
        app.query_one("#ad").focus()
        await pilot.type("Efe")
        await pilot.press("f5")                    # tuşlar: "tab", "ctrl+s", "enter"…
        assert any("Efe" in m for m, _ in app._toasts)
        await pilot.click("#ad")                   # seçici, tür ya da bileşen
        await pilot.drop("#ad", "metin")           # Path → dosya, str → yazı
        pilot.snapshot("ekran.png")                # ekran görüntüsü

asyncio.run(main())
```

Diğerleri: `pilot.pause(saniye)`, `pilot.wait_until(koşul, timeout=)`, `pilot.hover(...)`,
`pilot.scroll(hedef, dy)`. Testler kullanıcının ayar dosyasından etkilenmesin diye `TERMIK_CONFIG`
olmayan bir dosyayı gösterebilir; durum kaydı `run_test` altında yalnızca açıkça istenirse çalışır.

---

<a id="16"></a>

## 16. Görünüm: tema, görünüm kümesi, yoğunluk, belirteçler

Görünüş üç bağımsız eksende seçilir:

1. **Renk teması** (`theme`): `okyanus` (varsayılan), `günbatımı`, `orman`, `neon`, `mono`, `lavanta`.
2. **Görünüm kümesi** (`look`): `terminal` (keskin köşe, dolu kutu butonlar) ya da `modern` (yuvarlak,
   kart zeminli).
3. **Yoğunluk** (`density`): `sıkı`, `dengeli`, `rahat` (varsayılan), `ferah`.

Bunların üstüne tek tek **biçim belirteçleri** ezilebilir:

| Belirteç | Değerler |
|---|---|
| `title` | `inverse` · `inline` · `tab` |
| `frame` | `faint` (varsayılan; soluk ince çizgi) · `line` · `corners` · `none` (modern görünümde kart) |
| `focus` | `title` (varsayılan; odakta yalnızca panel başlığı vurgu renginde) · `color` · `double` · `bar` · `none` |
| `button` | `solid` (varsayılan; butonlar yazıdan ve köşeli form alanlarından ayrılsın diye) · `tinted` · `bracket` · `boxed` · `angle` · `pill` |
| `bar` | `block` · `segment` · `line` · `ascii` |
| `selection` | `inverse` · `pointer` |
| `shadow` | `hard` · `soft` · `none` |
| `toggle` | `drawn` (varsayılan; kutucuk ve yuvarlak düğme çizilmiş şekil) · `text` (`[✓]`, `(•)`) |
| `radio` | `paren` · `dot` (yalnızca `toggle = "text"` iken) |
| `tabs` | `inverse` · `folder` · `underline` · `bracket` |
| `slider` | `bar` · `line` · `value` |
| `field` | `boxed` (varsayılan; Input, Select, Spinbox ince çerçeveli kutuda) · `filled` · `underline` · `plain` (kutusuz, eski hal) |
| `select` | `bracket` · `arrows` · `underline` (yalnızca `field = "plain"` iken) |
| `image` | `smooth` · `pixel` · `blocks` |
| `spin` | `bracket` · `arrows` · `stacked` (yalnızca `field = "plain"` iken) |
| `split` | `line` · `bar` · `hidden` |
| `form_label` | `left` · `top` |
| `chart` | `smooth` · `braille` · `blocks` |
| `radius`, `panel_fill`, `font_size`, `line_height`, `pad_x`, `pad_y` | sayılar / mantıksal |
| renkler | `accent = "#ff8800"`, `accent2`, `accent3` gibi |

```python
App(theme="neon", look="modern", density="ferah", bar="segment", accent="#ff8800")
self.set_theme("orman", density="sıkı")         # çalışırken; bütün pencerelere yansır
```

**Koda tema yazmadan önce düşün:** kullanıcı kendi tercihini ayar dosyasında tutar. Kod tema
vermezse onun tercihi geçerli olur. Tema yalnızca uygulamanın kimliği için gerekiyorsa ver.

### 16.1 Renkler: palet, roller, öge başına renk

Her tema üç renkten oluşur: birincil (`accent`), ikincil (`accent2`), üçüncül (`accent3`);
`make_theme` ile dördüncül ve sonrası da eklenir. Hangi öge türünün kaçıncı renkle çizileceği
temadan bağımsız `ui.ROLES` tablosundadır: 1 etkileşim (Button, Input, Select, Checkbox…, odak),
2 değer (ProgressBar, Slider, Sparkline), 3 gezinme ve yapı (Tabs, Tree, Table, Header, StatusBar,
KeyBar).

```python
deniz = ui.make_theme("deniz", ["#38bdf8", "#f472b6", "#a3e635", "#fbbf24"])  # 4 renk
ui.register_theme(deniz)                      # App(theme="deniz"), ayar dosyası, komut paleti

class Uygulama(ui.App):
    ROLES = {"Tabs": 2}                       # bu uygulamada sekmeler ikincil renkte

    def compose(self):
        yield ui.Button("Sil", self.sil, variant="primary", color="red")   # tek öge
        yield ui.ProgressBar(color="quaternary")                         # dördüncül renk
```

Renk tanımı her yerde aynıdır: sıra numarası (`2`), sıra adı (`"secondary"`, `"ikincil"`,
`"tertiary"`, `"üçüncül"`, `"quaternary"`, `"dördüncül"`), tema rengi (`"green"`, `"red"`, `"dim"`),
`"#rrggbb"` ya da `(r, g, b)`. Çalışırken: `app.set_roles(Tabs=3)`, `öge.color = 2; öge.refresh()`.
Kendi bileşenini çizerken `p.theme.accent` kullan: öge kendi rengiyle çizilirken vurgu rengi o renktir,
roller ve `color=` kendiliğinden işler. Markup'ta `[secondary]`, `[tertiary]`, `[ikincil]` geçer.

---

<a id="17"></a>

## 17. Ayarlar ve durum kaydı

### 17.1 Kullanıcı tercihleri

Öncelik: **kodda verilen değer > ortam değişkeni > ayar dosyası > varsayılan.**

Ayar dosyası TOML: Windows'ta `%APPDATA%\termik\ayarlar.toml`, diğerlerinde
`~/.config/termik/ayarlar.toml`. `termik ayarlar` pencerede düzenler.

```toml
theme = "orman"
look = "terminal"
density = "dengeli"
mode = "auto"            # akış API'si: auto · window · terminal
dialogs = "native"       # dosya diyalogları: native · builtin
fullscreen = false       # uygulamalar tam ekran açılsın
bar = "segment"          # herhangi bir biçim belirteci
accent = "#ff8800"
```

Ortam değişkenleri `TERMIK_` önekli büyük harfli adlardır: `TERMIK_THEME=neon`,
`TERMIK_FULLSCREEN=evet`. Geçersiz değer programı durdurmaz (bir kez uyarı); kodda verilen yanlış ad
(`App(theme="yok")`) ise `ValueError`dır.

### 17.2 Durum kaydı

```python
class Araç(ui.App):
    SAVE_STATE = True
```

Kapanırken pencerenin yeri ve boyutu, `Split` oranları, açık sekmeler ve `bind=` ile bağlı değerler
saklanır; açılınca geri gelir. Bir alanı dışarıda bırakmak: `persist=False`. Parola alanları zaten
saklanmaz.

---

<a id="18"></a>

## 18. Markup

Bileşenlerin yazı aldığı her yerde (Static, Label, notify, Log, akış API'si...) rich benzeri markup
geçer:

```
[bold]kalın[/]   [italic]eğik[/]   [u]altı çizili[/]   [strike]üstü çizili[/]   [dim]soluk[/]
[green]yeşil[/]   [accent]tema vurgusu[/]   [#ff8800 on #1a2232]rozet[/]
[bold red]iki biçim[/]   [/] son açılanı kapatır, [/bold] adıyla kapatır
```

Renk adları tema renkleridir (`accent`, `dim`, `faint`, `red`, `green`, `yellow`, `blue`, `magenta`,
`cyan`, ...) ya da `#rrggbb`. Bilinmeyen etiketler (`[1/3]`) olduğu gibi yazılır. Köşeli parantezi
yazdırmak: `\[`. **Kullanıcıdan ya da dosyadan gelen yazı her zaman `ui.escape()`'ten geçirilir.**
Markup'sız düz yazı: `ui.plain_text(markup)`.

---

<a id="19"></a>

## 19. Bileşen başvurusu

Her bileşen ortak parametreleri alır: `id=`, `classes=`, `width=`, `height=`, `min_*`, `max_*`,
`padding=`, `gap=`, `disabled=`, `display=`, `tooltip=` (fare üstünde baloncuk), `label=` (Form
içinde etiket), `bind=` (değerli bileşenlerde), `persist=`.

### Yazı ve gösterim

| Bileşen | Kurulum | Önemli üyeler |
|---|---|---|
| `Static` | `Static("markup")` | `.update(yazı)`; genişliğe göre kaydırır |
| `Label` | `Label("markup")` | tek satır, sığmazsa `…` |
| `Header` | `Header("başlık", "alt başlık")` | logo ve saat |
| `KeyBar` | `KeyBar()` | geçerli kısayollar, tıklanabilir |
| `StatusBar` | `StatusBar(mode="HAZIR", left="…")` | `.mode`, `.mode_color`, `.right` |
| `Image` | `Image("foto.png", fit="contain", caption=)` | `.source = yol` |
| `Sparkline` | `Sparkline(label="CPU", value_format="{:.0%}", max_value=1)` | `.append(değer)` |
| `Chart` | `Chart({"a": [], "b": []}, kind="line", max_points=60)` | `.append("a", 3)`, `.set_data`, `.kind` |
| `ProgressBar` | `ProgressBar()` | `.progress` (0–1), `.advance(x)` |
| `Log` | `Log(timestamps=True)` | `.info/.ok/.warn/.error(yazı)`, `.write`, `.clear()` |

### Girdi

| Bileşen | Kurulum | Değer / mesaj |
|---|---|---|
| `Button` | `Button("Kaydet", fn_ya_da_eylem, key="ctrl+s", variant="primary")` | `Pressed` |
| `FullscreenButton` | `FullscreenButton()` | tam ekranı açar/kapatır |
| `Input` | `Input(değer, label=, placeholder=, password=, on_submit=)` | `.value`; `Changed`, `Submitted` |
| `TextArea` | `TextArea(rows=6, line_numbers=True, submit_key="ctrl+enter")` | `.text`; `Changed` |
| `Checkbox` | `Checkbox("Sıkıştır", True)` | `.value`; `Changed` |
| `RadioSet` | `RadioSet("Tam", "Artımlı")` | `.value`; `Changed` |
| `Select` | `Select(["Elle", "Her gün"], index=0)` | `.index`, `.value`; `Changed` |
| `Slider` | `Slider(6, min=0, max=9, step=1)` | `.value`; `Changed` |
| `Spinbox` | `Spinbox(12, min=1, max=99, step=1, format=)` | `.value`; `Changed` |
| `OptionList` | `OptionList(["a", "b"], multi=False, rows=8)` | `Selected`, `Submitted` |

### Yapı ve kapsayıcılar

| Bileşen | Kurulum | Not |
|---|---|---|
| `Row`, `Column` | `with ui.Row(gap=1):` | yan yana / alt alta |
| `Spacer` | `Spacer()` | kalan yeri doldurur |
| `Panel` | `with ui.Panel(title="…", info="…"):` | başlıklı çerçeve; içinde odak varsa yanar |
| `Form` | `with ui.Form():` | `label=`'lı alanları hizalar |
| `Tabs`, `Tab` | `with ui.Tabs(): with ui.Tab("Genel"):` | `.active`, `.select(i)`; Ctrl+Tab |
| `Split` | `with ui.Split(sizes=[30, "1fr"]):` | sürüklenebilir ayraç; `direction="column"` |
| `ScrollView` | `ScrollView(içerik, height=12)` | kaydırma; odaktakini görünür kılar |
| `Table` | `Table("Ad", ("Boyut", 10, "right"))` | `.add_row(*hücreler, key=)`, `.clear()`, `RowSelected` |
| `Tree`, `DirectoryTree` | `DirectoryTree(".", patterns=["*.py"])` | `.root.add(…)`, `NodeSelected` |
| `Canvas` | `Canvas(height=10)` | `.line/.rect/.circle/.arc/.polygon/.text/.image`, `.clear()` |
| `MenuBar`, `Menu`, `MenuItem` | yukarıda | |
| `Dialog`, `PromptDialog`, `Popup`, `Screen` | yukarıda | |

Görüntüleri ve tam örnekleri: [bileşen galerisi](bilesenler.md).

---

<a id="20"></a>

## 20. Sık yapılan hatalar

| Belirti | Sebep | Doğrusu |
|---|---|---|
| Pencere donuyor | İşleyicide `time.sleep`, `requests.get`, büyük döngü | `await self.run_worker(fn)` ya da `async` + `await asyncio.sleep` |
| Thread'den güncelleme bazen çöküyor | Worker thread'inde bileşene doğrudan yazmak | `self.call_from_thread(fn, ...)` |
| `await` çalışmıyor / "coroutine never awaited" | `confirm`, `prompt`, `ask_open` senkron işleyiciden | İşleyiciyi `async def` yap |
| Bileşen bütün satırı kaplıyor | Varsayılan genişlik `1fr` | `width=20` ya da `width="auto"` |
| Bir şey kalan yüksekliği doldurmuyor | Yükseklik içerik kadar | `height="1fr"` |
| Köşeli parantezli dosya adı bozuk görünüyor | Markup sanıldı | `ui.escape(ad)` |
| Harf kısayolu çalışmıyor | Odak bir yazı alanında | `ctrl+…` ya da `F` tuşu kullan, ya da `priority=True` |
| `on_click` iki kez geliyor / gelmiyor | Mesaj kabarcıklanıyor ya da iç bileşen durduruyor | `event.stop()`; doğru bileşende yakala |
| Ek penceredeki soru ana pencerede açılıyor | `self.app.confirm` | `self.window.confirm` |
| `query_one` `LookupError` | Bileşen henüz compose edilmedi ya da başka pencerede | `on_mount`'ta ya da sonra sorgula; o pencereden sorgula |
| `bind=` `TypeError` | Değeri olmayan bileşen | Yalnızca girdi bileşenlerine bind ver |
| Tema her makinede aynı, kullanıcının tercihi yok sayılıyor | Kodda `theme=` sabit | Tema vermeyi bırak; tercih ayar dosyasından gelir |
| Testte gerçek dosya diyaloğu bekliyor | — | Sahte sürücüde (run_test) termik gezgini açılır; diyalog beklemez |

---

<a id="21"></a>

## 21. LLM'ler için kurallar

Bu bölüm kod üreten modeller için yazıldı. Kısa, kesin kurallar:

1. **İçe aktarma:** `import termik as ui` (bileşenler) ve/veya `import termik` (akış). Alt modüllerden
   içe aktarma (`from termik.widgets.button import Button`) yapma; her şey üst düzeyde.
2. **Katmanı doğru seç** (bkz. [3](#3)). Düz akışlı script'e sınıf yazma; akış API'si yeter.
3. **Uygulama iskeleti:**
   ```python
   import termik as ui

   class Ad(ui.App):
       TITLE = "…"
       SIZE = (genişlik, yükseklik)

       def compose(self):
           ...
           yield ui.KeyBar()

   if __name__ == "__main__":
       Ad().run()
   ```
4. **Boyutları karakter/satır biriminde ver** (`width=30`, `height=8`, `"1fr"`); piksel kullanma.
5. **Komutları `@ui.action(label, key=...)` ile tanımla**, butonlara ve menülere adını ya da metodunu ver.
   Aynı işi hem tuşa hem butona ayrı ayrı bağlama.
6. **Bloklama yok:** I/O ve uzun hesap `run_worker`'da; arayüz güncellemesi `call_from_thread` ile.
7. **`confirm/alert/prompt/ask_open/ask_save/ask_folder/push_screen_wait/open_window_wait` `await`
   edilir**; çağıran metot `async def` olmalı.
8. **Mesaj metodu adları kesindir:** `on_<bileşen>_<mesaj>` (bkz. tablo [9.1](#9)). Var olmayan ad
   uydurma; emin değilsen bileşenin `on_change=` / ikinci argüman geri çağırmasını kullan.
9. **Değer okumak için `bind=` tercih et**; `query_one(...).value` yalnızca gerektiğinde.
10. **Kullanıcı/dosya kaynaklı yazıyı `ui.escape()` et.**
11. **Renk için `color=` ve `ROLES` kullan**, ögeyi çizen kodda sabit renk yazma; kendi temanı
    `ui.make_theme` + `ui.register_theme` ile yap. **Tema, görünüm, yoğunluğu kodda sabitleme**, kullanıcı istemedikçe. Belirteç adları ve değerleri
    yalnızca [16](#16)'daki tablodakilerdir; olmayan değer `ValueError` verir.
12. **Ek pencerede `self.window`**, uygulama geneli için `self.app`.
13. **Var olmayan API uydurma.** Bu belgede, [galeride](bilesenler.md) ve [tariflerde](tarifler.md)
    olmayan bir parametre gerekiyorsa en yakın genel mekanizmayı kullan: kendi `Widget`'ın (`render`,
    `measure`), `Canvas`, `add_action`, mesaj.
14. **Her uygulamaya `ui.KeyBar()`** koy: kısayolları keşfedilebilir kılar.
15. **Test istenirse** `run_test()` + `Pilot` kullan ([15](#15)); `time.sleep` ile bekleme, `pilot.pause`
    ya da `pilot.wait_until`.
16. Türkçe arayüz metinleri doğaldır; termik Türkçe klavye, sıralama ve aramayı doğru işler.

Doğrulama listesi (kod üretince kendine sor):

- [ ] `compose` bir üreteç mi (`yield`), kapsayıcılar `with` ile mi açıldı?
- [ ] Bloklayan bir çağrı arayüz thread'inde kaldı mı?
- [ ] `await` edilen her çağrının metodu `async def` mi?
- [ ] Kullanılan her bileşen ve parametre bu belgede var mı?
- [ ] `if __name__ == "__main__":` ile mi çalıştırılıyor?

---

<a id="22"></a>

## 22. Sözlük

| Terim | Anlamı |
|---|---|
| **App** | Uygulamanın kökü ve ana penceresi |
| **Window** | Ek işletim sistemi penceresi |
| **Screen** | Pencerede üst üste yığılan katman (ana ekran, diyalog, palet, menü) |
| **Widget / bileşen** | Ağacın her düğümü |
| **compose** | Çocukları üreten metot |
| **region / content** | Bileşenin dikdörtgeni / iç boşluk düşülmüş hali (piksel) |
| **ch / row** | Bir karakterin genişliği / bir satırın yüksekliği (piksel) |
| **fr** | Kalan alandan pay |
| **reactive** | Değişince yeniden çizdiren öznitelik |
| **bind** | Alanı bir özniteliğe iki yönlü bağlama |
| **action** | Tuşa, palete, butona, menüye bağlanan komut |
| **mesaj** | Bileşenden yukarı kabarcıklanan bildirim (`on_…`) |
| **worker** | Ayrı thread'de koşan bloklayan iş |
| **Pilot** | Testte uygulamayı süren nesne |
| **belirteç** | Bir biçim seçeneği (`button = "pill"` gibi) |
| **akış oturumu** | Akış API'sinin penceresi ya da terminali |
