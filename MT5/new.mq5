#include <Trade\Trade.mqh>
CTrade trade;

//--------------------- INPUTS ---------------------
input double InpLotSize        = 0.1;
input int    InpMagicNumber    = 123456;
input double InpSLAtrMultiplier = 10;   // Stop loss = ATR x this multiplier
input double InpTPAtrMultiplier = 200;   // Take profit = ATR x this multiplier

input double InpUTKeyValue     = 2.0;   // UT Bot sensitivity
input int    InpUTAtrPeriod    = 1;     // UT Bot ATR period

input int    InpHMAPeriod      = 31;    // Hull MA period

input string InpORBStart       = "10:10"; // Opening range start (HH:MM, server time)
input string InpORBEnd         = "10:15"; // Opening range end   (HH:MM, server time)

input int    InpBarsToFetch    = 3000;   // History depth for calculations

input bool     InpUseCustomPeriod = false;                 // Enable custom backtest period
input datetime InpStartDate       = D'2026.01.01 00:00';   // Only trade on/after this date
input datetime InpEndDate         = D'2026.12.31 23:59';   // Only trade on/before this date

//--------------------- GLOBALS ---------------------
int      atrHandle;
datetime lastBarTime = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   atrHandle = iATR(_Symbol, PERIOD_CURRENT, InpUTAtrPeriod);
   if(atrHandle == INVALID_HANDLE)
     {
      Print("Failed to create ATR handle");
      return(INIT_FAILED);
     }

   trade.SetExpertMagicNumber(InpMagicNumber);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   IndicatorRelease(atrHandle);
  }

//+------------------------------------------------------------------+
//| Weighted Moving Average of an array, ending at index 'endIdx'    |
//| (arrays are chronological: index 0 = oldest)                    |
//+------------------------------------------------------------------+
double WMA(const double &arr[], int endIdx, int period)
  {
   if(endIdx - period + 1 < 0)
      return(0.0);

   double sum = 0.0, weightSum = 0.0;
   for(int i = 0; i < period; i++)
     {
      double weight = i + 1;
      sum       += arr[endIdx - period + 1 + i] * weight;
      weightSum += weight;
     }
   return(sum / weightSum);
  }

//+------------------------------------------------------------------+
//| Hull MA value ending at index endIdx                             |
//+------------------------------------------------------------------+
double HullMA(const double &close[], int endIdx, int period)
  {
   int halfPeriod = (int)MathRound(period / 2.0);
   int sqrtPeriod = (int)MathRound(MathSqrt(period));

   // Need a short series of "diff" values (length sqrtPeriod) ending at endIdx
   double diff[];
   ArrayResize(diff, sqrtPeriod);

   for(int k = 0; k < sqrtPeriod; k++)
     {
      int idx = endIdx - sqrtPeriod + 1 + k;
      if(idx - period + 1 < 0)
        {
         diff[k] = 0.0;
         continue;
        }
      double n2ma = 2 * WMA(close, idx, halfPeriod);
      double nma  = WMA(close, idx, period);
      diff[k] = n2ma - nma;
     }

   // WMA of the diff array itself (treat as chronological, endIdx = last element)
   double sum = 0.0, weightSum = 0.0;
   for(int i = 0; i < sqrtPeriod; i++)
     {
      double weight = i + 1;
      sum       += diff[i] * weight;
      weightSum += weight;
     }
   return(sum / weightSum);
  }

//+------------------------------------------------------------------+
//| Parse "HH:MM" into minutes since midnight                        |
//+------------------------------------------------------------------+
int ParseMinutes(string hhmm)
  {
   string parts[];
   StringSplit(hhmm, ':', parts);
   if(ArraySize(parts) < 2)
      return(0);
   return((int)StringToInteger(parts[0]) * 60 + (int)StringToInteger(parts[1]));
  }

//+------------------------------------------------------------------+
//| Returns true if barTime falls inside the user-defined test       |
//| window (or always true if the custom period is disabled).       |
//+------------------------------------------------------------------+
bool InCustomPeriod(datetime barTime)
  {
   if(!InpUseCustomPeriod)
      return(true);

   return(barTime >= InpStartDate && barTime <= InpEndDate);
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   datetime currentBarTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(currentBarTime == lastBarTime)
      return;               // only act once per new bar
   lastBarTime = currentBarTime;

   if(!InCustomPeriod(currentBarTime))
      return;               // outside the custom test window, skip entirely

   int total = InpBarsToFetch;
   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int copied = CopyRates(_Symbol, PERIOD_CURRENT, 1, total, rates); // exclude forming bar
   if(copied < 50)
      return;

   double atrBuf[];
   ArraySetAsSeries(atrBuf, false);
   if(CopyBuffer(atrHandle, 0, 1, copied, atrBuf) <= 0)
      return;

   double close[], high[], low[];
   ArrayResize(close, copied);
   ArrayResize(high, copied);
   ArrayResize(low, copied);
   for(int i = 0; i < copied; i++)
     {
      close[i] = rates[i].close;
      high[i]  = rates[i].high;
      low[i]   = rates[i].low;
     }

   //--------------- UT BOT (recursive trailing stop) ---------------
   double trailingStop[];
   int    pos[];
   ArrayResize(trailingStop, copied);
   ArrayResize(pos, copied);

   trailingStop[0] = 0.0;
   pos[0] = 0;

   for(int i = 1; i < copied; i++)
     {
      double src      = close[i];
      double prevSrc   = close[i - 1];
      double prevStop  = trailingStop[i - 1];
      double nLoss     = InpUTKeyValue * atrBuf[i];

      if(src > prevStop && prevSrc > prevStop)
         trailingStop[i] = MathMax(prevStop, src - nLoss);
      else if(src < prevStop && prevSrc < prevStop)
         trailingStop[i] = MathMin(prevStop, src + nLoss);
      else if(src > prevStop)
         trailingStop[i] = src - nLoss;
      else
         trailingStop[i] = src + nLoss;

      if(prevSrc < prevStop && src > trailingStop[i])
         pos[i] = 1;
      else if(prevSrc > prevStop && src < trailingStop[i])
         pos[i] = -1;
      else
         pos[i] = pos[i - 1];
     }

   int last = copied - 1;
   int prev = copied - 2;

   bool above = (close[last] > trailingStop[last]) && (close[prev] <= trailingStop[prev]);
   bool below = (trailingStop[last] > close[last]) && (trailingStop[prev] <= close[prev]);

   bool utBuy  = (close[last] > trailingStop[last]) && above;
   bool utSell = (close[last] < trailingStop[last]) && below;

   //--------------- HULL MA ---------------
   double hmaNow  = HullMA(close, last, InpHMAPeriod);
   double hmaPrev = HullMA(close, prev, InpHMAPeriod);
   bool   hmaRising = hmaNow > hmaPrev;

   //--------------- ORB (opening range high/low for today) ---------------
   int startMin = ParseMinutes(InpORBStart);
   int endMin   = ParseMinutes(InpORBEnd);

   MqlDateTime tmLast;
   TimeToStruct(rates[last].time, tmLast);
   int todayDate = tmLast.year * 10000 + tmLast.mon * 100 + tmLast.day;

   double orbHigh = -1, orbLow = -1;
   for(int i = 0; i < copied; i++)
     {
      MqlDateTime tm;
      TimeToStruct(rates[i].time, tm);
      int dateKey = tm.year * 10000 + tm.mon * 100 + tm.day;
      if(dateKey != todayDate)
         continue;

      int minutesOfDay = tm.hour * 60 + tm.min;
      if(minutesOfDay >= startMin && minutesOfDay <= endMin)
        {
         if(orbHigh < 0 || high[i] > orbHigh) orbHigh = high[i];
         if(orbLow  < 0 || low[i]  < orbLow)  orbLow  = low[i];
        }
     }

   bool haveORB = (orbHigh > 0 && orbLow > 0);

   //--------------- COMBINED SIGNAL ---------------
   bool longSignal  = utBuy  && hmaRising  && haveORB && (close[last] > orbHigh);
   bool shortSignal = utSell && !hmaRising && haveORB && (close[last] < orbLow);

   Print("Bar=", TimeToString(rates[last].time), " close=", close[last],
         " stop=", trailingStop[last], " hma=", hmaNow,
         " long=", longSignal, " short=", shortSignal);

   //--------------- EXECUTION ---------------
   double currentAtr = atrBuf[last];
   ManageTrade(longSignal, shortSignal, currentAtr);
  }

//+------------------------------------------------------------------+
void ManageTrade(bool longSignal, bool shortSignal, double currentAtr)
  {
   bool hasPosition = PositionSelect(_Symbol);
   long posType = -1;
   if(hasPosition)
      posType = PositionGetInteger(POSITION_TYPE);

   double slDistance = currentAtr * InpSLAtrMultiplier;
   double tpDistance = currentAtr * InpTPAtrMultiplier;

   if(longSignal)
     {
      if(hasPosition && posType == POSITION_TYPE_SELL)
        {
         trade.PositionClose(_Symbol);
         hasPosition = false;
        }
      if(!hasPosition)
        {
         double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double sl  = ask - slDistance;
         double tp  = ask + tpDistance;
         trade.Buy(InpLotSize, _Symbol, ask, sl, tp, "UT_HMA_ORB long");
        }
     }
   else if(shortSignal)
     {
      if(hasPosition && posType == POSITION_TYPE_BUY)
        {
         trade.PositionClose(_Symbol);
         hasPosition = false;
        }
      if(!hasPosition)
        {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         double sl  = bid + slDistance;
         double tp  = bid - tpDistance;
         trade.Sell(InpLotSize, _Symbol, bid, sl, tp, "UT_HMA_ORB short");
        }
     }
  }
//+------------------------------------------------------------------+