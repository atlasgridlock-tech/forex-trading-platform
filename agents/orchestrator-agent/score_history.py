"""
Confluence Score History Tracker
Tracks and visualizes how confluence scores evolve over time for each symbol.
"""

import os
import json
import io
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator

# Storage path
MT5_FILES_PATH = Path(os.getenv("MT5_FILES_PATH", "/mt5files"))
HISTORY_DIR = MT5_FILES_PATH / "score_history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# Chart styling
CHART_COLORS = {
    "background": "#131722",
    "grid": "#1e222d",
    "text": "#848e9c",
    "total": "#2196f3",  # Blue for total confluence
    "technical": "#26a69a",  # Teal
    "structure": "#ab47bc",  # Purple
    "macro": "#ff9800",  # Orange
    "sentiment": "#e91e63",  # Pink
    "regime": "#00bcd4",  # Cyan
    "risk_execution": "#8bc34a",  # Light green
    "threshold_75": "#26a69a",  # Green for execute threshold
    "threshold_60": "#f59e0b",  # Amber for watchlist threshold
}


class ScoreHistoryTracker:
    """Tracks confluence score history for all symbols."""
    
    def __init__(self, max_history_hours: int = 48):
        self.max_history_hours = max_history_hours
        self.history: Dict[str, List[dict]] = defaultdict(list)
        self._load_history()
    
    def _get_history_file(self, date: str) -> Path:
        """Get history file path for a date."""
        return HISTORY_DIR / f"scores_{date}.json"
    
    def _load_history(self):
        """Load history from recent files."""
        for i in range(3):  # Load last 3 days
            date = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
            file_path = self._get_history_file(date)
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        for symbol, scores in data.items():
                            self.history[symbol].extend(scores)
                except Exception as e:
                    print(f"[ScoreHistory] Error loading {file_path}: {e}")
        
        # Sort and dedupe
        for symbol in self.history:
            self.history[symbol] = sorted(
                self.history[symbol],
                key=lambda x: x.get("timestamp", "")
            )
            # Remove duplicates by timestamp
            seen = set()
            unique = []
            for entry in self.history[symbol]:
                ts = entry.get("timestamp", "")
                if ts not in seen:
                    seen.add(ts)
                    unique.append(entry)
            self.history[symbol] = unique
        
        # Prune old entries
        self._prune_old_entries()
    
    def _prune_old_entries(self):
        """Remove entries older than max_history_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=self.max_history_hours)
        cutoff_str = cutoff.isoformat()
        
        for symbol in self.history:
            self.history[symbol] = [
                e for e in self.history[symbol]
                if e.get("timestamp", "") >= cutoff_str
            ]
    
    def _save_history(self):
        """Save today's history to file."""
        date = datetime.utcnow().strftime("%Y-%m-%d")
        file_path = self._get_history_file(date)
        
        # Filter to today's entries only
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        today_data = {}
        
        for symbol, scores in self.history.items():
            today_scores = [s for s in scores if s.get("timestamp", "") >= today_start]
            if today_scores:
                today_data[symbol] = today_scores
        
        try:
            with open(file_path, 'w') as f:
                json.dump(today_data, f, indent=2, default=str)
        except Exception as e:
            print(f"[ScoreHistory] Error saving: {e}")
    
    def record_score(
        self,
        symbol: str,
        total_score: int,
        breakdown: Dict[str, int],
        direction: str,
        strategy: str = "",
        decision: str = "",  # "execute", "watchlist", "blocked"
    ):
        """Record a confluence score reading."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "total": total_score,
            "breakdown": breakdown,
            "direction": direction,
            "strategy": strategy,
            "decision": decision,
        }
        
        self.history[symbol].append(entry)
        self._prune_old_entries()
        self._save_history()
    
    def get_history(
        self,
        symbol: str,
        hours: int = 24,
    ) -> List[dict]:
        """Get score history for a symbol."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()
        
        return [
            e for e in self.history.get(symbol, [])
            if e.get("timestamp", "") >= cutoff_str
        ]
    
    def get_all_symbols(self) -> List[str]:
        """Get all symbols with history."""
        return list(self.history.keys())
    
    def get_latest_scores(self) -> Dict[str, dict]:
        """Get the most recent score for each symbol."""
        latest = {}
        for symbol, scores in self.history.items():
            if scores:
                latest[symbol] = scores[-1]
        return latest


def generate_score_history_chart(
    history: List[dict],
    symbol: str,
    show_breakdown: bool = True,
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a line chart showing confluence score evolution over time.
    
    Args:
        history: List of score entries with timestamps
        symbol: Symbol name for title
        show_breakdown: Whether to show component breakdown
        output_path: Optional file path to save
    
    Returns:
        PNG image bytes
    """
    if not history:
        return None
    
    try:
        # Parse data
        timestamps = []
        totals = []
        breakdowns = defaultdict(list)
        decisions = []
        
        for entry in history:
            try:
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                timestamps.append(ts)
                totals.append(entry.get("total", 0))
                decisions.append(entry.get("decision", ""))
                
                bd = entry.get("breakdown", {})
                for key in ["technical", "structure", "macro", "sentiment", "regime", "risk_execution"]:
                    breakdowns[key].append(bd.get(key, 0))
            except:
                continue
        
        if not timestamps:
            return None
        
        # Create figure
        fig, ax = plt.subplots(figsize=(14, 7), facecolor=CHART_COLORS["background"])
        ax.set_facecolor(CHART_COLORS["background"])
        
        # Plot total score
        ax.plot(timestamps, totals, 
                color=CHART_COLORS["total"], 
                linewidth=2.5, 
                label=f'Total Confluence',
                marker='o',
                markersize=4)
        
        # Fill area under curve with gradient effect
        ax.fill_between(timestamps, totals, alpha=0.2, color=CHART_COLORS["total"])
        
        # Plot breakdown components if requested
        if show_breakdown and len(timestamps) > 1:
            for key, values in breakdowns.items():
                if any(v > 0 for v in values):
                    ax.plot(timestamps, values,
                           color=CHART_COLORS.get(key, "#666"),
                           linewidth=1,
                           alpha=0.7,
                           label=key.replace("_", " ").title(),
                           linestyle='--')
        
        # Threshold lines
        ax.axhline(y=75, color=CHART_COLORS["threshold_75"], linestyle='-', 
                   linewidth=1.5, alpha=0.8, label='Execute (75)')
        ax.axhline(y=60, color=CHART_COLORS["threshold_60"], linestyle='--', 
                   linewidth=1, alpha=0.6, label='Watchlist (60)')
        
        # Mark execution/watchlist decisions
        for i, (ts, score, dec) in enumerate(zip(timestamps, totals, decisions)):
            if dec == "execute":
                ax.scatter([ts], [score], color='#26a69a', s=100, zorder=5, marker='^')
            elif dec == "watchlist":
                ax.scatter([ts], [score], color='#f59e0b', s=60, zorder=5, marker='s')
        
        # Styling
        ax.set_title(f'{symbol} Confluence Score History', 
                    fontsize=16, fontweight='bold', color='white', pad=20)
        ax.set_xlabel('Time (UTC)', fontsize=10, color=CHART_COLORS["text"])
        ax.set_ylabel('Score', fontsize=10, color=CHART_COLORS["text"])
        
        # Y-axis
        ax.set_ylim(0, 105)
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        
        # X-axis formatting
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        plt.xticks(rotation=45)
        
        # Grid
        ax.grid(True, color=CHART_COLORS["grid"], alpha=0.5, linestyle='-', linewidth=0.5)
        
        # Spines
        for spine in ax.spines.values():
            spine.set_color(CHART_COLORS["grid"])
        
        # Tick colors
        ax.tick_params(colors=CHART_COLORS["text"])
        
        # Legend
        ax.legend(loc='upper left', fontsize=8,
                 facecolor=CHART_COLORS["background"],
                 edgecolor=CHART_COLORS["grid"],
                 labelcolor=CHART_COLORS["text"])
        
        # Add current score annotation
        if totals:
            current = totals[-1]
            status = "EXECUTE" if current >= 75 else "WATCHLIST" if current >= 60 else "NO TRADE"
            status_color = "#26a69a" if current >= 75 else "#f59e0b" if current >= 60 else "#ef5350"
            ax.annotate(
                f'Current: {current}\n{status}',
                xy=(timestamps[-1], current),
                xytext=(10, 20),
                textcoords='offset points',
                fontsize=11,
                fontweight='bold',
                color=status_color,
                bbox=dict(boxstyle='round,pad=0.5', facecolor=CHART_COLORS["background"],
                         edgecolor=status_color, alpha=0.9)
            )
        
        # Stats box
        if totals:
            avg_score = sum(totals) / len(totals)
            max_score = max(totals)
            min_score = min(totals)
            
            stats_text = f'Avg: {avg_score:.0f} | Max: {max_score} | Min: {min_score}'
            ax.text(0.98, 0.02, stats_text, transform=ax.transAxes,
                   fontsize=9, color=CHART_COLORS["text"],
                   ha='right', va='bottom',
                   bbox=dict(boxstyle='round', facecolor=CHART_COLORS["background"],
                            edgecolor=CHART_COLORS["grid"], alpha=0.8))
        
        plt.tight_layout()
        
        # Save to bytes
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150,
                   facecolor=CHART_COLORS["background"],
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
        print(f"[ScoreHistory] Chart generation error: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_multi_symbol_chart(
    tracker: ScoreHistoryTracker,
    symbols: List[str],
    hours: int = 12,
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    """
    Generate a chart comparing confluence scores across multiple symbols.
    """
    try:
        fig, ax = plt.subplots(figsize=(14, 8), facecolor=CHART_COLORS["background"])
        ax.set_facecolor(CHART_COLORS["background"])
        
        colors = ['#2196f3', '#26a69a', '#ff9800', '#e91e63', '#ab47bc', 
                  '#00bcd4', '#8bc34a', '#ff5722', '#607d8b']
        
        for i, symbol in enumerate(symbols):
            history = tracker.get_history(symbol, hours)
            if not history:
                continue
            
            timestamps = []
            totals = []
            for entry in history:
                try:
                    ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    timestamps.append(ts)
                    totals.append(entry.get("total", 0))
                except:
                    continue
            
            if timestamps:
                color = colors[i % len(colors)]
                ax.plot(timestamps, totals, color=color, linewidth=2,
                       label=f'{symbol} ({totals[-1]})', marker='o', markersize=3)
        
        # Threshold lines
        ax.axhline(y=75, color=CHART_COLORS["threshold_75"], linestyle='-',
                   linewidth=1.5, alpha=0.8, label='Execute (75)')
        ax.axhline(y=60, color=CHART_COLORS["threshold_60"], linestyle='--',
                   linewidth=1, alpha=0.6, label='Watchlist (60)')
        
        # Styling
        ax.set_title('Multi-Symbol Confluence Comparison', 
                    fontsize=16, fontweight='bold', color='white', pad=20)
        ax.set_xlabel('Time (UTC)', fontsize=10, color=CHART_COLORS["text"])
        ax.set_ylabel('Confluence Score', fontsize=10, color=CHART_COLORS["text"])
        ax.set_ylim(0, 105)
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)
        
        ax.grid(True, color=CHART_COLORS["grid"], alpha=0.5)
        for spine in ax.spines.values():
            spine.set_color(CHART_COLORS["grid"])
        ax.tick_params(colors=CHART_COLORS["text"])
        
        ax.legend(loc='upper left', fontsize=9,
                 facecolor=CHART_COLORS["background"],
                 edgecolor=CHART_COLORS["grid"],
                 labelcolor=CHART_COLORS["text"],
                 ncol=2)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150,
                   facecolor=CHART_COLORS["background"],
                   edgecolor='none', bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(buf.getvalue())
            buf.seek(0)
        
        return buf.getvalue()
        
    except Exception as e:
        print(f"[ScoreHistory] Multi-chart error: {e}")
        return None


# Global tracker instance
_tracker: Optional[ScoreHistoryTracker] = None

def get_tracker() -> ScoreHistoryTracker:
    """Get or create the global tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = ScoreHistoryTracker()
    return _tracker


# Test
if __name__ == "__main__":
    import random
    
    tracker = ScoreHistoryTracker()
    
    # Generate test data
    base_time = datetime.utcnow() - timedelta(hours=12)
    
    for symbol in ["USDJPY", "GBPUSD", "AUDNZD"]:
        base_score = random.randint(55, 70)
        for i in range(48):  # 48 readings over 12 hours (15 min intervals)
            # Simulate score fluctuation
            score = base_score + random.randint(-10, 15)
            score = max(40, min(85, score))
            
            breakdown = {
                "technical": random.randint(15, 25),
                "structure": random.randint(8, 15),
                "macro": random.randint(3, 12),
                "sentiment": random.randint(5, 10),
                "regime": random.randint(3, 10),
                "risk_execution": random.randint(8, 11),
            }
            
            # Manually set timestamp for test data
            entry = {
                "timestamp": (base_time + timedelta(minutes=15*i)).isoformat(),
                "total": score,
                "breakdown": breakdown,
                "direction": "short" if symbol == "USDJPY" else "long",
                "strategy": "TREND_CONTINUATION",
                "decision": "execute" if score >= 75 else "watchlist" if score >= 60 else "blocked",
            }
            tracker.history[symbol].append(entry)
    
    # Generate single symbol chart
    history = tracker.get_history("USDJPY", 24)
    chart_bytes = generate_score_history_chart(
        history, "USDJPY",
        show_breakdown=True,
        output_path="/tmp/usdjpy_score_history.png"
    )
    print(f"Single chart generated: {len(chart_bytes) if chart_bytes else 0} bytes")
    
    # Generate multi-symbol chart
    multi_bytes = generate_multi_symbol_chart(
        tracker,
        ["USDJPY", "GBPUSD", "AUDNZD"],
        hours=12,
        output_path="/tmp/multi_score_history.png"
    )
    print(f"Multi chart generated: {len(multi_bytes) if multi_bytes else 0} bytes")
