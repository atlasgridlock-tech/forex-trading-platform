"""
Chart Generator for Trade Journal
Generates professional candlestick charts with entry/exit markers
"""

import os
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from PIL import Image

# Chart style configuration
CHART_STYLE = {
    "base_mpl_style": "dark_background",
    "marketcolors": {
        "candle": {"up": "#26a69a", "down": "#ef5350"},
        "edge": {"up": "#26a69a", "down": "#ef5350"},
        "wick": {"up": "#26a69a", "down": "#ef5350"},
        "ohlc": {"up": "#26a69a", "down": "#ef5350"},
        "volume": {"up": "#26a69a80", "down": "#ef535080"},
        "vcedge": {"up": "#26a69a", "down": "#ef5350"},
        "vcdopcod": False,
        "alpha": 1.0,
    },
    "mavcolors": ["#2196f3", "#ff9800", "#9c27b0"],
    "facecolor": "#131722",
    "figcolor": "#131722",
    "gridcolor": "#1e222d",
    "gridstyle": "-",
    "gridwidth": 0.5,
    "rc": {
        "axes.labelcolor": "#848e9c",
        "axes.edgecolor": "#1e222d",
        "xtick.color": "#848e9c",
        "ytick.color": "#848e9c",
        "font.size": 9,
    },
}


def create_chart_style():
    """Create mplfinance style from configuration."""
    mc = mpf.make_marketcolors(
        up=CHART_STYLE["marketcolors"]["candle"]["up"],
        down=CHART_STYLE["marketcolors"]["candle"]["down"],
        edge={"up": CHART_STYLE["marketcolors"]["edge"]["up"], 
              "down": CHART_STYLE["marketcolors"]["edge"]["down"]},
        wick={"up": CHART_STYLE["marketcolors"]["wick"]["up"], 
              "down": CHART_STYLE["marketcolors"]["wick"]["down"]},
        volume={"up": CHART_STYLE["marketcolors"]["volume"]["up"], 
                "down": CHART_STYLE["marketcolors"]["volume"]["down"]},
    )
    
    style = mpf.make_mpf_style(
        base_mpl_style=CHART_STYLE["base_mpl_style"],
        marketcolors=mc,
        facecolor=CHART_STYLE["facecolor"],
        figcolor=CHART_STYLE["figcolor"],
        gridcolor=CHART_STYLE["gridcolor"],
        gridstyle=CHART_STYLE["gridstyle"],
        rc=CHART_STYLE["rc"],
    )
    
    return style


def generate_sample_ohlc(symbol: str, periods: int = 100, 
                         base_price: float = 1.0, 
                         volatility: float = 0.001) -> pd.DataFrame:
    """
    Generate sample OHLC data for testing.
    In production, this would fetch from the data-agent.
    """
    import numpy as np
    
    np.random.seed(42)  # Reproducible for testing
    
    dates = pd.date_range(end=datetime.utcnow(), periods=periods, freq='1h')
    
    # Generate random walk
    returns = np.random.randn(periods) * volatility
    prices = base_price * np.exp(np.cumsum(returns))
    
    # Generate OHLC from close prices
    data = []
    for i, close in enumerate(prices):
        high = close * (1 + abs(np.random.randn() * volatility * 0.5))
        low = close * (1 - abs(np.random.randn() * volatility * 0.5))
        open_price = prices[i-1] if i > 0 else close
        
        # Ensure OHLC consistency
        high = max(high, open_price, close)
        low = min(low, open_price, close)
        
        data.append({
            'Date': dates[i],
            'Open': open_price,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': np.random.randint(1000, 10000),
        })
    
    df = pd.DataFrame(data)
    df.set_index('Date', inplace=True)
    return df


async def fetch_ohlc_data(symbol: str, timeframe: str = "H1", 
                          periods: int = 100) -> Optional[pd.DataFrame]:
    """
    Fetch OHLC data from the data-agent (Curator).
    Falls back to sample data if unavailable.
    """
    import httpx
    
    try:
        async with httpx.AsyncClient() as client:
            # Try to get data from Curator
            resp = await client.get(
                f"http://localhost:3021/api/ohlc/{symbol}",
                params={"timeframe": timeframe, "periods": periods},
                timeout=5.0
            )
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("candles"):
                    df = pd.DataFrame(data["candles"])
                    df['Date'] = pd.to_datetime(df['time'])
                    df = df.rename(columns={
                        'open': 'Open', 'high': 'High', 
                        'low': 'Low', 'close': 'Close', 
                        'volume': 'Volume'
                    })
                    df.set_index('Date', inplace=True)
                    return df
    except Exception as e:
        print(f"[ChartGen] Could not fetch OHLC: {e}")
    
    # Fallback to sample data
    base_price = 150.0 if "JPY" in symbol else 1.0
    volatility = 0.002 if "JPY" in symbol else 0.0005
    return generate_sample_ohlc(symbol, periods, base_price, volatility)


def generate_trade_chart(
    ohlc_data: pd.DataFrame,
    symbol: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    entry_time: Optional[datetime] = None,
    exit_time: Optional[datetime] = None,
    exit_price: Optional[float] = None,
    title: Optional[str] = None,
    show_ema: bool = True,
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a professional trading chart with entry/exit markers.
    
    Args:
        ohlc_data: DataFrame with OHLC data
        symbol: Trading pair
        direction: "long" or "short"
        entry_price: Entry price level
        stop_loss: Stop loss level
        take_profit: Take profit level
        entry_time: When trade was entered
        exit_time: When trade was closed (optional)
        exit_price: Exit price (optional)
        title: Chart title
        show_ema: Whether to show EMAs
        output_path: Save to file path (optional)
    
    Returns:
        PNG image bytes or None if failed
    """
    try:
        style = create_chart_style()
        
        # Create figure
        fig, axes = mpf.plot(
            ohlc_data,
            type='candle',
            style=style,
            title=title or f"{symbol} Trade Setup",
            ylabel='Price',
            volume=False,
            figsize=(12, 7),
            returnfig=True,
            tight_layout=True,
        )
        
        ax = axes[0]
        
        # Get x-axis range for horizontal lines
        x_min, x_max = ax.get_xlim()
        
        # Entry line (blue dashed)
        ax.axhline(y=entry_price, color='#2196f3', linestyle='--', 
                   linewidth=1.5, alpha=0.8, label=f'Entry: {entry_price}')
        
        # Stop loss line (red)
        ax.axhline(y=stop_loss, color='#ef5350', linestyle='-', 
                   linewidth=1.5, alpha=0.8, label=f'SL: {stop_loss}')
        
        # Take profit line (green)
        if take_profit > 0:
            ax.axhline(y=take_profit, color='#26a69a', linestyle='-', 
                       linewidth=1.5, alpha=0.8, label=f'TP: {take_profit}')
        
        # Fill zones
        if direction.lower() in ['long', 'buy']:
            # Profit zone (green) above entry
            if take_profit > entry_price:
                ax.axhspan(entry_price, take_profit, alpha=0.1, color='#26a69a')
            # Risk zone (red) below entry
            if stop_loss < entry_price:
                ax.axhspan(stop_loss, entry_price, alpha=0.1, color='#ef5350')
        else:
            # Profit zone (green) below entry for shorts
            if take_profit < entry_price and take_profit > 0:
                ax.axhspan(take_profit, entry_price, alpha=0.1, color='#26a69a')
            # Risk zone (red) above entry for shorts
            if stop_loss > entry_price:
                ax.axhspan(entry_price, stop_loss, alpha=0.1, color='#ef5350')
        
        # Exit marker if trade is closed
        if exit_time and exit_price:
            # Find the x position for exit time
            try:
                exit_idx = ohlc_data.index.get_indexer([exit_time], method='nearest')[0]
                ax.scatter(exit_idx, exit_price, marker='x', s=200, 
                          color='#ff9800', zorder=5, linewidths=3)
                ax.annotate(f'Exit: {exit_price}', xy=(exit_idx, exit_price),
                           xytext=(10, 10), textcoords='offset points',
                           color='#ff9800', fontsize=9)
            except:
                pass
        
        # Add legend
        ax.legend(loc='upper left', fontsize=8, 
                 facecolor='#1e222d', edgecolor='#333',
                 labelcolor='#848e9c')
        
        # Direction indicator
        direction_color = '#26a69a' if direction.lower() in ['long', 'buy'] else '#ef5350'
        direction_text = 'LONG' if direction.lower() in ['long', 'buy'] else 'SHORT'
        ax.text(0.02, 0.98, direction_text, transform=ax.transAxes,
                fontsize=12, fontweight='bold', color=direction_color,
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='#1e222d', 
                         edgecolor=direction_color, alpha=0.8))
        
        # Save to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, 
                   facecolor=CHART_STYLE["figcolor"],
                   edgecolor='none', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        
        # Save to file if path provided
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(buf.getvalue())
            buf.seek(0)
        
        return buf.getvalue()
        
    except Exception as e:
        print(f"[ChartGen] Error generating chart: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_trade_summary_image(
    trade_data: dict,
    confluence_breakdown: dict,
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a trade summary infographic showing:
    - Trade details
    - Confluence scores
    - Agent verdicts
    """
    try:
        fig, ax = plt.subplots(figsize=(10, 8), facecolor='#131722')
        ax.set_facecolor('#131722')
        ax.axis('off')
        
        symbol = trade_data.get('symbol', 'UNKNOWN')
        direction = trade_data.get('direction', 'long').upper()
        entry = trade_data.get('entry_price', 0)
        stop = trade_data.get('stop_loss', 0)
        tp = trade_data.get('take_profit', 0)
        
        # Title
        dir_color = '#26a69a' if direction == 'LONG' else '#ef5350'
        ax.text(0.5, 0.95, f"{symbol} {direction}", fontsize=24, fontweight='bold',
                color=dir_color, ha='center', transform=ax.transAxes)
        
        # Trade details section
        ax.text(0.05, 0.85, "TRADE DETAILS", fontsize=12, fontweight='bold',
                color='#848e9c', transform=ax.transAxes)
        
        details = [
            f"Entry: {entry}",
            f"Stop Loss: {stop}",
            f"Take Profit: {tp}",
            f"Risk: {abs(entry - stop) * (100 if entry > 50 else 10000):.1f} pips",
        ]
        
        for i, detail in enumerate(details):
            ax.text(0.05, 0.80 - i*0.05, detail, fontsize=10, color='#e0e0e0',
                   transform=ax.transAxes)
        
        # Confluence breakdown section
        ax.text(0.55, 0.85, "CONFLUENCE BREAKDOWN", fontsize=12, fontweight='bold',
                color='#848e9c', transform=ax.transAxes)
        
        total_score = sum(confluence_breakdown.values())
        y_pos = 0.80
        
        for category, score in confluence_breakdown.items():
            # Draw bar
            bar_width = score / 100 * 0.35
            color = '#26a69a' if score >= 15 else '#f59e0b' if score >= 10 else '#ef5350'
            
            ax.barh(y_pos, bar_width, height=0.03, left=0.55,
                   color=color, transform=ax.transAxes)
            ax.text(0.55, y_pos + 0.015, f"{category}: {score}", fontsize=9,
                   color='#e0e0e0', va='center', transform=ax.transAxes)
            y_pos -= 0.05
        
        # Total confluence
        ax.text(0.55, y_pos - 0.02, f"TOTAL: {total_score}/100", fontsize=14,
               fontweight='bold', color='#2196f3', transform=ax.transAxes)
        
        # Timestamp
        ax.text(0.5, 0.02, f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
               fontsize=8, color='#666', ha='center', transform=ax.transAxes)
        
        # Save to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150,
                   facecolor='#131722', edgecolor='none', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(buf.getvalue())
            buf.seek(0)
        
        return buf.getvalue()
        
    except Exception as e:
        print(f"[ChartGen] Error generating summary: {e}")
        return None


async def create_trade_journal_entry(
    trade_id: str,
    symbol: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    confluence_breakdown: dict,
    thesis: dict,
    strategy: str,
    output_dir: str = "/mt5files/trade_journal",
) -> dict:
    """
    Create a complete trade journal entry with charts and metadata.
    
    Returns:
        dict with paths to generated files
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    dir_short = 'LONG' if direction.lower() in ['long', 'buy'] else 'SHORT'
    
    # Create trade folder
    trade_folder = Path(output_dir) / f"{timestamp}_{symbol}_{dir_short}"
    trade_folder.mkdir(parents=True, exist_ok=True)
    
    result = {
        "trade_id": trade_id,
        "folder": str(trade_folder),
        "files": {},
    }
    
    # 1. Save trade metadata JSON
    metadata = {
        "trade_id": trade_id,
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confluence_breakdown": confluence_breakdown,
        "total_confluence": sum(confluence_breakdown.values()),
        "thesis": thesis,
        "strategy": strategy,
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    metadata_path = trade_folder / "trade_info.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2, default=str)
    result["files"]["metadata"] = str(metadata_path)
    
    # 2. Generate candlestick chart
    ohlc_data = await fetch_ohlc_data(symbol, "H1", 100)
    if ohlc_data is not None:
        chart_path = trade_folder / "chart_H1.png"
        chart_bytes = generate_trade_chart(
            ohlc_data=ohlc_data,
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            title=f"{symbol} {dir_short} - {strategy}",
            output_path=str(chart_path),
        )
        if chart_bytes:
            result["files"]["chart_h1"] = str(chart_path)
    
    # 3. Generate trade summary infographic
    summary_path = trade_folder / "confluence_summary.png"
    summary_bytes = generate_trade_summary_image(
        trade_data=metadata,
        confluence_breakdown=confluence_breakdown,
        output_path=str(summary_path),
    )
    if summary_bytes:
        result["files"]["summary"] = str(summary_path)
    
    # 4. Save confluence breakdown separately
    confluence_path = trade_folder / "confluence.json"
    with open(confluence_path, 'w') as f:
        json.dump({
            "breakdown": confluence_breakdown,
            "total": sum(confluence_breakdown.values()),
            "threshold": 75,
            "passed": sum(confluence_breakdown.values()) >= 75,
        }, f, indent=2)
    result["files"]["confluence"] = str(confluence_path)
    
    print(f"[ChartGen] Trade journal created: {trade_folder}")
    return result


# Test function
if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await create_trade_journal_entry(
            trade_id="TEST-001",
            symbol="USDJPY",
            direction="short",
            entry_price=150.500,
            stop_loss=150.600,
            take_profit=149.500,
            confluence_breakdown={
                "technical": 22,
                "structure": 14,
                "macro": 7,
                "sentiment": 8,
                "regime": 10,
                "risk_execution": 11,
            },
            thesis={
                "why_here": "Price at key resistance",
                "why_now": "Session open momentum",
                "why_direction": "Bearish trend + structure break",
                "invalidation": "Close above 150.600",
            },
            strategy="TREND_CONTINUATION",
            output_dir="/tmp/trade_journal_test",
        )
        print(f"Result: {json.dumps(result, indent=2)}")
    
    asyncio.run(test())
