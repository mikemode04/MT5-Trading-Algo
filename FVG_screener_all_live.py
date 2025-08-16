# This work is licensed under a Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0) https://creativecommons.org/licenses/by-nc-sa/4.0/
# © LuxAlgo - Live FVG Screener with Gmail Alerts

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import logging
import time
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Gmail configuration - Update these with your credentials
GMAIL_USER = "algotradingmike@gmail.com"  # Change this to your Gmail
GMAIL_PASSWORD = "alxy xltn ahbn ikal"  # Use App Password, not regular password
GMAIL_TO = "algotradingmike@gmail.com"  # Change this to recipient email

@dataclass
class FVG:
    """Fair Value Gap data structure"""
    max_price: float
    min_price: float
    is_bull: bool
    timestamp: datetime
    bar_index: int

class LiveFVGScreener:
    """Live Fair Value Gap Screener with Gmail Alerts"""
    
    def __init__(self, 
                 timeframe: int = mt5.TIMEFRAME_H4,
                 threshold_percent: float = 0.0,
                 auto_threshold: bool = False,
                 lookback_days: int = 30,
                 custom_symbols: Optional[List[str]] = None):
        
        self.timeframe = timeframe
        self.threshold_percent = threshold_percent
        self.auto_threshold = auto_threshold
        self.lookback_days = lookback_days
        self.custom_symbols = custom_symbols
        
        # Track all symbols and their FVGs
        self.symbol_data: Dict[str, List[FVG]] = {}
        self.last_prices: Dict[str, float] = {}
        self.alerted_fvgs: Dict[str, set] = {}  # Track which FVGs have been alerted for proximity
        
        # Email management with rate limiting
        self.last_summary_sent = None  # Track when last summary was sent
        self.summary_cooldown = 600  # Increased to 10 minutes between summary emails
        self.active_alert_count = 0  # Track number of active alerts
        self.email_sent_today = 0  # Track emails sent today
        self.last_email_reset = datetime.now().date()  # Track when to reset daily counter
        self.max_daily_emails = 80  # Conservative limit (Gmail allows 100/day for regular accounts)
        self.email_disabled = False  # Flag to disable emails when limit is reached
        
        # HTML file management
        self.html_file_path = r"c:\Users\mike\OneDrive - Universitetet i Oslo\API\Algo v2\FVG_Live_Report.html"
        self.last_html_update = None  # Track when HTML was last updated
        self.html_update_interval = 300  # Update HTML every 5 minutes (300 seconds)
        
        # Proximity settings
        self.proximity_percent = 0.1  # Alert when price is within 0.1% of FVG zone
        
        # Initialize MT5
        self.initialize_mt5()
        
        # Get forex symbols (either custom list or all available)
        if custom_symbols:
            self.forex_symbols = custom_symbols
            logger.info(f"Using custom symbols: {len(self.forex_symbols)} symbols")
        else:
            self.forex_symbols = self.get_forex_symbols()
            logger.info(f"Found {len(self.forex_symbols)} forex symbols")
    
    def initialize_mt5(self) -> bool:
        """Initialize MT5 connection"""
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return False
        
        logger.info("MT5 initialized successfully")
        return True
    
    def get_forex_symbols(self) -> List[str]:
        """Get all available forex symbols from MT5"""
        symbols = mt5.symbols_get()
        if symbols is None:
            logger.error("Failed to get symbols")
            return []
        
        # Filter for forex symbols (usually contain USD, EUR, GBP, etc.)
        forex_symbols = []
        # Expanded list of forex currencies including exotic pairs
        forex_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD', 
                           'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'TRY', 'ZAR',
                           'MXN', 'SGD', 'HKD', 'CNH', 'RUB', 'INR', 'BRL', 'KRW']
        
        for symbol in symbols:
            symbol_name = symbol.name
            # Check if symbol contains forex currency pairs
            if (any(curr in symbol_name for curr in forex_currencies) and 
                len(symbol_name) == 6 and  # Standard forex pair length
                symbol.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL):
                forex_symbols.append(symbol_name)
        
        return sorted(forex_symbols[:50])  # Increased limit to 50 for more pairs
    
    def check_daily_email_limit(self) -> bool:
        """Check and update daily email limit"""
        current_date = datetime.now().date()
        
        # Reset counter if it's a new day
        if current_date != self.last_email_reset:
            self.email_sent_today = 0
            self.last_email_reset = current_date
            self.email_disabled = False
            logger.info("Daily email counter reset")
        
        # Check if we've hit the limit
        if self.email_sent_today >= self.max_daily_emails:
            if not self.email_disabled:
                logger.warning(f"Daily email limit reached ({self.max_daily_emails}). Disabling emails until tomorrow.")
                self.email_disabled = True
            return False
        
        return True
    
    def send_gmail_alert(self, subject: str, message: str, is_html: bool = False):
        """Send Gmail alert with HTML support and rate limiting"""
        # Check if emails are disabled due to rate limiting
        if not self.check_daily_email_limit():
            logger.warning(f"Email blocked due to daily limit. Emails sent today: {self.email_sent_today}")
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = GMAIL_USER
            msg['To'] = GMAIL_TO
            msg['Subject'] = subject
            
            # Attach message as HTML or plain text
            if is_html:
                msg.attach(MIMEText(message, 'html'))
            else:
                msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            text = msg.as_string()
            server.sendmail(GMAIL_USER, GMAIL_TO, text)
            server.quit()
            
            # Update counter on successful send
            self.email_sent_today += 1
            logger.info(f"Email sent: {subject} (Daily count: {self.email_sent_today}/{self.max_daily_emails})")
            return True
            
        except Exception as e:
            error_msg = str(e)
            
            # Check for specific Gmail rate limiting errors
            if "Daily user sending limit exceeded" in error_msg or "5.4.5" in error_msg:
                logger.error("Gmail daily sending limit exceeded. Disabling emails for today.")
                self.email_disabled = True
                self.email_sent_today = self.max_daily_emails  # Set to max to prevent further attempts
                return False
            elif "Message rate limit exceeded" in error_msg:
                logger.error("Gmail rate limit exceeded. Waiting before retry...")
                time.sleep(60)  # Wait 1 minute before allowing next email
                return False
            else:
                logger.error(f"Failed to send email: {e}")
                return False
    
    def should_update_html_file(self) -> bool:
        """Check if HTML file should be updated (every 5 minutes)"""
        if self.last_html_update is None:
            return True
        
        now = datetime.now()
        return (now - self.last_html_update).total_seconds() >= self.html_update_interval
    
    def generate_html_file(self):
        """Generate and save HTML file with live FVG data"""
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            symbol_status = {}
            
            # Same logic as email generation but for HTML file
            for symbol, fvgs in self.symbol_data.items():
                if symbol not in self.last_prices:
                    continue
                
                current_price = self.last_prices[symbol]
                bull_count = 0
                bear_count = 0
                latest_time = None
                state = "INGEN FVG"
                state_detail = ""
                
                # Priority: AKTIV > NÆRMER > OVERVÅKET > INGEN FVG
                for fvg in fvgs:
                    if fvg.is_bull:
                        bull_count += 1
                        if current_price <= fvg.max_price:
                            if latest_time is None or fvg.timestamp > latest_time:
                                state = "BULL AKTIV"
                                state_detail = f"{fvg.timestamp.strftime('%d/%m %H:%M')}"
                                latest_time = fvg.timestamp
                        elif self.is_approaching_fvg(current_price, fvg, True):
                            if state != "BULL AKTIV" and (latest_time is None or fvg.timestamp > latest_time):
                                state = "BULL NÆRMER"
                                state_detail = f"{fvg.timestamp.strftime('%d/%m %H:%M')}"
                                latest_time = fvg.timestamp
                    else:
                        bear_count += 1
                        if current_price >= fvg.min_price:
                            if latest_time is None or fvg.timestamp > latest_time:
                                state = "BEAR AKTIV"
                                state_detail = f"{fvg.timestamp.strftime('%d/%m %H:%M')}"
                                latest_time = fvg.timestamp
                        elif self.is_approaching_fvg(current_price, fvg, False):
                            if state not in ("BULL AKTIV", "BEAR AKTIV") and (latest_time is None or fvg.timestamp > latest_time):
                                state = "BEAR NÆRMER"
                                state_detail = f"{fvg.timestamp.strftime('%d/%m %H:%M')}"
                                latest_time = fvg.timestamp
                
                if bull_count > 0 or bear_count > 0:
                    if state == "INGEN FVG":
                        state = "OVERVÅKET"
                
                symbol_status[symbol] = {
                    'state': state,
                    'detail': state_detail,
                    'bull': bull_count,
                    'bear': bear_count,
                    'total': bull_count + bear_count,
                    'price': current_price
                }
            
            # Group symbols by status
            grupper = [
                ("BULL AKTIV", [], "#28a745", "🟢"),
                ("BEAR AKTIV", [], "#dc3545", "🔴"),
                ("BULL NÆRMER", [], "#ffc107", "🟡"),
                ("BEAR NÆRMER", [], "#fd7e14", "🟠"),
                ("OVERVÅKET", [], "#6c757d", "⚪"),
            ]
            
            for symbol, data in symbol_status.items():
                for group, lst, color, icon in grupper:
                    if data['state'] == group:
                        lst.append((symbol, data))
            
            # Generate HTML content with auto-refresh
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>📊 Live FVG Screener - {current_time}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            margin: 0;
            padding: 10px;
            background-color: #f8f9fa;
            font-size: 14px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .header p {{
            margin: 5px 0 0 0;
            opacity: 0.9;
            font-size: 14px;
        }}
        .content {{
            padding: 15px;
        }}
        .alert-section {{
            margin-bottom: 25px;
        }}
        .alert-header {{
            display: flex;
            align-items: center;
            margin-bottom: 10px;
            padding: 8px 12px;
            border-radius: 5px;
            font-weight: bold;
            font-size: 16px;
        }}
        .alert-active {{
            background-color: #d4edda;
            color: #155724;
        }}
        .alert-approaching {{
            background-color: #fff3cd;
            color: #856404;
        }}
        .alert-monitored {{
            background-color: #f8f9fa;
            color: #6c757d;
        }}
        .symbol-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
        }}
        .symbol-table th {{
            background-color: #f8f9fa;
            padding: 8px 10px;
            text-align: left;
            border-bottom: 2px solid #dee2e6;
            font-weight: 600;
            font-size: 12px;
        }}
        .symbol-table td {{
            padding: 6px 10px;
            border-bottom: 1px solid #dee2e6;
            font-size: 12px;
        }}
        .symbol-table tr:hover {{
            background-color: #f8f9fa;
        }}
        .status-badge {{
            padding: 3px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .status-bull-aktiv {{
            background-color: #d4edda;
            color: #155724;
        }}
        .status-bear-aktiv {{
            background-color: #f8d7da;
            color: #721c24;
        }}
        .status-bull-nærmer {{
            background-color: #fff3cd;
            color: #856404;
        }}
        .status-bear-nærmer {{
            background-color: #fce4e0;
            color: #975a16;
        }}
        .status-overvåket {{
            background-color: #e2e3e5;
            color: #383d41;
        }}
        .summary-box {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }}
        .summary-stats {{
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 15px;
        }}
        .stat-item {{
            text-align: center;
            flex: 1;
            min-width: 80px;
        }}
        .stat-value {{
            font-size: 20px;
            font-weight: bold;
            color: #495057;
        }}
        .stat-label {{
            font-size: 12px;
            color: #6c757d;
        }}
        .footer {{
            text-align: center;
            padding: 15px;
            background-color: #f8f9fa;
            border-top: 1px solid #dee2e6;
            font-size: 11px;
            color: #6c757d;
        }}
        .live-indicator {{
            display: inline-block;
            width: 8px;
            height: 8px;
            background-color: #28a745;
            border-radius: 50%;
            margin-right: 5px;
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
            100% {{ opacity: 1; }}
        }}
        
        /* Mobile responsive */
        @media (max-width: 768px) {{
            .container {{
                margin: 5px;
                border-radius: 5px;
            }}
            .header h1 {{
                font-size: 20px;
            }}
            .content {{
                padding: 10px;
            }}
            .summary-stats {{
                gap: 10px;
            }}
            .stat-item {{
                min-width: 60px;
            }}
            .symbol-table th,
            .symbol-table td {{
                padding: 4px 6px;
                font-size: 11px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><span class="live-indicator"></span>📊 LIVE FVG SCREENER</h1>
            <p>Sist oppdatert: {current_time} • Neste oppdatering: {(datetime.now() + timedelta(seconds=300)).strftime('%H:%M:%S')}</p>
        </div>
        
        <div class="content">
"""
            
            # Add tables for each group
            for group, lst, color, icon in grupper:
                if lst:
                    css_class = group.lower().replace(' ', '-')
                    
                    if 'AKTIV' in group:
                        section_class = 'alert-active'
                    elif 'NÆRMER' in group:
                        section_class = 'alert-approaching'
                    else:
                        section_class = 'alert-monitored'
                    
                    html_content += f"""
            <div class="alert-section">
                <div class="alert-header {section_class}">
                    {icon} {group} ({len(lst)} symboler)
                </div>
                <table class="symbol-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Status</th>
                            <th>Pris</th>
                            <th>Tid</th>
                            <th>FVG Info</th>
                        </tr>
                    </thead>
                    <tbody>
"""
                    
                    for symbol, data in sorted(lst):
                        status_class = f"status-{css_class}"
                        fvg_info = f"{data['total']} FVG"
                        if data['bull'] > 0 and data['bear'] > 0:
                            fvg_info += f" ({data['bull']}🟢 {data['bear']}🔴)"
                        elif data['bull'] > 0:
                            fvg_info += f" ({data['bull']}🟢)"
                        elif data['bear'] > 0:
                            fvg_info += f" ({data['bear']}🔴)"
                        
                        html_content += f"""
                        <tr>
                            <td><strong>{symbol}</strong></td>
                            <td><span class="status-badge {status_class}">{data['state']}</span></td>
                            <td>{data['price']:.5f}</td>
                            <td>{data['detail']}</td>
                            <td>{fvg_info}</td>
                        </tr>
"""
                    
                    html_content += """
                    </tbody>
                </table>
            </div>
"""
            
            # Add summary
            antall = len(symbol_status)
            total_fvg = sum(d['total'] for d in symbol_status.values())
            total_bull = sum(d['bull'] for d in symbol_status.values())
            total_bear = sum(d['bear'] for d in symbol_status.values())
            aktive_alerts = sum(1 for d in symbol_status.values() if 'AKTIV' in d['state'])
            nærmer_alerts = sum(1 for d in symbol_status.values() if 'NÆRMER' in d['state'])
            
            html_content += f"""
            <div class="summary-box">
                <h3 style="margin-top: 0;">📈 SAMMENDRAG</h3>
                <div class="summary-stats">
                    <div class="stat-item">
                        <div class="stat-value">{antall}</div>
                        <div class="stat-label">Symboler</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{total_fvg}</div>
                        <div class="stat-label">Totalt FVG</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{total_bull}</div>
                        <div class="stat-label">Bull FVG</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{total_bear}</div>
                        <div class="stat-label">Bear FVG</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{aktive_alerts}</div>
                        <div class="stat-label">Aktive Alerts</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">{nærmer_alerts}</div>
                        <div class="stat-label">Nærmer Seg</div>
                    </div>
                </div>
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d;">
                    📧 E-post: {self.email_sent_today}/{self.max_daily_emails} • 🌐 HTML: Auto-oppdatering hver 5. minutt
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>🔄 Siden oppdateres automatisk hver 5. minutt • 📱 Mobilvennlig • 💾 Lagret i OneDrive</p>
            <p>Generert av Live FVG Screener • © LuxAlgo</p>
        </div>
    </div>
</body>
</html>
"""
            
            # Write HTML file
            with open(self.html_file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            self.last_html_update = datetime.now()
            logger.info(f"HTML file updated: {self.html_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to generate HTML file: {e}")
    
    def get_data(self, symbol: str, bars: int = None) -> pd.DataFrame:
        """Get OHLC data from MT5"""
        if bars is None:
            bars = self.lookback_days * 6  # 6 bars per day for 4H timeframe
        
        try:
            rates = mt5.copy_rates_from_pos(symbol, self.timeframe, 0, bars)
            if rates is None:
                return None
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df = df.set_index('time')
            
            return df
        except Exception as e:
            logger.error(f"Error getting data for {symbol}: {e}")
            return None
    
    def calculate_threshold(self, df: pd.DataFrame) -> float:
        """Calculate dynamic threshold if auto mode is enabled"""
        if self.auto_threshold:
            # Calculate cumulative average of (high - low) / low
            hl_ratio = (df['high'] - df['low']) / df['low']
            return hl_ratio.expanding().mean().iloc[-1]
        else:
            return self.threshold_percent / 100
    
    def detect_fvgs_for_symbol(self, symbol: str) -> List[FVG]:
        """Detect all FVGs for a symbol"""
        df = self.get_data(symbol)
        if df is None or len(df) < 3:
            return []
        
        fvgs = []
        
        # Process each bar for FVG detection
        for i in range(2, len(df)):
            current = df.iloc[i]
            prev1 = df.iloc[i-1]
            prev2 = df.iloc[i-2]
            
            threshold = self.calculate_threshold(df.iloc[:i+1])
            
            # Bullish FVG: low > high[2] and close[1] > high[2]
            bull_fvg = (current['low'] > prev2['high'] and 
                       prev1['close'] > prev2['high'] and
                       (current['low'] - prev2['high']) / prev2['high'] > threshold)
            
            # Bearish FVG: high < low[2] and close[1] < low[2]
            bear_fvg = (current['high'] < prev2['low'] and 
                       prev1['close'] < prev2['low'] and
                       (prev2['low'] - current['high']) / current['high'] > threshold)
            
            if bull_fvg:
                fvg = FVG(
                    max_price=current['low'],
                    min_price=prev2['high'],
                    is_bull=True,
                    timestamp=current.name,
                    bar_index=i
                )
                fvgs.append(fvg)
            
            elif bear_fvg:
                fvg = FVG(
                    max_price=prev2['low'],
                    min_price=current['high'],
                    is_bull=False,
                    timestamp=current.name,
                    bar_index=i
                )
                fvgs.append(fvg)
        
        return fvgs
    
    def check_price_alerts(self, symbol: str, current_price: float):
        """Check if current price hits FVG levels and update tracking data"""
        if symbol not in self.symbol_data:
            return
        
        # Update last price (this will be used by summary email generation)
        self.last_prices[symbol] = current_price
    
    def is_approaching_fvg(self, current_price: float, fvg: FVG, is_bull: bool) -> bool:
        """Check if price is approaching FVG zone within proximity threshold"""
        if is_bull:
            # For bullish FVG, check if price is approaching from above
            if current_price > fvg.max_price:
                distance = current_price - fvg.max_price
                proximity_threshold = fvg.max_price * (self.proximity_percent / 100)
                return distance <= proximity_threshold
        else:
            # For bearish FVG, check if price is approaching from below
            if current_price < fvg.min_price:
                distance = fvg.min_price - current_price
                proximity_threshold = current_price * (self.proximity_percent / 100)
                return distance <= proximity_threshold
        
        return False
    
    def scan_symbol(self, symbol: str):
        """Scan single symbol for FVGs and check alerts"""
        try:
            # Get current price
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return
            
            current_price = (tick.bid + tick.ask) / 2
            
            # Initial FVG detection if not done yet
            if symbol not in self.symbol_data:
                logger.info(f"Initial FVG scan for {symbol}")
                fvgs = self.detect_fvgs_for_symbol(symbol)
                self.symbol_data[symbol] = fvgs
                logger.info(f"{symbol}: Found {len(fvgs)} FVGs")
            
            # Check for price alerts
            self.check_price_alerts(symbol, current_price)
            
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
    
    def should_send_summary_email(self) -> bool:
        """Determine if a summary email should be sent based on conditions"""
        # Don't send if emails are disabled
        if self.email_disabled:
            return False
        
        now = datetime.now()
        
        # Send if there are active alerts and enough time has passed (reduced frequency for alerts)
        if self.active_alert_count > 0:
            if self.last_summary_sent is None:
                return True
            # For active alerts, send every 30 minutes instead of 5 minutes
            if (now - self.last_summary_sent).total_seconds() >= 1800:  # 30 minutes
                return True
        
        # Send periodic update if cooldown period has passed and it's first time
        if self.last_summary_sent is None:
            return True
        
        # For non-alert summaries, use the longer cooldown period
        if (now - self.last_summary_sent).total_seconds() >= self.summary_cooldown:
            return True
        
        return False

    def run_live_screening(self, scan_interval: int = 60):
        """Run live FVG screening with intelligent summary email alerts"""
        logger.info(f"Starting live FVG screening for {len(self.forex_symbols)} symbols")
        logger.info(f"Scan interval: {scan_interval} seconds")
        
        # Initial scan for all symbols
        for symbol in self.forex_symbols:
            self.scan_symbol(symbol)
            time.sleep(0.5)  # Small delay between symbols
        
        logger.info("Initial scan complete. Starting live monitoring...")
        
        # Send initial summary email
        try:
            subject, html_message = self.generate_fvg_summary_email()
            if self.send_gmail_alert(subject, html_message, is_html=True):
                self.last_summary_sent = datetime.now()
                logger.info("Initial summary email sent successfully")
            else:
                logger.warning("Failed to send initial summary email")
        except Exception as e:
            logger.error(f"Failed to send initial summary email: {e}")
        
        # Generate initial HTML file
        try:
            self.generate_html_file()
            logger.info(f"Initial HTML file created: {self.html_file_path}")
        except Exception as e:
            logger.error(f"Failed to create initial HTML file: {e}")
        
        # Live monitoring loop
        while True:
            try:
                # Scan all symbols
                for symbol in self.forex_symbols:
                    self.scan_symbol(symbol)
                
                # Check if we should send a summary email
                if self.should_send_summary_email():
                    subject, html_message = self.generate_fvg_summary_email()
                    if self.send_gmail_alert(subject, html_message, is_html=True):
                        self.last_summary_sent = datetime.now()
                        
                        if self.active_alert_count > 0:
                            logger.info(f"Summary email sent successfully - {self.active_alert_count} active alerts detected")
                        else:
                            logger.info(f"Periodic summary email sent successfully (no active alerts)")
                    else:
                        logger.warning("Failed to send summary email (likely rate limited)")
                else:
                    if self.email_disabled:
                        logger.info(f"Scan complete - emails disabled due to daily limit ({self.email_sent_today}/{self.max_daily_emails})")
                    else:
                        logger.info(f"Scan complete - no email sent (cooldown active, no alerts)")
                
                # Check if we should update HTML file (every 5 minutes)
                if self.should_update_html_file():
                    try:
                        self.generate_html_file()
                        logger.info("HTML file updated successfully")
                    except Exception as e:
                        logger.error(f"Failed to update HTML file: {e}")
                
                logger.info(f"Scanned {len(self.forex_symbols)} symbols. Next scan in {scan_interval}s")
                time.sleep(scan_interval)
                
            except KeyboardInterrupt:
                logger.info("Live screening stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in live screening: {e}")
                time.sleep(10)  # Wait before retrying
    
    def get_summary(self) -> Dict:
        """Get summary of all detected FVGs"""
        summary = {}
        total_fvgs = 0
        
        for symbol, fvgs in self.symbol_data.items():
            bull_count = sum(1 for fvg in fvgs if fvg.is_bull)
            bear_count = len(fvgs) - bull_count
            
            summary[symbol] = {
                'total_fvgs': len(fvgs),
                'bull_fvgs': bull_count,
                'bear_fvgs': bear_count
            }
            total_fvgs += len(fvgs)
        
        summary['TOTAL'] = total_fvgs
        return summary
    
    def close_mt5(self):
        """Close MT5 connection"""
        mt5.shutdown()
        logger.info("MT5 connection closed")
    
    def generate_fvg_summary_email(self) -> tuple[str, str]:
        """Generate a professional HTML-formatted FVG summary email"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        symbol_status = {}
        
        for symbol, fvgs in self.symbol_data.items():
            if symbol not in self.last_prices:
                continue
            
            current_price = self.last_prices[symbol]
            bull_count = 0
            bear_count = 0
            latest_time = None
            state = "INGEN FVG"
            state_detail = ""
            
            # Priority: AKTIV > NÆRMER > OVERVÅKET > INGEN FVG
            for fvg in fvgs:
                if fvg.is_bull:
                    bull_count += 1
                    if current_price <= fvg.max_price:
                        if latest_time is None or fvg.timestamp > latest_time:
                            state = "BULL AKTIV"
                            state_detail = f"{fvg.timestamp.strftime('%d/%m %H:%M')}"

                            latest_time = fvg.timestamp
                else:
                    bear_count += 1
                    if current_price >= fvg.min_price:
                        if latest_time is None or fvg.timestamp > latest_time:
                            state = "BEAR AKTIV"
                            state_detail = f"{fvg.timestamp.strftime('%d/%m %H:%M')}"

                            latest_time = fvg.timestamp
            
            if bull_count > 0 or bear_count > 0:
                if state == "INGEN FVG":
                    state = "OVERVÅKET"
            
            symbol_status[symbol] = {
                'state': state,
                'detail': state_detail,
                'bull': bull_count,
                'bear': bear_count,
                'total': bull_count + bear_count,
                'price': current_price
            }
        
        # Gruppering med fargekoder
        grupper = [
            ("BULL AKTIV", [], "#28a745", "🟢"),
            ("BEAR AKTIV", [], "#dc3545", "🔴"),
            ("BULL NÆRMER", [], "#ffc107", "🟡"),
            ("BEAR NÆRMER", [], "#fd7e14", "🟠"),
            ("OVERVÅKET", [], "#6c757d", "⚪"),
        ]
        
        for symbol, data in symbol_status.items():
            for group, lst, color, icon in grupper:
                if data['state'] == group:
                    lst.append((symbol, data))
        
        # Generer HTML e-post
        subject = f"📊 FVG OVERSIKT - {current_time}"
        
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f8f9fa;
                }}
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                }}
                .header p {{
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                }}
                .content {{
                    padding: 20px;
                }}
                .alert-section {{
                    margin-bottom: 30px;
                }}
                .alert-header {{
                    display: flex;
                    align-items: center;
                    margin-bottom: 15px;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    font-size: 16px;
                }}
                .alert-active {{
                    background-color: #d4edda;
                    color: #155724;
                }}
                .alert-approaching {{
                    background-color: #fff3cd;
                    color: #856404;
                }}
                .alert-monitored {{
                    background-color: #f8f9fa;
                    color: #6c757d;
                }}
                .symbol-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }}
                .symbol-table th {{
                    background-color: #f8f9fa;
                    padding: 12px;
                    text-align: left;
                    border-bottom: 2px solid #dee2e6;
                    font-weight: 600;
                }}
                .symbol-table td {{
                    padding: 10px 12px;
                    border-bottom: 1px solid #dee2e6;
                }}
                .symbol-table tr:hover {{
                    background-color: #f8f9fa;
                }}
                .status-badge {{
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                    text-transform: uppercase;
                }}
                .status-bull-aktiv {{
                    background-color: #d4edda;
                    color: #155724;
                }}
                .status-bear-aktiv {{
                    background-color: #f8d7da;
                    color: #721c24;
                }}
                .status-bull-nærmer {{
                    background-color: #fff3cd;
                    color: #856404;
                }}
                .status-bear-nærmer {{
                    background-color: #fce4e0;
                    color: #975a16;
                }}
                .status-overvåket {{
                    background-color: #e2e3e5;
                    color: #383d41;
                }}
                .summary-box {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin-top: 20px;
                }}
                .summary-stats {{
                    display: flex;
                    justify-content: space-between;
                    flex-wrap: wrap;
                }}
                .stat-item {{
                    text-align: center;
                    margin: 10px;
                }}
                .stat-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #495057;
                }}
                .stat-label {{
                    font-size: 14px;
                    color: #6c757d;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    background-color: #f8f9fa;
                    border-top: 1px solid #dee2e6;
                    font-size: 12px;
                    color: #6c757d;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 FVG SCREENER RAPPORT</h1>
                    <p>Generert: {current_time}</p>
                </div>
                
                <div class="content">
        """
        
        # Lag tabeller for hver gruppe
        for group, lst, color, icon in grupper:
            if lst:
                css_class = group.lower().replace(' ', '-')
                
                if 'AKTIV' in group:
                    section_class = 'alert-active'
                elif 'NÆRMER' in group:
                    section_class = 'alert-approaching'
                else:
                    section_class = 'alert-monitored'
                
                html_message += f"""
                    <div class="alert-section">
                        <div class="alert-header {section_class}">
                            {icon} {group} ({len(lst)} symboler)
                        </div>
                        <table class="symbol-table">
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Status</th>
                                    <th>Pris</th>
                                    <th>Tid</th>
                                    <th>FVG Info</th>
                                </tr>
                            </thead>
                            <tbody>
                """
                
                for symbol, data in sorted(lst):
                    status_class = f"status-{css_class}"
                    fvg_info = f"{data['total']} FVG"
                    if data['bull'] > 0 and data['bear'] > 0:
                        fvg_info += f" ({data['bull']}🟢 {data['bear']}🔴)"
                    elif data['bull'] > 0:
                        fvg_info += f" ({data['bull']}🟢)"
                    elif data['bear'] > 0:
                        fvg_info += f" ({data['bear']}🔴)"
                    
                    html_message += f"""
                                <tr>
                                    <td><strong>{symbol}</strong></td>
                                    <td><span class="status-badge {status_class}">{data['state']}</span></td>
                                    <td>{data['price']:.5f}</td>
                                    <td>{data['detail']}</td>
                                    <td>{fvg_info}</td>
                                </tr>
                    """
                
                html_message += """
                            </tbody>
                        </table>
                    </div>
                """
        
        # Sammendrag
        antall = len(symbol_status)
        total_fvg = sum(d['total'] for d in symbol_status.values())
        total_bull = sum(d['bull'] for d in symbol_status.values())
        total_bear = sum(d['bear'] for d in symbol_status.values())
        aktive_alerts = sum(1 for d in symbol_status.values() if 'AKTIV' in d['state'])
        nærmer_alerts = sum(1 for d in symbol_status.values() if 'NÆRMER' in d['state'])
        
        html_message += f"""
                    <div class="summary-box">
                        <h3 style="margin-top: 0;">📈 SAMMENDRAG</h3>
                        <div class="summary-stats">
                            <div class="stat-item">
                                <div class="stat-value">{antall}</div>
                                <div class="stat-label">Symboler</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">{total_fvg}</div>
                                <div class="stat-label">Totalt FVG</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">{total_bull}</div>
                                <div class="stat-label">Bull FVG</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">{total_bear}</div>
                                <div class="stat-label">Bear FVG</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">{aktive_alerts}</div>
                                <div class="stat-label">Aktive Alerts</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">{nærmer_alerts}</div>
                                <div class="stat-label">Nærmer Seg</div>
                            </div>
                        </div>
                        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #dee2e6; font-size: 12px; color: #6c757d;">
                            📧 E-post status: {self.email_sent_today}/{self.max_daily_emails} sendt i dag
                        </div>
                    </div>
                </div>
                
                <div class="footer">
                    <p>Automatisk rapport fra din FVG Screener • Neste oppdatering om {'30 minutter' if aktive_alerts > 0 else '10 minutter'}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Oppdater aktivt antall for e-postlogikk
        self.active_alert_count = aktive_alerts
        
        return subject, html_message


def main():
    """Main execution function for Live FVG Screener"""
    print("="*60)
    print("  LIVE FVG SCREENER WITH SMART EMAIL ALERTS")
    print("="*60)
    print("⚠️  IMPORTANT: Update Gmail credentials in the code before running!")
    print(f"Current Gmail User: {GMAIL_USER}")
    print(f"Current Gmail To: {GMAIL_TO}")
    print()
    print("📧 EMAIL BEHAVIOR:")
    print("• Initial summary sent immediately")
    print("• Active alerts: every 30 minutes (reduced frequency)")
    print("• Periodic summaries: every 10 minutes when no alerts")
    print("• Daily limit: 80 emails (auto-disabled when reached)")
    print("• Smart error handling for Gmail rate limits")
    print()
    print("🌐 HTML FILE BACKUP:")
    print("• Live HTML file updated every 5 minutes")
    print("• Saved to OneDrive for mobile/PC access")
    print("• Auto-refreshes every 5 minutes in browser")
    print("• Mobile-friendly responsive design")
    print("• Available at: c:\\Users\\mike\\OneDrive - Universitetet i Oslo\\API\\Algo v2\\FVG_Live_Report.html")
    print("="*60)
    
    # Specify custom currency pairs if needed
    custom_pairs = [
        # Major pairs
        'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD', 'NZDUSD',
        # Minor pairs
        'EURGBP', 'EURJPY', 'EURCHF', 'EURAUD', 'EURCAD', 'EURNZD',
        'GBPJPY', 'GBPCHF', 'GBPAUD', 'GBPCAD', 'GBPNZD',
        'AUDJPY', 'AUDCHF', 'AUDCAD', 'AUDNZD',
        'CADJPY', 'CADCHF', 'NZDJPY', 'NZDCHF', 'NZDCAD', 'CHFJPY',
        # Exotic pairs (add if available on your broker)
        'USDSEK', 'USDNOK', 'USDPLN', 'USDCZK', 'USDHUF', 'USDTRY', 'USDZAR',
        'EUROSEK', 'EURNOK', 'EURPLN', 'EURCZK', 'EURHUF', 'EURTRY', 'EURZAR',
        'GBPSEK', 'GBPNOK', 'GBPZAR'
    ]
    
    # Create live screener with custom pairs (comment out custom_symbols to use auto-detection)
    screener = LiveFVGScreener(
        timeframe=mt5.TIMEFRAME_H4,
        threshold_percent=0.0,
        auto_threshold=False,
        lookback_days=30
        # custom_symbols=custom_pairs  # Commented out to use auto-detection
    )
    
    # Optional: Adjust email frequency and limits
    screener.summary_cooldown = 600  # 10 minutes between non-alert summaries
    screener.max_daily_emails = 80   # Conservative daily limit
    screener.html_update_interval = 300  # Update HTML every 5 minutes
    # screener.proximity_percent = 0.1  # Adjust proximity threshold if needed
    
    try:
        # Show initial summary
        summary = screener.get_summary()
        
        print("\n" + "="*50)
        print("  INITIAL FVG SUMMARY")
        print("="*50)
        for symbol, data in summary.items():
            if symbol != 'TOTAL':
                print(f"{symbol}: {data['total_fvgs']} FVGs "
                      f"({data['bull_fvgs']} bull, {data['bear_fvgs']} bear)")
        print(f"\nTotal FVGs found: {summary.get('TOTAL', 0)}")
        print("="*50)
        
        # Start live monitoring (will run indefinitely)
        screener.run_live_screening(scan_interval=60)  # Scan every 60 seconds
        
    except KeyboardInterrupt:
        print("\n\nLive screening stopped by user.")
        print(f"📄 HTML report is still available at: {screener.html_file_path}")
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
    finally:
        screener.close_mt5()
        print("MT5 connection closed. Goodbye!")
        print(f"📄 Final HTML report saved at: {screener.html_file_path}")


def test_email():
    """Test function to verify Gmail setup with summary email"""
    screener = LiveFVGScreener()
    try:
        # Test basic email functionality
        success = screener.send_gmail_alert(
            "🧪 FVG Screener Test", 
            "This is a test email from your Live FVG Screener. If you receive this, your Gmail setup is working correctly!"
        )
        if success:
            print("Basic test email sent successfully!")
        else:
            print("Basic test email failed!")
        
        # Test summary email format (if there's data available)
        if screener.symbol_data:
            subject, html_message = screener.generate_fvg_summary_email()
            success = screener.send_gmail_alert(subject, html_message, is_html=True)
            if success:
                print("Summary email test sent successfully!")
            else:
                print("Summary email test failed!")
        else:
            print("No symbol data available for summary email test.")
            
        # Show current email status
        print(f"Daily email count: {screener.email_sent_today}/{screener.max_daily_emails}")
        print(f"Emails disabled: {screener.email_disabled}")
        print(f"HTML file path: {screener.html_file_path}")
        
        # Test HTML file generation
        try:
            screener.generate_html_file()
            print("HTML file test generated successfully!")
        except Exception as e:
            print(f"HTML file test failed: {e}")
            
    except Exception as e:
        print(f"Test email failed: {e}")
    finally:
        screener.close_mt5()


if __name__ == "__main__":
    # Uncomment the line below to test email functionality first
    # test_email()
    
    # Run the main live screener
    main()
