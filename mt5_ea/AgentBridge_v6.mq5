//+------------------------------------------------------------------+
//|                                             AgentBridge_v6.mq5   |
//|                                    Forex Multi-Agent Platform    |
//|                      Full Bridge: Data Export + Order Execution  |
//|                      v6.1 - Fixed CSV delimiter (semicolon)      |
//+------------------------------------------------------------------+
#property copyright "Forex Platform"
#property version   "6.10"
#property strict

// Settings
input int UpdateInterval = 5;  // Update interval in seconds
input double MaxSlippagePips = 3.0;  // Maximum allowed slippage in pips

// Will be populated dynamically from Market Watch
string activeSymbols[];
int symbolCount = 0;

// Timeframes to export
ENUM_TIMEFRAMES timeframes[] = {PERIOD_M15, PERIOD_M30, PERIOD_H1, PERIOD_H4, PERIOD_D1};

datetime lastUpdate = 0;
datetime lastOrderCheck = 0;

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
    Print("═══════════════════════════════════════════════════════════════");
    Print("AgentBridge v6.1 - FULL BRIDGE (Data + Orders)");
    Print("═══════════════════════════════════════════════════════════════");
    Print("FIXED: CSV delimiter now uses semicolon (;) for all files");
    Print("Found ", symbolCount, " symbols in Market Watch");
    Print("Update interval: ", UpdateInterval, " seconds");
    Print("Max slippage: ", MaxSlippagePips, " pips");
    Print("═══════════════════════════════════════════════════════════════");
    
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
    ProcessPendingOrders();
}

//+------------------------------------------------------------------+
void ExportAllData()
{
    ExportMarketData();
    ExportCandleData();
    ExportAccountData();
    ExportPositions();
    lastUpdate = TimeCurrent();
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
}

//+------------------------------------------------------------------+
void ExportPositions()
{
    string filename = "positions.csv";
    // Use semicolon delimiter for consistency with Python reader
    int handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI, ';');
    
    if(handle == INVALID_HANDLE)
    {
        return;
    }
    
    // Write header
    FileWrite(handle, "Ticket", "Symbol", "Type", "Volume", "OpenPrice", "SL", "TP", "Profit", "OpenTime", "Magic", "Comment");
    
    int total = PositionsTotal();
    for(int i = 0; i < total; i++)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0)
        {
            string sym = PositionGetString(POSITION_SYMBOL);
            string cleanSym = CleanSymbolName(sym);
            int type = (int)PositionGetInteger(POSITION_TYPE);
            double volume = PositionGetDouble(POSITION_VOLUME);
            double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            double sl = PositionGetDouble(POSITION_SL);
            double tp = PositionGetDouble(POSITION_TP);
            double profit = PositionGetDouble(POSITION_PROFIT);
            datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
            long magic = PositionGetInteger(POSITION_MAGIC);
            string comment = PositionGetString(POSITION_COMMENT);
            
            FileWrite(handle,
                      IntegerToString(ticket),
                      cleanSym,
                      type == POSITION_TYPE_BUY ? "BUY" : "SELL",
                      DoubleToString(volume, 2),
                      DoubleToString(openPrice, 5),
                      DoubleToString(sl, 5),
                      DoubleToString(tp, 5),
                      DoubleToString(profit, 2),
                      TimeToString(openTime, TIME_DATE|TIME_SECONDS),
                      IntegerToString(magic),
                      comment);
        }
    }
    
    FileClose(handle);
}

//+------------------------------------------------------------------+
// ORDER EXECUTION SYSTEM
//+------------------------------------------------------------------+
void ProcessPendingOrders()
{
    string filename = "pending_orders.csv";
    
    if(!FileIsExist(filename, FILE_COMMON))
        return;
    
    int handle = FileOpen(filename, FILE_READ|FILE_CSV|FILE_COMMON|FILE_ANSI, ';');
    if(handle == INVALID_HANDLE)
    {
        Print("ERROR: Cannot open ", filename, " - Error: ", GetLastError());
        return;
    }
    
    Print("[OrderBridge] Processing pending_orders.csv...");
    
    // Process orders - NO HEADER EXPECTED (Python writes without header)
    int orderCount = 0;
    while(!FileIsEnding(handle))
    {
        string orderId = FileReadString(handle);
        string symbol = FileReadString(handle);
        string action = FileReadString(handle);
        string volumeStr = FileReadString(handle);
        string slStr = FileReadString(handle);
        string tpStr = FileReadString(handle);
        string comment = FileReadString(handle);
        
        if(orderId == "" || symbol == "")
            continue;
        
        Print("[OrderBridge] Order: ", orderId, " | ", symbol, " | ", action, " | Vol:", volumeStr, " | SL:", slStr);
        
        // Find broker symbol
        string brokerSymbol = FindBrokerSymbol(symbol);
        if(brokerSymbol == "")
        {
            WriteOrderResult(orderId, "REJECTED", "Symbol not found: " + symbol);
            continue;
        }
        
        double volume = StringToDouble(volumeStr);
        double sl = StringToDouble(slStr);
        double tp = StringToDouble(tpStr);
        
        // Execute order
        bool success = false;
        string resultMsg = "";
        ulong ticket = 0;
        
        if(action == "BUY")
        {
            success = ExecuteMarketOrder(brokerSymbol, ORDER_TYPE_BUY, volume, sl, tp, comment, ticket, resultMsg);
        }
        else if(action == "SELL")
        {
            success = ExecuteMarketOrder(brokerSymbol, ORDER_TYPE_SELL, volume, sl, tp, comment, ticket, resultMsg);
        }
        else if(action == "CLOSE")
        {
            success = ClosePosition(brokerSymbol, volume, resultMsg);
        }
        else if(action == "MODIFY")
        {
            success = ModifyPosition(brokerSymbol, sl, tp, resultMsg);
        }
        else
        {
            WriteOrderResult(orderId, "REJECTED", "Unknown action: " + action);
            continue;
        }
        
        // Write result
        WriteOrderResult(orderId, success ? "FILLED" : "REJECTED", resultMsg, ticket);
        orderCount++;
    }
    
    FileClose(handle);
    
    // Delete processed file
    if(orderCount > 0)
    {
        Print("[OrderBridge] Processed ", orderCount, " orders, deleting file");
    }
    FileDelete(filename, FILE_COMMON);
}

//+------------------------------------------------------------------+
bool ExecuteMarketOrder(string symbol, ENUM_ORDER_TYPE orderType, double volume, 
                        double sl, double tp, string comment, ulong &ticket, string &resultMsg)
{
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_DEAL;
    request.symbol = symbol;
    request.volume = NormalizeVolume(symbol, volume);
    request.type = orderType;
    request.price = orderType == ORDER_TYPE_BUY ? 
                    SymbolInfoDouble(symbol, SYMBOL_ASK) : 
                    SymbolInfoDouble(symbol, SYMBOL_BID);
    request.deviation = (ulong)(MaxSlippagePips * 10);
    request.magic = 123456;  // Magic number for platform orders
    request.comment = comment != "" ? comment : "AgentPlatform";
    
    // Set SL/TP if provided
    int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
    if(sl > 0) request.sl = NormalizeDouble(sl, digits);
    if(tp > 0) request.tp = NormalizeDouble(tp, digits);
    
    // Send order
    if(!OrderSend(request, result))
    {
        resultMsg = "OrderSend failed: " + IntegerToString(result.retcode) + " - " + result.comment;
        Print("❌ ", resultMsg);
        return false;
    }
    
    if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED)
    {
        ticket = result.deal;
        resultMsg = "Order filled at " + DoubleToString(result.price, digits) + 
                    ", Ticket: " + IntegerToString(result.deal);
        Print("✅ ", symbol, " ", (orderType == ORDER_TYPE_BUY ? "BUY" : "SELL"), 
              " ", volume, " lots - ", resultMsg);
        return true;
    }
    
    resultMsg = "Order rejected: " + IntegerToString(result.retcode) + " - " + result.comment;
    Print("❌ ", resultMsg);
    return false;
}

//+------------------------------------------------------------------+
bool ClosePosition(string symbol, double volume, string &resultMsg)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == symbol)
        {
            MqlTradeRequest request = {};
            MqlTradeResult result = {};
            
            request.action = TRADE_ACTION_DEAL;
            request.symbol = symbol;
            request.volume = volume > 0 ? volume : PositionGetDouble(POSITION_VOLUME);
            request.type = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 
                          ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            request.price = request.type == ORDER_TYPE_BUY ? 
                           SymbolInfoDouble(symbol, SYMBOL_ASK) : 
                           SymbolInfoDouble(symbol, SYMBOL_BID);
            request.position = ticket;
            request.deviation = (ulong)(MaxSlippagePips * 10);
            
            if(OrderSend(request, result))
            {
                if(result.retcode == TRADE_RETCODE_DONE)
                {
                    resultMsg = "Position closed at " + DoubleToString(result.price, 5);
                    Print("✅ Closed ", symbol, " position - ", resultMsg);
                    return true;
                }
            }
            
            resultMsg = "Close failed: " + IntegerToString(result.retcode);
            return false;
        }
    }
    
    resultMsg = "No position found for " + symbol;
    return false;
}

//+------------------------------------------------------------------+
bool ModifyPosition(string symbol, double newSL, double newTP, string &resultMsg)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == symbol)
        {
            MqlTradeRequest request = {};
            MqlTradeResult result = {};
            
            int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
            
            request.action = TRADE_ACTION_SLTP;
            request.symbol = symbol;
            request.position = ticket;
            request.sl = newSL > 0 ? NormalizeDouble(newSL, digits) : PositionGetDouble(POSITION_SL);
            request.tp = newTP > 0 ? NormalizeDouble(newTP, digits) : PositionGetDouble(POSITION_TP);
            
            if(OrderSend(request, result))
            {
                if(result.retcode == TRADE_RETCODE_DONE)
                {
                    resultMsg = "Position modified - SL: " + DoubleToString(request.sl, digits) + 
                               " TP: " + DoubleToString(request.tp, digits);
                    Print("✅ Modified ", symbol, " - ", resultMsg);
                    return true;
                }
            }
            
            resultMsg = "Modify failed: " + IntegerToString(result.retcode);
            return false;
        }
    }
    
    resultMsg = "No position found for " + symbol;
    return false;
}

//+------------------------------------------------------------------+
void WriteOrderResult(string orderId, string status, string message, ulong ticket = 0)
{
    string filename = "order_results.csv";
    // Use semicolon delimiter explicitly to match Python reader
    int handle = FileOpen(filename, FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI, ';');
    
    if(handle == INVALID_HANDLE)
    {
        handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI, ';');
        if(handle == INVALID_HANDLE)
        {
            Print("ERROR: Cannot write order result to ", filename, " - Error: ", GetLastError());
            return;
        }
        // Write header for new file
        FileWrite(handle, "OrderId", "Status", "Message", "Ticket", "Time");
    }
    else
    {
        FileSeek(handle, 0, SEEK_END);
    }
    
    FileWrite(handle, orderId, status, message, IntegerToString(ticket), 
              TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
    FileClose(handle);
    
    Print("[OrderBridge] Result written: ", orderId, " = ", status, " - ", message);
}

//+------------------------------------------------------------------+
string FindBrokerSymbol(string cleanSymbol)
{
    // First try exact match
    for(int i = 0; i < symbolCount; i++)
    {
        if(CleanSymbolName(activeSymbols[i]) == cleanSymbol)
            return activeSymbols[i];
    }
    
    // Try with common suffixes
    string suffixes[] = {".ecn", ".ECN", ".s", ".r", ".pro", ""};
    for(int s = 0; s < ArraySize(suffixes); s++)
    {
        string testSym = cleanSymbol + suffixes[s];
        if(SymbolInfoDouble(testSym, SYMBOL_BID) > 0)
            return testSym;
    }
    
    return "";
}

//+------------------------------------------------------------------+
double NormalizeVolume(string symbol, double volume)
{
    double minVol = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
    double maxVol = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
    double stepVol = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
    
    volume = MathMax(minVol, MathMin(maxVol, volume));
    volume = MathRound(volume / stepVol) * stepVol;
    
    return NormalizeDouble(volume, 2);
}

//+------------------------------------------------------------------+
string CleanSymbolName(string sym)
{
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
    // Check for pending orders on each tick for faster execution
    ProcessPendingOrders();
}
//+------------------------------------------------------------------+
