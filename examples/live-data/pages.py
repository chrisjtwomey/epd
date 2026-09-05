"""The two pages this display draws.

A page names the datasets it needs in ``requires``. The pipeline fetches
each named dataset once per regeneration, however many pages asked for it,
and passes them to ``template()`` by name.
"""
from __future__ import annotations

from epd_server import Page

CSS = """
body { margin:0; height:100vh; box-sizing:border-box; padding:60px;
       display:flex; flex-direction:column; font-family:Helvetica, sans-serif; }
h1 { font-size:44px; font-weight:400; margin:0 0 40px; letter-spacing:2px;
     text-transform:uppercase; border-bottom:3px solid #000; padding-bottom:20px; }
.middle { flex:1; display:flex; flex-direction:column;
          align-items:center; justify-content:center; }
.days { flex:1; display:flex; flex-direction:column; justify-content:center; }
.temperature { font-size:230px; font-weight:700; line-height:1; }
.condition { font-size:64px; margin-top:20px; }
.humidity { font-size:40px; color:#555; margin-top:40px; }
.day { display:flex; align-items:baseline; padding:34px 0;
       border-bottom:2px solid #bbb; font-size:46px; }
.day .name { flex:1; font-weight:700; }
.day .text { flex:1; color:#555; }
.day .range { font-variant-numeric:tabular-nums; }
.day .low { color:#777; }
"""


class NowPage(Page):
    """The current temperature, large enough to read across a room."""

    requires = ("conditions",)

    def template(self, **kwargs):
        now = kwargs["conditions"]
        with self.airium.html():
            with self.airium.head():
                self.airium.style(_t=CSS)
            with self.airium.body():
                self.airium.h1(_t="Outside")
                with self.airium.div(klass="middle"):
                    self.airium.div(klass="temperature", _t=f"{now['temperature']}°")
                    self.airium.div(klass="condition", _t=now["text"])
                    self.airium.div(klass="humidity", _t=f"{now['humidity']}% humidity")


class ForecastPage(Page):
    """The days ahead, one row each."""

    requires = ("outlook",)

    def template(self, **kwargs):
        days = kwargs["outlook"]
        with self.airium.html():
            with self.airium.head():
                self.airium.style(_t=CSS)
            with self.airium.body():
                self.airium.h1(_t="Next five days")
                with self.airium.div(klass="days"):
                    for i, day in enumerate(days):
                        with self.airium.div(klass="day"):
                            name = "Today" if i == 0 else day["date"].strftime("%A")
                            self.airium.div(klass="name", _t=name)
                            self.airium.div(klass="text", _t=day["text"])
                            with self.airium.div(klass="range"):
                                self.airium.span(_t=f"{day['high']}°")
                                self.airium.span(klass="low", _t=f" / {day['low']}°")
