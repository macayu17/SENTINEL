# ABIDES-Style Modules

This package provides a lightweight, ABIDES-style simulation stack that lives alongside the existing SENTINEL simulator. It includes:

- Discrete event kernel
- Exchange agent with an order book
- Base agent class
- Example agents (market maker + noise)
- Simple simulation runner
- Optional oracle + latency integration

## Quick Start

Run the demo script:

```powershell
Set-Location d:\Sentinel\SENTINEL-main\backend
..\.venv\Scripts\python.exe .\scripts\run_abides_demo.py
```

You should see a short summary including total trades and final prices.

## Oracle + Latency

The ABIDES simulator can consume the existing oracle + latency models from the SENTINEL market module. You can enable them in the demo script by passing `OracleConfig` and `LatencyConfig`.

## Structure

- backend/src/abides
  - kernel.py
  - messages.py
  - order_book.py
  - simulation.py
  - agents/
    - base.py
    - exchange.py
    - market_maker.py
    - noise.py

## Notes

This is intentionally minimal and intended as a foundation for additional ABIDES-style agents, message types, and replay pipelines.

To remove ABIDES later, delete the [backend/src/abides](backend/src/abides) folder and the demo/test files. The backend will detect the missing module and disable ABIDES endpoints automatically.
