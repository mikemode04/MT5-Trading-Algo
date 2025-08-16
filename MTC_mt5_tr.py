import MetaTrader5 as mt5
import ccxt
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import logging
import os
import colorama
from colorama import Fore, Style, Back
import sys
from tqdm import tqdm
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Initialize colorama for colored console output
colorama.init()

class MT5FuturesStrategy:
    """
    MT5 Bitcoin Trading Strategy that:
    1. Uses leverage on BTCUSD
    2. Places market orders instead of limit orders
    3. Takes profit at fixed $ gain
    4. Uses both LONG and SHORT positions
    5. Provides live PnL monitoring

    def verify_position



    """

    def setup_email(self):
        """Setup email configuration for notifications"""
        # Store email configuration
        self.email_enabled = True
        
        # You can replace these with your actual Gmail credentials
        self.email_sender = "algotradingmike@gmail.com"  # Replace with your Gmail
        self.email_password = "alxy xltn ahbn ikal"   # Replace with app password (not regular password)
        self.email_recipient = "algotradingmike@gmail.com"  # Where to send notifications
        
        # Test email connection
        try:
            self.send_email("🚀 MT5 Futures Strategy Initialized", 
                        f"🤖 The trading bot has been started!\n\n" +
                        f"💰 Position size: ${self.position_size}\n" +
                        f"⚡ Leverage: {self.leverage}x\n" +
                        f"🎯 Target profit: ${self.take_profit_amount} per trade\n\n"
                        )
            self.print_live(f"{Fore.GREEN}Email notifications enabled and tested successfully{Style.RESET_ALL}", persist=True)
        except Exception as e:
            self.print_live(f"{Fore.RED}Error setting up email: {e}{Style.RESET_ALL}", persist=True)
            self.email_enabled = False

    def calculate_position_size(self):
        """
        Calculate position size for BTCUSD with USD settlement on MT5/IC Markets.
        Uses 90% of balance as margin, and IC Markets BTCUSD contract specs.
        """
        # Use 90% of balance as margin
        available_margin = self.balance * 0.95
        # Position size = available margin * leverage (IC Markets BTCUSD = 2x gearing)
        self.position_size = available_margin
        self.print_live(
            f"{Fore.CYAN}Position size set to ${self.position_size:.2f} for {self.leverage}x leverage (using ~{available_margin:.2f} USD margin){Style.RESET_ALL}",
            persist=True
        )
        return self.position_size
    
    def send_email(self, subject, body):
        """Send email notification"""
        if not hasattr(self, 'email_enabled') or not self.email_enabled:
            return
    
        try:
            # Create message
            message = MIMEMultipart()
            message['From'] = self.email_sender
            message['To'] = self.email_recipient
            message['Subject'] = f"MT5 Trader: {subject}"
    
            # Add body
            message.attach(MIMEText(body, 'plain'))
    
            # Connect to Gmail
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email_sender, self.email_password)
    
            # Send email
            server.send_message(message)
            server.quit()
    
            self.print_live(f"{Fore.CYAN}Email notification sent: {subject}{Style.RESET_ALL}", persist=True)
        except Exception as e:
            self.print_live(f"{Fore.RED}Failed to send email: {e}{Style.RESET_ALL}", persist=True)
            self.email_enabled = False  # Disable to prevent further errors
        
    def _get_mt5_timeframe(self, tf_str):
        """Map string timeframe (f.eks. '1m', '5m', '15m', '1h', '4h', '1d') til MT5 timeframe-konstant."""
        tf_map = {
            "1m": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "30m": mt5.TIMEFRAME_M30,
            "1h": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
            "1M": mt5.TIMEFRAME_MN1,
        }
        return tf_map.get(tf_str.lower(), mt5.TIMEFRAME_M1)
        
    def __init__(self, symbol="BTCUSD", timeframe="1m", server="ICMarkets-Demo", paper_mode=False, login=0, password=""):
        self.symbol = symbol  # MT5 symbol for Bitcoin (IC Markets: BTCUSD)
        self.timeframe = timeframe
        self.server = server
        self.login = login
        self.password = password
        self.test_mode = False
        self.paper_mode = paper_mode
        self.position_time = None
        self.position_size = 0  # Will be calculated dynamically
        self.leverage = 2  # IC Markets BTCUSD = 2x gearing
        self.shorts_only = False
        self.confirm_orders = False
    
        # Initialize the last_status_length attribute first
        self.last_status_length = 0
        self.start_time = datetime.now()
    
        # Logging
        logging.basicConfig(level=logging.INFO,
                           format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                           filename='mt5_futures_strategy.log')
        self.logger = logging.getLogger('MT5Futures')
    
        # Market data containers
        self.recent_ticks = []
        self.recent_trades = []
    
        # Strategy parameters - keeping algorithm the same
        self.base_overreaction_threshold = 1.5
        self.overreaction_threshold = self.base_overreaction_threshold
        self.patience_window = 13
        self.detection_window = 120
    
        # Strategy parameters - 2x leverage for IC Markets BTCUSD
        self.position_size = 1700
        self.take_profit_amount = 1
        self.max_loss_amount = 30
    
        # Limit order parameters (not used, but kept for compatibility)
        self.spread_placement = 0.5
        self.limit_order_offset = 0.0
        self.limit_order_timeout = 15
        self.order_update_interval = 30
    
        # Portfolio tracking
        self.balance = 15000  # Startkapital 15 000 USD
        self.position = 0
        self.position_entry = 0
        self.position_size_contracts = 0
        self.position_notional = 0
        self.position_ticket = 0
        self.trade_history = []
    
        # PnL tracking
        self.peak_unrealized_pnl = 0
        self.pnl_updates = []
    
        # Set up ccxt Deribit for orderbook only
        self.deribit_exchange = ccxt.deribit({'enableRateLimit': True})
    
        # Set up MT5 connection
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                self.print_live(f"{Fore.RED}MT5 initialization failed: {mt5.last_error()}{Style.RESET_ALL}", persist=True)
                raise Exception(f"MT5 initialization failed: {mt5.last_error()}")

                raise Exception(f"MT5 login failed: {mt5.last_error()}")
            self.print_live(f"{Fore.GREEN}Successfully connected to MetaTrader 5{Style.RESET_ALL}", persist=True)
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                self.print_live(f"{Fore.RED}Symbol {self.symbol} not found in MT5.{Style.RESET_ALL}", persist=True)
                raise Exception(f"Symbol {self.symbol} not found")
            if not mt5.symbol_select(self.symbol, True):
                self.print_live(f"{Fore.RED}Failed to select {self.symbol}: {mt5.last_error()}{Style.RESET_ALL}", persist=True)
                raise Exception(f"Failed to select {self.symbol}")
            self.fetch_account_data()
        except Exception as e:
            self.print_live(f"{Fore.RED}Failed to initialize MT5: {e}{Style.RESET_ALL}", persist=True)
            raise
    
        self.print_live(f"{Fore.CYAN}Strategy initialized for {symbol} with {self.leverage}x leverage{Style.RESET_ALL}", persist=True)
        self.print_live(f"{Fore.CYAN}Account balance: ${self.balance:.2f}{Style.RESET_ALL}", persist=True)
        self.print_live(f"{Fore.CYAN}Position size: ${self.position_size:.2f} × {self.leverage}x = ${self.position_size*self.leverage:.2f} exposure{Style.RESET_ALL}", persist=True)
        self.setup_email()

    def setup_confirmation(self):
        """Ask the user if they want to confirm orders before execution (MT5 version)"""
        try:
            print(f"\n{Fore.CYAN}═══════════════════════════════════════════════{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Do you want to confirm each order before execution (y/n)?{Style.RESET_ALL}")
            print(f"{Fore.CYAN}This will let you approve or reject orders before they are sent to the exchange.{Style.RESET_ALL}")
            print(f"{Fore.CYAN}═══════════════════════════════════════════════{Style.RESET_ALL}")
    
            response = input(f"{Fore.GREEN}Enable order confirmation (y/n): {Style.RESET_ALL}").strip().lower()
    
            if response == 'y' or response == 'yes':
                self.confirm_orders = True
                self.print_live(f"{Fore.GREEN}Order confirmation enabled! You will be asked to approve each order.{Style.RESET_ALL}", persist=True)
            else:
                self.confirm_orders = False
                self.print_live(f"{Fore.YELLOW}Order confirmation disabled. Orders will be executed automatically.{Style.RESET_ALL}", persist=True)
    
        except Exception as e:
            self.print_live(f"{Fore.RED}Error during order confirmation setup: {e}. Continuing without confirmation.{Style.RESET_ALL}", persist=True)
            self.confirm_orders = False

    def check_for_existing_positions(self):
        """
        Check if there are any existing positions on MT5 before opening new ones.
        Updates local state if a position is found.
        """
        try:
            import MetaTrader5 as mt5
            positions = mt5.positions_get(symbol=self.symbol)
            if positions and len(positions) > 0:
                # Found an existing position
                position = positions[0]  # Get first position for this symbol
                entry_price = position.price_open
                volume = position.volume
                position_type = "LONG" if position.type == mt5.POSITION_TYPE_BUY else "SHORT"
    
                self.print_live(
                    f"{Fore.RED}WARNING: Existing position found on MT5! {volume} lots at ${entry_price}{Style.RESET_ALL}",
                    persist=True
                )
    
                # Update local state to match MT5
                self.position_size_contracts = abs(volume)
                self.position = volume * entry_price * (1 if position.type == mt5.POSITION_TYPE_BUY else -1)
                self.position_entry = entry_price
                self.position_time = datetime.fromtimestamp(position.time)
                self.position_notional = abs(self.position)
                self.position_ticket = position.ticket
    
                return True
    
            # No positions found
            return False
        except Exception as e:
            self.print_live(f"{Fore.RED}Error checking for existing positions: {e}{Style.RESET_ALL}", persist=True)
            # Safer to assume we might have a position if we can't check
            return True
        
    def fetch_account_data(self):
        """
        Fetch real account data from MT5 and update local state.
        """
        try:
            account_info = mt5.account_info()
            if account_info:
                self.balance = account_info.balance
                self.equity = account_info.equity
                self.margin = account_info.margin
                self.free_margin = account_info.margin_free
                self.print_live(f"{Fore.GREEN}Account balance: ${self.balance:.2f}{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Account equity: ${self.equity:.2f}{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Margin level: {account_info.margin_level:.2f}%{Style.RESET_ALL}", persist=True)
                # Calculate position size based on account balance
                self.calculate_position_size()
            else:
                self.print_live(f"{Fore.RED}Failed to get account info: {mt5.last_error()}{Style.RESET_ALL}", persist=True)
                self.balance = 15000  # Default fallback
    
            # Check for existing positions
            positions = mt5.positions_get(symbol=self.symbol)
            if positions and len(positions) > 0:
                for position in positions:
                    # Found an open position in our symbol
                    self.position_size_contracts = position.volume
                    entry_price = position.price_open
                    position_type = "LONG" if position.type == mt5.POSITION_TYPE_BUY else "SHORT"
    
                    # Calculate position value
                    if position_type == "LONG":
                        self.position = self.position_size_contracts * entry_price
                    else:
                        self.position = -self.position_size_contracts * entry_price
    
                    self.position_entry = entry_price
                    self.position_notional = abs(self.position)
                    self.position_time = datetime.fromtimestamp(position.time)
                    self.position_ticket = position.ticket
    
                    self.print_live(
                        f"{Fore.YELLOW}Found existing {position_type} position: {abs(self.position_size_contracts):.2f} lots "
                        f"at ${self.position_entry:.2f} (${abs(self.position_notional):.2f}){Style.RESET_ALL}",
                        persist=True
                    )
                    break  # Only process the first position
    
            return True
        except Exception as e:
            self.print_live(f"{Fore.RED}Error fetching account data: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Error fetching account data: {e}")
            # Set a fallback default balance if we can't fetch it
            self.balance = 15000
            self.print_live(f"{Fore.YELLOW}Using default balance: ${self.balance:.2f}{Style.RESET_ALL}", persist=True)
            return False
        
    def update_account_data(self):
        """
        Update account data periodically from MT5 and refresh local state.
        """
        try:
            account_info = mt5.account_info()
            if account_info:
                self.balance = account_info.balance
                self.equity = account_info.equity
                self.margin = account_info.margin
                self.free_margin = account_info.margin_free
                self.print_live(f"{Fore.GREEN}Account balance updated: ${self.balance:.2f}{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Account equity: ${self.equity:.2f}{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Margin level: {account_info.margin_level:.2f}%{Style.RESET_ALL}", persist=True)
                self.calculate_position_size()
            else:
                self.print_live(f"{Fore.RED}Failed to update account info: {mt5.last_error()}{Style.RESET_ALL}", persist=True)
                self.balance = 15000  # Default fallback
    
            # Update position info if any
            positions = mt5.positions_get(symbol=self.symbol)
            if positions and len(positions) > 0:
                position = positions[0]
                self.position_size_contracts = position.volume
                entry_price = position.price_open
                position_type = "LONG" if position.type == mt5.POSITION_TYPE_BUY else "SHORT"
    
                if position_type == "LONG":
                    self.position = self.position_size_contracts * entry_price
                else:
                    self.position = -self.position_size_contracts * entry_price
    
                self.position_entry = entry_price
                self.position_notional = abs(self.position)
                self.position_time = datetime.fromtimestamp(position.time)
                self.position_ticket = position.ticket
    
                self.print_live(
                    f"{Fore.YELLOW}Updated {position_type} position: {abs(self.position_size_contracts):.2f} lots "
                    f"at ${self.position_entry:.2f} (${abs(self.position_notional):.2f}){Style.RESET_ALL}",
                    persist=True
                )
            else:
                # No open position
                self.position = 0
                self.position_entry = 0
                self.position_size_contracts = 0
                self.position_notional = 0
                self.position_ticket = 0
    
            return True
        except Exception as e:
            self.print_live(f"{Fore.RED}Error updating account data: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Error updating account data: {e}")
            return False
        
    def print_live(self, message, persist=False):
        """
        Print a status message to the console, optionally overwriting the previous line.
        If persist=True, prints as a new line (for logs and important info).
        """
        if persist:
            print(message)
            self.last_status_length = 0
        else:
            # Overwrite previous line in console
            print(' ' * self.last_status_length, end='\r')
            print(message, end='\r')
            self.last_status_length = len(message)
    
    def print_pnl_status(self, current_price, current_pnl, target_pnl=None):
        """
        Display live PnL status with visual indicators (MT5/IC Markets version)
        """
        if not self.position or self.position == 0:
            return
    
        is_long = self.position > 0
        direction_str = "LONG" if is_long else "SHORT"
    
        # Calculate PnL target if not provided
        if target_pnl is None:
            target_pnl = self.take_profit_amount
    
        # Calculate progress toward target
        progress = min(1.0, max(-1.0, current_pnl / target_pnl))
        progress_pct = int(abs(progress) * 30)  # 30 characters for progress bar
    
        # Format progress bar
        if progress >= 0:
            progress_color = Fore.GREEN
            progress_bar = f"[{'■' * progress_pct}{' ' * (30-progress_pct)}]"
            progress_text = f"+${current_pnl:.2f} / +${target_pnl:.2f}"
        else:
            progress_color = Fore.RED
            progress_bar = f"[{'■' * progress_pct}{' ' * (30-progress_pct)}]"
            progress_text = f"-${abs(current_pnl):.2f}"
    
        # Track PnL history for this position
        self.pnl_updates.append(current_pnl)
    
        # Update peak PnL
        if current_pnl > self.peak_unrealized_pnl:
            self.peak_unrealized_pnl = current_pnl
    
        # Calculate time in position
        if self.position_time:
            seconds_in_position = (datetime.now() - self.position_time).total_seconds()
            time_str = f"{int(seconds_in_position//60)}m {int(seconds_in_position%60)}s"
        else:
            time_str = "0s"
    
        # Display entry and current price
        price_change = (current_price - self.position_entry) / self.position_entry * 100
        if (is_long and price_change >= 0) or (not is_long and price_change <= 0):
            price_color = Fore.GREEN
        else:
            price_color = Fore.RED
    
        entry_exit_str = f"Entry: ${self.position_entry:.2f} | Current: {price_color}${current_price:.2f} ({price_change:+.4f}%){Style.RESET_ALL}"
    
        # Full status display
        pnl_display = (
            f"{Fore.CYAN}[{datetime.now().strftime('%H:%M:%S')}] {direction_str} | Time: {time_str} | {entry_exit_str}\n"
            f"PnL: {progress_color}{progress_text} {progress_bar} {abs(progress)*100:.1f}%{Style.RESET_ALL}\n"
            f"Peak: ${self.peak_unrealized_pnl:.2f} | Target: ${target_pnl:.2f} | Notional: ${self.position_notional:.2f}"
        )
    
        self.print_live(pnl_display, persist=True)

    def fetch_market_data(self):
        """Fetch recent market data from MT5 and Deribit order book"""
        self.print_live(f"{Fore.CYAN}[{datetime.now().strftime('%H:%M:%S')}] Fetching market data...{Style.RESET_ALL}", persist=True)
        try:
            # Fetch recent ticks/trades from MT5
            self.print_live(f"{Fore.CYAN}Fetching recent ticks for {self.symbol} from MT5...{Style.RESET_ALL}", persist=False)
            ticks = mt5.copy_ticks_from(self.symbol, datetime.now() - timedelta(minutes=30), 1000, mt5.COPY_TICKS_ALL)
            recent_price = ticks[-1]['last'] if ticks is not None and len(ticks) > 0 else 'N/A'
            self.print_live(f"{Fore.GREEN}Fetched {len(ticks) if ticks is not None else 0} ticks. Last price: {recent_price}{Style.RESET_ALL}", persist=True)
    
            # Fetch order book from Deribit (ccxt)
            self.print_live(f"{Fore.CYAN}Fetching order book for {'BTC-PERPETUAL'} from Deribit...{Style.RESET_ALL}", persist=False)
            order_book = self.deribit_exchange.fetch_order_book('BTC-PERPETUAL', limit=50)
            if order_book:
                best_bid = order_book['bids'][0][0] if order_book['bids'] else 'N/A'
                best_ask = order_book['asks'][0][0] if order_book['asks'] else 'N/A'
                spread = best_ask - best_bid if best_bid != 'N/A' and best_ask != 'N/A' else 'N/A'
                spread_pct = (spread / best_bid * 100) if best_bid != 'N/A' and spread != 'N/A' else 'N/A'
                self.print_live(
                    f"{Fore.GREEN}Order book: {len(order_book['bids'])} bids, {len(order_book['asks'])} asks. "
                    f"Spread: {spread:.2f} ({spread_pct:.3f}%){Style.RESET_ALL}", 
                    persist=True
                )
    
            # Fetch recent candles from MT5
            self.print_live(f"{Fore.CYAN}Fetching recent {self.timeframe} candles from MT5...{Style.RESET_ALL}", persist=False)
            rates = mt5.copy_rates_from(self.symbol, self._get_mt5_timeframe(self.timeframe), datetime.now() - timedelta(minutes=30), 30)
            candles = rates if rates is not None else []
            if candles is not None and len(candles) > 0:
                last_candle = candles[-1]
                open_price = last_candle['open']
                close_price = last_candle['close']
                change_pct = (close_price - open_price) / open_price * 100
                direction = "↑" if change_pct >= 0 else "↓"
                color = Fore.GREEN if change_pct >= 0 else Fore.RED
                self.print_live(
                    f"{color}Latest candle: O:{open_price:.2f} H:{last_candle['high']:.2f} L:{last_candle['low']:.2f} "
                    f"C:{close_price:.2f} {direction}{abs(change_pct):.2f}%{Style.RESET_ALL}", 
                    persist=True
                )
    
            return {'ticks': ticks, 'order_book': order_book, 'candles': candles}
        except Exception as e:
            self.print_live(f"{Fore.RED}Error fetching market data: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Error fetching market data: {e}")
            return None
        
    def detect_algo_patterns(self, data):
        """
        Analyze market data to detect common algorithmic trading patterns
        that might lead to overreactions and inefficiencies (MT5/Deribit DOM version)
        """
        self.print_live(f"{Fore.CYAN}[{datetime.now().strftime('%H:%M:%S')}] Analyzing for algorithmic patterns...{Style.RESET_ALL}", persist=True)
    
        if not data:
            self.print_live(f"{Fore.YELLOW}No data available for pattern detection{Style.RESET_ALL}", persist=True)
            return None
    
        # Dynamic threshold based on market volatility
        self.overreaction_threshold = self.calculate_adaptive_threshold(data, self.base_overreaction_threshold)
    
        patterns_detected = {
            'iceberg_orders': False,
            'momentum_chase': False,
            'stop_hunting': False,
            'liquidity_sweeps': False,
            'direction': 0,  # 1 for up, -1 for down
            'confidence': 0,
            'expected_reversion': 0
        }
    
        try:
            # Use MT5 ticks/candles and Deribit order book
            ticks = data.get('ticks', [])
            book = data.get('order_book', {})
            candles = data.get('candles', [])
    
            # Momentum chase detection (using ticks)
            if ticks is not None and len(ticks) > 100:
                self.print_live(f"{Fore.CYAN}Analyzing tick volume acceleration patterns...{Style.RESET_ALL}", persist=False)
                mid_point = len(ticks) // 2
                first_half_volume = sum(abs(tick['volume']) for tick in ticks[:mid_point])
                second_half_volume = sum(abs(tick['volume']) for tick in ticks[mid_point:])
                volume_increase = second_half_volume / first_half_volume if first_half_volume > 0 else 0
    
                if volume_increase > 1.5:
                    patterns_detected['momentum_chase'] = True
                    recent_prices = [tick['last'] for tick in ticks[-20:]]
                    start_price = recent_prices[0]
                    end_price = recent_prices[-1]
                    price_change = (end_price - start_price) / start_price if start_price != 0 else 0
                    direction = 1 if price_change > 0 else -1
                    patterns_detected['direction'] = direction
                    patterns_detected['confidence'] = min(1.0, volume_increase / 3.0)
                    reversion_pct = min(0.02, volume_increase * 0.005)
                    patterns_detected['expected_reversion'] = reversion_pct
                    self.print_live(
                        f"{Fore.MAGENTA}Detected momentum chase: Volume increased by {volume_increase:.2f}x with "
                        f"price moving {'UP' if direction > 0 else 'DOWN'} {abs(price_change)*100:.2f}%{Style.RESET_ALL}",
                        persist=True
                    )
    
            # Stop hunting detection (using candles)
            if candles is not None and len(candles) > 5:
                self.print_live(f"{Fore.CYAN}Analyzing price volatility for stop hunting patterns...{Style.RESET_ALL}", persist=False)
                movements = [abs(candle['high'] - candle['low']) / candle['open'] for candle in candles[-5:]]
                avg_movement = np.mean(movements[:-1])
                latest_movement = movements[-1]
                volatility_ratio = latest_movement / avg_movement if avg_movement > 0 else 0
    
                if volatility_ratio > self.overreaction_threshold:
                    patterns_detected['stop_hunting'] = True
                    latest_candle = candles[-1]
                    open_price, close_price = latest_candle['open'], latest_candle['close']
                    direction = 1 if close_price > open_price else -1
                    patterns_detected['direction'] = direction
                    patterns_detected['confidence'] = min(1.0, volatility_ratio / 5.0)
                    reversion_pct = min(0.015, volatility_ratio * 0.003)
                    patterns_detected['expected_reversion'] = reversion_pct
                    self.print_live(
                        f"{Fore.MAGENTA}Detected stop hunting: {volatility_ratio:.2f}x normal volatility, "
                        f"likely {'UP' if direction > 0 else 'DOWN'} stops targeted{Style.RESET_ALL}",
                        persist=True
                    )
    
            # Iceberg orders detection (using ticks)
            if ticks is not None and len(ticks) > 50:
                self.print_live(f"{Fore.CYAN}Analyzing for iceberg order patterns...{Style.RESET_ALL}", persist=False)
                price_levels = {}
                for tick in ticks[-100:]:
                    price = round(tick['last'], 1)
                    if price not in price_levels:
                        price_levels[price] = []
                    price_levels[price].append(abs(tick['volume']))
                for price, amounts in price_levels.items():
                    if len(amounts) < 5:
                        continue
                    amounts = np.array(amounts)
                    mean_size = np.mean(amounts)
                    size_deviation = np.std(amounts) / mean_size if mean_size > 0 else 0
                    if size_deviation < 0.3 and len(amounts) >= 5:
                        recent_prices = [tick['last'] for tick in ticks[-20:]]
                        price_direction = 1 if recent_prices[-1] > np.mean(recent_prices) else -1
                        patterns_detected['iceberg_orders'] = True
                        patterns_detected['direction'] = price_direction
                        patterns_detected['confidence'] = 0.7 - size_deviation
                        patterns_detected['expected_reversion'] = 0.01
                        self.print_live(
                            f"{Fore.MAGENTA}Detected iceberg orders at ${price}: {len(amounts)} trades "
                            f"with avg size {mean_size:.4f} (deviation: {size_deviation:.2f}){Style.RESET_ALL}",
                            persist=True
                        )
                        break
    
            # Liquidity sweeps detection (using ticks and Deribit DOM)
            if ticks is not None and len(ticks) > 30 and 'bids' in book and 'asks' in book:
                self.print_live(f"{Fore.CYAN}Analyzing for liquidity sweep patterns...{Style.RESET_ALL}", persist=False)
                recent_ticks = ticks[-30:]
                recent_volume = sum(abs(tick['volume']) for tick in recent_ticks)
                avg_trade_size = recent_volume / len(recent_ticks) if len(recent_ticks) > 0 else 0
                large_trades = [tick for tick in recent_ticks if abs(tick['volume']) > avg_trade_size * 3]
                if large_trades:
                    price_before_large = recent_ticks[0].last
                    price_after_large = recent_ticks[-1].last
                    price_change_pct = abs(price_after_large - price_before_large) / price_before_large * 100 if price_before_large != 0 else 0
                    if price_change_pct > 0.2:
                        sweep_direction = 1 if price_after_large > price_before_large else -1
                        bid_volume = sum(b[1] for b in book['bids'][:5])
                        ask_volume = sum(a[1] for a in book['asks'][:5])
                        book_imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume) if (bid_volume + ask_volume) != 0 else 0
                        if abs(book_imbalance) > 0.3:
                            patterns_detected['liquidity_sweeps'] = True
                            patterns_detected['direction'] = sweep_direction
                            patterns_detected['confidence'] = min(1.0, price_change_pct / 0.5)
                            patterns_detected['expected_reversion'] = price_change_pct / 100 * 0.5
                            self.print_live(
                                f"{Fore.MAGENTA}Detected liquidity sweep: {len(large_trades)} large trades "
                                f"moved price {price_change_pct:.2f}% with {abs(book_imbalance)*100:.1f}% "
                                f"order book imbalance{Style.RESET_ALL}",
                                persist=True
                            )
    
            # Multi-factor validation
            if any(patterns_detected[key] for key in ['momentum_chase', 'stop_hunting', 'iceberg_orders', 'liquidity_sweeps']):
                validated = self.validate_pattern(patterns_detected, data)
                if not validated:
                    self.print_live(f"{Fore.YELLOW}Pattern detected but failed multi-factor validation{Style.RESET_ALL}", persist=True)
                    for key in ['momentum_chase', 'stop_hunting', 'iceberg_orders', 'liquidity_sweeps']:
                        patterns_detected[key] = False
                    patterns_detected['confidence'] = 0
                    patterns_detected['direction'] = 0
                else:
                    self.print_live(f"{Fore.GREEN}Pattern confirmed with multi-factor validation{Style.RESET_ALL}", persist=True)
    
            return patterns_detected
    
        except Exception as e:
            self.print_live(f"{Fore.RED}Error in pattern detection: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Error in pattern detection: {e}")
            return None
        
    def place_market_order(self, side, lots):
        """Place a market order in MT5 with immediate execution"""
        try:
            # Get symbol info to determine valid lot sizes
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                self.print_live(f"{Fore.RED}Failed to get symbol info for {self.symbol}. Error: {mt5.last_error()}{Style.RESET_ALL}", persist=True)
                return None
                
            # Round lot size to comply with symbol volume_step
            volume_step = symbol_info.volume_step
            rounded_lots = round(lots / volume_step) * volume_step
            
            # Ensure the lot size is within allowed limits
            min_lot = symbol_info.volume_min
            max_lot = symbol_info.volume_max
            valid_lots = max(min_lot, min(max_lot, rounded_lots))
            
            # Print info about lot adjustment
            if valid_lots != lots:
                self.print_live(f"{Fore.YELLOW}Adjusted lot size from {lots:.8f} to {valid_lots:.8f} to comply with broker requirements{Style.RESET_ALL}", persist=True)
                lots = valid_lots
            
            # Get current tick data
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                self.print_live(f"{Fore.RED}Failed to get tick data for {self.symbol}. Error: {mt5.last_error()}{Style.RESET_ALL}", persist=True)
                return None
                    
            # In place_market_order:
            if side == 'buy':
                price = tick['ask']
                order_type = mt5.ORDER_TYPE_BUY
                tp_price = price + (self.take_profit_pips * self.btc_pip_value)
                sl_price = price - (self.stop_loss_pips * self.btc_pip_value)
            else:  # sell
                price = tick['bid']
                order_type = mt5.ORDER_TYPE_SELL
                tp_price = price - (self.take_profit_pips * self.btc_pip_value)
                sl_price = price + (self.stop_loss_pips * self.btc_pip_value)
            
            # Round prices to proper precision
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info:
                digits = symbol_info.digits
                price = round(price, digits)
                tp_price = round(tp_price, digits)
                sl_price = round(sl_price, digits)
                    
            order_info = f"{Fore.YELLOW}MARKET {side.upper()} order for {lots} lots at {price:.3f}{Style.RESET_ALL}"
            self.print_live(order_info, persist=True)
            
            # Confirm order if enabled
            if self.confirm_orders:
                confirm = input(f"{Fore.GREEN}Do you want to proceed with this market order? (y/n): {Style.RESET_ALL}").strip().lower()
                if confirm != 'y' and confirm != 'yes':
                    self.print_live(f"{Fore.YELLOW}Order cancelled by user.{Style.RESET_ALL}", persist=True)
                    return None
            
            # Prepare order request for market execution
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": lots,
                "type": order_type,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "deviation": 20,  # Allow 2 pip slippage (20 points)
                "magic": 12345,   # Unique identifier for this strategy
                "comment": "MT5 Micro Target Market",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,  # Immediate or Cancel
            }
            
            # Send order
            result = mt5.order_send(request)
            
            # In place_market_order, after the error message when order fails (around line 930):
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                self.print_live(f"{Fore.RED}Failed to place market order. Error code: {result.retcode}, Description: {result.comment}{Style.RESET_ALL}", persist=True)
                self.last_trade_attempt_time = datetime.now()  # Set cooldown timer
                return None
                    
            self.print_live(f"{Fore.GREEN}Market order executed successfully with ticket: {result.order}{Style.RESET_ALL}", persist=True)
            self.last_trade_attempt_time = None

            # For market orders, the position is opened immediately
            # Update position tracking directly
            self.position = 1 if side == 'buy' else -1
            self.position_entry = result.price
            self.position_size = lots
            self.position_ticket = result.order
            self.position_time = datetime.now()
            self.peak_unrealized_pnl = 0
            self.pnl_updates = []
            
            return result.order
                    
        except Exception as e:
            self.print_live(f"{Fore.RED}Error placing market order: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Error placing market order: {e}")
            return None
        
    def validate_pattern(self, pattern_results, data):
        """
        Multi-factor validation to confirm detected patterns (MT5/Deribit DOM version)
        Requires at least 2 of 3 confirmations to proceed with a trade
        """
        confirmations = 0
    
        try:
            # 1. Primary pattern detection confidence
            if pattern_results['confidence'] > 0.6:
                self.print_live(f"{Fore.CYAN}Validation: Pattern strength confirmed ({pattern_results['confidence']:.2f} > 0.6){Style.RESET_ALL}", persist=True)
                confirmations += 1
    
            # 2. Volume confirmation (MT5 ticks)
            ticks = data.get('ticks', [])
            if ticks is not None and len(ticks) > 20:
                recent_volume = sum(abs(tick['volume']) for tick in ticks[-20:])
                avg_volume = sum(abs(tick['volume']) for tick in ticks) / len(ticks)
                volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 0
    
                if volume_ratio > 1.3:
                    self.print_live(f"{Fore.CYAN}Validation: Volume confirmation ({volume_ratio:.2f}x normal){Style.RESET_ALL}", persist=True)
                    confirmations += 1
    
            # 3. Order book imbalance confirmation (Deribit DOM)
            book = data.get('order_book', {})
            if 'bids' in book and 'asks' in book and len(book['bids']) >= 5 and len(book['asks']) >= 5:
                bid_volume = sum(b[1] for b in book['bids'][:5])
                ask_volume = sum(a[1] for a in book['asks'][:5])
                imbalance = abs(bid_volume - ask_volume) / (bid_volume + ask_volume) if (bid_volume + ask_volume) != 0 else 0
    
                if imbalance > 0.2:  # 20% imbalance
                    self.print_live(f"{Fore.CYAN}Validation: Order book imbalance confirmed ({imbalance*100:.1f}%){Style.RESET_ALL}", persist=True)
                    confirmations += 1
    
            # Require at least 2 of 3 confirmations
            is_valid = confirmations >= 2
            self.print_live(f"{Fore.CYAN}Pattern validation: {confirmations}/3 confirmations ({is_valid}){Style.RESET_ALL}", persist=True)
    
            return is_valid
    
        except Exception as e:
            self.print_live(f"{Fore.RED}Error in pattern validation: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Error in pattern validation: {e}")
            return False
        
    def _record_closed_trade(self, is_long, current_price, pnl, pnl_percentage, close_type="limit"):
        """
        Record trade details and send notifications when a position is closed (MT5/IC Markets version)
        """
        # Calculate time held
        time_held = (datetime.now() - self.position_time).total_seconds() if self.position_time else 0
    
        # Determine if target was hit
        target_profit = getattr(self, 'current_take_profit', self.take_profit_amount)
        target_hit = pnl >= target_profit
    
        # Update balance
        self.balance += pnl
    
        # Display success message
        pnl_color = Fore.GREEN if pnl >= 0 else Fore.RED
        self.print_live(f"{Fore.GREEN}Position closed! P&L: {pnl_color}${pnl:.2f} ({pnl_percentage:+.4f}%){Style.RESET_ALL}", persist=True)
        self.print_live(f"{Fore.GREEN}New balance: ${self.balance:.2f}{Style.RESET_ALL}", persist=True)
    
        # Display trade metrics
        target_message = f"{Fore.GREEN}Target hit!{Style.RESET_ALL}" if target_hit else f"{Fore.RED}Target missed{Style.RESET_ALL}"
    
        self.print_live(
            f"{Fore.CYAN}Trade summary: {target_message} | "
            f"Time held: {int(time_held//60)}m {int(time_held%60)}s | "
            f"Peak PnL: ${self.peak_unrealized_pnl:.2f}{Style.RESET_ALL}",
            persist=True
        )
    
        # Record trade
        self.trade_history.append({
            'entry_time': self.position_time,
            'exit_time': datetime.now(),
            'direction': 'LONG' if is_long else 'SHORT',
            'entry': self.position_entry,
            'exit': current_price,
            'size': abs(self.position_notional),
            'contracts': abs(self.position_size_contracts),
            'leverage': self.leverage,
            'pnl': pnl,
            'peak_pnl': self.peak_unrealized_pnl,
            'success': pnl > 0,
            'target_reached': target_hit,
            'time_held': time_held,
            'order_type': close_type
        })
    
        # Send email notification
        try:
            self.send_email(
                f"{'✅ Profit!' if pnl >= 0 else '❌ Loss'} Position Closed",
                f"📈 MT5 BTCUSD Futures Trade Summary\n"
                f"═════════════════════════\n\n"
                f"🔹 Direction: {'LONG' if is_long else 'SHORT'}\n"
                f"⚡ Leverage: {self.leverage}x\n"
                f"💲 Entry: ${self.position_entry:.2f}\n"
                f"💲 Exit: ${current_price:.2f}\n"
                f"{'💰' if pnl >= 0 else '💸'} P&L: ${pnl:.2f} ({pnl_percentage:+.4f}%)\n"
                f"🎯 Target ${target_profit:.2f}: {'✅ REACHED!' if target_hit else '❌ MISSED'}\n"
                f"⏱️ Time Held: {int(time_held//60)}m {int(time_held%60)}s\n\n"
                f"💵 New Balance: ${self.balance:.2f}\n\n"
            )
        except Exception as e:
            self.print_live(f"{Fore.YELLOW}Error sending trade email: {e}{Style.RESET_ALL}", persist=True)
    
        # Reset position state
        self.position = 0
        self.position_entry = 0
        self.position_notional = 0
        self.position_size_contracts = 0
        self.position_time = None

    def calculate_adaptive_threshold(self, data, base_threshold=1.5, lookback_periods=20):
        """Calculate adaptive threshold based on recent market volatility (MT5/Deribit DOM version)"""
        try:
            # Sjekk at vi har nok candle-data
            candles = data.get('candles', [])
            if candles is None or len(candles) < lookback_periods:
                return base_threshold
    
            # Hent siste candles for lookback
            recent_candles = candles[-lookback_periods:]
    
            # Merk: For MT5-candles er det vanligvis dict med 'high' og 'low'
            # Hvis du bruker numpy array eller annen struktur, tilpass til ['high'] og ['low']
            current_volatility = np.std([candle['high'] - candle['low'] for candle in recent_candles[-5:]])
            baseline_volatility = np.std([candle['high'] - candle['low'] for candle in recent_candles])
    
            volatility_ratio = current_volatility / baseline_volatility if baseline_volatility > 0 else 1
    
            # Skaler threshold: høyere volatilitet gir høyere terskel
            adaptive_threshold = base_threshold * max(1.0, volatility_ratio)
    
            self.print_live(
                f"{Fore.CYAN}Volatility adjustment: Current vol: {current_volatility:.4f} | "
                f"Baseline: {baseline_volatility:.4f} | Ratio: {volatility_ratio:.2f}x | "
                f"Adjusted threshold: {adaptive_threshold:.2f} SD{Style.RESET_ALL}",
                persist=True
            )
    
            return adaptive_threshold
    
        except Exception as e:
            self.print_live(f"{Fore.RED}Error calculating adaptive threshold: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Error calculating adaptive threshold: {e}")
            return base_threshold  # Returner base threshold ved feil
    
    def detect_market_regime(self, candles, lookback=20):
        """
        Detect current market regime (TREND, RANGE, VOLATILE) using MT5/ccxt candle data.
        """
        # Hent closing-priser fra siste lookback-perioder
        closes = np.array([candle['close'] if isinstance(candle, dict) else candle[4] for candle in candles[-lookback:]])
        returns = np.diff(closes) / closes[:-1]
    
        # Beregn trendindikatorer
        ma_fast = np.mean(closes[-5:])
        ma_slow = np.mean(closes)
        trending = abs((ma_fast / ma_slow) - 1) > 0.01
    
        # Beregn volatilitet (annualisert)
        volatility = np.std(returns) * np.sqrt(252)
    
        # Klassifiser markedsregime
        if trending and volatility < 0.3:
            return "TREND", volatility
        elif volatility > 0.5:
            return "VOLATILE", volatility
        else:
            return "RANGE", volatility
        
    def calculate_contract_size(self, price, amount_usd):
        """
        Calculate lot size for MT5 BTCUSD based on current price and desired USD exposure.
        Returns lots rounded to nearest 0.01 (IC Markets BTCUSD min lot = 0.01).
        """
        # Bruk gearing hvis ønskelig, ellers kun USD-eksponering
        leveraged_amount = amount_usd * self.leverage
        lots = leveraged_amount / price
        # Rund til nærmeste 0.01 (IC Markets BTCUSD min lot = 0.01)
        lots = round(lots * 100) / 100
        return max(lots, 0.01)  # Minste tillatte lot
    
    def execute_fixed_strategy(self, pattern_results):
        """
        Utfør en trade basert på detekterte algoritmiske mønstre (MT5/IC Markets-versjon).
        Bruker market orders og kan ta både LONG og SHORT posisjoner.
        """
        if not pattern_results or pattern_results['confidence'] < 0.6:
            self.print_live(f"{Fore.YELLOW}[{datetime.now().strftime('%H:%M:%S')}] Ingen handlingsverdige mønstre funnet (for lav confidence){Style.RESET_ALL}", persist=True)
            return
    
        direction = -1 * pattern_results['direction']
    
        if self.shorts_only and direction > 0:
            self.print_live(f"{Fore.YELLOW}[{datetime.now().strftime('%H:%M:%S')}] SHORT-only modus: Hopper over LONG-signal{Style.RESET_ALL}", persist=True)
            return
    
        if self.position != 0 or self.check_for_existing_positions():
            self.print_live(f"{Fore.YELLOW}[{datetime.now().strftime('%H:%M:%S')}] Har allerede en aktiv posisjon, hopper over nytt signal{Style.RESET_ALL}", persist=True)
            return
    
        side = 'buy' if direction > 0 else 'sell'
        position_type = "LONG" if direction > 0 else "SHORT"
    
        pattern_type = "unknown"
        for key in ['momentum_chase', 'stop_hunting', 'iceberg_orders', 'liquidity_sweeps']:
            if pattern_results.get(key):
                pattern_type = key
                break
    
        self.print_live(
            f"{Fore.BLUE}[{datetime.now().strftime('%H:%M:%S')}] Tar motsatt {position_type}-posisjon mot {pattern_type.replace('_', ' ')}-mønster med ${self.position_size} eksponering ved {self.leverage}x leverage (market order){Style.RESET_ALL}",
            persist=True
        )
        
        wait_seconds = 13
        self.print_live(f"{Fore.YELLOW}Patience strategy: Venter {wait_seconds} sekunder før ordre legges inn...{Style.RESET_ALL}", persist=True)
        for i in range(wait_seconds, 0, -1):
            if i % 5 == 0 or i <= 3:
                self.print_live(f"{Fore.YELLOW}Venter... {i}s igjen{Style.RESET_ALL}", persist=False)
            time.sleep(0.01)

    
        try:
            # Hent siste pris fra MT5
            symbol_info = mt5.symbol_info_tick(self.symbol)
            if not symbol_info:
                self.print_live(f"{Fore.RED}Kunne ikke hente siste pris fra MT5, avbryter trade{Style.RESET_ALL}", persist=True)
                return
            current_price = symbol_info.last
            if not current_price or current_price <= 0:
                # Fallback til ask/bid hvis last er ugyldig
                current_price = symbol_info.ask if direction > 0 else symbol_info.bid
                self.print_live(
                    f"{Fore.YELLOW}Bruker {'ask' if direction > 0 else 'bid'}-pris {current_price} fordi last=0 fra MT5{Style.RESET_ALL}",
                    persist=True
                )
            if not current_price or current_price <= 0:
                self.print_live(f"{Fore.RED}Ugyldig pris fra MT5 ({current_price}), avbryter trade!{Style.RESET_ALL}", persist=True)
                return
    
            # Kalkuler lot-størrelse ut fra ønsket USD-eksponering
            lots = self.calculate_contract_size(current_price, self.position_size)
    
            # Bruk din egen market order-funksjon
            order_ticket = self.place_market_order(side, lots)
            if not order_ticket:
                self.print_live(f"{Fore.RED}Market order feilet, ingen posisjon åpnet.{Style.RESET_ALL}", persist=True)
                return
    
            self.print_live(f"{Fore.GREEN}Market order utført: {position_type} {lots:.2f} lots til ${current_price:.2f}{Style.RESET_ALL}", persist=True)
    
            self.send_email(
                f"{'🔵 Ny LONG' if side == 'buy' else '🔴 Ny SHORT'} posisjon åpnet",
                f"📊 MT5 BTCUSD Futures Trade Alert\n"
                f"═════════════════════════\n\n"
                f"🔹 Posisjon: {position_type} {lots:.2f} lots\n"
                f"⚡ Leverage: {self.leverage}x\n"
                f"💲 Entry Price: ${self.position_entry:.2f}\n"
                f"💵 Notional Value: ${abs(self.position_notional):.2f}\n"
                f"🎯 Target Profit: ${self.take_profit_amount:.2f}\n\n"
                f"⏱️ Entry Time: {datetime.now().strftime('%H:%M:%S')}\n\n"
            )
    
        except Exception as e:
            self.print_live(f"{Fore.RED}Feil under utførelse av strategi: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Feil under utførelse av strategi: {e}")
            return
        
    def manage_positions(self):
            """
            Overvåk og håndter åpne posisjoner, med mål om å ta gevinst ved f.eks. $2 profit (MT5/IC Markets-versjon).
            """
            if self.position == 0:
                return
        
            is_long = self.position > 0
            position_type = "LONG" if is_long else "SHORT"
        
            self.print_live(
                f"{Fore.CYAN}[{datetime.now().strftime('%H:%M:%S')}] Håndterer {position_type}-posisjon "
                f"på {abs(self.position_size_contracts):.2f} lots fra ${self.position_entry:.2f}{Style.RESET_ALL}",
                persist=True
            )
        
            try:
                # Hent nåværende pris fra MT5
                symbol_info = mt5.symbol_info_tick(self.symbol)
                if not symbol_info:
                    self.print_live(f"{Fore.RED}Kunne ikke hente siste pris fra MT5{Style.RESET_ALL}", persist=True)
                    return
                current_price = symbol_info.last
        
                # Beregn PnL for posisjonen
                if is_long:
                    price_diff = current_price - self.position_entry
                    price_change_pct = price_diff / self.position_entry
                else:
                    price_diff = self.position_entry - current_price
                    price_change_pct = price_diff / self.position_entry
        
                # Beregn urealiserte PnL (eksponering * prosentvis endring)
                unrealized_pnl = abs(self.position_notional) * price_change_pct
        
                # Vis PnL-status live
                self.print_pnl_status(current_price, unrealized_pnl)
        
                # Hent profit target for denne posisjonen (skalert hvis delvis fylt)
                target_profit = getattr(self, 'current_take_profit', self.take_profit_amount)
        
                # Ta gevinst hvis profit target nås
                if unrealized_pnl >= target_profit:
                    self.print_live(f"{Fore.GREEN}${target_profit:.2f} profit target nådd, lukker posisjon{Style.RESET_ALL}", persist=True)
                    self._close_position(is_long, current_price, unrealized_pnl, price_change_pct * 100, close_type="limit")
        
                # Stop loss hvis tapet blir for stort
                elif unrealized_pnl <= -self.max_loss_amount:
                    self.print_live(f"{Fore.RED}Stop loss utløst, lukker posisjon{Style.RESET_ALL}", persist=True)
                    self._close_position(is_long, current_price, unrealized_pnl, price_change_pct * 100, close_type="market")
        
                # Tidsbasert exit hvis posisjonen har vært åpen for lenge (f.eks. 30 min)
                elif (datetime.now() - self.position_time).total_seconds() > 1800:
                    self.print_live(f"{Fore.YELLOW}Tidsbasert exit, lukker posisjon{Style.RESET_ALL}", persist=True)
                    self._close_position(is_long, current_price, unrealized_pnl, price_change_pct * 100, close_type="limit")
        
            except Exception as e:
                self.print_live(f"{Fore.RED}Feil i posisjonshåndtering: {e}{Style.RESET_ALL}", persist=True)
                self.logger.error(f"Feil i posisjonshåndtering: {e}")

    def _reset_position_state(self):
        """
        Nullstill all intern posisjonsstatus når det ikke finnes noen åpen posisjon på børsen.
        Brukes for å sikre at botens interne tilstand alltid samsvarer med faktisk posisjon på Deribit.
        """
        self.print_live(f"{Fore.YELLOW}Nullstiller posisjonssporing (ingen åpen posisjon på børsen){Style.RESET_ALL}", persist=True)
        self.position = 0
        self.position_entry = 0
        self.position_notional = 0
        self.position_size_contracts = 0
        self.position_time = None
        self.peak_unrealized_pnl = 0
        self.pnl_updates = []

    def _close_position(self, is_long, current_price, pnl, pnl_percentage, close_type="market"):
        """
        Lukk nåværende posisjon i MT5 med market order.
        Logger, oppdaterer balanse og sender e-post.
        """
        import MetaTrader5 as mt5
    
        if self.position == 0 or not self.position_ticket:
            self.print_live(f"{Fore.YELLOW}Ingen åpen posisjon å lukke.{Style.RESET_ALL}", persist=True)
            return
    
        close_side = mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY
        lots = abs(self.position_size) if self.position_size else abs(self.position_size_contracts)
        if not lots or lots < 0.01:
            lots = 0.01  # fallback minimum
    
        # Hent siste pris for korrekt utførelse
        symbol_info = mt5.symbol_info_tick(self.symbol)
        if not symbol_info:
            self.print_live(f"{Fore.RED}Kunne ikke hente siste pris fra MT5 for lukking.{Style.RESET_ALL}", persist=True)
            return
        price = symbol_info.bid if close_side == mt5.ORDER_TYPE_SELL else symbol_info.ask
    
        # Bekreft ordre hvis ønskelig
        if self.confirm_orders:
            confirm = input(f"{Fore.GREEN}Vil du lukke posisjonen med market ordre? (y/n): {Style.RESET_ALL}").strip().lower()
            if confirm not in ['y', 'yes']:
                self.print_live(f"{Fore.YELLOW}Lukking av posisjon avbrutt av bruker.{Style.RESET_ALL}", persist=True)
                return
    
        # Lag og send market close request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": lots,
            "type": close_side,
            "price": price,
            "deviation": 20,
            "magic": 12345,
            "comment": "MT5 Micro Target Market CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
            "position": self.position_ticket
        }
        result = mt5.order_send(request)
    
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            self.print_live(f"{Fore.RED}Feil ved lukking av posisjon. Error code: {result.retcode}, Description: {result.comment}{Style.RESET_ALL}", persist=True)
            return
    
        # Oppdater balanse og logg trade
        self._record_closed_trade(is_long, current_price, pnl, pnl_percentage, close_type=close_type)

    def run_market_trading(self, duration_minutes=60):
            """
            Kjør live/paper trading i MT5 med market orders i angitt antall minutter (eller uendelig hvis None).
            """
            import MetaTrader5 as mt5
        
            if duration_minutes is None:
                self.print_live(f"{Fore.BLUE}[{datetime.now().strftime('%H:%M:%S')}] Starter LIVE trading uten tidsbegrensning{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.BLUE}Posisjonsstørrelse: ${self.position_size} med {self.leverage}x leverage | Mål: ${self.take_profit_amount}{Style.RESET_ALL}", persist=True)
                try:
                    while True:
                        running_time = (datetime.now() - self.start_time).total_seconds()
                        running_hours = int(running_time // 3600)
                        running_min = int((running_time % 3600) // 60)
                        running_sec = int(running_time % 60)
                        self.print_live(
                            f"{Fore.BLUE}Live trading: {running_hours}t {running_min}m {running_sec}s | "
                            f"Saldo: ${self.balance:.2f} | "
                            f"Handler: {len(self.trade_history)} | "
                            f"Total PnL: ${sum(trade['pnl'] for trade in self.trade_history):.2f} | "
                            f"Posisjon: {abs(self.position_size):.2f} {'LONG' if self.position > 0 else ('SHORT' if self.position < 0 else 'NONE')}{Style.RESET_ALL}",
                            persist=False
                        )
        
                        data = self.fetch_market_data()
        
                        if self.position == 0:
                            patterns = self.detect_algo_patterns(data)
                            if patterns and patterns['confidence'] > 0.5:
                                self.execute_fixed_strategy(patterns)
                        else:
                            self.manage_positions()
        
                        # Hyppigere PnL-sjekk for åpen posisjon
                        if self.position != 0:
                            self.manage_positions()
                            for _ in range(10):
                                if self.position == 0:
                                    break
                                try:
                                    symbol_info = mt5.symbol_info_tick(self.symbol)
                                    if not symbol_info:
                                        continue
                                    current_price = symbol_info.last
                                    is_long = self.position > 0
                                    price_diff = current_price - self.position_entry if is_long else self.position_entry - current_price
                                    price_change_pct = price_diff / self.position_entry
                                    unrealized_pnl = abs(self.position_notional) * price_change_pct
                                    target_profit = getattr(self, 'current_take_profit', self.take_profit_amount)
                                    if unrealized_pnl >= target_profit:
                                        self.print_live(f"{Fore.GREEN}${target_profit:.2f} profit target nådd, lukker posisjon umiddelbart{Style.RESET_ALL}", persist=True)
                                        self._close_position(is_long, current_price, unrealized_pnl, price_change_pct * 100, close_type="market")
                                        break
                                    self.print_pnl_status(current_price, unrealized_pnl)
                                    time.sleep(1)
                                except Exception as e:
                                    self.print_live(f"{Fore.YELLOW}Feil i hyppig PnL-sjekk: {e}{Style.RESET_ALL}", persist=False)
                                    time.sleep(1)
                        else:
                            # Ingen posisjon - vent før neste sjekk
                            wait_time = 30
                            for i in range(wait_time):
                                if i % 5 == 0:
                                    time_left = wait_time - i
                                    self.print_live(f"{Fore.CYAN}Venter {time_left}s før neste sjekk...{Style.RESET_ALL}", persist=False)
                                time.sleep(1)
                except KeyboardInterrupt:
                    self.print_live(f"\n{Fore.YELLOW}Trading manuelt stoppet med Ctrl+C{Style.RESET_ALL}", persist=True)
                    if self.position != 0:
                        self.print_live(f"{Fore.YELLOW}Lukker åpen posisjon ved slutten av økten{Style.RESET_ALL}", persist=True)
                        self._close_position(self.position > 0, current_price, 0, 0, close_type="market")
                    self.print_trading_summary()
                    return
        
            else:
                self.print_live(f"{Fore.BLUE}[{datetime.now().strftime('%H:%M:%S')}] Starter trading i {duration_minutes} minutter{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.BLUE}Posisjonsstørrelse: ${self.position_size} med {self.leverage}x leverage | Mål: ${self.take_profit_amount}{Style.RESET_ALL}", persist=True)
                end_time = datetime.now() + timedelta(minutes=duration_minutes)
                try:
                    while datetime.now() < end_time:
                        remaining = end_time - datetime.now()
                        remaining_min = int(remaining.total_seconds() // 60)
                        remaining_sec = int(remaining.total_seconds() % 60)
                        self.print_live(
                            f"{Fore.BLUE}Trading: {remaining_min}m {remaining_sec}s igjen | "
                            f"Saldo: ${self.balance:.2f} | "
                            f"Handler: {len(self.trade_history)} | "
                            f"Total PnL: ${sum(trade['pnl'] for trade in self.trade_history):.2f} | "
                            f"Posisjon: {abs(self.position_size):.2f} {'LONG' if self.position > 0 else ('SHORT' if self.position < 0 else 'NONE')}{Style.RESET_ALL}",
                            persist=False
                        )
        
                        data = self.fetch_market_data()
        
                        if self.position == 0:
                            patterns = self.detect_algo_patterns(data)
                            if patterns and patterns['confidence'] > 0.5:
                                self.execute_fixed_strategy(patterns)
                        else:
                            self.manage_positions()
        
                        wait_time = 10 if self.position != 0 else 30
                        for i in range(wait_time):
                            if i % 5 == 0:
                                time_left = wait_time - i
                                status = f"{Fore.CYAN}Venter {time_left}s før neste sjekk... " + \
                                         f"{'(Åpen posisjon)' if self.position != 0 else ''}{Style.RESET_ALL}"
                                self.print_live(status, persist=False)
                            time.sleep(1)
                except KeyboardInterrupt:
                    self.print_live(f"\n{Fore.YELLOW}Trading manuelt stoppet med Ctrl+C{Style.RESET_ALL}", persist=True)
        
                self.print_live(f"\n{Fore.YELLOW}Trading-økt ferdig{Style.RESET_ALL}", persist=True)
                if self.position != 0:
                    self.print_live(f"{Fore.YELLOW}Lukker åpen posisjon ved slutten av økten{Style.RESET_ALL}", persist=True)
                    self._close_position(self.position > 0, current_price, 0, 0, close_type="market")
                self.print_trading_summary()

    def print_trading_summary(self):
        """Skriv ut sammendrag av trading-økten (MT5/IC Markets-versjon)"""
        if not self.trade_history:
            self.print_live(f"{Fore.YELLOW}Ingen handler utført i denne økten.{Style.RESET_ALL}", persist=True)
            return
    
        trades = len(self.trade_history)
        wins = sum(1 for trade in self.trade_history if trade['pnl'] > 0)
        losses = trades - wins
        win_rate = (wins / trades) * 100 if trades > 0 else 0
    
        total_pnl = sum(trade['pnl'] for trade in self.trade_history)
        avg_pnl = total_pnl / trades if trades > 0 else 0
    
        best_trade = max(self.trade_history, key=lambda x: x['pnl']) if self.trade_history else None
        worst_trade = min(self.trade_history, key=lambda x: x['pnl']) if self.trade_history else None
    
        avg_hold_time = sum(trade['time_held'] for trade in self.trade_history) / trades if trades > 0 else 0
    
        self.print_live(
            f"\n{Fore.BLUE}═════════════════════════════════════════{Style.RESET_ALL}\n"
            f"{Fore.BLUE}Trading-økt sammendrag{Style.RESET_ALL}\n"
            f"{Fore.BLUE}═════════════════════════════════════════{Style.RESET_ALL}\n"
            f"Antall handler: {trades}\n"
            f"Gevinster: {wins} | Tap: {losses}\n"
            f"Win Rate: {win_rate:.2f}%\n"
            f"Total P&L: {Fore.GREEN if total_pnl >= 0 else Fore.RED}${total_pnl:.2f}{Style.RESET_ALL}\n"
            f"Gj.snitt P&L: {Fore.GREEN if avg_pnl >= 0 else Fore.RED}${avg_pnl:.2f}{Style.RESET_ALL}\n"
            f"Gj.snitt holdetid: {int(avg_hold_time//60)}m {int(avg_hold_time%60)}s\n"
            f"Beste trade: ${best_trade['pnl']:.2f}\n"
            f"Dårligste trade: ${worst_trade['pnl']:.2f}\n"
            f"Sluttbalanse: ${self.balance:.2f}\n"
            f"{Fore.BLUE}═════════════════════════════════════════{Style.RESET_ALL}\n",
            persist=True
        )
    
        # Send e-post med resultater
        if hasattr(self, 'email_enabled') and self.email_enabled:
            self.send_email(
                f"📊 Trading-økt ferdig - P&L: ${total_pnl:.2f}",
                f"📈 MT5 BTCUSD Futures Trading Summary\n"
                f"═════════════════════════\n\n"
                f"🔢 Antall handler: {trades}\n"
                f"✅ Gevinster: {wins} | ❌ Tap: {losses}\n"
                f"🎯 Win Rate: {win_rate:.2f}%\n"
                f"💰 Total P&L: ${total_pnl:.2f}\n"
                f"⚖️ Gj.snitt P&L: ${avg_pnl:.2f}\n"
                f"⏱️ Gj.snitt holdetid: {int(avg_hold_time//60)}m {int(avg_hold_time%60)}s\n"
                f"🟢 Beste trade: ${best_trade['pnl']:.2f}\n"
                f"🔴 Dårligste trade: ${worst_trade['pnl']:.2f}\n\n"
                f"💵 Sluttbalanse: ${self.balance:.2f}\n\n"
            )

    def display_account_summary(self):
        """Vis detaljert kontosammendrag før trading starter (MT5/IC Markets-versjon)"""
        try:
            if not self.paper_mode:
                import MetaTrader5 as mt5
                account_info = mt5.account_info()
                if not account_info:
                    self.print_live(f"{Fore.RED}Kunne ikke hente konto-informasjon fra MT5.{Style.RESET_ALL}", persist=True)
                    return False
    
                # Hent balanse og margin
                balance = account_info.balance
                equity = account_info.equity
                margin = account_info.margin
                free_margin = account_info.margin_free
                margin_level = account_info.margin_level
    
                self.print_live(f"\n{Back.BLUE}{Fore.WHITE} MT5 KONTO-SAMMENDRAG {Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}═══════════════════════════════════════════════════════{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Total balanse: ${balance:.2f}{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Equity: ${equity:.2f} | Margin: ${margin:.2f} | Fri margin: ${free_margin:.2f}{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Margin-nivå: {margin_level:.2f}%{Style.RESET_ALL}", persist=True)
    
                # Vis åpne posisjoner
                positions = mt5.positions_get(symbol=self.symbol)
                if positions and len(positions) > 0:
                    self.print_live(f"\n{Fore.YELLOW}Åpne posisjoner:{Style.RESET_ALL}", persist=True)
                    for pos in positions:
                        pos_type = "LONG" if pos.type == mt5.POSITION_TYPE_BUY else "SHORT"
                        lots = pos.volume
                        entry = pos.price_open
                        ticket = pos.ticket
                        pnl = pos.profit
                        self.print_live(
                            f"{Fore.YELLOW}{pos_type} {self.symbol}: {lots:.2f} lots @ ${entry:.2f} | "
                            f"P&L: ${pnl:.2f} | Ticket: {ticket}{Style.RESET_ALL}", persist=True
                        )
                else:
                    self.print_live(f"\n{Fore.GREEN}Ingen åpne posisjoner{Style.RESET_ALL}", persist=True)
    
                # Vis planlagte trading-parametre
                self.print_live(f"\n{Fore.CYAN}Trading-parametre:{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}Posisjonsstørrelse: ${self.position_size} med {self.leverage}x leverage "
                                f"(${self.position_size * self.leverage} eksponering){Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}Mål for gevinst: ${self.take_profit_amount} per trade{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}Maksimalt tap: ${self.max_loss_amount} per trade{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}════════════════════════════════════════════════════════{Style.RESET_ALL}\n", persist=True)
                return True
    
            else:
                # Paper trading mode
                self.print_live(f"\n{Back.YELLOW}{Fore.BLACK} PAPER TRADING KONTO-SAMMENDRAG {Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}═══════════════════════════════════════════════════════{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.GREEN}Simulert balanse: ${self.balance:.2f}{Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}Posisjonsstørrelse: ${self.position_size} med {self.leverage}x leverage "
                                f"(${self.position_size * self.leverage} eksponering){Style.RESET_ALL}", persist=True)
                self.print_live(f"{Fore.CYAN}════════════════════════════════════════════════════════{Style.RESET_ALL}\n", persist=True)
                return True
    
        except Exception as e:
            self.print_live(f"{Fore.RED}Feil ved henting av kontosammendrag: {e}{Style.RESET_ALL}", persist=True)
            self.logger.error(f"Feil ved henting av kontosammendrag: {e}")
            return False
        
    def run(self):
        """Hovedinngangspunkt for å starte MT5-strategien"""
        self.print_live(f"{Fore.GREEN}Starter MT5 BTCUSD Market Order-strategi{Style.RESET_ALL}", persist=True)
    
        # Sett opp bekreftelsesinnstilling
        self.setup_confirmation()
    
        # Vis kontosammendrag før start
        self.display_account_summary()
    
        # Sjekk om det er paper trading
        if self.paper_mode:
            self.run_market_trading(duration_minutes=60)  # Paper trading med tidsbegrensning
        else:
            self.print_live(f"{Fore.RED}ADVARSEL: LIVE TRADING MODUS AKTIVERT{Style.RESET_ALL}", persist=True)
            confirmation = input(f"{Fore.YELLOW}Skriv 'CONFIRM' for å starte live trading med ${self.balance:.2f} saldo: {Style.RESET_ALL}")
    
            if confirmation.strip().upper() == 'CONFIRM':
                self.print_live(f"{Fore.GREEN}Live trading bekreftet. Starter...{Style.RESET_ALL}", persist=True)
                self.run_market_trading(duration_minutes=None)  # Ubegrenset tid
            else:
                self.print_live(f"{Fore.YELLOW}Live trading avbrutt. Avslutter.{Style.RESET_ALL}", persist=True)

    # Startpunkt for scriptet
# Endre symbol og parametre her hvis ønskelig
if __name__ == "__main__":
    # Opprett strategi med standardparametre
    strategy = MT5FuturesStrategy(symbol="BTCUSD", paper_mode=True)  # Sett paper_mode=False for live
    strategy.run()