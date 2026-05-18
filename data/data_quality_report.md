# Data Quality Report

All timestamps are UTC. Missing rows are reported only; the script does not synthesize candles.

| symbol | source | market_type | timeframe | train_start | train_end | test_start | test_end | train_rows | test_rows | missing_count | duplicate_count | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC/USDT | Binance Spot historical klines | Spot | 1h | 2023-07-01 00:00:00 | 2025-06-30 23:00:00 | 2025-07-01 00:00:00 | 2025-12-31 23:00:00 | 17544 | 4416 | 0 | 0 | ok |
| ETH/USDT | Binance Spot historical klines | Spot | 1h | 2023-07-01 00:00:00 | 2025-06-30 23:00:00 | 2025-07-01 00:00:00 | 2025-12-31 23:00:00 | 17544 | 4416 | 0 | 0 | ok |
| SOL/USDT | Binance Spot historical klines | Spot | 1h | 2023-07-01 00:00:00 | 2025-06-30 23:00:00 | 2025-07-01 00:00:00 | 2025-12-31 23:00:00 | 17544 | 4416 | 0 | 0 | ok |

## Files

- `BTC_train_1h.csv`
- `BTC_test_1h.csv`
- `ETH_train_1h.csv`
- `ETH_test_1h.csv`
- `SOL_train_1h.csv`
- `SOL_test_1h.csv`
