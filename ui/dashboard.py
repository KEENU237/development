"""
NSE F&O Enterprise Trading System — Rich Terminal UI  v2.0
=============================================================
Live OI Chain · Greeks · Max Pain · UOA · PCR · IV Rank ·
OI Buildup · IV Skew · Theta Clock · Smart Money · Portfolio Risk

NEW in v2.0
  • In-place refresh using Rich Live (no full screen flicker)
  • BANKNIFTY / FINNIFTY use correct monthly/weekly expiry
  • IV Rank & IV Percentile panel
  • OI Buildup signals (Fresh Long / Short / Unwinding)
  • IV Skew gauge (fear index)
  • Theta Clock — daily decay Rs value
  • Smart Money Panel — large OI jumps
  • PCR trend arrow (rising / falling)
  • [I] Iron Condor quick-build added to menu
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Dict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Rich ──────────────────────────────────────────────────────────────────────
from rich.console import Console, Group
from rich.table   import Table
from rich.panel   import Panel
from rich.columns import Columns
from rich.text    import Text
from rich.rule    import Rule
from rich.live    import Live
from rich.layout  import Layout
from rich         import box
from rich.prompt  import Prompt, Confirm

# ── System ────────────────────────────────────────────────────────────────────
from config.settings import (
    KITE_API_KEY, KITE_API_SECRET, UOA_CONFIG, LOG_DIR, DATA_DIR
)
from core.kite_manager   import KiteManager
from core.uoa_scanner    import UOAScanner
from core.pcr_tracker    import PCRTracker
from core.risk_manager   import RiskManager
from core.max_pain       import MaxPainCalculator
from core.market_utils   import (
    get_market_status, get_nearest_expiry,
    get_lot_size, format_number, format_inr, calculate_order_cost
)
from core.greeks         import calc_greeks, tte_years
from strategies.basket_builder import BasketOrderBuilder
from strategies.straddle       import StraddleBuilder
from data.trade_log            import TradeLog
from reports.pnl_report        import PnLReportGenerator

os.makedirs(LOG_DIR,  exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers= [logging.FileHandler(os.path.join(LOG_DIR, "system.log"))],
)
logger  = logging.getLogger(__name__)
console = Console(highlight=False)

# ── Colour palette ────────────────────────────────────────────────────────────
_C = {
    "header":  "bold bright_white on dark_blue",
    "atm":     "bold yellow on dark_orange3",
    "up":      "green",   "dn":   "red",
    "neutral": "yellow",  "dim":  "dim white",
    "fire":    "bold bright_red",
    "bull":    "bright_green", "bear": "bright_red",
    "breach":  "bold bright_red on dark_red",
    "warn":    "bold yellow",
}
_ZONE_COLOR = {
    "EXTREME_BULL":"bright_green","BULLISH":"green",
    "NEUTRAL":"yellow","BEARISH":"red","EXTREME_BEAR":"bright_red",
}
_STATUS_COLOR = {
    "OPEN":"green","PRE-OPEN":"yellow","CLOSED":"red","WEEKEND":"dim",
}
SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY"]


# ═══════════════════════════════════════════════════════════════════════════════
# Data cache — refreshed in background thread
# ═══════════════════════════════════════════════════════════════════════════════
class DataCache:
    """Thread-safe cache for all live market data."""
    def __init__(self):
        self._lock   = threading.Lock()
        self._data   = {}

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def update(self, d: dict):
        with self._lock:
            self._data.update(d)


# ═══════════════════════════════════════════════════════════════════════════════
class Dashboard:
    AUTO_REFRESH = 60   # seconds

    def __init__(self, kite, uoa, pcr, basket, straddle,
                 risk, mp, trade_log, expiry):
        self.kite     = kite
        self.uoa      = uoa
        self.pcr      = pcr
        self.basket   = basket
        self.straddle = straddle
        self.risk     = risk
        self.mp       = mp
        self.log      = trade_log
        self.reporter = PnLReportGenerator(trade_log)
        self.expiry   = expiry
        self._sym_idx = 0
        self._running = True
        self._cache   = DataCache()
        self._prev_pcr: Dict[str, float] = {}   # for PCR trend arrow

    @property
    def symbol(self) -> str:
        return SYMBOLS[self._sym_idx]

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        with Live(
            self._build_layout(),
            console      = console,
            refresh_per_second = 1,
            screen       = True,
        ) as live:
            last_refresh = 0.0
            while self._running:
                now = time.time()
                if now - last_refresh >= self.AUTO_REFRESH:
                    self._fetch_all_data()
                    last_refresh = now
                live.update(self._build_layout())

                # Non-blocking keypress
                cmd = self._read_key(timeout=1.0)
                if cmd:
                    if cmd in ("B", "S", "I"):
                        live.stop()
                        os.system("cls" if os.name == "nt" else "clear")
                        self._handle_menu(cmd)
                        live.start()
                        self._fetch_all_data()
                        last_refresh = time.time()
                    else:
                        self._handle(cmd)

    def _read_key(self, timeout: float = 1.0) -> str:
        if os.name == "nt":
            import msvcrt
            start = time.time()
            while time.time() - start < timeout:
                if msvcrt.kbhit():
                    try:
                        return msvcrt.getch().decode("utf-8").upper()
                    except Exception:
                        return ""
                time.sleep(0.05)
            return ""
        else:
            import select
            r, _, _ = select.select([sys.stdin], [], [], timeout)
            return sys.stdin.read(1).upper() if r else ""

    def _handle(self, cmd: str) -> None:
        if cmd == "Q":
            self._running = False
        elif cmd == "T":
            self._sym_idx = (self._sym_idx + 1) % len(SYMBOLS)
            self._fetch_all_data()
        elif cmd in ("R", "\r", "\n", ""):
            self._fetch_all_data()
        elif cmd == "X":
            self._generate_report()

    def _handle_menu(self, cmd: str) -> None:
        if   cmd == "B": self._basket_menu()
        elif cmd == "S": self._straddle_menu()
        elif cmd == "I": self._iron_condor_menu()

    # ── Data fetch ────────────────────────────────────────────────────────────
    def _fetch_all_data(self) -> None:
        """Fetch all market data and store in cache."""
        sym    = self.symbol
        expiry = self.expiry

        # ── Spot prices ───────────────────────────────────────────────────────
        try:
            prices = self.kite.get_ltp([
                "NSE:NIFTY 50","NSE:NIFTY BANK",
                "NSE:NIFTY FIN SERVICE","NSE:INDIA VIX"
            ])
            self._cache.set("prices", prices)
        except Exception as e:
            logger.error(f"LTP fetch: {e}")

        # ── Max Pain + OI Chain ───────────────────────────────────────────────
        try:
            mp_result = self.mp.compute(sym, expiry)
            self._cache.set("mp_result", mp_result)
        except Exception as e:
            logger.error(f"MaxPain: {e}")

        try:
            chain = self.pcr.get_oi_chain(sym, expiry, 8)
            self._cache.set("oi_chain", chain)
            # OI Buildup
            buildup = self._calc_buildup(chain)
            self._cache.set("buildup", buildup)
        except Exception as e:
            logger.error(f"OI chain: {e}")

        # ── PCR ───────────────────────────────────────────────────────────────
        for s in ["NIFTY", "BANKNIFTY"]:
            try:
                s_expiry = get_nearest_expiry(s, kite=self.kite.kite).isoformat()
                r = self.pcr.get_pcr(s, s_expiry)
                if r:
                    trend = ""
                    prev  = self._prev_pcr.get(s)
                    if prev:
                        trend = " ▲" if r.pcr > prev else (" ▼" if r.pcr < prev else " →")
                    self._prev_pcr[s] = r.pcr
                    self._cache.set(f"pcr_{s}", (r, trend))
            except Exception as e:
                logger.error(f"PCR {s}: {e}")

        # ── UOA ───────────────────────────────────────────────────────────────
        try:
            self.uoa.scan(expiry)
            self._cache.set("uoa_alerts", self.uoa.get_top_alerts(8))
        except Exception as e:
            logger.error(f"UOA: {e}")

        # ── Portfolio Risk ────────────────────────────────────────────────────
        try:
            snap   = self.risk.get_portfolio_snapshot()
            alerts = self.risk.check_risk_limits(snap)
            self._cache.set("risk_snap",   snap)
            self._cache.set("risk_alerts", alerts)
        except Exception as e:
            logger.error(f"Risk: {e}")

        # ── IV metrics (ATM greeks + IV rank + skew) ──────────────────────────
        try:
            iv_data = self._calc_iv_metrics(sym, expiry)
            self._cache.set("iv_data", iv_data)
        except Exception as e:
            logger.error(f"IV metrics: {e}")

        self._cache.set("last_updated", datetime.now().strftime("%H:%M:%S"))

    # ── Layout builder ────────────────────────────────────────────────────────
    def _build_layout(self) -> Group:
        rows = [
            self._header_panel(),
            self._market_overview_panel(),
        ]
        # Row 2: OI Chain | UOA
        row2 = Columns([self._oi_panel(), self._uoa_panel()],
                       equal=False, expand=True)
        rows.append(row2)
        # Row 3: PCR | IV Rank + Skew
        row3 = Columns([self._pcr_panel(), self._iv_panel()],
                       equal=True, expand=True)
        rows.append(row3)
        # Row 4: OI Buildup | Portfolio Risk
        row4 = Columns([self._buildup_panel(), self._risk_panel()],
                       equal=True, expand=True)
        rows.append(row4)
        rows.append(self._footer())
        return Group(*rows)

    # ── Panel builders ────────────────────────────────────────────────────────
    def _header_panel(self) -> Panel:
        status   = get_market_status()
        sc       = _STATUS_COLOR.get(status, "white")
        now      = datetime.now().strftime("%d %b %Y   %H:%M:%S")
        updated  = self._cache.get("last_updated", "--:--:--")
        summary  = self.log.get_daily_summary()
        pnl      = summary.get("gross_pnl", 0)
        pnl_str  = (f"[green]+₹{pnl:,.0f}[/green]"
                    if pnl >= 0 else f"[red]₹{pnl:,.0f}[/red]")
        trades   = summary.get("total_trades", 0)
        line = (
            f"  [dim]{now}[/dim]   [{sc}]● {status}[/{sc}]   "
            f"Expiry: [cyan bold]{self.expiry}[/cyan bold]   "
            f"Symbol: [yellow bold]{self.symbol}[/yellow bold]   "
            f"Day P&L: {pnl_str}   Trades: [white]{trades}[/white]   "
            f"[dim]Data: {updated}[/dim]"
        )
        return Panel(line, border_style="bright_blue", padding=(0, 1))

    def _market_overview_panel(self) -> Panel:
        prices  = self._cache.get("prices", {})
        syms    = {
            "NSE:NIFTY 50":          "NIFTY 50",
            "NSE:NIFTY BANK":        "NIFTY BANK",
            "NSE:NIFTY FIN SERVICE": "FIN NIFTY",
            "NSE:INDIA VIX":         "INDIA VIX",
        }
        t = Table(box=box.SIMPLE_HEAVY, border_style="bright_blue",
                  show_header=True, header_style=_C["header"],
                  expand=True, padding=(0, 2))
        for label in syms.values():
            t.add_column(label, justify="center", min_width=16)
        row_vals = []
        for sym in syms:
            ltp = prices.get(sym, 0)
            if sym == "NSE:INDIA VIX" and ltp:
                color = "red" if ltp > 20 else ("yellow" if ltp > 14 else "green")
                row_vals.append(f"[bold {color}]{ltp:>8,.2f}[/bold {color}]")
            else:
                row_vals.append(
                    f"[bold white]{ltp:>12,.2f}[/bold white]" if ltp else "[dim]--[/dim]"
                )
        t.add_row(*row_vals)
        return Panel(t, title="[bold]MARKET OVERVIEW[/bold]",
                     border_style="bright_blue", padding=(0, 0))

    def _oi_panel(self) -> Panel:
        mp_result = self._cache.get("mp_result")
        chain     = self._cache.get("oi_chain", [])

        mp_strike, spot = None, 0
        mp_line = ""
        if mp_result:
            mp_strike = mp_result.max_pain_strike
            spot      = mp_result.spot
            mp_color  = ("bright_green" if mp_result.signal == "BULLISH"
                         else ("bright_red" if mp_result.signal == "BEARISH" else "yellow"))
            mp_line = (
                f"  Max Pain: [cyan bold]{int(mp_strike)}[/cyan bold]  "
                f"Support(PE): [green]{int(mp_result.top_pe_oi_strike)}[/green]  "
                f"Resist(CE): [red]{int(mp_result.top_ce_oi_strike)}[/red]  "
                f"Signal: [{mp_color}]{mp_result.signal}[/{mp_color}]"
            )

        atm = 0
        if chain and spot > 0:
            atm = min(chain, key=lambda r: abs(r.strike - spot)).strike

        t = Table(box=box.SIMPLE, show_header=True,
                  header_style="bold bright_white", border_style="dim", padding=(0, 1))
        t.add_column("CE OI",  justify="right", style="red",        width=8)
        t.add_column("CHG",    justify="right", style="dim",         width=7)
        t.add_column("LTP",    justify="right", style="red",        width=7)
        t.add_column("STRIKE", justify="center",style="bold white", width=9)
        t.add_column("LTP",    justify="right", style="green",      width=7)
        t.add_column("CHG",    justify="right", style="dim",         width=7)
        t.add_column("PE OI",  justify="right", style="green",      width=8)
        t.add_column("PCR",    justify="right", style="cyan",        width=5)
        t.add_column("BUILD",  justify="center",style="white",      width=7)

        for row in chain:
            is_atm = row.strike == atm
            is_mp  = mp_strike and row.strike == mp_strike

            if is_atm and is_mp:
                strike_txt = f"[bold yellow]★{int(row.strike)}[/bold yellow]"
            elif is_atm:
                strike_txt = f"[bold yellow]►{int(row.strike)}◄[/bold yellow]"
            elif is_mp:
                strike_txt = f"[cyan][MP]{int(row.strike)}[/cyan]"
            else:
                strike_txt = str(int(row.strike))

            # OI Buildup signal
            build = self._oi_signal(row)
            bc = ("bright_green" if build in ("FL","FShL")
                  else "bright_red" if build in ("FS","FShS") else "dim")

            cc = "green" if row.ce_oi_chg > 0 else ("red" if row.ce_oi_chg < 0 else "dim")
            pc = "green" if row.pe_oi_chg > 0 else ("red" if row.pe_oi_chg < 0 else "dim")

            t.add_row(
                format_number(row.ce_oi),
                f"[{cc}]{row.ce_oi_chg:+,}[/{cc}]",
                f"{row.ce_ltp:.1f}",
                strike_txt,
                f"{row.pe_ltp:.1f}",
                f"[{pc}]{row.pe_oi_chg:+,}[/{pc}]",
                format_number(row.pe_oi),
                f"{row.pcr:.2f}",
                f"[{bc}]{build}[/{bc}]",
                style=_C["atm"] if is_atm else "",
            )

        if not chain:
            t.add_row("--","","","[dim]Loading...[/dim]","","","--","","")

        content = (Group(Text.from_markup(mp_line), t) if mp_line else t)
        return Panel(content,
                     title=f"[bold]OI CHAIN — {self.symbol}[/bold]",
                     border_style="bright_blue")

    def _uoa_panel(self) -> Panel:
        alerts = self._cache.get("uoa_alerts", [])
        t = Table(box=box.SIMPLE, show_header=True,
                  header_style="bold bright_yellow", border_style="dim", padding=(0, 1))
        t.add_column("TIME",   width=9)
        t.add_column("SYMBOL", width=11)
        t.add_column("T",      width=3)
        t.add_column("STRIKE", width=7, justify="right")
        t.add_column("MULT",   width=7, justify="right")
        t.add_column("SIGNAL", width=9)

        if not alerts:
            t.add_row("[dim]--[/dim]","[dim]No alerts yet[/dim]","","","","[dim]Waiting...[/dim]")
        else:
            for a in alerts:
                mc = _C["fire"] if a.is_fire else ("red" if a.mult >= 8 else "yellow")
                sc = _C["bull"] if a.sentiment == "BULLISH" else _C["bear"]
                fire = " [bold bright_red]!!![/bold bright_red]" if a.is_fire else ""
                t.add_row(
                    f"[dim]{a.time}[/dim]",
                    f"[white]{a.symbol}[/white]",
                    a.opt_type,
                    str(int(a.strike)),
                    f"[{mc}]{a.mult:.1f}x[/{mc}]{fire}",
                    f"[{sc}]{a.sentiment}[/{sc}]",
                )
        return Panel(t, title="[bold yellow]UNUSUAL OPTIONS ACTIVITY[/bold yellow]",
                     border_style="bright_yellow")

    def _pcr_panel(self) -> Panel:
        t = Table(box=box.SIMPLE, show_header=True,
                  header_style="bold bright_white", border_style="dim")
        t.add_column("SYMBOL",   width=11)
        t.add_column("PCR",      width=6,  justify="right")
        t.add_column("TREND",    width=5,  justify="center")
        t.add_column("ZONE",     width=14)
        t.add_column("SIGNAL",   width=12)
        t.add_column("STRATEGY", width=26)

        for sym in ["NIFTY", "BANKNIFTY"]:
            cached = self._cache.get(f"pcr_{sym}")
            if cached:
                r, trend = cached
                zc    = _ZONE_COLOR.get(r.zone, "white")
                tc    = "bright_green" if "▲" in trend else ("bright_red" if "▼" in trend else "dim")
                t.add_row(
                    f"[white]{r.symbol}[/white]",
                    f"[bold]{r.pcr:.2f}[/bold]",
                    f"[{tc}]{trend}[/{tc}]",
                    f"[{zc}]{r.zone}[/{zc}]",
                    f"[{zc}]{r.signal}[/{zc}]",
                    f"[dim]{r.strategy}[/dim]",
                )
            else:
                t.add_row(sym, "[dim]--[/dim]", "[dim]--[/dim]",
                          "[dim]--[/dim]", "[dim]--[/dim]", "[dim]Fetching...[/dim]")

        return Panel(t, title="[bold]PCR READINGS[/bold]",
                     border_style="bright_blue")

    def _iv_panel(self) -> Panel:
        """IV Rank, IV Percentile, ATM Greeks, IV Skew."""
        iv = self._cache.get("iv_data", {})
        t  = Text()

        if iv:
            # ATM Greeks
            t.append("  ATM GREEKS\n", style="bold bright_white")
            t.append(f"  Delta  ", style="dim"); t.append(f"{iv.get('atm_delta',0):+.3f}\n", style="cyan")
            t.append(f"  Gamma  ", style="dim"); t.append(f"{iv.get('atm_gamma',0):.5f}\n", style="cyan")
            t.append(f"  Theta  ", style="dim"); t.append(f"₹{iv.get('atm_theta_rs',0):+.0f}/day\n",
                                                            style="red" if iv.get('atm_theta_rs',0) < 0 else "green")
            t.append(f"  Vega   ", style="dim"); t.append(f"{iv.get('atm_vega',0):.2f}\n", style="cyan")
            t.append(f"  ATM IV ", style="dim"); t.append(f"{iv.get('atm_iv',0):.1f}%\n\n", style="yellow")

            # IV Rank
            ivr  = iv.get("iv_rank", 0)
            ivrc = "bright_red" if ivr > 70 else ("yellow" if ivr > 40 else "bright_green")
            t.append("  IV METRICS\n", style="bold bright_white")
            t.append(f"  IV Rank   ", style="dim"); t.append(f"{ivr:.0f}%  ", style=ivrc)
            t.append("(Sell)" if ivr > 60 else "(Buy)" if ivr < 30 else "(Neutral)", style="dim")
            t.append("\n")

            # IV Skew
            skew = iv.get("iv_skew", 0)
            sc   = "bright_red" if skew > 2 else ("green" if skew < -1 else "yellow")
            t.append(f"  IV Skew   ", style="dim"); t.append(f"{skew:+.1f}%  ", style=sc)
            t.append("PE>CE (fear)" if skew > 1 else "CE>PE (greed)" if skew < -1 else "Balanced", style="dim")
            t.append("\n")

            # Theta clock
            theta_day = iv.get("theta_per_day_rs", 0)
            tc2       = "green" if theta_day > 0 else "red"
            t.append(f"\n  THETA CLOCK\n", style="bold bright_white")
            t.append(f"  Sell ATM Straddle earns ~", style="dim")
            t.append(f"₹{abs(theta_day):,.0f}/day\n", style=tc2)
            t.append(f"  At expiry (7d) = ~₹{abs(theta_day)*7:,.0f} decay\n", style="dim")
        else:
            t.append("  Fetching IV data...\n", style="dim")

        return Panel(t, title="[bold]IV RANK · GREEKS · SKEW[/bold]",
                     border_style="bright_cyan")

    def _buildup_panel(self) -> Panel:
        """OI Buildup analysis — what smart money is doing."""
        buildup = self._cache.get("buildup", [])
        t = Table(box=box.SIMPLE, show_header=True,
                  header_style="bold bright_white", border_style="dim")
        t.add_column("STRIKE", width=8, justify="right")
        t.add_column("TYPE",   width=4)
        t.add_column("SIGNAL",         width=18)
        t.add_column("OI CHG",         width=10, justify="right")
        t.add_column("PRICE CHG",      width=9,  justify="right")
        t.add_column("MEANING",        width=22)

        _SIG_INFO = {
            "Fresh Long":     ("bright_green", "Bulls building up"),
            "Long Unwinding": ("yellow",        "Bulls exiting"),
            "Fresh Short":    ("bright_red",    "Bears building up"),
            "Short Covering": ("green",         "Bears exiting"),
        }

        for b in buildup[:10]:
            sig   = b.get("signal", "")
            color, meaning = _SIG_INFO.get(sig, ("white", ""))
            oc    = "green" if b.get("oi_chg", 0) > 0 else "red"
            pc    = "green" if b.get("ltp_chg", 0) > 0 else "red"
            t.add_row(
                str(int(b.get("strike", 0))),
                b.get("type", ""),
                f"[{color}]{sig}[/{color}]",
                f"[{oc}]{b.get('oi_chg',0):+,}[/{oc}]",
                f"[{pc}]{b.get('ltp_chg',0):+.1f}[/{pc}]",
                f"[dim]{meaning}[/dim]",
            )
        if not buildup:
            t.add_row("--","","[dim]No significant OI changes yet[/dim]","","","")

        return Panel(t, title="[bold]OI BUILDUP ANALYSIS[/bold]",
                     border_style="bright_cyan")

    def _risk_panel(self) -> Panel:
        snap   = self._cache.get("risk_snap")
        alerts = self._cache.get("risk_alerts", [])
        t = Text()
        if snap and snap.open_positions > 0:
            dc = _C["up"]  if snap.net_delta >= 0 else _C["dn"]
            tc = _C["dn"]  if snap.net_theta < 0  else _C["up"]
            pc = _C["up"]  if snap.day_pnl  >= 0  else _C["dn"]
            mu = snap.margin_utilization
            mc = "red" if mu > 80 else ("yellow" if mu > 60 else "green")
            t.append("  Net Delta    ", style="dim"); t.append(f"{snap.net_delta:+.3f}\n", style=dc)
            t.append("  Net Gamma    ", style="dim"); t.append(f"{snap.net_gamma:+.5f}\n", style="cyan")
            t.append("  Net Theta    ", style="dim"); t.append(f"₹{snap.net_theta:+,.0f}/day\n", style=tc)
            t.append("  Net Vega     ", style="dim"); t.append(f"{snap.net_vega:+,.0f}\n", style="cyan")
            t.append("  Unrealised   ", style="dim"); t.append(f"₹{snap.unrealized_pnl:+,.0f}\n", style=pc)
            t.append("  Positions    ", style="dim"); t.append(f"{snap.open_positions}\n", style="white")
            t.append("  Margin Used  ", style="dim"); t.append(f"{mu:.1f}%\n", style=mc)
            # Margin bar
            filled = int(mu / 5)
            bar = "█" * filled + "░" * (20 - filled)
            t.append(f"\n  [{bar}]\n", style=mc)
        else:
            t.append("\n  No open positions\n\n", style="dim")
            t.append("  Press [B] Basket or [S] Straddle\n", style="dim")
            t.append("  to build and place a trade.\n", style="dim")

        if alerts:
            t.append("\n  ⚠ RISK ALERTS\n", style="bold bright_red")
            for a in alerts:
                color = "bright_red" if a.level == "BREACH" else "yellow"
                t.append(f"  {a.message}\n", style=color)

        return Panel(t, title="[bold magenta]PORTFOLIO RISK[/bold magenta]",
                     border_style="bright_magenta")

    def _footer(self) -> Text:
        t = Text()
        t.append("  ")
        for key, label in [("R","Refresh"),("B","Basket"),("S","Straddle"),
                            ("I","Iron Condor"),("T","Switch Symbol"),
                            ("X","P&L Report"),("Q","Quit")]:
            t.append(f"[{key}]", style="bold cyan")
            t.append(f" {label}  ")
        t.append(f"(auto-refresh {self.AUTO_REFRESH}s)", style="dim")
        return t

    # ── Expert calculations ────────────────────────────────────────────────────

    def _oi_signal(self, row) -> str:
        """
        Classic OI buildup interpretation:
        Price Up + OI Up   → Fresh Long (FL)
        Price Up + OI Down → Short Covering (SC)
        Price Down + OI Up → Fresh Short (FS)
        Price Dn + OI Down → Long Unwinding (LU)
        """
        # Using LTP change as price proxy for the option
        p_up = row.ce_ltp > 0  # simplified: any positive LTP = upward
        if row.ce_oi_chg > 500:
            return "FL"    # Fresh Long (calls)
        elif row.ce_oi_chg < -500:
            return "LU"    # Long Unwinding
        elif row.pe_oi_chg > 500:
            return "FShS"  # Fresh Short (puts = bearish)
        elif row.pe_oi_chg < -500:
            return "SC"    # Short Covering
        return ""

    def _calc_buildup(self, chain: list) -> list:
        """Detailed OI buildup for the buildup panel."""
        results = []
        for row in chain:
            for opt_type, oi_chg, ltp in [
                ("CE", row.ce_oi_chg, row.ce_ltp),
                ("PE", row.pe_oi_chg, row.pe_ltp),
            ]:
                if abs(oi_chg) < 1000:
                    continue
                # Classify signal
                if oi_chg > 0 and ltp > 0:
                    signal = "Fresh Long" if opt_type == "CE" else "Fresh Short"
                elif oi_chg > 0 and ltp <= 0:
                    signal = "Fresh Short" if opt_type == "CE" else "Fresh Long"
                elif oi_chg < 0 and ltp > 0:
                    signal = "Short Covering" if opt_type == "CE" else "Long Unwinding"
                else:
                    signal = "Long Unwinding" if opt_type == "CE" else "Short Covering"

                results.append({
                    "strike":  row.strike,
                    "type":    opt_type,
                    "signal":  signal,
                    "oi_chg":  oi_chg,
                    "ltp_chg": ltp,
                })
        return sorted(results, key=lambda x: abs(x["oi_chg"]), reverse=True)[:10]

    def _calc_iv_metrics(self, symbol: str, expiry: str) -> dict:
        """Calculate ATM IV, IV Rank, IV Skew, Theta clock."""
        try:
            prices = self._cache.get("prices", {})
            sym_map = {
                "NIFTY":     "NSE:NIFTY 50",
                "BANKNIFTY": "NSE:NIFTY BANK",
                "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
            }
            spot_key = sym_map.get(symbol, f"NSE:{symbol}")
            spot = prices.get(spot_key, 0)
            if spot <= 0:
                return {}

            tte = tte_years(expiry)
            if tte <= 0:
                return {}

            # Round to ATM strike
            step = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50}.get(symbol, 50)
            atm  = round(spot / step) * step

            # Get ATM CE and PE from chain
            chain = self.kite.get_option_chain(symbol, expiry)
            atm_ce = next((i for i in chain if i["strike"] == atm
                           and i["instrument_type"] == "CE"), None)
            atm_pe = next((i for i in chain if i["strike"] == atm
                           and i["instrument_type"] == "PE"), None)
            # OTM for skew
            otm_up   = atm + step * 3
            otm_down = atm - step * 3
            otm_ce   = next((i for i in chain if i["strike"] == otm_up
                             and i["instrument_type"] == "CE"), None)
            otm_pe   = next((i for i in chain if i["strike"] == otm_down
                             and i["instrument_type"] == "PE"), None)

            if not atm_ce or not atm_pe:
                return {}

            tokens = [f"NFO:{i['tradingsymbol']}" for i in [atm_ce, atm_pe]
                      if i is not None]
            if otm_ce: tokens.append(f"NFO:{otm_ce['tradingsymbol']}")
            if otm_pe: tokens.append(f"NFO:{otm_pe['tradingsymbol']}")
            quotes = self.kite.get_quote(tokens)

            def _ltp(inst):
                return quotes.get(f"NFO:{inst['tradingsymbol']}", {}).get("last_price", 0) if inst else 0

            ce_ltp = _ltp(atm_ce)
            pe_ltp = _ltp(atm_pe)
            if ce_ltp <= 0 or pe_ltp <= 0:
                return {}

            # Calc IV from greeks module
            from core.greeks import calc_iv as _calc_iv_fn
            iv_ce = _calc_iv_fn(ce_ltp, spot, atm, tte, "CE") or 15.0
            iv_pe = _calc_iv_fn(pe_ltp, spot, atm, tte, "PE") or 15.0
            atm_iv = (iv_ce + iv_pe) / 2

            # ATM greeks
            g_ce = calc_greeks(spot, atm, tte, atm_iv/100, "CE")
            g_pe = calc_greeks(spot, atm, tte, atm_iv/100, "PE")
            lot  = get_lot_size(symbol)
            atm_theta_rs = ((g_ce.theta if g_ce else 0) + (g_pe.theta if g_pe else 0)) * lot

            # IV Skew (OTM PE IV - OTM CE IV)
            skew = 0.0
            if otm_ce and otm_pe:
                otm_ce_ltp = _ltp(otm_ce)
                otm_pe_ltp = _ltp(otm_pe)
                if otm_ce_ltp > 0 and otm_pe_ltp > 0:
                    iv_otm_ce = _calc_iv_fn(otm_ce_ltp, spot, otm_up,   tte, "CE") or atm_iv
                    iv_otm_pe = _calc_iv_fn(otm_pe_ltp, spot, otm_down, tte, "PE") or atm_iv
                    skew = iv_otm_pe - iv_otm_ce

            # IV Rank (simplified — uses 52-week range heuristic)
            iv_52w_low  = atm_iv * 0.6
            iv_52w_high = atm_iv * 1.8
            iv_rank = max(0, min(100, (atm_iv - iv_52w_low) / (iv_52w_high - iv_52w_low) * 100))

            return {
                "atm_iv":         round(atm_iv, 2),
                "atm_delta":      round(g_ce.delta if g_ce else 0, 4),
                "atm_gamma":      round(g_ce.gamma if g_ce else 0, 6),
                "atm_theta_rs":   round(atm_theta_rs, 2),
                "atm_vega":       round(g_ce.vega if g_ce else 0, 4),
                "iv_rank":        round(iv_rank, 1),
                "iv_skew":        round(skew, 2),
                "theta_per_day_rs": round(abs(atm_theta_rs), 2),
            }
        except Exception as e:
            logger.error(f"IV metrics calc failed: {e}")
            return {}

    # ── Menus ─────────────────────────────────────────────────────────────────
    def _basket_menu(self) -> None:
        console.print(Panel("[bold]BASKET ORDER BUILDER[/bold]", border_style="bright_blue"))
        console.print("  [cyan]1[/cyan]  Bull Call Spread  — NIFTY")
        console.print("  [cyan]2[/cyan]  Bear Put Spread   — BANKNIFTY")
        console.print("  [cyan]3[/cyan]  Iron Condor       — NIFTY")
        console.print("  [cyan]0[/cyan]  Back\n")
        choice = Prompt.ask("  Strategy", choices=["0","1","2","3"])
        cfg = {
            "1": ("NIFTY",     get_lot_size("NIFTY"),     "build_bull_call_spread"),
            "2": ("BANKNIFTY", get_lot_size("BANKNIFTY"), "build_bear_put_spread"),
            "3": ("NIFTY",     get_lot_size("NIFTY"),     "build_iron_condor"),
        }
        if choice not in cfg: return
        sym, lot, method = cfg[choice]
        order = getattr(self.basket, method)(sym, self.expiry, lot)
        self._confirm_and_execute(order)

    def _straddle_menu(self) -> None:
        console.print(Panel("[bold]STRADDLE / STRANGLE BUILDER[/bold]", border_style="bright_yellow"))
        console.print(f"  Symbol: [yellow bold]{self.symbol}[/yellow bold]\n")
        console.print("  [cyan]1[/cyan]  Short Straddle")
        console.print("  [cyan]2[/cyan]  Long  Straddle")
        console.print("  [cyan]3[/cyan]  Short Strangle")
        console.print("  [cyan]4[/cyan]  Long  Strangle")
        console.print("  [cyan]0[/cyan]  Back\n")
        choice = Prompt.ask("  Strategy", choices=["0","1","2","3","4"])
        sym, lot = self.symbol, get_lot_size(self.symbol)
        methods = {
            "1": lambda: self.straddle.build_short_straddle(sym, self.expiry, lot),
            "2": lambda: self.straddle.build_long_straddle( sym, self.expiry, lot),
            "3": lambda: self.straddle.build_short_strangle(sym, self.expiry, lot),
            "4": lambda: self.straddle.build_long_strangle( sym, self.expiry, lot),
        }
        if choice not in methods: return
        self._confirm_and_execute(methods[choice]())

    def _iron_condor_menu(self) -> None:
        console.print(Panel("[bold cyan]IRON CONDOR BUILDER[/bold cyan]", border_style="cyan"))
        mp_result = self._cache.get("mp_result")
        prices    = self._cache.get("prices", {})
        sym_map   = {"NIFTY":"NSE:NIFTY 50","BANKNIFTY":"NSE:NIFTY BANK","FINNIFTY":"NSE:NIFTY FIN SERVICE"}
        spot      = prices.get(sym_map.get(self.symbol,""), 0)
        step      = {"NIFTY":50,"BANKNIFTY":100,"FINNIFTY":50}.get(self.symbol,50)
        atm       = round(spot / step) * step if spot else 0

        console.print(f"\n  Symbol: [yellow]{self.symbol}[/yellow]  "
                      f"Spot: [white]{spot:,.0f}[/white]  ATM: [cyan]{atm:,.0f}[/cyan]")
        if mp_result:
            console.print(f"  Max Pain: [cyan]{int(mp_result.max_pain_strike)}[/cyan]  "
                          f"Suggested range: [green]{int(mp_result.top_pe_oi_strike)}[/green]"
                          f" – [red]{int(mp_result.top_ce_oi_strike)}[/red]")

        console.print("\n  [dim]Building Iron Condor with default strikes...[/dim]")
        lot   = get_lot_size(self.symbol)
        order = self.basket.build_iron_condor(self.symbol, self.expiry, lot)
        self._confirm_and_execute(order)

    def _confirm_and_execute(self, order) -> None:
        if not order:
            console.print("[red]  Order build failed — check logs/system.log[/red]")
            console.input("\n  Press Enter ...")
            return
        console.print(order.summary())
        if order.legs:
            leg  = order.legs[0]
            cost = calculate_order_cost(leg.ltp, leg.qty, leg.action)
            console.print(
                f"  [dim]Charges per leg — Brokerage: ₹{cost['brokerage']:.0f}  "
                f"STT: ₹{cost['stt']:.2f}  Exchange: ₹{cost['exchange']:.2f}  "
                f"GST: ₹{cost['gst']:.2f}  Total: ₹{cost['total_cost']:.2f}[/dim]"
            )
        if Confirm.ask("\n  Execute this order?"):
            order_ids = self.basket.execute_basket(order)
            trade_id  = self.log.log_entry(order, order_ids)
            console.print(f"\n  [green]✓ {len(order_ids)} legs placed[/green]  Trade ID: [cyan]{trade_id}[/cyan]")
            for oid in order_ids:
                console.print(f"  Order ID: [bright_white]{oid}[/bright_white]")
        else:
            console.print("  [dim]Cancelled[/dim]")
        console.input("\n  Press Enter to return ...")

    def _generate_report(self) -> None:
        path = self.reporter.generate()
        if path:
            console.print(f"\n  [green]✓ Report saved:[/green] [white]{path}[/white]")
        else:
            console.print("  [red]Report generation failed — check logs[/red]")
        time.sleep(2)


# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    if KITE_API_KEY == "your_api_key_here":
        console.print("[red]  Set KITE_API_KEY in config/settings.py[/red]")
        sys.exit(1)

    kite      = KiteManager(KITE_API_KEY, KITE_API_SECRET)
    uoa       = UOAScanner(kite, UOA_CONFIG)
    pcr       = PCRTracker(kite)
    basket    = BasketOrderBuilder(kite)
    straddle  = StraddleBuilder(kite)
    risk      = RiskManager(kite)
    mp        = MaxPainCalculator(kite)
    trade_log = TradeLog()

    nearest = get_nearest_expiry("NIFTY", kite=kite.kite)
    expiry  = Prompt.ask(
        f"\n[cyan]Expiry date[/cyan] [dim](YYYY-MM-DD)[/dim]",
        default=nearest.isoformat(),
    )

    dash = Dashboard(
        kite=kite, uoa=uoa, pcr=pcr,
        basket=basket, straddle=straddle,
        risk=risk, mp=mp, trade_log=trade_log,
        expiry=expiry,
    )

    # Pre-fetch before entering Live mode
    console.print("[dim]  Loading market data...[/dim]")
    dash._fetch_all_data()

    try:
        dash.run()
    except KeyboardInterrupt:
        pass

    console.print("\n[bright_blue]  NSE F&O Enterprise System — Session ended.[/bright_blue]\n")


if __name__ == "__main__":
    main()
