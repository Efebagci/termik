"""termik demo: bileşen katmanıyla yazılmış küçük bir yedekleme aracı.

    termik demo                      # ya da: python -m termik demo
    termik demo C:\\Projeler --theme neon --density ferah

Tuşlar: ctrl+p komut paleti · f1 yardım · tab/shift+tab odak · f5 başlat · esc iptal (onay ister)
f2 tema · f4 yoğunluk · ctrl+o kaynak seç · ctrl+q çık. Alttaki kısayol satırındaki öğelere
tıklamak da çalışır.

Dosya ağacı verilen klasörü (verilmezse çalışılan klasörü) gösterir; bir klasörde Enter ya da çift
tık onu kaynak yapar. Dosya yöneticisinden pencereye bırakılan klasör de kaynak olur. Kaynak
gerçekten taranır (ayrı thread'de, pencere donmadan), kopyalama ise taklittir. Görünüm → Ayarlar
ayrı bir pencere açar; oradaki seçimler iki pencereye de hemen yansır. Sistem paneli bu sürecin
kendi CPU kullanımını ve saniyede çizilen kare sayısını gösterir: boştayken ikisi de sıfıra
yakındır, çünkü ekran yalnızca bir şey değişince çizilir.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

import termik as ui

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
IDLE = "[faint]●[/] [dim]başlamaya hazır[/]"
HELP = """[bold accent]termik demo[/] · küçük bir yedekleme aracı

[bold]Genel[/]
  alt+d    Dosya menüsü (alt+g Görünüm, alt+y Yardım) · f10 menü
  ctrl+p   komut paleti: bütün komutlar buradan aranır
  tab      sonraki alan · shift+tab önceki
  f2 / f4  tema / yoğunluk değiştir
  Görünüm → Ayarlar: ayrı pencerede tema, görünüm, yoğunluk
  ctrl+q   çık (yedekleme sürüyorsa sorar; ✕ de öyle)

[bold]Yedekleme[/]
  f5       başlat · esc iptal (onay ister)
  ctrl+o   kaynak klasörü işletim sisteminin diyaloğuyla seç
  Dosya yöneticisinden pencereye bir klasör bırakmak da
  onu kaynak yapar; yol alanlarına bırakılan yol oraya yazılır.
  Kaynak klasör gerçekten taranır; tarama ayrı bir
  thread'de koşar, pencere donmaz. Kopyalama taklittir.

[bold]Dosya ağacı[/]
  ↑ ↓      gez · → aç · ← kapat ya da üste çık
  enter    klasörü kaynak yap (çift tık da olur)
  sağ tık  kaynak ya da hedef yap, yolu panoya kopyala

[bold]Geçmiş tablosu[/]
  Başlığa tıkla: o sütuna göre sırala, tekrar: tersine.
  Enter ya da çift tık satırı günlüğe yazar.

[bold]Günlük ve notlar[/]
  ctrl+tab sekme değiştirir. Notlar çok satırlı bir yazı alanı:
  ctrl+z geri al, ctrl+y yinele, ctrl+a hepsini seç, ctrl+c/x/v pano.
  Dosya → Notları aç / kaydet (ctrl+s) dosya diyaloğunu kullanır.

[bold]Sistem paneli[/]
  Bu sürecin kendi CPU kullanımı ve saniyede çizilen kare
  sayısı. Boştayken ikisi de sıfıra yaklaşır: ekran yalnızca
  bir şey değişince çizilir."""

HISTORY = [  # örnek geçmiş; gerçek yedeklemeler en üste eklenir
    ("[green]✓[/]", "27.10 22:14", "artımlı", "38", "412 KB", "0:42"),
    ("[green]✓[/]", "20.10 22:10", "tam", "612", "2.3 MB", "4:05"),
    ("[yellow]⚠[/]", "13.10 22:12", "artımlı", "55", "601 KB", "0:51"),
    ("[green]✓[/]", "06.10 22:09", "tam", "598", "2.2 MB", "3:58"),
]


def scan(folder: str) -> tuple[int, int]:
    """Bloklayan iş: klasördeki dosyaları say, boyutlarını topla. Ayrı thread'de koşar."""
    count = size = 0
    for root, _dirs, files in os.walk(os.path.expanduser(folder)):
        for name in files:
            count += 1
            try:
                size += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return count, size


class FileTree(ui.DirectoryTree):
    """Dosya ağacı; sağ tık menüsü klasörü kaynak ya da hedef yapar, yolu panoya kopyalar."""

    def context_menu(self, event):
        if event is not None:  # sağ tıklanan satıra geç
            line = self._line_at(event.y)
            if line is not None:
                self.move_cursor(line)
        node = self.cursor_node
        if node is None or not node.data:
            return None
        path, app = node.data, self.app
        folder = os.path.isdir(path)
        return [ui.MenuItem("&Kaynak yap", lambda: app.use_source(path), disabled=not folder),
                ui.MenuItem("&Hedef yap", lambda: app.use_target(path), disabled=not folder),
                None,
                ui.MenuItem("Yolu &panoya kopyala", lambda: app.copy_path(path))]


class EventLog(ui.Log):
    """Günlük; sağ tık menüsünden temizlenir."""

    def context_menu(self, event):
        return [ui.MenuItem("Günlüğü &temizle", self.clear)]


class SettingsWindow(ui.Window):
    """Ayrı pencerede görünüm ayarları: her seçim iki pencereye de hemen yansır; Kaydet ayar
    dosyasına yazar, böylece termik ile açılan her uygulama bu tercihleri kullanır."""

    TITLE = "termik · ayarlar"
    SIZE = (660, 360)
    DIALOGS = {"native": "İşletim sisteminin", "builtin": "termik gezgini"}

    def compose(self):
        app = self.app
        rows = [("Tema", list(ui.THEMES), app.theme.name, "theme"),
                ("Görünüm", list(ui.LOOKS), app.look, "look"),
                ("Yoğunluk", list(ui.DENSITIES), app.density, "density"),
                ("Dosya diyaloğu", list(self.DIALOGS.values()), self.DIALOGS[app.dialogs], "dialogs")]
        with ui.Panel(title="Görünüm", gap=0.5):
            for label, options, current, key in rows:
                with ui.Row(gap=1):
                    yield ui.Label(f"[dim]{label}[/]", width=16)
                    yield ui.Select(options, index=options.index(current), id=key)
            yield ui.Static("[faint]Seçimler bütün pencerelere hemen yansır. Kaydet, ayar dosyasına yazar.[/]")
        with ui.Row(gap=2):
            yield ui.Spacer()
            yield ui.Button("Kaydet", action="save", tooltip=str(ui.settings.config_path()))
            yield ui.Button("Kapat", action="window.close", variant="primary")
        yield ui.Spacer()
        yield ui.KeyBar()

    def on_select_changed(self, event: ui.Select.Changed) -> None:
        key, value, app = event.select.id, event.value, self.app
        if key == "dialogs":
            app.dialogs = next(k for k, v in self.DIALOGS.items() if v == value)
        else:
            app.set_theme(**{"name" if key == "theme" else key: value})

    def sync(self) -> None:
        """Ana penceredeki f2/f4 de buradaki seçimleri güncellesin."""
        app = self.app
        for key, current in (("theme", app.theme.name), ("look", app.look), ("density", app.density)):
            select = self.query_one(f"#{key}", ui.Select)
            select.index = select.options.index(current)

    @ui.action("Ayar dosyasına kaydet", key="ctrl+s", hint="kaydet")
    def save(self) -> None:
        app = self.app
        path = ui.settings.save({"theme": app.theme.name, "look": app.look, "density": app.density,
                                 "dialogs": app.dialogs})
        self.notify(f"kaydedildi: {path.name}", "ok")


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


class BackupApp(ui.App):
    TITLE = "termik · demo"
    SIZE = (1280, 800)
    running = ui.reactive(False)

    def __init__(self, folder: str | os.PathLike | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.folder = Path(folder or os.getcwd()).resolve()
        self._spin = None
        self._frame = 0
        self._done = (0, 0)
        self._cancel = False
        self._cpu_mark = (time.perf_counter(), time.process_time())
        self._frames_mark = 0
        self._settings: SettingsWindow | None = None

    def compose(self):
        yield ui.MenuBar(
            ui.Menu("&Dosya", [ui.MenuItem("Yedeklemeyi &başlat", "start"), ui.MenuItem("İ&ptal", "cancel"), None,
                               ui.MenuItem("&Kaynak klasörü seç…", "choose_source"),
                               ui.MenuItem("&Hedef klasörü seç…", "change_target"), None,
                               ui.MenuItem("Notları &aç…", "open_notes"),
                               ui.MenuItem("Notları &kaydet…", "save_notes"), None,
                               ui.MenuItem("Çı&k", "app.quit")]),
            ui.Menu("&Görünüm", [ui.MenuItem("&Temayı değiştir", "next_theme"),
                                 ui.MenuItem("&Yoğunluğu değiştir", "next_density"), None,
                                 ui.MenuItem("&Ayarlar…", "open_settings"),
                                 ui.MenuItem("&Komut paleti", "app.command_palette")]),
            ui.Menu("&Yardım", [ui.MenuItem("&Yardım", "help")]),
        )
        yield ui.Header("termik", "bileşen katmanı · demo")
        with ui.Row(gap=1):
            yield ui.Panel(FileTree(self.folder, id="tree"), title="Dosyalar", width=32, id="files")
            with ui.Column(gap=0.5):
                with ui.Panel(title="Yedekleme", info="[faint]tam yedek[/]", gap=0.5, id="form"):
                    yield ui.Input(str(self.folder), label="Kaynak klasör", id="src")
                    yield ui.Input("D:\\Yedek", label="Hedef klasör", id="dst")
                    with ui.Column(padding=(0, 0, 0, 1.5)):
                        yield ui.RadioSet("Tam", "Artımlı", label="Mod", id="mode")
                        with ui.Row():
                            yield ui.Label("[dim]Seçenekler[/]", width=12)
                            yield ui.Checkbox("Sıkıştır", True, id="zip")
                            yield ui.Checkbox("Şifrele", id="enc")
                        with ui.Row(gap=1):
                            yield ui.Label("[dim]Düzey[/]", width=11)
                            yield ui.Slider(6, min=0, max=9, id="level",
                                            tooltip="Sıkıştırma düzeyi: 0 en hızlısı, 9 en küçük dosyayı verir")
                        with ui.Row(gap=1):
                            yield ui.Label("[dim]Zamanlama[/]", width=11)
                            yield ui.Select(["Elle", "Her gün 22:00", "Her hafta", "Her ay"], id="schedule")
                        yield ui.Static(IDLE, id="status")
                        yield ui.ProgressBar(id="bar")
                    with ui.Row(gap=2):
                        yield ui.Spacer()
                        yield ui.Button("İptal", action="cancel", tooltip="Süren yedeklemeyi durdurur (onay ister)")
                        yield ui.Button("Başlat ⏎", action="start", variant="primary",
                                        tooltip="Kaynak klasörü tarar, sonra kopyalamayı canlandırır")
                yield ui.Panel(ui.Table(("", 2), ("Tarih", 12), ("Mod", "1fr"), ("Dosya", 6, "right"),
                                        ("Boyut", 9, "right"), ("Süre", 6, "right"), id="history"),
                               title="Geçmiş", info="[faint]başlığa tıkla: sırala[/]")
            with ui.Column(width=46, gap=0.5):
                with ui.Panel(title="Sistem", info="[faint]bu süreç[/]"):
                    yield ui.Sparkline(label="CPU", value_format="{:.0%}", max_value=1.0, id="cpu",
                                       tooltip="Bu sürecin işlemci kullanımı")
                    yield ui.Sparkline(label="FPS", value_format="{:.0f}", color="accent", id="fps",
                                       tooltip="Saniyede çizilen kare: ekran yalnızca bir şey değişince çizilir")
                with ui.Panel(id="notes-panel"):
                    with ui.Tabs(id="side"):
                        with ui.Tab("Günlük"):
                            yield EventLog(timestamps=True, id="log")
                        with ui.Tab("Notlar"):
                            yield ui.TextArea(placeholder="notlar…", line_numbers=True, rows=6, id="notes")
        yield ui.KeyBar()
        yield ui.StatusBar(mode="HAZIR", left="termik demo", id="statusbar")

    @property
    def log(self) -> ui.Log:
        return self.query_one("#log", ui.Log)

    def on_mount(self) -> None:
        history = self.query_one("#history", ui.Table)
        for row in HISTORY:
            history.add_row(*row)
        for field in self.query(ui.Input):  # bırakılan klasör yol alanındakinin yerine geçsin
            field.drop_replaces = True
        self.log.info("hazır: [bold]f5[/] başlat, [bold]ctrl+p[/] komutlar, [bold]tab[/] gezin")
        self._update_statusbar()
        self.set_interval(0.5, self._sample)

    # ── eylemler ──────────────────────────────────────────

    @ui.action("Yedeklemeyi başlat", key="f5", hint="başlat")
    async def start(self) -> None:
        if self.running:  # iptal edilmiş olsa bile önceki iş bitmeden yenisi başlamaz
            return
        bar = self.query_one("#bar", ui.ProgressBar)
        src = self.query_one("#src", ui.Input).value
        mode = self.query_one("#mode", ui.RadioSet).value.lower()
        self._done, self._cancel = (0, 0), False
        self.running = True
        started = time.monotonic()
        status, count, size = "[yellow]⚠[/]", 0, 0
        try:
            bar.progress = 0
            self.log.info(f"taranıyor: [accent]{ui.escape(src)}[/]")
            count, size = await self.run_worker(scan, src)  # pencere donmaz
            if not count:
                self.log.warn("klasörde dosya yok")
                return
            self.log.ok(f"[bold]{count}[/] dosya · {human(size)}")
            delay = min(0.05, 4 / count)
            for i in range(1, count + 1):
                if self._cancel:
                    self.log.warn("yedekleme iptal edildi")
                    return
                await asyncio.sleep(delay)  # gerçek kopyalama yerine
                self._done = (i, count)
                bar.progress = i / count
            status = "[green]✓[/]"
            self.log.ok("yedekleme tamamlandı 🎉")
            self.notify("Yedekleme tamamlandı 🎉", "ok")
        finally:
            seconds = round(time.monotonic() - started)
            self.query_one("#history", ui.Table).add_row(
                status, time.strftime("%d.%m %H:%M"), mode, str(self._done[0]), human(size),
                f"{seconds // 60}:{seconds % 60:02d}", index=0)
            self.running = False

    @ui.action("İptal", key="escape", hint="iptal")
    async def cancel(self) -> None:
        if self.running and await self.confirm("Yedekleme iptal edilsin mi?", title="İptal",
                                               yes="İptal et", no="Devam et"):
            self._cancel = True

    async def can_close(self) -> bool:  # ✕, Alt+F4 ve ctrl+q: yedekleme sürerken önce sor
        if not self.running:
            return True
        if isinstance(self.screen, ui.Dialog):  # soru zaten açık
            return False
        return await self.confirm("Yedekleme sürüyor. Yine de çıkılsın mı?", title="Çıkış", yes="Çık", no="Kal",
                                  default=False)

    @ui.action("Yardım", key="f1", hint="yardım")
    async def help(self) -> None:
        body = ui.ScrollView(ui.Static(HELP), height=14)
        await self.push_screen_wait(ui.Dialog("Yardım", body, buttons=[("Kapat", None)], width=64))

    @ui.action("Kaynak klasörü seç…", key="ctrl+o", hint="kaynak")
    async def choose_source(self) -> None:
        folder = await self.ask_folder("Yedeklenecek klasör", folder=self.query_one("#src", ui.Input).value)
        if folder:
            self.use_source(str(folder))

    @ui.action("Hedef klasörü seç…")
    async def change_target(self) -> None:
        dst = self.query_one("#dst", ui.Input).value
        folder = await self.ask_folder("Yedeklerin yazılacağı klasör", folder=dst if os.path.isdir(dst) else None)
        if folder:
            self.use_target(str(folder))

    @ui.action("Notları aç…")
    async def open_notes(self) -> None:
        path = await self.ask_open("Notları aç", filetypes=[("Metin", "*.txt *.md"), ("Tümü", "*.*")])
        if path is None:
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.notify(f"açılamadı: {exc.strerror or exc}", "err")
            return
        self.query_one("#notes", ui.TextArea).text = text
        self.query_one("#side", ui.Tabs).active = 1
        self.log.info(f"notlar: [accent]{ui.escape(path.name)}[/] açıldı")

    @ui.action("Notları kaydet…", key="ctrl+s", hint="kaydet")
    async def save_notes(self) -> None:
        path = await self.ask_save("Notları kaydet", name="notlar.txt",
                                   filetypes=[("Metin", "*.txt"), ("Markdown", "*.md")])
        if path is None:
            return
        try:
            path.write_text(self.query_one("#notes", ui.TextArea).text, encoding="utf-8")
        except OSError as exc:
            self.notify(f"kaydedilemedi: {exc.strerror or exc}", "err")
            return
        self.notify(f"kaydedildi: {path.name}", "ok")

    @ui.action("Ayarlar…")
    def open_settings(self) -> None:
        """Ayarlar ayrı pencerede; açıksa öne gelir."""
        if self._settings is not None and self._settings.is_open:
            self._settings.native.focus()
            return
        self._settings = self.open_window(SettingsWindow())

    @ui.action("Temayı değiştir", key="f2", hint="tema")
    def next_theme(self) -> None:
        names = list(ui.THEMES)
        self.set_theme(names[(names.index(self.theme.name) + 1) % len(names)])

    @ui.action("Yoğunluğu değiştir", key="f4", hint="yoğunluk")
    def next_density(self) -> None:
        names = list(ui.DENSITIES)
        self.set_theme(density=names[(names.index(self.density) + 1) % len(names)])

    def set_theme(self, name=None, *, density=None, **tokens) -> None:
        super().set_theme(name, density=density, **tokens)
        self._update_statusbar()  # paletteki "Tema: …" komutları da buradan geçer
        if self._settings is not None and self._settings.is_open:
            self._settings.sync()

    # ── durum ─────────────────────────────────────────────

    def watch_running(self, running: bool) -> None:
        statusbar = self.query_one("#statusbar", ui.StatusBar)
        statusbar.mode, statusbar.mode_color = ("ÇALIŞIYOR", "green") if running else ("HAZIR", "accent")
        if running:
            self._spin = self.set_interval(1 / 12, self._spin_status)
        else:
            if self._spin is not None:
                self._spin.stop()
            done, total = self._done
            text = f"[green]✓[/] {done} / {total} dosya" if total and done == total else IDLE
            self.query_one("#status", ui.Static).update(text)

    def _spin_status(self) -> None:
        self._frame += 1
        done, total = self._done
        detail = f"{done} / {total} dosya" if total else "taranıyor…"
        self.query_one("#status", ui.Static).update(
            f"[accent]{SPINNER[self._frame % len(SPINNER)]}[/] kopyalanıyor · [dim]{detail}[/]")

    def _sample(self) -> None:
        """Bu sürecin CPU kullanımı ve saniyede çizilen kare sayısı."""
        now, cpu = time.perf_counter(), time.process_time()
        then, cpu_then = self._cpu_mark
        self._cpu_mark = (now, cpu)
        elapsed = max(1e-6, now - then)
        self.query_one("#cpu", ui.Sparkline).append(min(1.0, (cpu - cpu_then) / elapsed))
        self.query_one("#fps", ui.Sparkline).append((self.frame_count - self._frames_mark) / elapsed)
        self._frames_mark = self.frame_count

    def _update_statusbar(self) -> None:
        if self.is_mounted:
            self.query_one("#statusbar", ui.StatusBar).right = f"[accent]{self.theme.name}[/] [faint]· {self.density}[/]"

    # ── bileşen mesajları ─────────────────────────────────

    def on_tree_node_selected(self, event: ui.Tree.NodeSelected) -> None:
        path = event.node.data
        if path and os.path.isdir(path):
            self.use_source(path)

    def _set_input(self, selector: str, path: str, what: str) -> None:
        field = self.query_one(selector, ui.Input)
        field.value = path
        field.cursor_position = len(path)
        self.log.info(f"{what}: [accent]{ui.escape(path)}[/]")

    def use_source(self, path: str) -> None:
        self._set_input("#src", path, "kaynak")

    def use_target(self, path: str) -> None:
        self._set_input("#dst", path, "hedef")

    def copy_path(self, path: str) -> None:
        ui.clipboard.put_text(path)
        self.notify("yol panoya kopyalandı", "ok")

    def on_drop(self, event: ui.Drop) -> None:
        """Pencereye bırakılan klasör (dosyaysa onun klasörü) kaynak olur."""
        if event.paths:
            path = event.paths[0]
            self.use_source(str(path if path.is_dir() else path.parent))
            self.notify("bırakılan klasör kaynak yapıldı", "ok")

    def on_table_row_selected(self, event: ui.Table.RowSelected) -> None:
        cells = event.table.get_row(event.key)
        self.log.info(f"geçmiş: {cells[1]} · {cells[2]} · {cells[4]}")

    def on_input_submitted(self, event: ui.Input.Submitted) -> None:
        self.log.info(f"{event.input.id}: {ui.escape(event.value)}")

    def on_radio_set_changed(self, event: ui.RadioSet.Changed) -> None:
        self.query_one("#form", ui.Panel).info = f"[faint]{event.value.lower()} yedek[/]"

    def on_checkbox_changed(self, event: ui.Checkbox.Changed) -> None:
        self.log.info(f"{event.checkbox.label}: {'açık' if event.value else 'kapalı'}")
        if event.checkbox.id == "zip":  # sıkıştırma kapalıyken düzey seçilmez
            self.query_one("#level", ui.Slider).disabled = not event.value

    def on_select_changed(self, event: ui.Select.Changed) -> None:
        self.log.info(f"zamanlama: {ui.escape(event.value)}")

    def on_text_area_changed(self, event: ui.TextArea.Changed) -> None:
        lines = event.text.count("\n") + 1
        self.query_one("#notes-panel", ui.Panel).info = f"[faint]{lines} satır · {len(event.text)} karakter[/]"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="termik demo", description="termik bileşen katmanı demosu")
    ap.add_argument("klasor", nargs="?", help="ağaçta gösterilecek klasör (varsayılan: çalışılan klasör)")
    # verilmezse ayar dosyasındaki ya da ortam değişkenindeki tercih geçerli olur
    ap.add_argument("--theme", choices=list(ui.THEMES))
    ap.add_argument("--density", choices=list(ui.DENSITIES))
    args = ap.parse_args(argv)
    BackupApp(args.klasor, theme=args.theme, density=args.density).run()


if __name__ == "__main__":
    main()
