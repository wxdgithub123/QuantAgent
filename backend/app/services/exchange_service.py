"""
Multi-Exchange Service
支持多个交易所的公开数据获取：Binance, OKX, Bybit, Gate.io, Bitget, Coinbase, Kraken
"""

import ccxt.async_support as ccxt
import asyncio
import aiohttp
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.core.config import get_proxy_url
from app.models.market_data import KlineData, TickerData, SymbolInfo
import logging

logger = logging.getLogger(__name__)


class ExchangeService:
    """多交易所服务类"""
    
    # 支持的交易所列表
    SUPPORTED_EXCHANGES = {
        "binance": {
            "id": "binance",
            "name": "币安",
            "ccxt_id": "binance",
            "default_type": "spot",
            "testnet": "binancecoin Futures",  # Binance 没有独立的 testnet ID
        },
        "okx": {
            "id": "okx",
            "name": "OKX",
            "ccxt_id": "okx",
            "default_type": "spot",
            "testnet": "okx",
        },
        "bybit": {
            "id": "bybit",
            "name": "Bybit",
            "ccxt_id": "bybit",
            "default_type": "spot",
            "testnet": "bybit",
        },
        "gateio": {
            "id": "gateio",
            "name": "Gate.io",
            "ccxt_id": "gateio",
            "default_type": "spot",
            "testnet": "gateio",
        },
        "bitget": {
            "id": "bitget",
            "name": "Bitget",
            "ccxt_id": "bitget",
            "default_type": "spot",
            "testnet": "bitget",
        },
        "coinbase": {
            "id": "coinbase",
            "name": "Coinbase",
            "ccxt_id": "coinbase",
            "default_type": "spot",
            "testnet": "coinbase",
        },
        "kraken": {
            "id": "kraken",
            "name": "Kraken",
            "ccxt_id": "kraken",
            "default_type": "spot",
            "testnet": "kraken",
        },
    }
    
    def __init__(self):
        self._exchanges: Dict[str, ccxt.Exchange] = {}
        self._proxy_url = get_proxy_url()
        self._config = {
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {
                'adjustForTimeDifference': True,
            }
        }
        
        if self._proxy_url:
            self._config['aiohttp_proxy'] = self._proxy_url
            logger.info(f"ExchangeService: using proxy {self._proxy_url}")
    
    async def _get_exchange(self, exchange_id: str, use_testnet: bool = False) -> ccxt.Exchange:
        """获取或创建交易所实例"""
        cache_key = f"{exchange_id}_testnet" if use_testnet else exchange_id
        
        if cache_key in self._exchanges:
            return self._exchanges[cache_key]
        
        config = self._config.copy()
        
        if use_testnet and exchange_id in self.SUPPORTED_EXCHANGES:
            testnet_id = self.SUPPORTED_EXCHANGES[exchange_id].get("testnet")
            if testnet_id:
                config['options']['defaultType'] = 'testnet'
        
        exchange_class = getattr(ccxt, self.SUPPORTED_EXCHANGES[exchange_id]['ccxt_id'])
        exchange = exchange_class(config)
        
        self._exchanges[cache_key] = exchange
        return exchange
    
    def _normalize_symbol(self, exchange_id: str, symbol: str) -> str:
        """根据交易所规范化交易对格式"""
        symbol = symbol.upper()
        
        # 已经是标准格式
        if "/" in symbol:
            return symbol
        
        # 常见报价货币
        for quote in ["USDT", "USDC", "USD", "BTC", "ETH", "BNB"]:
            if symbol.endswith(quote) and len(symbol) > len(quote):
                base = symbol[:-len(quote)]
                return f"{base}/{quote}"
        
        return symbol
    
    async def get_klines(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
        use_testnet: bool = False
    ) -> List[KlineData]:
        """获取 K 线数据"""
        exchange = await self._get_exchange(exchange_id, use_testnet)
        symbol = self._normalize_symbol(exchange_id, symbol)
        
        try:
            ohlcv = await exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                limit=min(limit, 1000),
                since=since
            )
            
            klines = []
            for item in ohlcv:
                klines.append(KlineData(
                    timestamp=datetime.fromtimestamp(item[0] / 1000),
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5])
                ))
            
            return klines
        except Exception as e:
            logger.error(f"[{exchange_id}] Failed to fetch klines for {symbol}: {e}")
            raise Exception(f"[{exchange_id}] Failed to fetch klines for {symbol}: {str(e)}")
        finally:
            await exchange.close()
    
    async def get_ticker(
        self,
        exchange_id: str,
        symbol: str,
        use_testnet: bool = False
    ) -> TickerData:
        """获取实时行情"""
        exchange = await self._get_exchange(exchange_id, use_testnet)
        symbol = self._normalize_symbol(exchange_id, symbol)
        
        try:
            ticker = await exchange.fetch_ticker(symbol)
            clean_symbol = symbol.replace("/", "")

            # 某些交易所可能返回 None 值，需要安全处理
            def safe_float(value, default=0.0):
                if value is None:
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            return TickerData(
                symbol=clean_symbol,
                price=safe_float(ticker.get('last'), 0.0),
                change_24h=safe_float(ticker.get('change'), 0.0),
                change_percent=safe_float(ticker.get('percentage'), 0.0),
                volume=safe_float(ticker.get('quoteVolume'), 0.0),
                high_24h=safe_float(ticker.get('high'), 0.0),
                low_24h=safe_float(ticker.get('low'), 0.0),
                timestamp=datetime.fromtimestamp(safe_float(ticker.get('timestamp'), 0) / 1000) if ticker.get('timestamp') else datetime.now()
            )
        except Exception as e:
            logger.error(f"[{exchange_id}] Failed to fetch ticker for {symbol}: {e}")
            raise Exception(f"[{exchange_id}] Failed to fetch ticker for {symbol}: {str(e)}")
        finally:
            await exchange.close()
    
    async def get_price(
        self,
        exchange_id: str,
        symbol: str,
        use_testnet: bool = False
    ) -> float:
        """获取当前价格"""
        ticker = await self.get_ticker(exchange_id, symbol, use_testnet)
        return ticker.price
    
    async def get_order_book(
        self,
        exchange_id: str,
        symbol: str,
        limit: int = 100,
        use_testnet: bool = False
    ) -> Dict[str, Any]:
        """获取订单簿"""
        exchange = await self._get_exchange(exchange_id, use_testnet)
        symbol = self._normalize_symbol(exchange_id, symbol)
        
        try:
            order_book = await exchange.fetch_order_book(symbol, limit=limit)
            return {
                'symbol': symbol.replace("/", ""),
                'exchange': exchange_id,
                'bids': order_book['bids'],
                'asks': order_book['asks'],
                'timestamp': datetime.fromtimestamp(order_book['timestamp'] / 1000)
            }
        except Exception as e:
            logger.error(f"[{exchange_id}] Failed to fetch order book for {symbol}: {e}")
            raise Exception(f"[{exchange_id}] Failed to fetch order book for {symbol}: {str(e)}")
        finally:
            await exchange.close()
    
    async def get_symbols(
        self,
        exchange_id: str,
        use_testnet: bool = False
    ) -> List[SymbolInfo]:
        """获取交易对列表"""
        exchange = await self._get_exchange(exchange_id, use_testnet)
        
        try:
            markets = await exchange.load_markets()
            symbols = []
            
            for symbol, market in markets.items():
                if market.get('active', False):
                    symbols.append(SymbolInfo(
                        symbol=symbol.replace('/', ''),
                        base=market['base'],
                        quote=market['quote'],
                        exchange=exchange_id
                    ))
            
            return symbols
        except Exception as e:
            logger.error(f"[{exchange_id}] Failed to fetch symbols: {e}")
            raise Exception(f"[{exchange_id}] Failed to fetch symbols: {str(e)}")
        finally:
            await exchange.close()
    
    async def get_recent_trades(
        self,
        exchange_id: str,
        symbol: str,
        limit: int = 100,
        use_testnet: bool = False
    ) -> List[Dict]:
        """获取最近成交记录"""
        exchange = await self._get_exchange(exchange_id, use_testnet)
        symbol = self._normalize_symbol(exchange_id, symbol)
        
        try:
            trades = await exchange.fetch_trades(symbol, limit=limit)
            return [
                {
                    'id': trade['id'],
                    'price': float(trade['price']),
                    'amount': float(trade['amount']),
                    'side': trade['side'],
                    'timestamp': datetime.fromtimestamp(trade['timestamp'] / 1000)
                }
                for trade in trades
            ]
        except Exception as e:
            logger.error(f"[{exchange_id}] Failed to fetch trades for {symbol}: {e}")
            raise Exception(f"[{exchange_id}] Failed to fetch trades for {symbol}: {str(e)}")
        finally:
            await exchange.close()
    
    def get_supported_exchanges(self) -> List[Dict[str, str]]:
        """获取支持的交易所列表"""
        return [
            {
                "id": info["id"],
                "name": info["name"],
                "has_testnet": info.get("testnet") is not None
            }
            for info in self.SUPPORTED_EXCHANGES.values()
        ]
    
    async def close_all(self):
        """关闭所有连接"""
        for exchange in self._exchanges.values():
            await exchange.close()
        self._exchanges.clear()


# 单例实例
exchange_service = ExchangeService()
