//+------------------------------------------------------------------+
//|                                             AgentBridge_v5.mq5   |
//|                                    Forex Multi-Agent Platform    |
//|                                 Fixed: Auto-detect broker symbols |
//+------------------------------------------------------------------+
#property copyright "Forex Platform"
#property version   "5.00"
#property strict

// Settings
input int UpdateInterval = 5;  // Update interval in seconds

// Will be populated dynamically from Market Watch
string activeSymbols[];
int symbolCount = 0;

// Timeframes to export
ENUM_TIMEFRAMES timeframes[] = {PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4, PERIOD_D1};

datetime lastUpdate = 0;

//+------------------------------------------------------------------+
int OnInit()
{
    // Get symbols from Market Watch
    DetectSymbols();
    
    if(symbolCount == 0)
    {
        Print("ERROR: No forex symbols found in Market Watch!");
        Print("Please add pairs like EURUSD, GBPUSD to your Market Watch");
        return(INIT_FAILED);
    }
    
    EventSetTimer(UpdateInterval);
    Print("═══════════════════════════════════════════════════════");
    Print("AgentBridge v5.0 initialized");
    Print("Found ", symbolCount, " symbols in Market Watch");
    Print("Update interval: ", UpdateInterval, " seconds");
    Print("═══════════════════════════════════════════════════════");
    
    // Initial export
    ExportAllData();
    
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void DetectSymbols()
{
    // Look for forex pairs in Market Watch
    string basePairs[] = {"EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCHF", 
                          "USDCAD", "AUDUSD", "NZDUSD", "EURJPY", "EURGBP",
                          "EURAUD", "AUDNZD", "AUDJPY", "GBPAUD", "GBPCAD"};
    
    ArrayResize(activeSymbols, 0);
    symbolCount = 0;
    
    int total = SymbolsTotal(true);  // Only symbols in Market Watch
    Print("Scanning ", total, " symbols in Market Watch...");
    
    for(int i = 0; i < total; i++)
    {
        string sym = SymbolName(i, true);
        string symUpper = sym;
        StringToUpper(symUpper);
        
        // Check if this is a forex pair we want
        for(int j = 0; j < ArraySize(basePairs); j++)
        {
            // Check if symbol contains the base pair name
            if(StringFind(symUpper, basePairs[j]) >= 0 || 
               StringFind(sym, basePairs[j]) >= 0)
            {
                // Verify we can get data for this symbol
                double bid = SymbolInfoDouble(sym, SYMBOL_BID);
                if(bid > 0)
                {
                    ArrayResize(activeSymbols, symbolCount + 1);
                    activeSymbols[symbolCount] = sym;
                    symbolCount++;
                    Print("  ✓ Found: ", sym, " (bid: ", bid, ")");
                    break;
                }
            }
        }
    }
    
    if(symbolCount == 0)
    {
        Print("No forex pairs found! Trying all symbols with valid prices...");
        
        for(int i = 0; i < total && symbolCount < 20; i++)
        {
            string sym = SymbolName(i, true);
            double bid = SymbolInfoDouble(sym, SYMBOL_BID);
            
            // Check if it looks like forex (has reasonable price and digits)
            int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
            if(bid > 0 && digits >= 4)
            {
                ArrayResize(activeSymbols, symbolCount + 1);
                activeSymbols[symbolCount] = sym;
                symbolCount++;
                Print("  ✓ Added: ", sym);
            }
        }
    }
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("AgentBridge stopped");
}

//+------------------------------------------------------------------+
void OnTimer()
{
    ExportAllData();
}

//+------------------------------------------------------------------+
void ExportAllData()
{
    ExportMarketData();
    ExportCandleData();
    ExportAccountData();
    lastUpdate = TimeCurrent();
}

//+------------------------------------------------------------------+
void ExportAccountData()
{
    string filename = "account_data.csv";
    int handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI);
    
    if(handle == INVALID_HANDLE)
    {
        Print("ERROR: Cannot open ", filename, " - Error: ", GetLastError());
        return;
    }
    
    // Write header
    FileWrite(handle, "Balance", "Equity", "Margin", "FreeMargin", "Leverage", "Currency", "Profit", "Server", "Company");
    
    // Write account data
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double margin = AccountInfoDouble(ACCOUNT_MARGIN);
    double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
    long leverage = AccountInfoInteger(ACCOUNT_LEVERAGE);
    string currency = AccountInfoString(ACCOUNT_CURRENCY);
    double profit = AccountInfoDouble(ACCOUNT_PROFIT);
    string server = AccountInfoString(ACCOUNT_SERVER);
    string company = AccountInfoString(ACCOUNT_COMPANY);
    
    FileWrite(handle, 
              DoubleToString(balance, 2),
              DoubleToString(equity, 2),
              DoubleToString(margin, 2),
              DoubleToString(freeMargin, 2),
              IntegerToString(leverage),
              currency,
              DoubleToString(profit, 2),
              server,
              company);
    
    FileClose(handle);
    
    Print("[", TimeToString(TimeCurrent(), TIME_SECONDS), "] Account: Balance=", balance, " Equity=", equity);
}

//+------------------------------------------------------------------+
void ExportMarketData()
{
    string filename = "market_data.csv";
    int handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI);
    
    if(handle == INVALID_HANDLE)
    {
        Print("ERROR: Cannot open ", filename, " - Error: ", GetLastError());
        return;
    }
    
    // Write header
    FileWrite(handle, "Symbol", "Bid", "Ask", "Spread", "Time");
    
    int exported = 0;
    for(int i = 0; i < symbolCount; i++)
    {
        string sym = activeSymbols[i];
        
        double bid = SymbolInfoDouble(sym, SYMBOL_BID);
        double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
        int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
        double point = SymbolInfoDouble(sym, SYMBOL_POINT);
        
        if(bid > 0 && point > 0)
        {
            double spread = (ask - bid) / point;
            
            // Clean symbol name (remove suffix for standardization)
            string cleanSym = CleanSymbolName(sym);
            
            FileWrite(handle, cleanSym, 
                      DoubleToString(bid, digits), 
                      DoubleToString(ask, digits),
                      DoubleToString(spread, 1),
                      TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
            exported++;
        }
    }
    
    FileClose(handle);
    
    if(exported > 0)
    {
        Print("[", TimeToString(TimeCurrent(), TIME_SECONDS), "] Market: ", exported, " symbols");
    }
}

//+------------------------------------------------------------------+
void ExportCandleData()
{
    string filename = "candle_data.csv";
    int handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI);
    
    if(handle == INVALID_HANDLE)
    {
        Print("ERROR: Cannot open ", filename, " - Error: ", GetLastError());
        return;
    }
    
    // Write header
    FileWrite(handle, "Symbol", "Timeframe", "DateTime", "Open", "High", "Low", "Close", "Volume");
    
    int totalCandles = 0;
    
    for(int i = 0; i < symbolCount; i++)
    {
        string sym = activeSymbols[i];
        string cleanSym = CleanSymbolName(sym);
        int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
        
        for(int t = 0; t < ArraySize(timeframes); t++)
        {
            ENUM_TIMEFRAMES tf = timeframes[t];
            string tfName = TimeframeToString(tf);
            
            MqlRates rates[];
            ArraySetAsSeries(rates, true);
            
            int copied = CopyRates(sym, tf, 0, 500, rates);
            
            if(copied <= 0)
            {
                int err = GetLastError();
                if(err != 0)
                {
                    Print("Warning: CopyRates failed for ", sym, " ", tfName, " - Error: ", err);
                }
                continue;
            }
            
            // Write candles (oldest first for the file)
            for(int r = copied - 1; r >= 0; r--)
            {
                FileWrite(handle, 
                          cleanSym, 
                          tfName,
                          TimeToString(rates[r].time, TIME_DATE|TIME_SECONDS),
                          DoubleToString(rates[r].open, digits),
                          DoubleToString(rates[r].high, digits),
                          DoubleToString(rates[r].low, digits),
                          DoubleToString(rates[r].close, digits),
                          IntegerToString(rates[r].tick_volume));
                totalCandles++;
            }
        }
    }
    
    FileClose(handle);
    
    if(totalCandles > 0)
    {
        Print("[", TimeToString(TimeCurrent(), TIME_SECONDS), "] Candles: ", totalCandles, " total");
    }
    else
    {
        Print("WARNING: No candles exported! Check if charts have data.");
    }
}

//+------------------------------------------------------------------+
string CleanSymbolName(string sym)
{
    // Remove common broker suffixes
    string result = sym;
    
    string suffixes[] = {".ecn", ".ECN", "-ECN", ".s", ".pro", ".r", "_SB", ".i", ".e", ".m", ".a", ".b", 
                         ".raw", ".std", "#", "+"};
    
    for(int i = 0; i < ArraySize(suffixes); i++)
    {
        int pos = StringFind(result, suffixes[i]);
        if(pos > 0)
        {
            result = StringSubstr(result, 0, pos);
            break;
        }
    }
    
    // Also try to extract just the currency pair (6 chars like EURUSD)
    if(StringLen(result) > 6)
    {
        // Check if first 6 chars are valid currency codes
        string first6 = StringSubstr(result, 0, 6);
        if(IsValidPair(first6))
        {
            result = first6;
        }
    }
    
    return result;
}

//+------------------------------------------------------------------+
bool IsValidPair(string pair)
{
    string currencies[] = {"EUR", "USD", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"};
    
    if(StringLen(pair) != 6) return false;
    
    string base = StringSubstr(pair, 0, 3);
    string quote = StringSubstr(pair, 3, 3);
    
    bool baseValid = false;
    bool quoteValid = false;
    
    for(int i = 0; i < ArraySize(currencies); i++)
    {
        if(base == currencies[i]) baseValid = true;
        if(quote == currencies[i]) quoteValid = true;
    }
    
    return baseValid && quoteValid;
}

//+------------------------------------------------------------------+
string TimeframeToString(ENUM_TIMEFRAMES tf)
{
    switch(tf)
    {
        case PERIOD_M1:  return "M1";
        case PERIOD_M5:  return "M5";
        case PERIOD_M15: return "M15";
        case PERIOD_M30: return "M30";
        case PERIOD_H1:  return "H1";
        case PERIOD_H4:  return "H4";
        case PERIOD_D1:  return "D1";
        case PERIOD_W1:  return "W1";
        case PERIOD_MN1: return "MN1";
        default: return "M1";
    }
}

//+------------------------------------------------------------------+
void OnTick()
{
    // Optional: Export on every tick for faster updates
    // Uncomment if you want real-time tick data
    // ExportMarketData();
}
//+------------------------------------------------------------------+
