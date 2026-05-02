#!/usr/bin/env python3
"""
Prepare training data by combining individual stock CSVs into a single historical_1m.csv
"""

import os
import sys
from pathlib import Path

import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def prepare_historical_data():
    """Load individual stock CSVs and combine into historical_1m.csv"""
    
    data_dir = Path(__file__).parent.parent / "data"
    output_file = data_dir / "historical_1m.csv"
    
    print(f"📂 Looking for stock CSV files in {data_dir}")
    
    # Get all CSV files except special ones
    csv_files = sorted([
        f for f in data_dir.glob("*.csv") 
        if f.name != "historical_1m.csv"
    ])
    
    print(f"📊 Found {len(csv_files)} stock files")
    
    if not csv_files:
        print("❌ No CSV files found!")
        return False
    
    # Use the first stock as base (e.g., RELIANCE.csv has good data)
    main_files = ["RELIANCE.csv", "TCS.csv", "INFY.csv", "HDFCBANK.csv", "SBIN.csv"]
    selected_files = [f for f in csv_files if f.name in main_files]
    
    if not selected_files:
        selected_files = csv_files[:1]  # Use first if none match
    
    selected_file = selected_files[0]
    print(f"\n📈 Using {selected_file.name} as training data")
    
    try:
        # Load the selected stock
        df = pd.read_csv(selected_file)
        
        # Expected columns: timestamp, open, high, low, close, volume
        print(f"\n   Columns: {list(df.columns)}")
        print(f"   Rows: {len(df)}")
        print(f"   Date range: {df.iloc[0, 0]} to {df.iloc[-1, 0]}")
        
        # Ensure required OHLCV columns exist
        required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
        
        # Check what columns we have
        col_map = {
            "datetime": "timestamp",
            "Datetime": "timestamp",
            "Date": "timestamp",
            "date": "timestamp",
            "timestamp": "timestamp",
            "Open": "open",
            "High": "high", 
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
        
        # Rename columns to lowercase
        df_renamed = df.rename(columns=col_map)
        
        # Check if we have the required columns
        missing = [c for c in required_cols if c not in df_renamed.columns]
        if missing:
            print(f"   ⚠️  Missing columns: {missing}")
            print(f"   Available: {list(df_renamed.columns)}")
            return False
        
        # Keep only required columns in correct order
        df_clean = df_renamed[required_cols].copy()
        
        # Ensure timestamp is datetime
        df_clean["timestamp"] = pd.to_datetime(df_clean["timestamp"])
        df_clean = df_clean.sort_values("timestamp")
        
        # Save to historical_1m.csv
        df_clean.to_csv(output_file, index=False)
        
        print(f"\n✅ Training data prepared!")
        print(f"   Saved to: {output_file}")
        print(f"   Rows: {len(df_clean)}")
        print(f"   Size: {output_file.stat().st_size / 1024 / 1024:.2f} MB")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = prepare_historical_data()
    sys.exit(0 if success else 1)
