from datetime import datetime
from zoneinfo import ZoneInfo

from epd_server import DisplayServer, Page, StaticSource

CSS = """
body { margin:0; height:100vh; display:flex; flex-direction:column;
       align-items:center; justify-content:center; font-family:Helvetica, sans-serif; }
.time { font-size:180px; font-weight:700; }
.date { font-size:48px; }
"""


class ClockPage(Page):
    def template(self, **kwargs):
        now = datetime.now()
        with self.airium.html():
            with self.airium.head():
                self.airium.style(_t=CSS)
            with self.airium.body():
                self.airium.div(klass="time", _t=now.strftime("%H:%M"))
                self.airium.div(klass="date", _t=now.strftime("%A %d %B"))


DisplayServer(
    pages=[ClockPage("clock", width=825, height=1200,
                     html_dir="build", png_dir="build")],
    source=StaticSource(),
    schedule=[("08:00:00", "clock.png"), ("20:00:00", "clock.png")],
    tz=ZoneInfo("Europe/Dublin"),
).run()
