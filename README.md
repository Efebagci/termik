# termik

[![PyPI](https://img.shields.io/pypi/v/termik)](https://pypi.org/project/termik/)
[![Python](https://img.shields.io/pypi/pyversions/termik)](https://pypi.org/project/termik/)
[![Lisans: MIT](https://img.shields.io/pypi/l/termik)](https://github.com/Efebagci/termik/blob/main/LICENSE)

CLI'ın görünüşü ve hissi, GUI'ın kullanım rahatlığıyla. pygame-ce üzerinde çalışan bir Python
arayüz kütüphanesi.

**Belgeler:** [efebagci.github.io/termik](https://efebagci.github.io/termik/) · [bileşen galerisi](https://efebagci.github.io/termik/bilesenler.html) ·
[tarifler](https://efebagci.github.io/termik/tarifler.html) · [kaynak kod](https://github.com/Efebagci/termik)

![demo](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/demo-calisiyor.png)

> **Durum: v0.10.0, [PyPI'de yayında](https://pypi.org/project/termik/).** İki katman da hazır. Akış API'si (`ask`,
> `choose`, `confirm`, `track`…) script'lere birkaç satırla pencere verir; pencere açılamazsa aynı
> script terminalde çalışır. Görünüm tercihleri bir ayar dosyasında tutulur.
> Bileşen katmanında çekirdek (ağaç, flex yerleşim, odak, olay yönlendirme, `@action`, reaktif
> öznitelikler, asyncio + thread işçileri), Ctrl+P komut paleti, modal diyaloglar, menü çubuğu ve
> sağ tık menüleri, ipuçları ve 28 bileşen var; üç sütunlu bir demo uygulama örnek. Bir uygulama
> birden çok pencere açabilir; dosya seçmek için işletim sisteminin kendi diyaloğu açılır, dosya
> yöneticisinden sürükleyip bırakmak çalışır, pencere simgesi temanın rengini alır. Kısa yazım:
> etiketli formlar (`ui.Form` + `label=`), alanı özniteliğe bağlama (`bind=`), sınıf yazmadan
> uygulama (`@app.compose`, `@app.action`), `termik yeni` iskeleti ve kaydettikçe yeniden açan
> `termik çalıştır --izle`. Çizgi, alan ve çubuk grafikleri (`ui.Chart`, akışta `termik.chart`), kapanınca
> pencereyi ve değerleri hatırlayan durum kaydı (`SAVE_STATE = True`).

![komut paleti](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/demo-palet.png)

## Kurulum

```bash
pip install termik
```

Paket [PyPI'de](https://pypi.org/project/termik/). Python 3.11 ya da daha yenisi gerekir; pygame-ce
kendiliğinden kurulur. Yeni sürüme geçmek için `pip install -U termik`. Kurulunca `termik` komutu
gelir:

```bash
termik akis                      # akış API'si örneği: script'e pencere
termik demo                      # bileşen katmanı demosu: çok panelli uygulama
termik yeni araç --tur arac      # proje iskeleti: uygulama (varsayılan) · arac · betik
termik çalıştır araç/araç.py --izle   # kaydettikçe pencere yeniden açılır
termik ayarlar                   # görünüm tercihlerini seç ve kaydet
```

pygame-ce kurulamayan bir ortamda (bazı sunucular) akış API'si terminalde çalışmayı sürdürür.

## Hızlı başlangıç

Script'ler için akış API'si: `input()` ve `print()` kadar kısa.

```python
import termik

ad = termik.ask("Adın?")
mod = termik.choose("Mod", ["Tam", "Artımlı"])
if termik.confirm(f"{mod} yedek alınsın mı?"):
    for dosya in termik.track(dosyalar, "Kopyalanıyor", unit="dosya"):
        kopyala(dosya)
termik.ok(f"Bitti, [bold]{ad}[/]!")
```

Çok panelli uygulamalar için bileşen katmanı:

```python
import termik as ui

class Merhaba(ui.App):
    ad = ui.reactive("")   # bind="ad": alan değişince bu da, bu değişince alan da

    def compose(self):
        with ui.Panel(title="Selam"):
            with ui.Form():
                yield ui.Input(label="Adın", bind="ad")
            yield ui.Button("Selamla", self.selamla, key="f5", variant="primary")
        yield ui.KeyBar()   # f5 Selamla · tab sonraki · ctrl+q çık

    def selamla(self):
        self.notify(f"Merhaba {ui.escape(self.ad)}!", "ok")

Merhaba().run()
```

Küçük bir araç için sınıf da gerekmez:

```python
app = ui.App(title="Dönüştürücü")
app.yol = ""

@app.compose
def arayuz():
    with ui.Form():
        yield ui.Input(label="Dosya", bind="yol")
    yield ui.Button("Dönüştür", donustur, key="f5")

@app.action("Dosya seç", key="ctrl+o")
async def sec():
    yol = await app.ask_open()
    if yol:
        app.yol = str(yol)   # alan da güncellenir

def donustur():
    app.notify(f"{app.yol} dönüştürülüyor")

app.run()
```

## Akış API'si

Pencere bir terminal oturumu gibi alt alta akan bir dökümdür. Cevaplanan soru tek satırlık özete
döner, özetlerin cevapları hizalı bir sütun oluşturur. Etkin soru hep en altta ve odaktadır.

![akış: seçim](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/akis-secim.png)

| Fonksiyon | İş |
|---|---|
| `print(*nesneler, sep=, end=, markup=True)` | `print()` gibi; yazılar markup'tır, diğer nesneler olduğu gibi yazılır |
| `ok`, `info`, `warn`, `error` | `✓ • ⚠ ✗` simgeli satır |
| `rule("Başlık")` | `── Başlık ──────` ayraç |
| `table(satırlar, headers=None)` | Hizalı tablo; sözlük listesinde başlıklar anahtarlardan gelir, sayılar sağa yaslanır |
| `chart(veri, **seçenekler)` | Grafik (`ui.Chart`'ın seçenekleri); canlı güncellemek için tutamak döndürür: `cpu.append("cpu", 42)`. Terminalde ▁▃▇ bloklarıyla |
| `show(bileşen)` | Bileşen katmanından bir bileşeni dökümde gösterir; tutamağın metotları pencerenin thread'inde çalışır |
| `ask(soru, default=, type=, validate=, password=)` | Yazı sorar. `type=int` çevirir, `validate` denetler; hatalı girişte soru hatayla tekrarlanır. `default` alanı dolu ve seçili getirir, türü de ondan çıkar (`default=8080` → `int`) |
| `ask_path(soru, kind="dir", must_exist=True)` | `Path` döndürür. Tab tamamlar (birden çok aday varsa aralarında döner), Ctrl+O klasör ağacını açar; `~`, ortam değişkenleri ve kopyalanan yolların tırnakları işlenir |
| `choose(soru, seçenekler, default=)` | Liste, `(etiket, değer)` çiftleri ya da sözlük alır, değeri döndürür; yazdıkça bulanık süzülür (`artim` → "Artımlı") |
| `choose_many(soru, seçenekler, default=, min=, max=)` | Çoklu seçim: space işaretler, ctrl+a görünenlerin hepsini işaretler ya da kaldırır |
| `confirm(soru, default=True, yes=, no=)` | `bool` döndürür; ←/→ ve Enter, ya da baş harfler (`e`/`h`) |
| `form(başlık, **alanlar)` | Birkaç alanı tek seferde sorar, sözlük döndürür (aşağıda) |
| `track(yinelenebilir, etiket, total=, unit=)` | Döngüyü ilerleme çubuğuyla sarar; `break` ile biterse satır "durduruldu" olur |
| `progress(etiket, total=, unit=)` | Elle ilerletilen çubuk: `with … as p: p.advance(n)`; `unit="B"` boyutları KB/MB gösterir |
| `spinner(etiket)` | `with` bloğu süresince dönen işaret ve geçen süre; `sp.update("12 MB alındı")` açıklama ekler |
| `setup(title=, theme=, look=, density=, keep_open=, mode=, capture=, …)` | İlk çağrıdan önce: pencere başlığı, görünüm ve biçim belirteçleri (bileşen katmanındakilerle aynı), yakalama |
| `restyle(theme=, look=, density=, …)` | Görünümü çalışırken değiştirir |

![akış: ilerleme](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/akis-ilerleme.png)

**Nasıl çalışır:**

- Pencere ilk çağrıda **ayrı bir thread'de** açılır; script kendi thread'inde sürer. Script uzun
  bir iş yaparken (indirme, kopyalama, `time.sleep`) pencere donmaz: spinner döner, döküm kayar.
  `track` döngünün her adımında mesaj göndermez, pencere sayacı kendi hızında okur.
- **Pencereyi kapatmak script'te `KeyboardInterrupt` doğurur**, terminalde Ctrl+C'ye basmak gibi.
  Script o an kendi işindeyse (ör. `time.sleep(30)`) de kesilir.
- **Script bitince pencere açık kalır**, durum satırı "bitti" der; ⏎ ya da esc kapatır.
  `setup(keep_open=False)` pencereyi kendiliğinden kapatır.
- **Yakalanmayan hata pencerede gösterilir** ve pencere her durumda açık kalır. Bu, `pythonw` ile
  çift tıklanıp konsolsuz açılan script'ler için önemli.
- Pencerede ctrl+p komut paleti (tema, yoğunluk), ctrl+shift+c dökümü panoya kopyalar. Dökümde
  en çok 2000 çıktı satırı tutulur.

![akış: gözat](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/akis-gozat.png)

**Form.** Birkaç alanı tek ekranda sorar; değerin türü alanı belirler:

```python
ayar = termik.form("Bağlantı",
    sunucu="localhost",        # yazı alanı, dolu gelir
    port=8080,                 # sayı: cevap int'e çevrilir
    mod=["Tam", "Artımlı"],    # seçim: kısa liste radyo, uzun liste süzülebilir liste
    sıkıştır=True,             # onay kutusu
    parola=termik.Password)    # gizli yazı
ayar["port"]                   # → 8080
```

`str`, `int`, `float` ya da `Path` türü boş bir alan açar. Etiketler adlardan çıkar
(`hedef_klasör` → "Hedef klasör", `isim` → "İsim"). Etiket, doğrulama ya da seçimde varsayılan
için `termik.Field(8080, label="Port numarası", validate=…)`, `termik.Field("Artımlı",
choices=[…])`. Tab alanlar arasında gezer, ⏎ sonraki alana geçer (sonuncusunda gönderir), ctrl+⏎
hemen gönderir. Hatalı alanların etiketi kırmızıya döner, odak ilkine gider ve form yeniden sorulur.
Cevaplanınca başlığın altında alan başına bir özet satırı kalır. Terminalde alanlar sırayla sorulur.

![akış: form](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/akis-form.png)

**Script'in kendi `print()` ve `input()`'u.** Pencere açıkken (varsayılan olarak) script'in
`print()`'leri, `sys.stdout` ve `sys.stderr`'e yazılanlar dökümde de görünür; konsol varsa oraya da
yazılmayı sürdürür. `stderr` kırmızıdır, `\r` ile yerinde güncellenen satırlar (tqdm gibi) dökümde de
yerinde güncellenir, renk kaçışları atılır. logging kayıtları simgeli satır olur (`⚠ disk dolu`);
kendi `basicConfig` ayarın konsolda geçerliliğini korur. `input()` ve `getpass.getpass()`
pencerede soru olarak sorulur. Böylece eski bir script'e pencere vermek için tek satır yeter:

```python
import termik
termik.setup()             # pencere ilk yazıda açılır

ad = input("Adın: ")       # → pencerede soru
print(f"Merhaba {ad}")     # → dökümde satır
```

Pencere kapanınca her şey eski haline döner; `setup(capture=False)` yakalamayı kapatır.

**Terminal kipi.** Pencere açılamıyorsa (pygame-ce kurulu değil, Linux'ta görüntü sunucusu yok)
aynı script terminalde çalışır. macOS pencereyi ana thread'de istediği için orada da şimdilik terminal
kipi kullanılır. `TERMIK_MODE=terminal` ya da `TERMIK_MODE=window` kipi zorlar. Etkileşimli bir
terminalde renkler gelir, ilerleme satırları yerinde güncellenir, cevaplanan soru özete döner.
Boruya ya da dosyaya giden çıktı düz yazıdır. Seçimler numara ya da yazıyla yapılır; çoklu seçimde
`1,3`, `2-4` ve `*` geçerlidir. Girdi kapalıysa (stdin yok) soru `EOFError` verir; cevapsız soru
sessizce varsayılana düşmez.

```
termik terminal kipi · deneme
── Sorular ──────────────────────────────────
✓ Port  8080
✓ Mod   Artımlı
✓ Uzantılar  .py, .txt
✓ Devam edilsin mi?  Evet
── İş ───────────────────────────────────────
✓ Bağlanılıyor       el sıkışma · 1,8 sn
✓ Kopyalanıyor       60 dosya · 2,4 sn
```

Akış API'si bileşen katmanının bileşenlerini de kullanabilir. `termik.show(bileşen)` bileşeni dökümde
gösterir ve bir tutamak döndürür; tutamağın metotları pencerenin kendi thread'inde çalışır, script'ten
güvenle güncellenir. `form()`'a bir alan olarak doğrudan bileşen verilebilir; değeri bileşenden okunur:

```python
tablo = termik.show(ui.Table("Dosya", "Boyut"))
for f in dosyalar:
    tablo.add_row(f.name, boyut(f))

ayar = termik.form("Ayarlar", düzey=ui.Slider(6, max=9), zaman=ui.Select(["Elle", "Her gün"]), ad="Efe")
```

Terminal kipinde gösterilen bileşenin o anki hali yazıya dökülür (tablo ve yazı; öbürleri için kısa bir
not); formdaki bileşen türüne göre sayı, seçim ya da onay olarak sorulur, sınırları bileşende uygulanır.

Modül fonksiyonları ilk kullanımda kurulan varsayılan oturuma gider. Ayrı bir oturum
`termik.flow.Session(...)` ile kurulur ve aynı metotları taşır; testlerde
`Session(mode="window", headless=True)` pencereyi görünmez açar.

![akış: bitti](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/akis-bitti.png)

## Temel kavramlar

- **Bileşen ağacı.** `compose()` içinde `yield` ile bileşen, `with ui.Row():` ile iç içe kapsayıcı
  açılır. `query("#id")`, `query_one(".sınıf", Tür)` ile bulunur; `mount()` / `remove()` ile çalışırken
  değişir.
- **Yerleşim (flex).** `Row` yan yana, `Column` ve varsayılan dizim alt alta. Boyutlar CLI biriminde:
  `width=30` 30 karakter, `height=2` 2 satır; ayrıca `"12px"`, `"40%"`, `"2fr"`, `"auto"`. `gap`,
  `padding`, `min_width`… da aynı birimlerle. Kapsayıcılar içlerinde büyüyen bir bileşen (ör. `Log`)
  varsa büyür, yoksa içerikleri kadar yer kaplar. `Spacer` kalan yeri doldurur.
- **Odak ve klavye.** Tab/Shift+Tab odaklanabilir bileşenler arasında gezer, tıklamak odaklar; içinde
  odak olan `Panel`'in çerçevesi yanar. Tuş önce odaktaki bileşene gider (`on_key`), sonra ebeveynlere
  kabarcıklanır. Yazı alanındayken harf tuşları kısayol tetiklemez; Türkçe klavyedeki AltGr (`@`)
  kısayol sanılmaz.
- **`@action`.** Bir metodu komut yapar: tuşa bağlanır, `KeyBar`'da görünür (tıklanabilir), butona
  `action="ad"` ile verilir. Odaktaki bileşenden uygulamaya kadar en içteki kazanır;
  `priority=True` olanlar (ör. `ctrl+q`) her yerde önce gelir.
- **Komut paleti.** `ctrl+p` bağlamdaki bütün `@action`'ları (`palette=False` olanlar hariç) ve
  `App.get_commands()`'ın verdiklerini listeler; varsayılan olarak tema ve yoğunluk seçimi de oradadır.
  Bulanık arama Türkçe harfleri gevşek eşler: `baslat` yazınca "Başlat" bulunur.
- **Reaktif öznitelikler.** `progress = ui.reactive(0.0)`; değer değişince bileşen kendiliğinden
  yeniden çizilir, varsa `watch_progress(old, new)` çağrılır. Boyutu etkileyenler için `layout=True`.
- **Mesajlar.** Bileşenler mesaj gönderir ve bunlar yukarı kabarcıklanır: `Button.Pressed` →
  `on_button_pressed`, `Input.Submitted` → `on_input_submitted`. `event.stop()` yayılmayı durdurur.
- **async ve işçiler.** İşleyiciler ve eylemler `async def` olabilir; ağ çağrıları pencereyi dondurmadan
  `await` edilir. Bloklayan işler `await self.run_worker(fn, ...)` ile ayrı thread'de koşar;
  başka thread'den arayüz `call_from_thread()` ile güncellenir. `set_interval()` / `set_timer()`
  zamanlayıcıları bileşen kaldırılınca durur.
- **Diyaloglar.** `await self.confirm("İptal edilsin mi?")`, `await self.alert("Bitti")`,
  `await self.prompt("Yeni ad", value="rapor.md")`. Kendi diyaloğun için `Dialog(başlık, içerik,
  buttons=[("Vazgeç", False), ("Sil", True)])` ve `await self.push_screen_wait(diyalog)`; ekranlar
  `dismiss(sonuç)` ile kapanır, odak önceki yerine döner. Diyalog açıkken arka plandaki işler sürer.
- **Menüler.** `MenuBar(Menu("&Dosya", [MenuItem("Kaydet", "save"), None, …]))`: öğeler bir eylem adı
  ya da fonksiyonla verilir, eylemin kısayolu menüde kendiliğinden yazar; bulunamayan eylem soluk
  görünür. Alt+harf ya da F10 menüyü açar, açıkken ←/→ komşu menüye geçer. Bir bileşenin
  `context_menu(event)` metodu öğe döndürürse sağ tık (ya da Shift+F10) o menüyü açar;
  `app.open_menu(öğeler, (x, y))` istenen yerde açar.
- **İpuçları.** Her bileşen `tooltip="…"` alır; fare üstünde 0,6 sn durunca baloncuk çıkar.
- **Bildirim ve hatalar.** `notify("…", "ok")` sağ üstte kısa süreli bildirim gösterir. İşleyicideki
  bir hata uygulamayı düşürmez: konsola iz, ekrana bildirim olarak düşer.
- **Çizim.** Ekran yalnızca bir şey değişince (ya da animasyon varken) çizilir; boşta döngü yalnızca
  olayları yoklar.

## Kısa yazım

Aşağıdakilerin hepsi var olan yapının üstünde ince bir katman: kısa yazım arka planda aynı bileşenleri
kurar, ayrıntılı yol (`query_one`, `on_..._changed`, sınıflar, `@action`) olduğu gibi çalışır.

- **Etiketli form.** `ui.Form` içinde her bileşen `label=` alır; Form etiketleri en uzun etikete göre
  hizalı bir sütunda solda çizer (`form_label = "top"` ile alanın üstünde). `Input` ve `RadioSet`
  Form içinde etiketlerini kendileri çizmez, tek satır olur. Kendi yazısı `label` olan bileşenler
  (`Button`, `Checkbox`) bir `Row`'a konup `ui.Row(label="Seçenekler")` ile etiketlenir. Etiketsiz
  bileşenler (not, ilerleme çubuğu) bütün genişliği kaplar; odaktaki alanın etiketi parlar.
- **Değer bağlama (`bind=`).** `ui.Input(bind="kaynak")` alanı en yakın atadaki (çoğunlukla pencere)
  `kaynak` özniteliğine bağlar. Öznitelik varsa değeri alana gelir, yoksa alanın değeriyle oluşur.
  Alan değişince öznitelik, öznitelik değişince alan güncellenir: pencerenin özniteliklerinde her
  zaman, ara bileşenlerde öznitelik `reactive` ise. Sayı tutan özniteliğe bağlı yazı alanının değeri
  sayıya çevrilir (çevrilemezse öznitelik eskisinde kalır). Bağlanabilenler: `Input`, `TextArea`,
  `Checkbox`, `RadioSet`, `Select`, `Slider`, `Spinbox`.
- **Sınıf yazmadan.** `app = ui.App(...)`; arayüz `@app.compose`, komutlar `@app.action("Ad", key=…)`
  (kısayol satırında ve palette görünür), mesajlar `@app.on(ui.Button.Pressed)` ya da
  `@app.on("mount")` ile. Fonksiyonlar argümansız ya da uygulamayı alan biçimde yazılabilir.
  Çalışırken eylem eklemek için her bileşende `add_action(ad, fonksiyon, key=…)` var.
- **Kısa düğme.** `ui.Button("Kaydet", self.kaydet, key="ctrl+s")`: ikinci argüman fonksiyon ya da
  eylem adı; `key=` düğmenin ekranında odak nerede olursa olsun çalışır ve kısayol satırında görünür
  (üstte bir diyalog açıkken çalışmaz).
- **Proje iskeleti.** `termik yeni AD` menüsüz ama formlu, bağlamalı, kısayollu bir uygulama ve
  testini; `--tur arac` sınıfsız küçük bir araç ve testini; `--tur betik` akış betiği kurar.
  Üretilen testler pencere açmadan çalışır.
- **Kaydettikçe yeniden aç.** `termik çalıştır dosya.py --izle` klasördeki `.py` dosyaları değişince
  programı yeniden başlatır; pencere bir önceki yerinde ve boyutunda açılır. Pencere kapatılınca
  izleme de biter; program hatayla biterse düzeltilip kaydedilmesi beklenir.
- **Durum kaydı.** Sınıfta `SAVE_STATE = True` (ya da `App(save_state=True)`): kapanırken pencerenin yeri ve
  boyutu, kimliği (`id=`) olan `Split`'lerin oranları, `Tabs`'ların açık sekmesi ve `bind=` ile bağlı
  alanların değerleri saklanır, açılınca geri gelir. `persist=False` bir alanı dışarıda tutar; parola
  alanları kendiliğinden tutulmaz. Dosya ayar klasöründe `durum/<ad>.json` (`app.state_path`);
  `app.write_state()` hemen yazar, `app.forget_state()` siler. Saklanan pencere yeri artık hiçbir
  ekranda değilse (monitör çıkarılmış) yok sayılır.
- **Editör desteği.** Açık API'nin tamamında tip ipuçları var (`SizeSpec`, `ColorSpec`, `ImageSource`
  gibi adlarla); VS Code ve PyCharm'da tamamlama ve parametre önerileri çalışır.

![sınıf yazmadan kurulmuş araç: Form, bind ve düğme kısayolu](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/kolay-arac.png)

## Grafikler

```python
cpu = ui.Chart({"cpu": [], "bellek": []}, title="Kullanım %", y_min=0, y_max=100, max_points=60)
cpu.append("cpu", 42)                                  # canlı veri: en yenisi sağda
ui.Chart({"Ocak": 12, "Şubat": 30}, kind="bar")         # kategoriler
ui.Chart([3, 5, 4, 8], kind="area", x=["pzt", "sal", "çar", "per"])
```

Eksen değerleri yuvarlak adımlarla seçilir, sayılar Türkçe biçimde yazılır (`12.400`, `0,25`). Birden çok
seri ya da adlı seriler varken gösterge başlığın sağında durur; fare grafiğin üstündeyken en yakın
noktanın bütün serilerdeki değerleri bir kutuda görünür. Akış API'sinde `termik.chart(...)` aynı
grafiği dökümde gösterir ve script'ten güncellenen bir tutamak döndürür; terminalde blok grafik basar
(pygame kurulu olmasa da).

![grafikler: çizgi, alan, çubuk, yan yana çubuk](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/grafik.png)

![aynı grafikler braille biçiminde](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/grafik-braille.png)

## Pencereler ve sistem

```python
class Ayarlar(ui.Window):
    TITLE = "Ayarlar"
    SIZE = (560, 360)

    def compose(self):
        yield ui.Select(list(ui.THEMES), id="tema")
        yield ui.Button("Kapat", action="window.close")

    def on_select_changed(self, event):
        self.app.set_theme(event.value)          # bütün pencerelere yansır

class Uygulama(ui.App):
    @ui.action("Ayarlar…", key="f9")
    def ayarlar(self):
        self.open_window(Ayarlar())              # modal=True: kapanana kadar bu pencere bekler

    @ui.action("Aç…", key="ctrl+o")
    async def ac(self):
        yol = await self.ask_open("Resim seç", filetypes=[("Resimler", "*.png *.jpg")])
        if yol:
            self.notify(f"açıldı: {yol.name}")

    def on_drop(self, event):                    # dosya yöneticisinden bırakılanlar
        self.notify(f"{len(event.paths)} dosya bırakıldı")

    async def can_close(self):                   # ✕, Alt+F4 ve ctrl+q önce bunu sorar
        return await self.confirm("Çıkılsın mı?")
```

- **Pencereler.** `App` ana penceredir; ek pencere `Window`'dan türetilir ve `open_window()` ile
  açılır (açanın ortasına yerleşir). Her pencerenin kendi ekran yığını, odağı, faresi, ipucu ve
  bildirimleri vardır; tema, olay döngüsü, zamanlayıcılar ve işçiler ortaktır. Bileşen kendi
  penceresine `self.window` ile ulaşır (`self.window.confirm(…)`, `.notify(…)`); `self.app` her
  yerde uygulamadır. `await self.open_window_wait(pencere)` pencere `close(sonuç)` ile kapanınca
  sonucu döndürür. `modal=True` ile açılan pencere kapanana kadar öncekiler girdi almaz (Windows'ta
  işletim sistemi de kilitler: kilitli pencereye tıklamak modal olanı öne getirir).
- **Kapatma.** ✕, Alt+F4 ve Ctrl+W (ana pencerede Ctrl+Q) `can_close()`'u sorar; `False` dönerse
  pencere açık kalır, `async` olabilir. `close()` ise sormadan kapatır. Ana pencere kapanınca
  uygulama da kapanır. Eylem adlarında `window.` öneki bileşenin penceresini gösterir
  (`action="window.close"`); önceksiz adlar ek pencerede bulunamazsa uygulamada aranır.
- **Dosya diyalogları.** `await self.ask_open(…)`, `ask_open(multiple=True)`, `ask_save(name=…)`,
  `ask_folder()` `pathlib.Path` (vazgeçilirse `None`) döndürür. Varsayılan olarak işletim sisteminin
  diyaloğu açılır: Windows'ta Common Item Dialog, macOS'ta Finder diyaloğu, Linux'ta zenity ya da
  kdialog. Diyalog ayrı thread'de açılır; açıkken pencere çizilmeye devam eder ama girdi almaz.
  `dialogs = "builtin"` ayarı (ya da yerel diyaloğun bulunmadığı bir sistem) termik'in klavyeyle
  gezilen gezginini açar; akış API'sinde `ask_path`'in Ctrl+O'su da aynı ayarı izler.
- **Sürükle-bırak.** Dosya yöneticisinden bırakılan dosyalar farenin altındaki bileşene `Drop`
  mesajı olarak gider (`event.paths`, yazı bırakıldıysa `event.text`) ve yukarı kabarcıklanır.
  `Input` ve `TextArea` yolu bırakılan yere yazar (`Input.drop_replaces = True` ise yazının yerine);
  akış penceresinde bırakılan dosya cevap bekleyen yol sorusuna gider.
- **Pencere simgesi.** Verilmezse koyu zeminde temanın vurgu renginde `❯` ve bir imleç bloğu çizilir;
  tema değişince rengi de değişir. Windows'ta başlık çubuğu ve görev çubuğu boyutları ayrı ayrı
  çizilir. Kendi simgen için `App(icon="simge.png")`, sınıfta `ICON = …` ya da `window.set_icon(…)`.

![ayarlar penceresi](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/pencere-ayarlar.png)

![termik gezgini: kaydet](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/pencere-gezgin.png)

![pencere simgesi, her temada](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/pencere-simgeleri.png)

## Bileşenler

| Bileşen | İş |
|---|---|
| `Static`, `Label` | Markup yazı; `Static` genişliğe göre kaydırır, `Label` `…` ile kısalır |
| `Button` | `[ Tamam ]`; ikinci argüman fonksiyon ya da eylem adı, `key=` kısayolu, `on_press=`, `variant="primary"`; Enter/Space/tık |
| `Input` | Tek satır yazı: blok imleç, seçim, pano, kelime kelime gezinme; `label=` ile etiketli alan |
| `TextArea` | Çok satırlı yazı: kelime sınırından kaydırma, seçim, pano, geri al/yinele, girinti koruma, satır numaraları, yazdıkça uzama (`max_rows`), gönderme tuşu (`submit_key="ctrl+enter"`) |
| `Checkbox`, `RadioSet` | `[✓]` ve `(•)`; tık, Space, ←/→ |
| `Select` | Açılır seçim kutusu: ⏎ ya da tık altında süzülebilir listeyi açar, ←/→ açmadan değiştirir; genişliği en uzun seçeneğe göre sabit |
| `Slider` | Kaydırıcı: `min`, `max`, `step`; ←/→ adım, PgUp/PgDn onda bir, Home/End uçlar, fareyle sürükleme ve tekerlek |
| `Tabs`, `Tab` | Sekmeli kapsayıcı: `with ui.Tabs(): with ui.Tab("Genel"): …`; ctrl+tab ya da başlığa tık; odak gizli sekmedeki bir alana geçerse o sekme açılır |
| `OptionList` | Süzülebilir seçenek listesi: yazdıkça bulanık süzer (Türkçe harfler gevşek eşleşir), `rows=` satır gösterir; `multi=True` ile çoklu seçim. `Highlighted`, `Selected`, `Submitted` mesajları |
| `ProgressBar` | Temadaki çubuk biçimiyle ilerleme + yüzde |
| `Log` | Kayan kayıt: `info/ok/warn/error`, saat damgası, tekerlek ve tuşlarla gezinme, canlı takip |
| `Tree`, `DirectoryTree` | Açılır kapanır ağaç: `├─ └─` dalları, ←/→ aç-kapa, tembel yükleme (`load_children`); klasör ağacı alt klasörleri ilk açılışta okur |
| `Table` | Sabit başlıklı tablo: satır imleci, başlığa tıklayınca doğal sıralama, çift tık/Enter ile seçim |
| `Sparkline` | Akan değerler için mini grafik; etiket ve son değer |
| `Chart` | Çizgi, alan ve çubuk grafiği: veri liste, `{ad: liste}` ya da `{etiket: sayı}`; eksenler yuvarlak adımlarla, noktalı ızgara, gösterge, fareyle en yakın noktanın değerleri; `append`/`max_points` ile canlı veri; `y_min`, `y_max`, `y_format`, `x=` etiketleri |
| `Image` | Resim (dosya yolu ya da `pygame.Surface`): `fit="contain"` sığdırır, `cover` kırparak doldurur, `stretch` esnetir, `none` asıl boyut; ince çerçeve, `caption=`; açılamayan resim yerinde hata yazar; `source=` ile değişir |
| `Canvas` | Serbest çizim: `line`, `lines`, `rect`, `circle`, `arc`, `polygon`, `text`, `image` çağrıları saklanır ve kendiliğinden yeniden çizilir; birim karakter/satır (`px=True` piksel); renkler tema adlarıyla; `remove(numara)`, `clear()`; `Canvas.Clicked`, `Canvas.Dragged` |
| `Spinbox` | Sayı alanı `[ − 12 + ]`: ↑/↓ adım, PgUp/PgDn on adım, Home/End sınırlar, yazınca baştan yazılır (⏎ onaylar, Esc vazgeçer, virgül de ondalık), ± tık ve tekerlek; `min`, `max`, `step`, `format` |
| `Split` | Bölünebilir kapsayıcı: `with ui.Split(sizes=[32, "1fr"]):`; ayraç sürüklenir (oranlar korunur), çift tık başa döndürür, Alt+Shift+ok klavyeyle kaydırır; `direction="column"` alt alta; `fractions` / `set_fractions()` |
| `Panel` | Başlıklı çerçeve; içindekileri alt alta dizer; `floating=True` yüzen kutular için |
| `ScrollView` | Kaydırılabilir kapsayıcı: tekerlek, PgUp/PgDn, sürüklenebilir çubuk; odaktaki bileşeni görünür alana getirir |
| `Dialog`, `PromptDialog` | Modal kutular; çoğunlukla `App.confirm/alert/prompt` ile kullanılır |
| `Form` | Etiketli alanlar: çocukların `label=`'larını hizalı bir sütunda çizer (yukarıda **Kısa yazım**) |
| `Window` | Ek işletim sistemi penceresi (yukarıda **Pencereler ve sistem**) |
| `FileBrowser` | termik'in dosya gezgini: açma, çoklu seçim (space işaretler), klasör, kaydetme (ad alanı, uzantı süzgeçten, üzerine yazma onayı); yerel diyalog yoksa açılır |
| `MenuBar`, `Menu`, `MenuItem` | Menü çubuğu ve menüler (yukarıda **Menüler**) |
| `Popup` | Bir bileşene ya da noktaya bağlı yüzen kutu: arka planı karartmaz, dışarı tık ya da Esc kapatır; açılır liste ve menülerin temeli |
| `Header`, `KeyBar`, `StatusBar` | Logo ve saat; geçerli kısayollar (tıklanabilir); mod rozetli durum çubuğu |
| `Row`, `Column`, `Spacer` | Yerleşim |

![menü](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/bilesen-menu.png)

![açılır seçim ve kaydırıcı](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/bilesen-select.png)

![sağ tık menüsü](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/bilesen-sagtik.png)

![modern görünümde menü](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/bilesen-modern-menu2.png)

![resim, sayı alanı, Canvas ve bölünebilir paneller](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/bilesen-kalan.png)

![aynı ekran: resim terminal blokları, sağda oklu sayı alanı, gizli ayraç](https://raw.githubusercontent.com/Efebagci/termik/main/docs/ekran/bilesen-kalan-bloklar.png)

## Kararlar

**28.10.2026 · ilk tur:** serbest yerleşim, CLI teması (ölçü birimleri karakter ve satır); katmanlı
API (bileşen çekirdeği + üstünde akış API'si); backend pygame-ce; hedef script'lere hızlı arayüz ve
çok panelli uygulamalar.

**Görünüm turu:** daha terminal yönü (keskin köşe, düz panel, `[ köşeli ]` buton, ters renkli
seçim); JetBrains Mono'nun ligatürsüz NL kesimi pakete gömülü; yoğunluk, başlık ve bileşen biçimleri
ayarlanabilir (varsayılan `rahat` yoğunluk ve ters renkli başlık etiketi).

**Bileşen çekirdeği turu:** asyncio döngüsü + thread işçileri; reaktif öznitelikler; kısayollar ve
komutlar `@action` ile tek yerden; bu turun hedefi çekirdek + temel bileşenler + demo.

**Palet turu:** Ctrl+P komut paleti `@action`'lardan beslenir; `Tree`, `Table`, `Sparkline` eklendi;
demo vitrin gibi üç sütuna çıktı.

**Kalan bileşenler turu:** `ScrollView`, `await` ile kullanılan modal diyaloglar, `TextArea`.
Seçenekler ayarlanabilir: Tab varsayılan olarak odağı taşır (`tab_behavior="indent"` girinti
ekler); kaydırma, satır numarası ve gönderme tuşu birer seçenek.

**Akış API'si turu:** pencere ayrı thread'de, script kendi thread'inde (uzun işte pencere donmaz,
pencereyi kapatmak `KeyboardInterrupt`); cevaplanan soru tek satırlık özete döner; pencere
açılamazsa terminale düşülür.

**Paketleme ve ayarlar turu:** `pip install termik` (setuptools, MIT lisansı; gömülü font OFL'li);
`termik` komutu (`demo`, `akis`, `ayarlar`); tercihler TOML ayar dosyasında ve `TERMIK_*` ortam
değişkenlerinde, öncelik kod > ortam > dosya > varsayılan. Elle çizilmiş vitrin prototipi emekliye
ayrıldı; git geçmişinde duruyor.

**Akışı genişletme turu:** yakalama varsayılan olarak açık (`print`, `stderr` ve logging dökümde,
`input()` pencerede); `form()` anahtar kelimelerle yazılır, alanın türü değerden çıkar;
`OptionList` bileşen katmanına açıldı.

**Eksik bileşenler turu:** `Select`, `Tabs`, `Slider`, menü çubuğu ve sağ tık menüleri, ipuçları.
Görünüşleri üç yeni belirteçle seçilir: sekmeler ters renkli (`tabs`), kaydırıcı çubuk (`slider`),
seçim kutusu köşeli (`select`); modern görünümde alt çizgili, ince çizgi, alt çizgili. Menüler,
açılır liste ve bağlam menüsü arka planı karartmayan ortak bir yüzen kutu (`Popup`) kullanır.

**Çoklu pencere turu:** pencereye ait her şey (ekranlar, odak, fare, ipucu, bildirim, çizim) yeni
`Window` sınıfına taşındı, `App` ana pencere oldu; böylece eski kod değişmeden çalışıyor. Dosya
seçiminde varsayılan işletim sisteminin diyaloğu, `dialogs = "builtin"` ile termik'in gezgini.
Varsayılan pencere simgesi komut istemi (`❯` ve imleç, temanın vurgu renginde); uygulama kendi
simgesini verebilir. Pencereler pygame-ce'nin `Window` sınıfıyla açılıyor, ana pencere de.

**Son bileşenler turu:** `Image`, `Canvas`, `Spinbox`, `Split`. Resim varsayılan olarak gerçek
pikselleriyle yumuşak ölçeklenir (`image`: `pixel` iri pikseller, `blocks` terminal gibi ▀ yarım
bloklar); sayı alanı açılır seçimle aynı köşeli dilde (`spin`); ayraç ince çizgi ve ⋮ tutamak
(`split`). Canvas'ta çağrılar bir çizim listesinde saklanır, koordinatlar karakter ve satır birimi.

**29.10.2026 · ilk yayın:** 0.8.0 PyPI'ye yüklendi; `pip install termik` çalışıyor.

**Grafik, belgeler ve durum kaydı turu:** grafikler varsayılan olarak yumuşak kenarlı çizgiler ve
terminal havasında eksenlerle (`chart`: `braille`, `blocks` da seçilebilir); veri katmanı (`plot.py`)
pygame istemez, terminal de onu kullanır. Durum kaydı isteğe bağlı (`SAVE_STATE = True`) ve hepsini
saklar. Belgeler `docs/` içinde Markdown; GitHub Pages ile `efebagci.github.io/termik/` adresinde
(o adresin kökündeki kişisel site etkilenmez). Galeri `docs/galeri.py` ile koddan üretilir; README
görselleri PyPI'de de görünsün diye tam adresle bağlı.

**Kısa yazım turu:** özelleştirmeden ödün vermeden daha az kod. Etiketli formlar `ui.Form` +
`label=` (etiketler solda hizalı; `form_label` ile üstte); değer bağlama `bind=` ile pencerenin
özniteliğine; sınıfsız uygulama dekoratörlerle (`@app.compose`, `@app.action`, `@app.on`); düğmeye
fonksiyon ve kısayol doğrudan; akışta `show()` ve `form()`'da bileşen; `termik yeni` ve
`termik çalıştır --izle`; açık API'de tam tip ipuçları. Demo formu bu yazımla yeniden yazıldı.

## Görünüm ayarları

Renk teması (`THEMES`) ile biçim belirteçleri birbirinden bağımsızdır; `App(theme=…, density=…,
title=…)` ya da çalışırken `app.set_theme(…)` ile verilir. Verilmeyenler kullanıcının
tercihlerinden gelir (aşağıda **Ayarlar**).

| Belirteç | Değerler | Varsayılan |
|---|---|---|
| `density` (küme) | `sıkı` · `dengeli` · `rahat` · `ferah` | `rahat` |
| `line_height` | fontun doğal satır yüksekliğinin katı (terminallerdeki gibi) | `1.15` |
| `pad_x`, `pad_y` | panel iç boşluğu: karakter / satır cinsinden | `1.75`, `0.65` |
| `title` | `inverse` ters renkli etiket · `inline` `┌─ Başlık ─┐` · `tab` `┤ Başlık ├` | `inverse` |
| `focus` | `color` vurgu rengi · `double` odakta çift çizgi | `color` |
| `button` | `bracket` `[ Tamam ]` · `angle` `< Tamam >` · `solid` dolu blok · `pill` hap | `bracket` |
| `bar` | `block` `█▊░` · `segment` `▰▱` · `line` `━` · `ascii` `[##--]` | `block` |
| `selection` | `inverse` tam satır ters renk · `pointer` `❯` + hafif zemin | `inverse` |
| `radio` | `paren` `(•)` · `dot` `●` | `paren` |
| `shadow` | `hard` kaydırılmış koyu blok · `soft` bulanık · `none` | `hard` |
| `tabs` | `inverse` ters renkli · `folder` klasör sekmesi · `underline` alt çizgi · `bracket` `[ Genel ]` | `inverse` |
| `slider` | `bar` ilerleme çubuğu gibi (`bar` belirtecini izler) · `line` ince iz, yuvarlak tutamak · `value` `◂ 60 ▸` | `bar` |
| `select` | `bracket` `[ Artımlı ▾ ]` · `arrows` `◂ Artımlı ▸` · `underline` altı çizili | `bracket` |
| `image` | `smooth` yumuşak ölçek · `pixel` karakter ızgarasına oturan iri pikseller · `blocks` hücre başına iki piksel (▀) | `smooth` |
| `spin` | `bracket` `[ − 12 + ]` · `arrows` `◂ 12 ▸` · `stacked` alan ve sağda ▴▾ | `bracket` (modern: `stacked`) |
| `split` | `line` ince çizgi ve ⋮ tutamak · `bar` dolu sütun · `hidden` yalnızca fare gelince | `line` |
| `form_label` | `left` etiketler solda, en uzun etikete göre hizalı · `top` alanın üstünde | `left` |
| `chart` | `smooth` yumuşak kenarlı çizgiler · `braille` ⣀⡠ nokta ızgarası · `blocks` ▁▃▇ blokları | `smooth` |
| `radius`, `panel_fill` | köşe yarıçapı; panellerin kart gibi dolu olup olmadığı | `0`, `False` |

`LOOKS` içinde iki hazır küme var: `terminal` (yukarıdaki varsayılanlar) ve `modern` (ilk
prototipin yuvarlak, kart zeminli hali).

## Ayarlar

Görünüm ve kip tercihleri koda dokunmadan seçilir. Öncelik sırası: kodda verilen değer > ortam
değişkeni > ayar dosyası > varsayılan. `termik ayarlar` tercihleri pencerede sorar; seçtiğin tema
hemen uygulanır, onaylarsan dosyaya yazılır.

Ayar dosyası TOML'dur: Windows'ta `%APPDATA%\termik\ayarlar.toml`, diğerlerinde
`~/.config/termik/ayarlar.toml` (`XDG_CONFIG_HOME` varsa onun altında). `TERMIK_CONFIG` başka bir
dosyayı gösterir; `termik ayarlar --yol` yerini yazar.

```toml
theme = "orman"
look = "terminal"
density = "dengeli"
mode = "auto"              # akış API'si: auto · window · terminal
dialogs = "native"         # dosya diyalogları: native (işletim sisteminin) · builtin (termik'in)
font = "C:/Fonts/Iosevka.ttf"
bar = "segment"            # yukarıdaki bütün biçim belirteçleri
accent = "#ff8800"         # renkler de ezilebilir
```

Ortam değişkenleri aynı adların `TERMIK_` önekli büyük harflisidir: `TERMIK_THEME=neon`,
`TERMIK_DENSITY=ferah`, `TERMIK_BAR=ascii`, `TERMIK_MODE=terminal`, `TERMIK_DIALOGS=builtin`,
`TERMIK_FONT=…`. Geçersiz bir
değer programı durdurmaz: bir kez uyarı yazılır, değer yok sayılır. Kodda verilen yanlış bir ad
(`App(theme="yok")`) ise `ValueError` verir. Akış API'sinde `termik.restyle(theme="neon")`
görünümü çalışırken değiştirir.

## Geliştirme

```bash
pip install -e .
termik demo C:\Projeler --theme neon --density ferah
python tests/test_core.py
python tests/test_widgets.py
python tests/test_textarea.py
python tests/test_dialog_scroll.py
python tests/test_flow.py
python tests/test_settings.py
python tests/test_components.py
python tests/test_windows.py
python tests/test_extras.py
python tests/test_easy.py
python tests/test_chart_state.py
python docs/galeri.py          # bileşen galerisini (görüntüler + docs/bilesenler.md) yeniden üret
```

`termik akis` (kaynağı `termik/demo/akis.py`) akış API'siyle yazılmış bir yedekleme betiği: klasör
sorar (Ctrl+O dosya diyaloğunu açar, klasörü pencereye bırakmak da olur), mod ve dosya türlerini seçtirir, klasörü tarar, onay alıp
kopyalamayı canlandırır (dosyalara dokunmaz), en büyük dosyaları tabloyla özetler. PowerShell'de
terminal kipi: `$env:TERMIK_MODE="terminal"; termik akis`.

Demo (`termik demo`, kaynağı `termik/demo/uygulama.py`): menü çubuğu (`alt+d`, `f10`), `ctrl+p` komut paleti, `f1` yardım, `f5` yedeklemeyi başlatır (kaynak klasör gerçekten, ayrı
thread'de taranır; kopyalama taklittir), `esc` iptal (onay ister), `f2` tema, `f4` yoğunluk, `tab`
odak, `ctrl+o` kaynak klasörü işletim sisteminin diyaloğuyla seçer, `ctrl+q` ya da ✕ çıkış
(yedekleme sürüyorsa sorar). Dosya yöneticisinden pencereye bırakılan klasör kaynak olur. Görünüm →
Ayarlar ayrı bir pencere açar: tema, görünüm, yoğunluk ve dosya diyaloğu seçimi iki pencereye de
hemen yansır, Kaydet ayar dosyasına yazar. Notlar paneli çok satırlı bir yazı alanıdır; Dosya
menüsünden bir dosyaya açılır ya da kaydedilir (`ctrl+s`). Üç sütun bir `Split`: aradaki ayraçlar
sürüklenir. Ağaçta bir resmin üstüne gelmek onu Önizleme sekmesinde gösterir; Sistem panelindeki
halka (Canvas) hedef diskin doluluğu; formdaki "Sakla" bir sayı alanıdır.
Dosya ağacı verilen klasörü (verilmezse çalışılan klasörü) gösterir; bir klasörde Enter ya da çift
tık onu kaynak yapar, sağ tık menüsü kaynak ya da hedef yapar ve yolu panoya kopyalar. Biten yedekleme
geçmiş tablosuna eklenir. Formda sıkıştırma düzeyi bir kaydırıcı ("Sıkıştır" kapalıyken devre dışı),
zamanlama bir açılır seçimdir; günlük ve notlar sekmelerdedir, butonlarda ipucu vardır. Sistem paneli demonun kendi CPU
kullanımını ve saniyede çizilen kare sayısını gösterir: boştayken ikisi de sıfıra yaklaşır.

Testler pencere açmadan (SDL'in sahte sürücüsüyle) `app.run_test()` ve `Pilot` ile sürülür:

```python
async with app.run_test() as pilot:
    await pilot.press("tab", "f5")
    await pilot.type("merhaba")
    await pilot.click("#tamam")
    pilot.snapshot("ekran.png")
```

Testler kullanıcının ayar dosyasından ve `TERMIK_*` değişkenlerinden yalıtılır (`tests/_ortam.py`).

Yeni sürüm yayınlamak (`pip install build twine` gerekir): önce `termik/__init__.py` içindeki
`__version__` artırılır (PyPI aynı sürümü ikinci kez kabul etmez), sonra paket derlenip yüklenir.
Kullanıcı adı `__token__`, şifre yalnızca `termik` projesine yetkili bir PyPI API token'ıdır.

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

## Yapı

| Dosya | İçerik |
|---|---|
| `pyproject.toml`, `LICENSE` | Paket tanımı (setuptools); MIT lisansı |
| `termik/__main__.py`, `settings.py` | `termik` komutu (`demo`, `akis`, `yeni`, `çalıştır`, `ayarlar`); ayar dosyası ve `TERMIK_*` ortam değişkenleri |
| `termik/plot.py` | Grafik verisi (pygame'siz): seriler, eksen adımları, Türkçe sayı biçimi, terminal için blok grafik |
| `docs/` | Belge sitesi (GitHub Pages): giriş, bileşen galerisi (`galeri.py` üretir), tarifler; README görselleri |
| `termik/dev.py` | Proje iskeletleri (`termik yeni`) ve kaydettikçe yeniden başlatan izleyici (`termik çalıştır --izle`) |
| `termik/flow/` | Akış API'si: `Session`, `form`, `Field` ve modül fonksiyonları (`__init__.py`); pencere arka ucu (`window.py`: döküm, soru ve form bileşenleri, thread köprüsü); terminal arka ucu (`terminal.py`: ANSI, yerinde güncellenen satırlar); `print`/`input`/logging yakalama (`capture.py`); ortak ilerleme kaydı ve biçimleme (`common.py`) |
| `termik/app.py` | `Window`: ekranlar, odak, fare ve klavye, ipucu, bildirimler, çizim; `App` (ana pencere): asyncio döngüsü, olayların pencerelere dağıtılması, modal kilit, zamanlayıcılar, işçiler; `Pilot` |
| `termik/filedialog.py`, `system.py`, `icon.py` | Dosya diyalogları (Windows'ta COM ile Common Item Dialog, macOS'ta osascript, Linux'ta zenity/kdialog, yoksa `FileBrowser`); işletim sistemi yardımcıları (ekran ölçeği, iki boyutlu pencere simgesi, modal kilit, farenin masaüstü konumu); varsayılan pencere simgesi |
| `termik/widget.py` | `Widget`: ağaç, compose, sorgular, mesajlar, `@action`, flex yerleşim; `Row`, `Column`, `Spacer` |
| `termik/widgets/` | Hazır bileşenler |
| `termik/palette.py`, `fuzzy.py` | Komut paleti (`CommandPalette`, `Command`); Türkçe gevşek bulanık arama |
| `termik/dialog.py`, `clipboard.py` | Modal diyaloglar; sistem panosu (pencere yoksa uygulama içi yedek) |
| `termik/popup.py`, `menu.py` | Yüzen kutu (`Popup`); menü çubuğu, açılır ve sağ tık menüleri |
| `termik/events.py`, `keys.py`, `reactive.py`, `layout.py` | Mesajlar ve olaylar; tuş adları; `reactive`; boyut çözme ve dağıtma |
| `termik/theme.py`, `markup.py`, `fonts.py`, `text.py`, `draw.py` | Tema ve biçim belirteçleri; markup ayrıştırma (pygame'siz, terminal kipi de kullanır); font yığını; yazı ölçme ve çizme; çizim ilkelleri (`Painter`) |
| `termik/fonts/` | JetBrains Mono NL Regular/Bold ve `OFL.txt` |
| `termik/demo/` | `termik akis` (akış API'siyle yazılmış betik) ve `termik demo` (bileşenlerle yazılmış uygulama) |
| `docs/ekran/` | README'deki ekran görüntüleri |
| `tests/` | 128 test: çekirdek (18), bileşenler (12), TextArea (12), diyalog/ScrollView (9), menü/seçim/sekme/kaydırıcı/ipucu (9), pencereler/sürükle-bırak/dosya diyalogları (9), akış API'si (28; beşi ayrı süreçte, gerçek ana thread'le), resim/Canvas/sayı alanı/Split (5), kısa yazım (8), grafik ve durum kaydı (7), ayarlar ve komut satırı (11) |

## Öğrendiklerimiz

- **Renkli emoji çalışıyor** (SDL_ttf 2.24 + Segoe UI Emoji), ama Segoe UI Symbol bazı emojilerin tek
  renkli kopyalarını taşıyor. U+1F000 üstündeki resimli emojiler önce renkli fonttan alınıyor.
- **Eksik glif tespiti** `pygame.freetype` ile yapılıyor; `pygame.font` eksik glifi bildirmiyor.
  Akraba simgeler (`✓ ✗ ⚠`, `● ○`, braille) grup halinde aynı fonttan alınıyor.
- **Ligatürler kapatılamıyor** (pygame-ce'de HarfBuzz özellik arayüzü yok); bu yüzden NL kesimi.
- **Sentetik kalınlık eş genişliği bozuyor**; gerçek `-Bold` dosyası varsa o kullanılıyor.
- **Satır yüksekliği fonta göre tanımlanmalı**, font boyutuna göre değil.
- **Türkçe:** AltGr, Windows'ta Ctrl+Alt olarak geliyor (`altgr+q` diye adlandırılıyor); Python'da
  `"i".upper()` `"I"` veriyor, `"İ"` değil; aramada `ı/i`, `ş/s` gevşetilerek eşleşiyor.
- **Uzun işte "çalışıyor" bayrağı iş gerçekten bitince düşmeli**; yoksa iptalden hemen sonra yeniden
  başlatınca iki görev aynı anda koşar.
- **SDL penceresi Windows'ta ana thread dışında da açılıyor**; yeter ki olaylar pencereyi açan
  thread'de işlensin. macOS bunu istemiyor.
- **Başka thread'den ana thread'i kesmek:** Windows'ta `_thread.interrupt_main()` yalnızca bayrağı
  kaldırıyor, `time.sleep`'i uyandırmıyor. `signal.raise_signal(SIGINT)` C düzeyindeki işleyiciyi
  çalıştırıp beklemeyi de kesiyor (0,3 sn'de). POSIX'te karşılığı `signal.pthread_kill(ana, SIGINT)`.
- **Script'in bittiği** pencere thread'inden `threading.main_thread().is_alive()` ile görülüyor.
  Yorumlayıcı kapanırken önce excepthook çalışıyor, sonra ana thread bitti sayılıyor, sonra daemon
  olmayan thread'ler bekleniyor; pencere bu arada hatayı gösterip açık kalabiliyor.
- **pygame süreç başına tek pencere tutuyor:** kapanan pencerenin geç gelen `pygame.quit()`'i
  yenisini öldürüyor; kapatırken thread'in bitmesini beklemek gerekiyor.
- **Eş genişlikli fontta genişlik çarpmayla:** satır kaydırma her kelimeyi ayrı ölçüyordu. Birincil
  font eş genişlikliyse (açılışta ölçülerek doğrulanıyor) genişlik harf sayısı × karakter genişliği;
  2000 satırı yeni genişlikte kaydırmak 520 ms'den 58 ms'ye indi.
- **`logging.warning()` kendiliğinden `basicConfig()` çağırıyor:** kök logger'da işleyici yoksa
  `stderr`'e yazan bir işleyici kuruluyor, `logging.lastResort` hiç devreye girmiyor. Yakalama bu
  yüzden `std` akışlara yazan işleyicilerin yanına pencereye yazan bir eş takıyor.
- **Windows'ta boruya ya da dosyaya giden çıktı cp1254 kodlanıyor:** `✓ ─ ›` gibi simgeler yazılamıyor.
  Terminal kipi bu durumda ASCII karşılıklarına (`+ - >`) düşüyor; konsolda sorun yok.
- **Ana pencere de `pygame.Window` ile açılıyor:** `display.set_mode` ile açılanı `Window`'a çeviren
  `from_display_module` kullanımdan kalkmış. Olaylar `event.window` ile hangi pencereden geldiğini
  söylüyor; söylemeyen olay klavye ya da fare odağındaki pencereye gidiyor.
- **SDL son pencereye kapat denince kendiliğinden QUIT yolluyor;** `SDL_QUIT_ON_LAST_WINDOW_CLOSE=0`
  ile kapatıp kapatmama kararı `can_close()`'a bırakıldı.
- **`SDL_SetWindowModalFor` yalnızca X11'de var.** Windows'ta modal pencere için sahibi
  `EnableWindow` ile kilitleniyor ve modal pencere ona sahiplendiriliyor. Sahibi, modal pencere yok
  edilmeden önce açılmalı; yoksa Windows odağı başka bir uygulamaya veriyor.
- **Windows başlık çubuğu ve görev çubuğu için farklı boyutta simge istiyor;** SDL tek resmi
  küçültüyor, kenarlar tırtıklanıyor. İki boyut ayrı ayrı çizilip `WM_SETICON` ile veriliyor.
- **Pencere gizli açılıp ilk kare çizilince gösteriliyor:** açılışta boş beyaz pencere görünmüyor.
- **SDL 2'nin bırakma olayında konum yok;** farenin masaüstündeki konumundan pencerenin konumu
  çıkarılarak bırakılan yer bulunuyor.
- **Common Item Dialog ctypes ile COM üzerinden açılıyor:** ayrı thread'de, kendi tek thread'li
  dairesinde. `Show(sahip)` sahibini kendisi kilitliyor; bu arada pygame döngüsü çizmeye devam ediyor.
- **Sınıf gövdesinde `action` adlı bir metot, ondan sonraki `@action` süslemelerini gölgeler:** gövdede
  ad önce sınıfın kendi isim alanında aranır. `Window.action` bu yüzden sınıfın en sonunda tanımlı.
- **Düz özniteliği izlemek için tanımlayıcı gerekmiyor:** `Window.__setattr__` atamadan sonra o ada
  bağlı alanlara haber veriyor; böylece `app.yol = …` gibi tanımsız öznitelikler de iki yönlü.

## Sıradaki adımlar

1. **Grafik eklemeleri:** pasta/halka grafik, iki y ekseni, yakınlaştırma ve kaydırma, grafiği PNG
   olarak kaydetme.
2. **Belgelerde arama** ve her sayfanın İngilizcesi.
3. **macOS kipi** (pencere ana thread'de, script ayrı thread'de) ve Linux denemeleri; yerel dosya
   diyaloğunun macOS (osascript) ve Linux (zenity, kdialog) yolları henüz yalnızca yazıldı, denenmedi.
4. **Akışta küçük eklemeler:** çok satırlı yazı soran `ask_text`, "devam etmek için ⏎" diyen `pause`,
   soru sormadan dosya diyaloğu açan bir kısayol.
