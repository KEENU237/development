"""
Alert Engine — Real-time signal detection + Telegram notification
=================================================================
Har 60 sec pe cache check karta hai.
Genuine signal milne pe Telegram message bhejta hai.
Same signal 30 min tak dobara alert nahi karta (spam filter).
"""

import requests
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Category emojis for Telegram ─────────────────────────────────────────────
CATEGORY_EMOJI = {
    "URGENT":    "🚨",
    "IMPORTANT": "⚠️",
    "INFO":      "ℹ️",
}


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TriggerAlert:
    time:       str    # "10:42"
    category:   str    # URGENT / IMPORTANT / INFO
    signal_key: str    # Unique key — cooldown ke liye
    title:      str    # Short title (1 line)
    detail:     str    # Multi-line detail text
    action:     str    # Kya karna chahiye
    score:      int    # Signal strength (1-3)


# ══════════════════════════════════════════════════════════════════════════════
# ALERT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AlertEngine:
    """
    Cache se signals check karo, score karo, Telegram pe bhejo.

    Usage:
        engine = AlertEngine(bot_token, chat_id, enabled=True)
        alerts = engine.check_and_send(cache, symbol, gex_history)
    """

    COOLDOWN_MINUTES = 30   # Same signal 30 min ke andar repeat nahi hoga

    def __init__(self, bot_token: str = "", chat_id: str = "",
                 enabled: bool = False):
        self.bot_token = bot_token.strip() if bot_token else ""
        self.chat_id   = chat_id.strip()   if chat_id   else ""
        self.enabled   = enabled
        self._last_sent: dict = {}   # signal_key → datetime of last send

    # ── Public: main check function ───────────────────────────────────────────

    def check_and_send(self, cache: dict, symbol: str,
                       gex_history: list) -> List[TriggerAlert]:
        """
        Sab signals check karo.
        Triggered alerts return karo (Telegram bhi already sent hoga).
        """
        triggered: List[TriggerAlert] = []

        # Saare checkers run karo — None matlab signal nahi mila
        checkers = [
            self._check_uoa(cache),
            self._check_gex_flip(gex_history, symbol),
            self._check_vix_spike(cache),
            self._check_pcr_extreme(cache),
            self._check_smi(cache),
            self._check_iv_rank(cache),
        ]

        for alert in checkers:
            if alert is None:
                continue
            if self._in_cooldown(alert.signal_key):
                continue
            triggered.append(alert)
            self._mark_sent(alert.signal_key)
            # Sirf tab bhejo jab enabled=True aur credentials set hon
            if self.enabled and self.bot_token and self.chat_id:
                self._send_telegram(alert)

        return triggered

    # ── Signal checkers ───────────────────────────────────────────────────────

    def _check_uoa(self, cache: dict) -> Optional[TriggerAlert]:
        """
        UOA Fire signal check karo.
        Sirf ATM/OTM signals — Deep ITM institutional ones ignore.
        """
        alerts = cache.get("uoa_alerts", [])
        if not alerts:
            return None

        # Actionable signals only (Deep ITM = institutional, not for retail)
        actionable = [
            a for a in alerts
            if a.is_fire and a.sentiment in (
                "BULLISH", "BEARISH", "MILD_ITM_BULL", "MILD_ITM_BEAR"
            )
        ]
        if not actionable:
            return None

        # Highest multiplier wala top alert lo
        top = max(actionable, key=lambda x: x.mult)

        is_bull   = "BULL" in top.sentiment
        dir_emoji = "📈" if is_bull else "📉"
        dir_text  = "BULLISH" if is_bull else "BEARISH"
        ce_pe_tip = "CE" if is_bull else "PE"

        depth_line = (
            f"\nDepth   : {top.itm_depth_pct:.1f}% ITM (Mild)"
            if top.itm_depth_pct > 0
            else ""
        )
        spot_line = (
            f"\nSpot    : Rs.{top.spot_at_alert:,.0f}"
            if top.spot_at_alert > 0
            else ""
        )

        detail = (
            f"Symbol  : {top.symbol}\n"
            f"Strike  : {int(top.strike)} {top.opt_type}\n"
            f"Volume  : {top.mult:.1f}x normal  FIRE!\n"
            f"Signal  : {dir_emoji} {dir_text}"
            f"{depth_line}{spot_line}"
        )
        action = (
            f"Dashboard > Tab 1 > UOA Panel dekho.\n"
            f"{ce_pe_tip} side pe opportunities explore karo.\n"
            f"Baaki indicators (PCR, GEX) se confirm zaroor karo."
        )
        return TriggerAlert(
            time=datetime.now().strftime("%H:%M"),
            category="URGENT",
            signal_key=f"UOA_{top.symbol}_{top.opt_type}_{int(top.strike)}",
            title=f"Unusual Activity — {top.symbol} {int(top.strike)} {top.opt_type}",
            detail=detail,
            action=action,
            score=3,
        )

    def _check_gex_flip(self, gex_history: list,
                        symbol: str) -> Optional[TriggerAlert]:
        """
        GEX ka sign flip detect karo.
        Positive→Negative = bearish regime.
        Negative→Positive = bullish regime.
        """
        if len(gex_history) < 2:
            return None

        prev_gex = gex_history[-2].get("gex", 0)
        curr_gex = gex_history[-1].get("gex", 0)

        if prev_gex == 0 or curr_gex == 0:
            return None

        flipped_bearish = (prev_gex > 0 and curr_gex < 0)
        flipped_bullish = (prev_gex < 0 and curr_gex > 0)

        if not (flipped_bearish or flipped_bullish):
            return None

        if flipped_bearish:
            flip_desc = "Positive se Negative (Bearish Flip)"
            meaning   = (
                "Dealer hedging support hata.\n"
                "Market ab freely neeche ja sakti hai."
            )
            action = (
                "CE positions ka stop-loss tight karo.\n"
                "PE buying opportunities dekho.\n"
                "Volatile move possible — position size chhoti rakho."
            )
        else:
            flip_desc = "Negative se Positive (Bullish Flip)"
            meaning   = (
                "Dealer hedging support aa gaya.\n"
                "Market ko neeche jaane me resistance hoga."
            )
            action = (
                "PE positions review karo.\n"
                "CE buying opportunities dekho.\n"
                "Range-bound ya bullish move possible."
            )

        detail = (
            f"Symbol : {symbol}\n"
            f"GEX    : {prev_gex:+.2f} Cr  ->  {curr_gex:+.2f} Cr\n"
            f"Flip   : {flip_desc}\n"
            f"Matlab : {meaning}"
        )
        return TriggerAlert(
            time=datetime.now().strftime("%H:%M"),
            category="URGENT",
            signal_key=f"GEX_FLIP_{symbol}",
            title=f"GEX Flip — {symbol} Market Regime Change!",
            detail=detail,
            action=action,
            score=3,
        )

    def _check_vix_spike(self, cache: dict) -> Optional[TriggerAlert]:
        """
        India VIX sudden spike +15% check karo.
        prev_vix AlertEngine instance me store hota hai (cache nahi —
        cache har 60 sec pe fresh dict banta hai).
        """
        prices   = cache.get("prices", {})
        curr_vix = prices.get("NSE:INDIA VIX", 0)
        if curr_vix <= 0:
            return None

        # Instance variable me store karo — cache nahi (cache = fresh dict every 60s)
        prev_vix = getattr(self, "_prev_vix", 0)
        self._prev_vix = curr_vix   # Update for next cycle

        if prev_vix <= 0:
            return None  # Pehli reading — baseline set ho rahi hai

        change_pct = ((curr_vix - prev_vix) / prev_vix) * 100
        if change_pct < 15.0:
            return None

        detail = (
            f"India VIX : {prev_vix:.1f}  ->  {curr_vix:.1f}\n"
            f"Change    : +{change_pct:.1f}% (Sudden Spike!)\n"
            f"Matlab    : Market me sudden fear aa gaya.\n"
            f"           Options ka premium bahut mehnge ho gaye."
        )
        action = (
            "Option BUYING abhi avoid karo — premium mehnge hain.\n"
            "Existing positions ka SL check karo.\n"
            "VIX 20+ pe toh koi naya trade mat lo."
        )
        return TriggerAlert(
            time=datetime.now().strftime("%H:%M"),
            category="IMPORTANT",
            signal_key="VIX_SPIKE",
            title=f"VIX Spike! {prev_vix:.1f} -> {curr_vix:.1f} (+{change_pct:.0f}%)",
            detail=detail,
            action=action,
            score=2,
        )

    def _check_pcr_extreme(self, cache: dict) -> Optional[TriggerAlert]:
        """
        NIFTY PCR extreme level check (<0.70 ya >1.30).
        """
        pcr_data = cache.get("pcr_data", {})
        nifty_tuple = pcr_data.get("NIFTY")
        if not nifty_tuple:
            return None

        pcr_result, _ = nifty_tuple
        pcr = getattr(pcr_result, "pcr", 0)
        if pcr <= 0:
            return None

        if pcr < 0.70:
            zone    = "EXTREME BEARISH"
            emoji   = "📉"
            meaning = (
                "Call buyers bahut zyada hain.\n"
                "Market overbought feel kar rahi hai.\n"
                "Reversal ya consolidation possible."
            )
            action = (
                "Naye CE positions lene se bachein.\n"
                "Contrarian — thoda bearish bias rakho.\n"
                "PCR 0.80 ke upar aaye toh reassess karo."
            )
            sig_key = "PCR_EXTREME_BEAR"
        elif pcr > 1.30:
            zone    = "EXTREME BULLISH"
            emoji   = "📈"
            meaning = (
                "Put buyers bahut zyada hain.\n"
                "Market oversold feel kar rahi hai.\n"
                "Bounce ya short-covering possible."
            )
            action = (
                "Naye PE positions lene se bachein.\n"
                "Contrarian — thoda bullish bias rakho.\n"
                "PCR 1.20 ke neeche aaye toh reassess karo."
            )
            sig_key = "PCR_EXTREME_BULL"
        else:
            return None

        detail = (
            f"NIFTY PCR : {pcr:.2f}  ({zone})  {emoji}\n"
            f"Matlab    : {meaning}"
        )
        return TriggerAlert(
            time=datetime.now().strftime("%H:%M"),
            category="IMPORTANT",
            signal_key=sig_key,
            title=f"PCR Extreme Level — {pcr:.2f} ({zone})",
            detail=detail,
            action=action,
            score=2,
        )

    def _check_smi(self, cache: dict) -> Optional[TriggerAlert]:
        """
        Smart Money Index (SMI) divergence check.
        smi_data session_state me Tab 2 se store hota hai.
        """
        smi_data = cache.get("smi_data", {})
        if not smi_data:
            return None

        signal        = smi_data.get("signal", "")
        morning_move  = smi_data.get("morning_move", 0)
        evening_move  = smi_data.get("evening_move", 0)

        # Exact signal names jo _calc_smi() return karta hai (spaces, no underscores)
        if signal == "INSTITUTIONS QUIETLY BUYING":
            emoji   = "📈"
            title   = "Smart Money Quietly BUYING!"
            meaning = (
                "Subah market gira (retail panic).\n"
                "Shaam market recover kiya (institutions buy kiya).\n"
                "Kal ke liye BULLISH bias strong hai."
            )
            action = (
                "Kal morning CE opportunities dekho.\n"
                "Dip pe buying consider karo.\n"
                "GEX aur PCR se confirm karo."
            )
            sig_key = "SMI_BUYING"
        elif signal == "DISTRIBUTION — INSTITUTIONS SELLING":
            emoji   = "📉"
            title   = "Smart Money Quietly SELLING!"
            meaning = (
                "Subah market chada (retail FOMO).\n"
                "Shaam market gira (institutions sell kiya).\n"
                "Kal ke liye BEARISH bias strong hai."
            )
            action = (
                "Kal morning PE opportunities dekho.\n"
                "Rally pe selling consider karo.\n"
                "GEX aur PCR se confirm karo."
            )
            sig_key = "SMI_SELLING"
        else:
            return None   # BULLISH MOMENTUM / BEARISH PRESSURE = alert nahi

        detail = (
            f"Signal       : {emoji} {title}\n"
            f"Morning Move : {morning_move:+.0f} pts  (Retail activity)\n"
            f"Evening Move : {evening_move:+.0f} pts  (Institution activity)\n"
            f"Matlab       : {meaning}"
        )
        return TriggerAlert(
            time=datetime.now().strftime("%H:%M"),
            category="IMPORTANT",
            signal_key=sig_key,
            title=title,
            detail=detail,
            action=action,
            score=2,
        )

    def _check_iv_rank(self, cache: dict) -> Optional[TriggerAlert]:
        """
        IV Rank > 70% — option selling opportunity.
        """
        iv_data = cache.get("iv_data", {})
        ivr     = iv_data.get("iv_rank", 0)
        if ivr < 70:
            return None

        atm_iv  = iv_data.get("atm_iv", 0)
        iv_line = f"ATM IV  : {atm_iv:.1f}%\n" if atm_iv > 0 else ""

        detail = (
            f"IV Rank : {ivr:.0f}%  (HIGH — Historically Expensive)\n"
            f"{iv_line}"
            f"Matlab  : Options abhi bahut mehnge hain.\n"
            f"         Premium SELL karne ka accha mauka."
        )
        action = (
            "Iron Condor ya Strangle SELL setup dekho.\n"
            "VIX bhi check karo — dono high ho toh best opportunity.\n"
            "Hedge zaroor rakho — naked selling risky hai."
        )
        return TriggerAlert(
            time=datetime.now().strftime("%H:%M"),
            category="INFO",
            signal_key="IV_RANK_HIGH",
            title=f"IV Rank High — {ivr:.0f}% (Selling Opportunity)",
            detail=detail,
            action=action,
            score=1,
        )

    def send_trade_signal(self, sig: dict) -> bool:
        """
        BUY CE / BUY PE / Iron Condor signal aane pe Telegram alert bhejo.
        Same signal 30 min tak dobara nahi bhejega (cooldown).
        Returns True if alert was sent.
        """
        s = sig.get("signal", "")
        if s not in ("BUY CE", "BUY PE", "SELL — Iron Condor"):
            return False

        strike  = sig.get("strike", sig.get("sell_ce", ""))
        score   = sig.get("score",  0)
        vix     = sig.get("vix",    0)
        pcr     = sig.get("pcr",    0)
        iv_rank = sig.get("iv_rank", 0)
        conf    = sig.get("confluence", "—")
        now_str = datetime.now().strftime("%H:%M")

        sig_key = f"TRADE_{s}_{strike}_{datetime.now().strftime('%Y%m%d_%H%M')[:13]}"
        if self._in_cooldown(sig_key.rsplit("_", 1)[0]):
            return False

        if s == "BUY CE":
            emoji   = "📈🟢"
            entry   = sig.get("entry",  0)
            target  = sig.get("target", 0)
            sl      = sig.get("sl",     0)
            detail  = (
                f"Strike  : {strike} CE\n"
                f"Entry   : ₹{entry}\n"
                f"Target  : ₹{target}  (+{sig.get('gain_pct',0)}%)\n"
                f"SL      : ₹{sl}  (-{sig.get('loss_pct',0)}%)\n"
                f"Lots    : {sig.get('lots',1)}  |  Max Loss: ₹{sig.get('max_loss',0):,.0f}\n"
                f"Score   : {score}/100  |  Confluence: {conf}\n"
                f"VIX: {vix:.1f}  PCR: {pcr:.2f}  IV Rank: {iv_rank:.0f}%"
            )
            action = f"NIFTY CE {strike} khareedon. Entry: ₹{entry}, Target: ₹{target}, SL: ₹{sl}"
        elif s == "BUY PE":
            emoji   = "📉🔴"
            entry   = sig.get("entry",  0)
            target  = sig.get("target", 0)
            sl      = sig.get("sl",     0)
            detail  = (
                f"Strike  : {strike} PE\n"
                f"Entry   : ₹{entry}\n"
                f"Target  : ₹{target}  (+{sig.get('gain_pct',0)}%)\n"
                f"SL      : ₹{sl}  (-{sig.get('loss_pct',0)}%)\n"
                f"Lots    : {sig.get('lots',1)}  |  Max Loss: ₹{sig.get('max_loss',0):,.0f}\n"
                f"Score   : {score}/100  |  Confluence: {conf}\n"
                f"VIX: {vix:.1f}  PCR: {pcr:.2f}  IV Rank: {iv_rank:.0f}%"
            )
            action = f"NIFTY PE {strike} khareedon. Entry: ₹{entry}, Target: ₹{target}, SL: ₹{sl}"
        else:  # Iron Condor
            emoji      = "🦅🟡"
            sell_ce    = sig.get("sell_ce",    "")
            sell_pe    = sig.get("sell_pe",    "")
            total_prem = sig.get("total_prem", 0)
            sl_prem    = sig.get("sl_premium", 0)
            detail  = (
                f"Sell CE : {sell_ce}  |  Sell PE: {sell_pe}\n"
                f"Premium : ₹{total_prem:.0f} collect karo\n"
                f"SL Rule : ₹{sl_prem:.0f} se upar gaya toh exit\n"
                f"Score   : {score}/100  |  IV Rank: {iv_rank:.0f}%\n"
                f"VIX: {vix:.1f}  PCR: {pcr:.2f}"
            )
            action = f"CE {sell_ce} + PE {sell_pe} SELL karo. Premium: ₹{total_prem:.0f}. SL: ₹{sl_prem:.0f}"

        alert = TriggerAlert(
            time=now_str, category="URGENT",
            signal_key=sig_key.rsplit("_", 1)[0],
            title=f"{emoji} {s} SIGNAL — Strike {strike}",
            detail=detail, action=action, score=3,
        )
        self._mark_sent(alert.signal_key)
        if self.enabled and self.bot_token and self.chat_id:
            self._send_telegram(alert)
            logger.info(f"Trade signal Telegram sent: {s} {strike}")
            return True
        return False

    def send_uoa_alert(self, alert) -> bool:
        """
        UOA alert aane pe Telegram bhejo — NIFTY aur BANKNIFTY dono ke liye.
        Same strike 30 min tak dobara nahi bhejega.
        Returns True if alert was sent.
        """
        sig_key = f"UOA_{alert.symbol}_{alert.opt_type}_{int(alert.strike)}"
        if self._in_cooldown(sig_key):
            return False

        is_bull   = "BULL" in alert.sentiment
        dir_emoji = "📈" if is_bull else "📉"
        fire_tag  = " 🔥 FIRE" if alert.is_fire else ""
        mult_tag  = f"{alert.mult:.1f}x{fire_tag}"
        sentiment = alert.sentiment.replace("_", " ")

        depth_line = f"\nITM Depth: {alert.itm_depth_pct:.1f}%" if alert.itm_depth_pct > 0 else ""
        spot_line  = f"\nSpot     : ₹{alert.spot_at_alert:,.0f}" if alert.spot_at_alert > 0 else ""

        detail = (
            f"Symbol   : {alert.symbol}\n"
            f"Strike   : {int(alert.strike)} {alert.opt_type}\n"
            f"Volume   : {mult_tag} avg se zyada\n"
            f"Sentiment: {dir_emoji} {sentiment}"
            f"{depth_line}{spot_line}"
        )
        action = (
            f"Dashboard pe UOA panel dekho.\n"
            f"PCR + GEX se confirm karo phir trade lo."
        )
        title = f"{dir_emoji} UOA — {alert.symbol} {int(alert.strike)} {alert.opt_type} ({mult_tag})"

        tg_alert = TriggerAlert(
            time=datetime.now().strftime("%H:%M"),
            category="URGENT" if alert.is_fire else "IMPORTANT",
            signal_key=sig_key,
            title=title,
            detail=detail,
            action=action,
            score=3 if alert.is_fire else 2,
        )
        self._mark_sent(sig_key)
        if self.enabled and self.bot_token and self.chat_id:
            self._send_telegram(tg_alert)
            logger.info(f"UOA Telegram sent: {alert.symbol} {int(alert.strike)} {alert.opt_type} {alert.mult:.1f}x")
            return True
        return False

    # ── Cooldown helpers ──────────────────────────────────────────────────────

    def _in_cooldown(self, signal_key: str) -> bool:
        """True = same signal recently bheja, dobara mat bhejo."""
        last_time = self._last_sent.get(signal_key)
        if last_time is None:
            return False
        elapsed = (datetime.now() - last_time).total_seconds()
        return elapsed < (self.COOLDOWN_MINUTES * 60)

    def _mark_sent(self, signal_key: str):
        """Signal sent — timestamp save karo."""
        self._last_sent[signal_key] = datetime.now()

    # ── Telegram sender ───────────────────────────────────────────────────────

    def _send_telegram(self, alert: TriggerAlert):
        """
        Telegram Bot API se message bhejo.
        HTML parse mode use karta hai.
        Error aane pe crash nahi karta — sirf log karta hai.
        """
        try:
            cat_emoji = CATEGORY_EMOJI.get(alert.category, "📢")

            text = (
                f"{cat_emoji} <b>NSE F&amp;O ALERT</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>{alert.title}</b>\n\n"
                f"<pre>{alert.detail}</pre>\n\n"
                f"<b>&#9889; Kya karo:</b>\n"
                f"{alert.action}\n\n"
                f"&#128336; Time: {alert.time}"
            )

            url  = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            resp = requests.post(
                url,
                json={
                    "chat_id":    self.chat_id,
                    "text":       text,
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
            if resp.ok:
                logger.info(f"Telegram alert sent: {alert.signal_key}")
            else:
                logger.warning(
                    f"Telegram failed [{resp.status_code}]: {resp.text[:200]}"
                )
        except requests.exceptions.Timeout:
            logger.warning("Telegram send timeout — skipping")
        except Exception as exc:
            logger.error(f"Telegram send error: {exc}")
